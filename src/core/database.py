"""
VAS — SQLite database layer

ไฟล์ DB: ~/.config/vas/vas.db  (สร้างอัตโนมัติถ้าไม่มี)

Tables:
    qr_scans       — ประวัติ QR scan ทุกครั้ง
    mqtt_events    — ทุก MQTT publish attempt
    audit_log      — system log snapshot events
    config_history — ทุกครั้งที่มีการบันทึก config เปลี่ยนแปลง
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
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
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
"""

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
# Init
# ---------------------------------------------------------------------------

def init_db() -> None:
    """สร้าง tables ถ้ายังไม่มี — เรียก 1 ครั้งตอน server start"""
    global _initialized
    with _init_lock:
        if _initialized:
            return
        conn = _get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()
        from core.auth import init_users
        init_users()
        _initialized = True


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_qr_scan(value: str, device: str | None = None, ts: str | None = None) -> None:
    try:
        with _cursor() as cur:
            cur.execute(
                "INSERT INTO qr_scans (ts, value, device) VALUES (?, ?, ?)",
                (ts or _now_utc(), value, device),
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
