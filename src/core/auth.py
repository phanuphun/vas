"""
VAS — Authentication & User Management

Roles (ลำดับสูงสุด → ต่ำสุด):
    root  — สร้างอัตโนมัติครั้งแรก, ลบไม่ได้, สิทธิ์สูงสุด
    admin — ดูแลระบบ, จัดการ user ได้ แต่ไม่สามารถจัดการ root
    user  — ผู้ใช้งานทั่วไป

Session key: "vas_user_id"
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import TypedDict

from werkzeug.security import check_password_hash, generate_password_hash

from core.database import _get_conn, _cursor

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ROLES = ("root", "admin", "user")
ROLE_WEIGHT = {"root": 100, "admin": 50, "user": 10}


class UserRow(TypedDict):
    id: int
    username: str
    display_name: str
    role: str
    created_at: str
    last_login: str | None


# ---------------------------------------------------------------------------
# Schema — เรียก init_users() จาก init_db()
# ---------------------------------------------------------------------------

_USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT    NOT NULL DEFAULT '',
    password_hash TEXT   NOT NULL,
    role         TEXT    NOT NULL DEFAULT 'user' CHECK(role IN ('root','admin','user')),
    created_at   TEXT    NOT NULL,
    last_login   TEXT    DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username COLLATE NOCASE);
"""


def init_users() -> None:
    """สร้าง users table (เรียกจาก init_db)"""
    conn = _get_conn()
    conn.executescript(_USERS_SCHEMA)
    conn.commit()


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def count_users() -> int:
    conn = _get_conn()
    row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    return row[0] if row else 0


def get_user_by_id(user_id: int) -> UserRow | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, username, display_name, role, created_at, last_login FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)  # type: ignore[return-value]


def get_user_by_username(username: str) -> dict | None:
    """คืน row พร้อม password_hash (ใช้เฉพาะ login)"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, username, display_name, role, created_at, last_login, password_hash FROM users WHERE username=? COLLATE NOCASE",
        (username,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def list_users() -> list[UserRow]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, username, display_name, role, created_at, last_login FROM users ORDER BY id ASC"
    ).fetchall()
    return [dict(r) for r in rows]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def create_user(
    username: str,
    password: str,
    display_name: str = "",
    role: str = "user",
) -> tuple[bool, str]:
    """
    สร้าง user ใหม่
    Returns (ok, error_msg)
    """
    username = username.strip()
    display_name = display_name.strip()
    if not username:
        return False, "กรุณาระบุชื่อผู้ใช้"
    if len(username) < 3:
        return False, "ชื่อผู้ใช้ต้องมีอย่างน้อย 3 ตัวอักษร"
    if role not in ROLES:
        return False, f"Role ไม่ถูกต้อง: {role}"
    if len(password) < 6:
        return False, "รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร"

    pw_hash = generate_password_hash(password)
    try:
        with _cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, display_name, password_hash, role, created_at) VALUES (?,?,?,?,?)",
                (username, display_name or username, pw_hash, role, _now()),
            )
        return True, ""
    except sqlite3.IntegrityError:
        return False, f"ชื่อผู้ใช้ '{username}' ถูกใช้งานแล้ว"
    except Exception as exc:
        return False, str(exc)


def update_user(
    user_id: int,
    *,
    display_name: str | None = None,
    role: str | None = None,
) -> tuple[bool, str]:
    """อัปเดตข้อมูล user (ไม่รวม password)"""
    fields: list[str] = []
    params: list[object] = []

    if display_name is not None:
        display_name = display_name.strip()
        if not display_name:
            return False, "กรุณาระบุชื่อแสดง"
        fields.append("display_name=?")
        params.append(display_name)

    if role is not None:
        if role not in ROLES:
            return False, f"Role ไม่ถูกต้อง: {role}"
        fields.append("role=?")
        params.append(role)

    if not fields:
        return False, "ไม่มีข้อมูลที่ต้องอัปเดต"

    params.append(user_id)
    try:
        with _cursor() as cur:
            cur.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", params)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def change_password(user_id: int, new_password: str) -> tuple[bool, str]:
    """เปลี่ยน password"""
    if len(new_password) < 6:
        return False, "รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร"
    pw_hash = generate_password_hash(new_password)
    try:
        with _cursor() as cur:
            cur.execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash, user_id))
        return True, ""
    except Exception as exc:
        return False, str(exc)


def verify_current_password(user_id: int, current_password: str) -> bool:
    """ตรวจสอบ password ปัจจุบัน (สำหรับ change password ของตัวเอง)"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT password_hash FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if row is None:
        return False
    return check_password_hash(row["password_hash"], current_password)


def delete_user(user_id: int) -> tuple[bool, str]:
    """ลบ user — root ลบไม่ได้"""
    user = get_user_by_id(user_id)
    if user is None:
        return False, "ไม่พบผู้ใช้งาน"
    if user["role"] == "root":
        return False, "ไม่สามารถลบ Root ได้"
    try:
        with _cursor() as cur:
            cur.execute("DELETE FROM users WHERE id=?", (user_id,))
        return True, ""
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def authenticate(username: str, password: str) -> tuple[UserRow | None, str]:
    """
    ตรวจสอบ username + password.
    Returns (user_row, error_msg) — user_row=None เมื่อ fail
    """
    user = get_user_by_username(username)
    if user is None:
        return None, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"
    if not check_password_hash(user["password_hash"], password):
        return None, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"

    # อัปเดต last_login
    try:
        with _cursor() as cur:
            cur.execute("UPDATE users SET last_login=? WHERE id=?", (_now(), user["id"]))
    except Exception:
        pass

    safe_user: UserRow = {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "created_at": user["created_at"],
        "last_login": user.get("last_login"),
    }
    return safe_user, ""


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

def can_manage_user(actor_role: str, target_role: str) -> bool:
    """actor สามารถจัดการ target ได้หรือไม่"""
    return ROLE_WEIGHT.get(actor_role, 0) > ROLE_WEIGHT.get(target_role, 0)


def is_first_run() -> bool:
    """คืน True ถ้ายังไม่มี user ในระบบ"""
    try:
        return count_users() == 0
    except Exception:
        return True


ROLE_LABELS: dict[str, str] = {
    "root":  "Root",
    "admin": "Admin",
    "user":  "User",
}

ROLE_BADGE_CLASS: dict[str, str] = {
    "root":  "zone-danger",
    "admin": "zone-caution",
    "user":  "zone-info",
}
