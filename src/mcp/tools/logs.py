from __future__ import annotations

import subprocess

from fastmcp import FastMCP

from system.audit import list_system_snapshots, read_system_snapshot

mcp = FastMCP("vas-logs")


@mcp.tool()
def get_logs(snapshot_id: str | None = None) -> dict:
    """รายการ log snapshots หรืออ่าน snapshot ย้อนหลัง

    ถ้าไม่ระบุ snapshot_id จะ return รายการ snapshots ทั้งหมด
    ถ้าระบุ snapshot_id จะ return เนื้อหาของ snapshot นั้น
    """
    try:
        if snapshot_id is None:
            snapshots = list_system_snapshots()
            return {"snapshots": list(snapshots)}
        return read_system_snapshot(snapshot_id)
    except FileNotFoundError:
        return {"error": "snapshot not found"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_journal_logs(
    since: str | None = None,
    until: str | None = None,
    unit: str | None = None,
    lines: int = 200,
) -> dict:
    """ดู systemd journal โดยกรองตามเวลาหรือ service unit

    since/until: เช่น "2026-06-15 12:00:00" หรือ "3 days ago"
    unit: เช่น "docker", "wg-quick@wg0", "vending-auto-setup-server"
    """
    try:
        lines = min(max(1, lines), 2000)
        cmd = ["journalctl", "--no-pager", "-n", str(lines)]
        if since:
            cmd += ["--since", since]
        if until:
            cmd += ["--until", until]
        if unit:
            cmd += ["-u", unit]

        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        content = result.stdout.strip() or result.stderr.strip()
        return {
            "query": {"since": since, "until": until, "unit": unit, "lines": lines},
            "content": content,
        }
    except subprocess.TimeoutExpired:
        return {"error": "journalctl timed out"}
    except OSError:
        return {"error": "journalctl not available"}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_logged_in_users(history: bool = False) -> dict:
    """ดูว่าใครใช้งานเครื่องอยู่และประวัติการ login

    history=True จะดึง login history ย้อนหลัง 50 รายการ
    """
    try:
        current_users = _parse_who()
        login_history = _parse_last() if history else []
        return {"current_users": current_users, "login_history": login_history}
    except Exception as e:
        return {"error": str(e)}


def _parse_who() -> list[dict]:
    try:
        result = subprocess.run(
            ["who"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []

    users = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        users.append(
            {
                "user": parts[0],
                "tty": parts[1] if len(parts) > 1 else "",
                "from": parts[4] if len(parts) > 4 else "",
                "login_time": " ".join(parts[2:4]) if len(parts) > 3 else "",
            }
        )
    return users


def _parse_last() -> list[dict]:
    try:
        result = subprocess.run(
            ["last", "-n", "50"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []

    history = []
    for line in result.stdout.splitlines():
        if not line.strip() or line.startswith("wtmp"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        history.append(
            {
                "user": parts[0],
                "tty": parts[1] if len(parts) > 1 else "",
                "from": parts[2] if len(parts) > 2 else "",
                "login": " ".join(parts[3:7]) if len(parts) > 6 else "",
                "logout": parts[7] if len(parts) > 7 else "",
                "duration": parts[8].strip("()") if len(parts) > 8 else "",
            }
        )
    return history
