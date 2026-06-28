# Database — Schema & การทำงาน

## ภาพรวม

VAS ใช้ **SQLite** เป็น database เก็บข้อมูลทั้งหมดในไฟล์เดียว

| ค่า | รายละเอียด |
|---|---|
| Engine | SQLite 3 |
| ที่เก็บไฟล์ | `~/.config/vas/vas.db` |
| WAL mode | เปิดอยู่ (`PRAGMA journal_mode=WAL`) |
| Foreign keys | เปิดอยู่ (`PRAGMA foreign_keys=ON`) |
| Source | `src/core/database.py` |

> เมื่อรัน `vas server` ครั้งแรก — `init_db()` จะสร้างทุก table อัตโนมัติถ้ายังไม่มี

---

## Tables

### `users`
จัดการ authentication และ role-based access

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    display_name  TEXT    NOT NULL DEFAULT '',
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'user'
                  CHECK(role IN ('root','admin','user')),
    created_at    TEXT    NOT NULL,
    last_login    TEXT    DEFAULT NULL
);
```

**Role hierarchy:**

| Role | Weight | สิทธิ์ |
|---|---|---|
| `root` | 100 | สร้างอัตโนมัติครั้งแรก, ลบไม่ได้, สิทธิ์สูงสุด |
| `admin` | 50 | จัดการ user ได้ แต่ไม่สามารถแตะ root |
| `user` | 10 | ผู้ใช้งานทั่วไป |

---

### `qr_scans`
ประวัติ QR scan ทุกครั้งที่อ่านค่าได้

```sql
CREATE TABLE qr_scans (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,    -- ISO 8601 UTC
    value   TEXT    NOT NULL,    -- ค่าที่ scan ได้
    device  TEXT    DEFAULT NULL -- path ของ device เช่น /dev/hidraw0
);
CREATE INDEX idx_qr_scans_ts ON qr_scans(ts DESC);
```

**เขียนโดย:** `log_qr_scan()` — เรียกอัตโนมัติจาก SSE stream `/api/qr/stream`

---

### `mqtt_events`
ประวัติ MQTT publish ทุกครั้ง (ทั้งสำเร็จและล้มเหลว)

```sql
CREATE TABLE mqtt_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,
    scan    TEXT    NOT NULL,    -- ค่า QR ที่ publish
    topic   TEXT    NOT NULL,    -- MQTT topic
    payload TEXT    NOT NULL,    -- JSON payload ที่ส่งไป
    ok      INTEGER NOT NULL DEFAULT 0  -- 1=สำเร็จ, 0=ล้มเหลว
);
CREATE INDEX idx_mqtt_events_ts ON mqtt_events(ts DESC);
```

**เขียนโดย:** `log_mqtt_event()` — เรียกจาก MQTT client หลัง publish

---

### `audit_log`
System log ทุก event สำคัญ (snapshot, table clear ฯลฯ)

```sql
CREATE TABLE audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,
    action  TEXT    NOT NULL,   -- เช่น "snapshot_created", "table_cleared"
    details TEXT    DEFAULT NULL -- JSON payload เพิ่มเติม
);
CREATE INDEX idx_audit_log_ts ON audit_log(ts DESC);
```

**เขียนโดย:** `log_audit()` — เรียกจาก snapshot API, clear table API

---

### `config_history`
ประวัติการเปลี่ยน config ทุกครั้ง

```sql
CREATE TABLE config_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT    NOT NULL,
    module    TEXT    NOT NULL,     -- เช่น "mqtt", "qr"
    key       TEXT    NOT NULL,     -- เช่น "*" (ทั้ง config)
    old_value TEXT    DEFAULT NULL, -- JSON ค่าเดิม
    new_value TEXT    DEFAULT NULL  -- JSON ค่าใหม่
);
CREATE INDEX idx_config_history_ts ON config_history(ts DESC);
```

**เขียนโดย:** `log_config_change()` — เรียกจาก `/api/qr/config`, `/api/mqtt/config`

---

### `mqtt_brokers`
ข้อมูล MQTT broker ที่ configure ไว้

```sql
CREATE TABLE mqtt_brokers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL DEFAULT 'Broker',
    broker_url    TEXT    NOT NULL DEFAULT 'mqtts://localhost:8883',
    username      TEXT    NOT NULL DEFAULT '',
    password      TEXT    NOT NULL DEFAULT '',
    client_id     TEXT    NOT NULL DEFAULT '',
    tls_insecure  INTEGER NOT NULL DEFAULT 0,   -- 1=ข้าม TLS verify
    qos           INTEGER NOT NULL DEFAULT 1,   -- 0/1/2
    retain        INTEGER NOT NULL DEFAULT 0,
    payload_mode  TEXT    NOT NULL DEFAULT 'decoded', -- "decoded" | "raw"
    enabled       INTEGER NOT NULL DEFAULT 1,
    is_primary    INTEGER NOT NULL DEFAULT 0,   -- 1 broker เท่านั้น
    keep_alive    INTEGER NOT NULL DEFAULT 60,  -- วินาที
    reconnect_min INTEGER NOT NULL DEFAULT 3,   -- วินาที
    reconnect_max INTEGER NOT NULL DEFAULT 30,  -- วินาที
    notes         TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);
```

> **is_primary:** ระบบรองรับ broker หลายตัว แต่ active ได้แค่ตัวเดียว (`is_primary=1`) เมื่อ set broker ใหม่เป็น primary จะ reset broker เดิมเป็น 0 อัตโนมัติ

---

### `mqtt_broker_topics`
Topics ของแต่ละ broker (many-to-one)

```sql
CREATE TABLE mqtt_broker_topics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_id  INTEGER NOT NULL REFERENCES mqtt_brokers(id) ON DELETE CASCADE,
    topic      TEXT    NOT NULL,
    label      TEXT    NOT NULL DEFAULT '',
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT    NOT NULL
);
CREATE INDEX idx_mqtt_broker_topics_bid ON mqtt_broker_topics(broker_id);
```

---

## Connection Pool

ใช้ **thread-local connection** — แต่ละ thread ได้ connection ของตัวเอง:

```python
_local = threading.local()

def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(str(db_path()), check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return _local.conn
```

---

## API Endpoints

| Method | Path | คำอธิบาย |
|---|---|---|
| `GET` | `/api/database/<table>` | ดึง rows + pagination + search |
| `POST` | `/api/database/<table>/clear` | ลบข้อมูลทั้งหมดใน table |
| `GET` | `/api/database/stats` | จำนวน rows แต่ละ table |

**Tables ที่เข้าถึงได้ผ่าน API:**
```
qr_scans, mqtt_events, audit_log, config_history
```

> `mqtt_brokers` และ `mqtt_broker_topics` เข้าถึงผ่าน `/api/mqtt/brokers/...` แทน

**Query parameters สำหรับ GET:**
```
?limit=50    (max 200)
?offset=0
?search=keyword
```
