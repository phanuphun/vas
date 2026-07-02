# Database — Schema & การทำงาน

## ภาพรวม

VAS ใช้ **SQLite** เป็น database เก็บข้อมูลทั้งหมดในไฟล์เดียว — แยกฐานข้อมูลต่อเครื่อง (per-machine) แต่ละเครื่องที่ลง VAS จะมี `vas.db` ของตัวเอง ไม่ share กัน

| ค่า | รายละเอียด |
|---|---|
| Engine | SQLite 3 |
| ที่เก็บไฟล์ | `~/.config/vas/vas.db` (นอกโฟลเดอร์ install `/opt/vending-auto-setup` โดยตั้งใจ — ดู "Migration System" ด้านล่าง) |
| WAL mode | เปิดอยู่ (`PRAGMA journal_mode=WAL`) |
| Foreign keys | เปิดอยู่ (`PRAGMA foreign_keys=ON`) |
| Source | `src/core/database.py` |

> **`init_db()` ไม่ได้สร้าง schema แล้ว** — เป็นแค่ read-only version check ตอน server boot: เทียบ `current_schema_version()` (จาก `PRAGMA user_version`) กับ `latest_schema_version()` (จาก `_MIGRATIONS` ล่าสุด) ถ้าต่ำกว่า จะ raise `SchemaOutOfDateError` และ **server ปฏิเสธที่จะ start** (fail loud ตามที่ตั้งใจ — ป้องกันการรันด้วย schema เก่าแบบไม่รู้ตัว) การสร้าง/อัปเดต schema จริงทำโดย `run_migrations()` เท่านั้น เรียกผ่าน `vas db migrate`, ตอน `vas install` (ครั้งแรก), และตอน `vas update` (ทุกครั้งที่อัปเดต)

---

## Migration System

แทนที่การใช้ `CREATE TABLE IF NOT EXISTS` แบบเดิม (เขียน schema ทุกครั้งที่ boot) ด้วยระบบ versioned migration บน `PRAGMA user_version`:

```python
_MIGRATIONS: list[tuple[int, str]] = [
    (1, _MIGRATION_1),  # baseline: qr_scans, mqtt_events, audit_log, config_history,
                         #           mqtt_brokers, mqtt_broker_topics, users
    (2, _MIGRATION_2),  # device_integrations table + data migration จาก config.json/qr_integrations.json
    (3, _MIGRATION_3),  # qr_scans: เพิ่ม raw_keycode, raw_report, read_mode
]
```

- **Additive-only เสมอ** — ห้าม `DROP`/`DELETE` ข้อมูลเดิมในทุก migration (กติกาตายตัว เพื่อให้ `vas update` ไม่มีทางลบข้อมูลเก่า)
- `run_migrations()` ใช้ `current_schema_version()` เทียบกับแต่ละ version ใน `_MIGRATIONS` ที่ยังไม่ apply แล้วรันทีละตัวตามลำดับ ใน transaction, อัปเดต `PRAGMA user_version` ทุกครั้งที่ migration หนึ่งสำเร็จ
- **Data migration** ที่ version 2 ย้ายข้อมูลจากไฟล์เดิม (`config.json`'s `"mqtt"` section → `mqtt_brokers`, `~/.config/vas/qr_integrations.json` → `device_integrations`) ด้วย pattern insert → read-back verify → ลบไฟล์เดิม (ลบก็ต่อเมื่อ verify สำเร็จเท่านั้น กันข้อมูลหายถ้า migration ล้มเหลวกลางทาง)

**ทำไม `vas.db` อยู่นอก `/opt/vending-auto-setup`:** `vas update` ทำ `shutil.rmtree` ทับโฟลเดอร์ install ทั้งหมดก่อน copy โค้ดใหม่ลงไป — ถ้า `vas.db` อยู่ในนั้นข้อมูลทั้งหมดจะหายทุกครั้งที่อัปเดต การเก็บที่ `~/.config/vas/` (นอกโฟลเดอร์ที่ถูกลบ) ทำให้ข้อมูลปลอดภัยโดยธรรมชาติ — สิ่งที่เหลือคือต้องรัน `run_migrations()` หลัง copy โค้ดใหม่เสร็จ (ทั้ง CLI path `SelfUpdater.update()` และ web UI path `start_web_update()` เรียกจุดนี้เหมือนกัน) เพื่ออัปเดต schema ให้ตรงกับโค้ดเวอร์ชันใหม่โดยไม่แตะข้อมูลเดิม

**CLI:**
```
vas db migrate    # รัน migration ที่ค้างทั้งหมด, แสดง schema version ก่อน/หลัง
```

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
ประวัติ QR scan ทุกครั้งที่อ่านค่าได้ — รองรับ 3 ระดับความดิบของข้อมูล (ดู `docs/qr/qr-reader.md`)

```sql
CREATE TABLE qr_scans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,    -- ISO 8601 UTC
    value       TEXT    NOT NULL,    -- ค่าที่ decode แล้ว
    device      TEXT    DEFAULT NULL,-- path ของ device เช่น /dev/hidraw0
    raw_keycode TEXT    DEFAULT NULL,-- JSON-encoded list[int], เพิ่มใน migration v3
    raw_report  TEXT    DEFAULT NULL,-- JSON-encoded list[str] (hex ต่อ report frame), NULL เสมอถ้า read_mode='evdev'
    read_mode   TEXT    DEFAULT NULL -- 'hidraw' | 'evdev' | NULL (row เก่าก่อน migration v3)
);
CREATE INDEX idx_qr_scans_ts ON qr_scans(ts DESC);
```

**เขียนโดย:** `log_qr_scan(value, device=None, ts=None, raw_keycode=None, raw_report=None, read_mode=None)` — เรียกอัตโนมัติจาก SSE stream `/api/qr/stream`, JSON-encode `raw_keycode`/`raw_report` เมื่อไม่ใช่ `None`

---

### `mqtt_events`
ประวัติ MQTT publish ทุกครั้ง (ทั้งสำเร็จและล้มเหลว รวมถึงกรณี publish ถูก reject เพราะ payload mode ที่เลือกไม่มีข้อมูล เช่น ขอ `raw_report` จาก evdev)

```sql
CREATE TABLE mqtt_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,
    scan    TEXT    NOT NULL,    -- ค่า QR ที่ publish
    topic   TEXT    NOT NULL,    -- MQTT topic
    payload TEXT    NOT NULL,    -- JSON payload ที่ส่งไป (หรือ error payload ถ้า ok=0)
    ok      INTEGER NOT NULL DEFAULT 0  -- 1=สำเร็จ, 0=ล้มเหลว
);
CREATE INDEX idx_mqtt_events_ts ON mqtt_events(ts DESC);
```

**เขียนโดย:** `log_mqtt_event()` — เรียกจาก MQTT client หลัง publish (หรือหลัง reject เพราะ no-silent-fallback)

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
ข้อมูล MQTT broker ที่ configure ไว้ — เดิมบางส่วนเก็บใน `config.json` ตอนนี้ย้ายมาเก็บที่นี่ทั้งหมดแล้ว (ดู `docs/networking/mqtt.md`)

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
    payload_mode  TEXT    NOT NULL DEFAULT 'decoded', -- "decoded" | "raw_keycode" | "raw_report"
    enabled       INTEGER NOT NULL DEFAULT 1,
    is_primary    INTEGER NOT NULL DEFAULT 0,
    keep_alive    INTEGER NOT NULL DEFAULT 60,  -- วินาที
    reconnect_min INTEGER NOT NULL DEFAULT 3,   -- วินาที
    reconnect_max INTEGER NOT NULL DEFAULT 30,  -- วินาที
    notes         TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);
```

> **is_primary:** ระบบรองรับ broker หลายตัว **connect พร้อมกันได้จริง** (ไม่ได้ active ได้แค่ตัวเดียวอีกต่อไป) — `is_primary=1` มีความหมายแค่ว่าเป็น broker ที่ใช้กับ path แบบ legacy/primary-only เท่านั้น (`vas mqtt test`, `/api/mqtt/test`, `/api/mqtt/config`) เมื่อ set broker ใหม่เป็น primary จะ reset broker เดิมเป็น 0 อัตโนมัติ (ยังเหลือ constraint นี้ไว้) ส่วนการ publish จริงจาก QR scan ใช้ `device_integrations` เลือก broker ต่อ device แยกจาก `is_primary` โดยสิ้นเชิง — broker ที่ไม่ใช่ primary ก็ connect และรับ publish ได้ปกติถ้าถูกผูกไว้กับ device

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

### `device_integrations`
เพิ่มใน migration v2 — เก็บการตั้งค่า integration ต่อ device (webhook / mqtt / pipe) แทน `~/.config/vas/qr_integrations.json` เดิม (ย้ายข้อมูลอัตโนมัติแล้วลบไฟล์ทิ้งตอน migrate)

```sql
CREATE TABLE device_integrations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id        TEXT    NOT NULL,   -- เช่น "zkteco-qr500"
    integration_type TEXT    NOT NULL CHECK(integration_type IN ('webhook','mqtt','pipe')),
    enabled          INTEGER NOT NULL DEFAULT 0,
    data             TEXT    NOT NULL DEFAULT '{}', -- JSON: broker_id, topic, qos ฯลฯ ตาม integration_type
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    UNIQUE(device_id, integration_type)
);
```

**อ่าน/เขียนโดย:** `list_device_integrations(device_id)`, `upsert_device_integration(device_id, integration_type, data)` ใน `core/database.py` — ห่อโดย `src/features/qr/registry.py` (`load_integrations()`/`save_integrations()`) เพื่อคง interface เดิม (dict-of-dicts) ให้ `server.py` ไม่ต้องแก้เยอะ

**ใช้งานจริงเฉพาะ `mqtt`:** `data` เก็บ `{"broker_id": int, "topic": str|None, "qos": int|None, "payload_mode": str|None}` — `broker_id`/`topic`/`qos` เป็น column จริงในตาราง (`upsert_device_integration()` เขียนตรงๆ), ส่วน `payload_mode` (และ field เสริมอื่นๆ ที่ไม่ตรงกับ column จริง) ถูกเก็บลงใน `settings_json` (JSON column) แล้ว flatten กลับเป็น top-level key ตอนอ่านผ่าน `list_device_integrations()` — ไม่ต้อง `ALTER TABLE` เพิ่มเมื่อมี field ใหม่แบบนี้ ดึงมาใช้ใน `publish_qr_scan_for_device()` (`features/mqtt/client.py`) เป็น payload_mode override ต่อ device เหนือค่า default ของ broker (ดู `docs/networking/mqtt.md`) ส่วน `webhook`/`pipe` เก็บ config ได้แต่ยังไม่มี publish logic จริง (schema เตรียมไว้ล่วงหน้า)

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
> `device_integrations` เข้าถึงผ่าน `/api/qr/integrations` แทน

**Query parameters สำหรับ GET:**
```
?limit=50    (max 200)
?offset=0
?search=keyword
```
