"""
VAS — SQLite database layer

ไฟล์ DB: ~/.config/vas/vas.db  (สร้างอัตโนมัติถ้าไม่มี)

Tables:
    qr_scans           — ประวัติ QR scan ทุกครั้ง
    mqtt_events        — ทุก MQTT publish attempt
    audit_log          — system log snapshot events
    config_history     — ทุกครั้งที่มีการบันทึก config เปลี่ยนแปลง
    mqtt_brokers        — MQTT broker ที่ configure ไว้ (รองรับหลายตัว)
    mqtt_broker_topics  — topics ของแต่ละ broker
    device_integrations — integration config ต่อ device (webhook/mqtt/pipe)

Schema migration:
    ใช้ PRAGMA user_version เก็บเลขเวอร์ชัน schema ปัจจุบัน
    ดู _MIGRATIONS ด้านล่าง — ห้าม DROP TABLE/DELETE ข้อมูลเดิมใน migration ใดๆ
    เรียก run_migrations() เพื่ออัปเดต schema จริง (จาก `vas db migrate` หรือตอน install/update)
    init_db() ที่ใช้ตอน server boot เป็นแค่ read-only version check เท่านั้น — ดู current_schema_version()
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

# ---------------------------------------------------------------------------
# DB path
# ---------------------------------------------------------------------------

def db_path() -> Path:
    """~/.config/vas/vas.db (ใช้ effective home เพื่อรองรับ sudo)"""
    try:
        from system.status import _effective_home  # type: ignore[import]
        base = _effective_home() / ".config" / "vas"
    except Exception:
        base = Path.home() / ".config" / "vas"
    base.mkdir(parents=True, exist_ok=True)
    return base / "vas.db"


# ---------------------------------------------------------------------------
# Schema migrations
# ---------------------------------------------------------------------------
#
# _MIGRATIONS: list[tuple[int, str]] เรียงตาม version (1, 2, 3, ...)
#   - ห้ามมี DROP TABLE / DELETE ข้อมูลเดิมใน statement ใดๆ
#   - ใช้ CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS เสมอ เพื่อให้ apply ซ้ำได้อย่างปลอดภัย
#   - แต่ละ migration ต้อง apply ได้ทั้งกับ DB ว่าง และ DB ที่มีข้อมูลอยู่แล้ว

_MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS qr_scans (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT    NOT NULL,
    value     TEXT    NOT NULL,
    device    TEXT    DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS mqtt_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT    NOT NULL,
    scan      TEXT    NOT NULL,
    topic     TEXT    NOT NULL,
    payload   TEXT    NOT NULL,
    ok        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT    NOT NULL,
    action    TEXT    NOT NULL,
    details   TEXT    DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS config_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT    NOT NULL,
    module    TEXT    NOT NULL,
    key       TEXT    NOT NULL,
    old_value TEXT    DEFAULT NULL,
    new_value TEXT    DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_qr_scans_ts        ON qr_scans(ts DESC);
CREATE INDEX IF NOT EXISTS idx_mqtt_events_ts     ON mqtt_events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_ts       ON audit_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_config_history_ts  ON config_history(ts DESC);

CREATE TABLE IF NOT EXISTS mqtt_brokers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL DEFAULT 'Broker',
    broker_url    TEXT    NOT NULL DEFAULT 'mqtts://localhost:8883',
    username      TEXT    NOT NULL DEFAULT '',
    password      TEXT    NOT NULL DEFAULT '',
    client_id     TEXT    NOT NULL DEFAULT '',
    tls_insecure  INTEGER NOT NULL DEFAULT 0,
    qos           INTEGER NOT NULL DEFAULT 1,
    retain        INTEGER NOT NULL DEFAULT 0,
    payload_mode  TEXT    NOT NULL DEFAULT 'decoded',
    enabled       INTEGER NOT NULL DEFAULT 1,
    is_primary    INTEGER NOT NULL DEFAULT 0,
    keep_alive    INTEGER NOT NULL DEFAULT 60,
    reconnect_min INTEGER NOT NULL DEFAULT 3,
    reconnect_max INTEGER NOT NULL DEFAULT 30,
    notes         TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS mqtt_broker_topics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_id  INTEGER NOT NULL REFERENCES mqtt_brokers(id) ON DELETE CASCADE,
    topic      TEXT    NOT NULL,
    label      TEXT    NOT NULL DEFAULT '',
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mqtt_brokers_primary   ON mqtt_brokers(is_primary DESC);
CREATE INDEX IF NOT EXISTS idx_mqtt_broker_topics_bid ON mqtt_broker_topics(broker_id);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    display_name  TEXT    NOT NULL DEFAULT '',
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'user' CHECK(role IN ('root','admin','user')),
    created_at    TEXT    NOT NULL,
    last_login    TEXT    DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username COLLATE NOCASE);
"""

_MIGRATION_2 = """
CREATE TABLE IF NOT EXISTS device_integrations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT    NOT NULL,
    integration_type TEXT   NOT NULL CHECK(integration_type IN ('webhook','mqtt','pipe')),
    enabled         INTEGER NOT NULL DEFAULT 0,
    broker_id       INTEGER REFERENCES mqtt_brokers(id) ON DELETE SET NULL,
    topic           TEXT    NOT NULL DEFAULT '',
    qos             INTEGER NOT NULL DEFAULT 1,
    settings_json   TEXT    NOT NULL DEFAULT '{}',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    UNIQUE(device_id, integration_type)
);
CREATE INDEX IF NOT EXISTS idx_device_integrations_device ON device_integrations(device_id);
"""

_MIGRATION_3 = """
ALTER TABLE qr_scans ADD COLUMN raw_keycode TEXT;
ALTER TABLE qr_scans ADD COLUMN raw_report  TEXT;
ALTER TABLE qr_scans ADD COLUMN read_mode   TEXT;
"""

_MIGRATIONS: list[tuple[int, str]] = [
    (1, _MIGRATION_1),
    (2, _MIGRATION_2),
    (3, _MIGRATION_3),
]

# ---------------------------------------------------------------------------
# Thread-local connection pool
# ---------------------------------------------------------------------------

_local = threading.local()
_init_lock = threading.Lock()
_initialized = False


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(
            str(db_path()),
            check_same_thread=False,
            timeout=10,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return _local.conn  # type: ignore[return-value]


@contextmanager
def _cursor() -> Generator[sqlite3.Cursor, None, None]:
    conn = _get_conn()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Schema version / migrations
# ---------------------------------------------------------------------------

def current_schema_version() -> int:
    """อ่าน PRAGMA user_version ปัจจุบันของ vas.db"""
    conn = _get_conn()
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def latest_schema_version() -> int:
    """เวอร์ชัน schema ล่าสุดที่โค้ดนี้รู้จัก (เลขสูงสุดใน _MIGRATIONS)"""
    return max(v for v, _ in _MIGRATIONS)


def run_migrations() -> None:
    """
    รัน migration ทุกตัวที่ยังไม่ถึง version ปัจจุบัน เรียงจากน้อยไปมาก (1 → 2 → ...)
    แต่ละ migration wrap ใน transaction เดียว — commit ต่อเมื่อสำเร็จทั้ง schema statement
    และ bump PRAGMA user_version แล้วเท่านั้น (ไม่ jump ข้าม version)

    ปลอดภัยเรียกซ้ำได้ — migration ที่ apply ไปแล้วจะถูกข้าม
    """
    with _init_lock:
        conn = _get_conn()
        current = current_schema_version()
        for version, script in sorted(_MIGRATIONS, key=lambda m: m[0]):
            if version <= current:
                continue
            try:
                conn.executescript(script)
                # data migration ผูกกับ version 2
                if version == 2:
                    _migrate_config_json_to_mqtt_brokers(conn)
                    _migrate_qr_integrations_json_to_device_integrations(conn)
                conn.execute(f"PRAGMA user_version = {int(version)}")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            current = version
        _initialized_flag[0] = True


# เก็บ flag แยกจาก _initialized เดิม (ใช้ภายใน run_migrations เท่านั้น ไม่ผูกกับ init_db)
_initialized_flag = [False]


# ---------------------------------------------------------------------------
# Init (read-only version check — ไม่เขียน schema อีกต่อไป)
# ---------------------------------------------------------------------------

class SchemaOutOfDateError(RuntimeError):
    """Raise เมื่อ DB schema เก่ากว่าที่โค้ดต้องการ — ต้องรัน `vas db migrate` ก่อน"""


def init_db() -> None:
    """
    ตรวจสอบ schema version ของ vas.db (read-only) — เรียก 1 ครั้งตอน server start

    ไม่เขียน schema ใดๆ อีกต่อไป (ย้ายไปที่ run_migrations() ซึ่งเรียกจาก
    `vas db migrate`, `vas install`, และ `vas update` แทน)

    Raises:
        SchemaOutOfDateError: ถ้า current_schema_version() < latest_schema_version()
    """
    global _initialized
    with _init_lock:
        if _initialized:
            return
        current = current_schema_version()
        latest = latest_schema_version()
        if current < latest:
            raise SchemaOutOfDateError(
                f"Database schema out of date (current={current}, latest={latest}) — "
                f"run: vas db migrate"
            )
        _initialized = True


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Data migrations (ผูกกับ migration version 2) — config.json / qr_integrations.json → SQLite
# ---------------------------------------------------------------------------

def _install_dir() -> Path:
    """Resolve install_dir แบบเดียวกับที่ core/config.py:44 เคยทำ (ก่อนลบ main_config_path)"""
    return Path(__file__).parent.parent


def _migrate_config_json_to_mqtt_brokers(conn: sqlite3.Connection) -> None:
    """
    ย้าย {install_dir}/config.json ส่วน "mqtt" → แถวใหม่ใน mqtt_brokers (is_primary=1)

    Insert แล้ว read-back ยืนยันก่อนเสมอ — ลบไฟล์ config.json จริงเฉพาะเมื่อยืนยันสำเร็จเท่านั้น
    ถ้าไม่มีไฟล์ → ข้าม ไม่ error
    """
    config_path = _install_dir() / "config.json"
    if not config_path.exists():
        return
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(raw, dict):
        return
    mqtt_section = raw.get("mqtt")
    if not isinstance(mqtt_section, dict):
        return

    now = _now_utc()

    def _str(key: str, default: str = "") -> str:
        return str(mqtt_section.get(key) or default)

    def _bool(key: str, default: bool = False) -> int:
        v = mqtt_section.get(key)
        return 1 if (v if isinstance(v, bool) else default) else 0

    def _int(key: str, default: int) -> int:
        try:
            return int(mqtt_section.get(key, default))
        except (TypeError, ValueError):
            return default

    payload_mode = _str("payload_mode", "decoded")
    if payload_mode not in ("decoded", "raw_keycode", "raw_report"):
        payload_mode = "decoded"

    cur = conn.cursor()
    cur.execute(
        """INSERT INTO mqtt_brokers
           (name, broker_url, username, password, client_id,
            tls_insecure, qos, retain, payload_mode, enabled, is_primary,
            keep_alive, reconnect_min, reconnect_max, notes, created_at, updated_at)
           VALUES (?,?,?,?,?, ?,?,?,?,?,1, ?,?,?,?, ?,?)""",
        (
            "Migrated from config.json",
            _str("broker_url", "mqtts://localhost:8883"),
            _str("username"),
            _str("password"),
            _str("client_id"),
            _bool("tls_insecure"),
            _int("qos", 1),
            _bool("retain"),
            payload_mode,
            _bool("enabled", False),
            60, 3, 30, "",
            now, now,
        ),
    )
    new_id = cur.lastrowid

    # Read-back เพื่อยืนยัน insert สำเร็จก่อนลบไฟล์
    verify_row = conn.execute(
        "SELECT id, broker_url FROM mqtt_brokers WHERE id = ?", (new_id,)
    ).fetchone()
    if verify_row is None or verify_row["broker_url"] != _str("broker_url", "mqtts://localhost:8883"):
        # ยืนยันไม่สำเร็จ — ไม่ลบไฟล์ ปล่อยให้ transaction rollback ทีหลังถ้ามี error อื่น
        return

    try:
        cur.execute(
            "INSERT INTO config_history (ts, module, key, old_value, new_value) VALUES (?, ?, ?, ?, ?)",
            (
                now, "mqtt", "*",
                None,
                json.dumps({k: v for k, v in mqtt_section.items() if k != "password"}, ensure_ascii=False),
            ),
        )
    except Exception:
        pass

    # ลบไฟล์จริงเฉพาะเมื่อ read-back ยืนยันสำเร็จเท่านั้น
    try:
        config_path.unlink()
    except OSError:
        pass


def _qr_integrations_json_path() -> Path:
    """~/.config/vas/qr_integrations.json (path เดิมจาก features/qr/registry.py)"""
    try:
        from system.status import _effective_home  # type: ignore[import]
        base = _effective_home() / ".config" / "vas"
    except Exception:
        base = Path.home() / ".config" / "vas"
    return base / "qr_integrations.json"


def _migrate_qr_integrations_json_to_device_integrations(conn: sqlite3.Connection) -> None:
    """
    ย้าย ~/.config/vas/qr_integrations.json → แถวใหม่ใน device_integrations
    ต่อ device_id="zkteco-qr500" (device เดียวใน DEVICE_CATALOG ตอนนี้)

    Insert แล้ว read-back ยืนยันก่อนเสมอ — ลบไฟล์จริงเฉพาะเมื่อยืนยันสำเร็จเท่านั้น
    ถ้าไม่มีไฟล์ → ข้าม ไม่ error
    """
    path = _qr_integrations_json_path()
    if not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(raw, dict):
        return

    device_id = "zkteco-qr500"
    device_section = raw.get(device_id)
    if not isinstance(device_section, dict):
        return

    now = _now_utc()
    cur = conn.cursor()
    inserted_ids: list[int] = []

    for integ_type, integ_data in device_section.items():
        if integ_type not in ("webhook", "mqtt", "pipe"):
            continue
        if not isinstance(integ_data, dict):
            continue

        enabled = 1 if integ_data.get("enabled") else 0

        if integ_type == "mqtt":
            broker_id = integ_data.get("broker_id")
            try:
                broker_id_val: int | None = int(broker_id) if broker_id is not None else None
            except (TypeError, ValueError):
                broker_id_val = None
            topic = str(integ_data.get("topic") or "")
            try:
                qos = int(integ_data.get("qos", 1))
            except (TypeError, ValueError):
                qos = 1
            extra = {k: v for k, v in integ_data.items() if k not in ("enabled", "broker_id", "topic", "qos")}
        else:
            broker_id_val = None
            topic = ""
            qos = 1
            extra = {k: v for k, v in integ_data.items() if k != "enabled"}

        settings_json = json.dumps(extra, ensure_ascii=False)

        cur.execute(
            """INSERT INTO device_integrations
               (device_id, integration_type, enabled, broker_id, topic, qos, settings_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(device_id, integration_type) DO NOTHING""",
            (device_id, integ_type, enabled, broker_id_val, topic, qos, settings_json, now, now),
        )
        if cur.lastrowid:
            inserted_ids.append(cur.lastrowid)

    if not inserted_ids:
        # ไม่มี key ที่รู้จักในไฟล์ (หรือ device section ว่าง) — ไม่ลบไฟล์เพื่อความปลอดภัย
        return

    # Read-back เพื่อยืนยัน insert สำเร็จก่อนลบไฟล์
    verify_rows = conn.execute(
        "SELECT id FROM device_integrations WHERE device_id = ?", (device_id,)
    ).fetchall()
    verify_ids = {r["id"] for r in verify_rows}
    if not set(inserted_ids).issubset(verify_ids):
        return

    try:
        path.unlink()
    except OSError:
        pass


def log_qr_scan(
    value: str,
    device: str | None = None,
    ts: str | None = None,
    raw_keycode: list[int] | None = None,
    raw_report: list[str] | None = None,
    read_mode: str | None = None,
) -> None:
    """
    บันทึก QR scan ลง qr_scans
    raw_keycode/raw_report เก็บเป็น JSON-encoded string ถ้าไม่ None (column เพิ่มจาก migration v3)
    read_mode: 'hidraw' | 'evdev' | None (เก็บตรงๆ ไม่ encode)
    """
    try:
        raw_keycode_json = json.dumps(raw_keycode, ensure_ascii=False) if raw_keycode is not None else None
        raw_report_json = json.dumps(raw_report, ensure_ascii=False) if raw_report is not None else None
        with _cursor() as cur:
            cur.execute(
                "INSERT INTO qr_scans (ts, value, device, raw_keycode, raw_report, read_mode) VALUES (?, ?, ?, ?, ?, ?)",
                (ts or _now_utc(), value, device, raw_keycode_json, raw_report_json, read_mode),
            )
    except Exception:
        pass


def log_mqtt_event(
    scan: str,
    topic: str,
    payload: str,
    ok: bool,
    ts: str | None = None,
) -> None:
    try:
        with _cursor() as cur:
            cur.execute(
                "INSERT INTO mqtt_events (ts, scan, topic, payload, ok) VALUES (?, ?, ?, ?, ?)",
                (ts or _now_utc(), scan, topic, payload, 1 if ok else 0),
            )
    except Exception:
        pass


def log_audit(action: str, details: object = None, ts: str | None = None) -> None:
    try:
        detail_str = json.dumps(details, ensure_ascii=False) if details is not None else None
        with _cursor() as cur:
            cur.execute(
                "INSERT INTO audit_log (ts, action, details) VALUES (?, ?, ?)",
                (ts or _now_utc(), action, detail_str),
            )
    except Exception:
        pass


def log_config_change(
    module: str,
    key: str,
    old_value: object = None,
    new_value: object = None,
    ts: str | None = None,
) -> None:
    try:
        old_str = json.dumps(old_value, ensure_ascii=False) if old_value is not None else None
        new_str = json.dumps(new_value, ensure_ascii=False) if new_value is not None else None
        with _cursor() as cur:
            cur.execute(
                "INSERT INTO config_history (ts, module, key, old_value, new_value) VALUES (?, ?, ?, ?, ?)",
                (ts or _now_utc(), module, key, old_str, new_str),
            )
    except Exception:
        pass


def list_kiosk_audit_log(limit: int = 50, offset: int = 0) -> dict[str, object]:
    """
    ประวัติ audit log เฉพาะ action ที่ขึ้นต้นด้วย 'kiosk_' — ใช้กับแท็บ "ประวัติ" ของหน้า
    Kiosk รองรับ pagination แบบเดียวกับ list_qr_scans() (offset paging ไม่ใช่ infinite scroll)
    """
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    conn = _get_conn()
    try:
        total_row = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action LIKE 'kiosk_%'"
        ).fetchone()
        total = total_row[0] if total_row else 0
        rows = conn.execute(
            """SELECT id, ts, action, details FROM audit_log
               WHERE action LIKE 'kiosk_%' ORDER BY id DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"rows": [], "total": 0, "limit": limit, "offset": offset}

    result_rows = []
    for r in rows:
        try:
            details = json.loads(r["details"]) if r["details"] else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            details = {}
        result_rows.append({"id": r["id"], "ts": r["ts"], "action": r["action"], "details": details})
    return {"rows": result_rows, "total": total, "limit": limit, "offset": offset}


def count_qr_scans_today(tz: str = "Asia/Bangkok") -> int:
    """
    นับจำนวน qr_scans ของ "วันนี้" ตาม timezone ที่กำหนด (default Asia/Bangkok)
    ใช้แทน session counter ฝั่ง browser ที่หายเมื่อ reload — ค่านี้มาจาก DB ตรงๆ
    """
    try:
        from zoneinfo import ZoneInfo
        now_local = datetime.now(ZoneInfo(tz))
    except Exception:
        now_local = datetime.now(timezone.utc)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_local.astimezone(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM qr_scans WHERE ts >= ?", (start_utc,)
        ).fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0


def list_qr_scans(limit: int = 100, offset: int = 0) -> dict[str, object]:
    """
    ประวัติการสแกน QR ทั้งหมดจาก DB (ไม่ใช่แค่ session ของ browser) — รองรับ pagination
    คืนค่า raw_keycode/raw_report เป็น list ที่ decode แล้ว (ไม่ใช่ JSON string ดิบ)
    """
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    conn = _get_conn()
    try:
        total_row = conn.execute("SELECT COUNT(*) FROM qr_scans").fetchone()
        total = total_row[0] if total_row else 0
        rows = conn.execute(
            """SELECT id, ts, value, device, raw_keycode, raw_report, read_mode
               FROM qr_scans ORDER BY id DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"rows": [], "total": 0, "limit": limit, "offset": offset}

    result_rows = []
    for r in rows:
        try:
            raw_keycode = json.loads(r["raw_keycode"]) if r["raw_keycode"] else None
        except (TypeError, ValueError):
            raw_keycode = None
        try:
            raw_report = json.loads(r["raw_report"]) if r["raw_report"] else None
        except (TypeError, ValueError):
            raw_report = None
        result_rows.append({
            "id": r["id"],
            "ts": r["ts"],
            "value": r["value"],
            "device": r["device"],
            "raw_keycode": raw_keycode,
            "raw_report": raw_report,
            "read_mode": r["read_mode"],
        })
    return {"rows": result_rows, "total": total, "limit": limit, "offset": offset}


def list_mqtt_events(limit: int = 100, offset: int = 0) -> dict[str, object]:
    """ประวัติการ publish MQTT ทั้งหมดจาก DB (ทุกครั้งที่มีการ publish_qr_scan) — รองรับ pagination"""
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    conn = _get_conn()
    try:
        total_row = conn.execute("SELECT COUNT(*) FROM mqtt_events").fetchone()
        total = total_row[0] if total_row else 0
        rows = conn.execute(
            """SELECT id, ts, scan, topic, payload, ok
               FROM mqtt_events ORDER BY id DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"rows": [], "total": 0, "limit": limit, "offset": offset}

    result_rows = [
        {
            "id": r["id"],
            "ts": r["ts"],
            "scan": r["scan"],
            "topic": r["topic"],
            "payload": r["payload"],
            "ok": bool(r["ok"]),
        }
        for r in rows
    ]
    return {"rows": result_rows, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

_ALLOWED_TABLES = frozenset(["qr_scans", "mqtt_events", "audit_log", "config_history"])

_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "qr_scans":       ("id", "ts", "value", "device"),
    "mqtt_events":    ("id", "ts", "scan", "topic", "payload", "ok"),
    "audit_log":      ("id", "ts", "action", "details"),
    "config_history": ("id", "ts", "module", "key", "old_value", "new_value"),
}


def get_rows(
    table: str,
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
) -> dict[str, object]:
    if table not in _ALLOWED_TABLES:
        return {"error": f"Unknown table: {table}"}

    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    cols = _TABLE_COLUMNS[table]
    col_list = ", ".join(cols)

    conn = _get_conn()
    try:
        if search:
            text_cols = [c for c in cols if c not in ("id", "ok")]
            where_clause = " OR ".join(f"{c} LIKE ?" for c in text_cols)
            like = f"%{search}%"
            params_search = [like] * len(text_cols)

            total_row = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {where_clause}",
                params_search,
            ).fetchone()
            total = total_row[0] if total_row else 0

            rows = conn.execute(
                f"SELECT {col_list} FROM {table} WHERE {where_clause} ORDER BY id DESC LIMIT ? OFFSET ?",
                params_search + [limit, offset],
            ).fetchall()
        else:
            total_row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            total = total_row[0] if total_row else 0
            rows = conn.execute(
                f"SELECT {col_list} FROM {table} ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
    except sqlite3.OperationalError:
        return {"columns": list(cols), "rows": [], "total": 0, "limit": limit, "offset": offset}

    return {
        "columns": list(cols),
        "rows": [list(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_stats() -> dict[str, int]:
    conn = _get_conn()
    stats: dict[str, int] = {}
    for table in sorted(_ALLOWED_TABLES):
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            stats[table] = row[0] if row else 0
        except sqlite3.OperationalError:
            stats[table] = 0
    return stats


def clear_table(table: str) -> dict[str, object]:
    """ลบทุก row ใน table (TRUNCATE equivalent)"""
    if table not in _ALLOWED_TABLES:
        return {"status": "error", "errors": [f"Unknown table: {table}"]}
    try:
        with _cursor() as cur:
            cur.execute(f"DELETE FROM {table}")
            cur.execute("DELETE FROM sqlite_sequence WHERE name=?", (table,))
        return {"status": "ok", "table": table}
    except Exception as exc:
        return {"status": "error", "errors": [str(exc)]}


# ---------------------------------------------------------------------------
# MQTT Broker CRUD
# ---------------------------------------------------------------------------

def _broker_row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id":            row["id"],
        "name":          row["name"],
        "broker_url":    row["broker_url"],
        "username":      row["username"],
        "password":      row["password"],
        "client_id":     row["client_id"],
        "tls_insecure":  bool(row["tls_insecure"]),
        "qos":           row["qos"],
        "retain":        bool(row["retain"]),
        "payload_mode":  row["payload_mode"],
        "enabled":       bool(row["enabled"]),
        "is_primary":    bool(row["is_primary"]),
        "keep_alive":    row["keep_alive"],
        "reconnect_min": row["reconnect_min"],
        "reconnect_max": row["reconnect_max"],
        "notes":         row["notes"],
        "created_at":    row["created_at"],
        "updated_at":    row["updated_at"],
    }


def list_mqtt_brokers() -> list[dict[str, object]]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mqtt_brokers ORDER BY is_primary DESC, id ASC"
        ).fetchall()
        return [_broker_row_to_dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def get_mqtt_broker(broker_id: int) -> dict[str, object] | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM mqtt_brokers WHERE id = ?", (broker_id,)
        ).fetchone()
        return _broker_row_to_dict(row) if row else None
    except sqlite3.OperationalError:
        return None


def create_mqtt_broker(data: dict[str, object]) -> int:
    """สร้าง broker ใหม่ — return new id"""
    now = _now_utc()
    is_primary = bool(data.get("is_primary", False))
    with _cursor() as cur:
        if is_primary:
            cur.execute("UPDATE mqtt_brokers SET is_primary = 0")
        cur.execute(
            """INSERT INTO mqtt_brokers
               (name, broker_url, username, password, client_id,
                tls_insecure, qos, retain, payload_mode, enabled, is_primary,
                keep_alive, reconnect_min, reconnect_max, notes, created_at, updated_at)
               VALUES (?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?, ?,?)""",
            (
                str(data.get("name") or "Broker"),
                str(data.get("broker_url") or "mqtts://localhost:8883"),
                str(data.get("username") or ""),
                str(data.get("password") or ""),
                str(data.get("client_id") or ""),
                1 if data.get("tls_insecure") else 0,
                int(data.get("qos", 1)),  # type: ignore[arg-type]
                1 if data.get("retain") else 0,
                str(data.get("payload_mode") or "decoded"),
                1 if data.get("enabled", True) else 0,
                1 if is_primary else 0,
                int(data.get("keep_alive", 60)),  # type: ignore[arg-type]
                int(data.get("reconnect_min", 3)),  # type: ignore[arg-type]
                int(data.get("reconnect_max", 30)),  # type: ignore[arg-type]
                str(data.get("notes") or ""),
                now, now,
            ),
        )
        return cur.lastrowid  # type: ignore[return-value]


def update_mqtt_broker(broker_id: int, data: dict[str, object]) -> bool:
    now = _now_utc()
    is_primary = bool(data.get("is_primary", False))
    try:
        with _cursor() as cur:
            if is_primary:
                cur.execute(
                    "UPDATE mqtt_brokers SET is_primary = 0 WHERE id != ?", (broker_id,)
                )
            cur.execute(
                """UPDATE mqtt_brokers SET
                   name=?, broker_url=?, username=?, password=?, client_id=?,
                   tls_insecure=?, qos=?, retain=?, payload_mode=?, enabled=?,
                   is_primary=?, keep_alive=?, reconnect_min=?, reconnect_max=?,
                   notes=?, updated_at=?
                   WHERE id=?""",
                (
                    str(data.get("name") or "Broker"),
                    str(data.get("broker_url") or "mqtts://localhost:8883"),
                    str(data.get("username") or ""),
                    str(data.get("password") or ""),
                    str(data.get("client_id") or ""),
                    1 if data.get("tls_insecure") else 0,
                    int(data.get("qos", 1)),  # type: ignore[arg-type]
                    1 if data.get("retain") else 0,
                    str(data.get("payload_mode") or "decoded"),
                    1 if data.get("enabled", True) else 0,
                    1 if is_primary else 0,
                    int(data.get("keep_alive", 60)),  # type: ignore[arg-type]
                    int(data.get("reconnect_min", 3)),  # type: ignore[arg-type]
                    int(data.get("reconnect_max", 30)),  # type: ignore[arg-type]
                    str(data.get("notes") or ""),
                    now,
                    broker_id,
                ),
            )
        return True
    except Exception:
        return False


def delete_mqtt_broker(broker_id: int) -> bool:
    try:
        with _cursor() as cur:
            cur.execute("DELETE FROM mqtt_brokers WHERE id = ?", (broker_id,))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# MQTT Broker Topic CRUD
# ---------------------------------------------------------------------------

def list_mqtt_topics(broker_id: int) -> list[dict[str, object]]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mqtt_broker_topics WHERE broker_id = ? ORDER BY id ASC",
            (broker_id,),
        ).fetchall()
        return [
            {
                "id":         r["id"],
                "broker_id":  r["broker_id"],
                "topic":      r["topic"],
                "label":      r["label"],
                "enabled":    bool(r["enabled"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []


def add_mqtt_topic(broker_id: int, topic: str, label: str = "") -> int:
    now = _now_utc()
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO mqtt_broker_topics (broker_id, topic, label, enabled, created_at) VALUES (?,?,?,1,?)",
            (broker_id, topic.strip(), label.strip(), now),
        )
        return cur.lastrowid  # type: ignore[return-value]


def update_mqtt_topic(topic_id: int, data: dict[str, object]) -> bool:
    try:
        with _cursor() as cur:
            cur.execute(
                "UPDATE mqtt_broker_topics SET topic=?, label=?, enabled=? WHERE id=?",
                (
                    str(data.get("topic") or ""),
                    str(data.get("label") or ""),
                    1 if data.get("enabled", True) else 0,
                    topic_id,
                ),
            )
        return True
    except Exception:
        return False


def delete_mqtt_topic(topic_id: int) -> bool:
    try:
        with _cursor() as cur:
            cur.execute("DELETE FROM mqtt_broker_topics WHERE id = ?", (topic_id,))
        return True
    except Exception:
        return False


def get_primary_broker_id() -> int | None:
    """คืน id ของ broker ที่ is_primary=1 (ถ้ามี)"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM mqtt_brokers WHERE is_primary = 1 LIMIT 1"
        ).fetchone()
        return int(row["id"]) if row else None
    except sqlite3.OperationalError:
        return None


# ---------------------------------------------------------------------------
# Device Integration CRUD (device_integrations — migration version 2)
# ---------------------------------------------------------------------------

def _device_integration_row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    try:
        settings = json.loads(row["settings_json"]) if row["settings_json"] else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        settings = {}
    d: dict[str, object] = {
        "id":               row["id"],
        "device_id":        row["device_id"],
        "integration_type": row["integration_type"],
        "enabled":          bool(row["enabled"]),
        "broker_id":        row["broker_id"],
        "topic":            row["topic"],
        "qos":              row["qos"],
        "created_at":       row["created_at"],
        "updated_at":       row["updated_at"],
    }
    # เติม field เฉพาะประเภทที่เก็บใน settings_json เข้าไปที่ระดับบนสุด (flatten)
    for k, v in settings.items():
        if k not in d:
            d[k] = v
    return d


def list_device_integrations(device_id: str) -> dict[str, dict[str, object]]:
    """คืน integration config ของ device หนึ่งตัว keyed by integration_type (webhook/mqtt/pipe)"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM device_integrations WHERE device_id = ?", (device_id,)
        ).fetchall()
        return {r["integration_type"]: _device_integration_row_to_dict(r) for r in rows}
    except sqlite3.OperationalError:
        return {}


def list_pipe_integrations() -> list[dict[str, object]]:
    """
    คืน integration แบบ "pipe" ของทุก device ในระบบ (ไม่ใช่แค่ device เดียว) — ใช้กับหน้า
    Pipe Tester (/pipe-tester) เป็นรายการ "pipe ที่ตั้งค่าไว้แล้ว" ให้เลือกทดสอบเร็วๆ แทน
    การพิมพ์ path เอง ทุกครั้ง — ดึงมาทั้ง enabled และ disabled (frontend ไปกรอง/แสดงสถานะเอง)
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM device_integrations WHERE integration_type = 'pipe' ORDER BY device_id"
        ).fetchall()
        return [_device_integration_row_to_dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def upsert_device_integration(
    device_id: str,
    integration_type: str,
    data: dict[str, object],
) -> bool:
    """สร้างหรืออัปเดต integration config ของ device+type (UNIQUE(device_id, integration_type))"""
    if integration_type not in ("webhook", "mqtt", "pipe"):
        return False
    now = _now_utc()
    enabled = 1 if data.get("enabled") else 0
    broker_id = data.get("broker_id")
    try:
        broker_id_val: int | None = int(broker_id) if broker_id not in (None, "") else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        broker_id_val = None
    topic = str(data.get("topic") or "")
    try:
        qos = int(data.get("qos", 1))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        qos = 1
    known_cols = {"enabled", "broker_id", "topic", "qos", "type"}
    extra = {k: v for k, v in data.items() if k not in known_cols}
    settings_json = json.dumps(extra, ensure_ascii=False)

    try:
        with _cursor() as cur:
            cur.execute(
                """INSERT INTO device_integrations
                   (device_id, integration_type, enabled, broker_id, topic, qos, settings_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(device_id, integration_type) DO UPDATE SET
                       enabled=excluded.enabled,
                       broker_id=excluded.broker_id,
                       topic=excluded.topic,
                       qos=excluded.qos,
                       settings_json=excluded.settings_json,
                       updated_at=excluded.updated_at""",
                (device_id, integration_type, enabled, broker_id_val, topic, qos, settings_json, now, now),
            )
        return True
    except Exception:
        return False
