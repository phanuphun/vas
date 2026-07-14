"""
MCP tool: guarded arbitrary shell execution (`run_command`)

ต่างจาก tool อื่นใน vas_mcp/tools/ (system.py, docker.py, network.py, logs.py) ที่เป็น read-only
diagnostics — ไฟล์นี้ให้ AI agent รันคำสั่งอะไรก็ได้บนเครื่อง (ไม่ fix เป็น whitelist คำสั่งตายตัว)
แต่กันไว้ 3 หมวดตามที่ผู้ใช้ยืนยัน: ลบไฟล์ (delete), ติดตั้งแพ็กเกจ (install), และอัปเดตระบบ/ตัวเอง
(update) — คำสั่งที่เข้าข่ายจะถูกปฏิเสธ "ก่อน" รันจริงเสมอ ไม่ใช่ retroactive

Policy logic (blocklist ของ binary/verb/pattern) อยู่ที่ core/exec_guard.py แยกต่างหาก — ไฟล์นี้
มีหน้าที่แค่ห่อ policy นั้นด้วย fastmcp decorator + รัน subprocess จริง + บันทึก audit log
(ดู docstring บนสุดของ core/exec_guard.py สำหรับเหตุผลที่แยกไฟล์)
"""
from __future__ import annotations

import subprocess

from fastmcp import FastMCP

from core.database import log_audit
from core.exec_guard import (
    DEFAULT_TIMEOUT,
    MAX_TIMEOUT,
    CommandRejected,
    check_command,
    exec_policy,
    truncate_output,
)

mcp = FastMCP("vas-shell")


@mcp.tool()
def run_command(command: str, timeout: int = DEFAULT_TIMEOUT, cwd: str | None = None) -> dict:
    """รันคำสั่ง shell ใดก็ได้บนเครื่อง (ไม่ fix เป็น whitelist คำสั่งตายตัว)

    ห้ามใช้คำสั่งที่เข้าข่าย 3 หมวด — จะถูกปฏิเสธก่อนรันจริงเสมอ (ดู get_exec_policy() สำหรับ
    รายละเอียด):
    1. ลบไฟล์/ข้อมูล: rm, rmdir, unlink, shred, find -delete, truncate -s 0
    2. ติดตั้ง/ถอนแพ็กเกจ: apt/apt-get install|remove|purge, dpkg -i/-r, pip install,
       npm install, snap install, gem install, curl|bash
    3. อัปเดตระบบ/ตัวเอง: apt update/upgrade/dist-upgrade, npm update, snap refresh,
       vas update, git pull

    ทุกคำสั่งที่เข้ามา (ทั้งที่ถูกบล็อกและที่รันจริง) ถูกบันทึกลง audit_log

    timeout: วินาที (1-120, default 30) — คำสั่งที่ค้างเกินจะถูก kill
    cwd: working directory (ค่าเริ่มต้น: home ของ process ที่รัน MCP server)
    """
    command = (command or "").strip()
    if not command:
        return {"error": "empty command"}

    timeout = max(1, min(int(timeout), MAX_TIMEOUT))

    try:
        check_command(command)
    except CommandRejected as exc:
        log_audit(
            "mcp_exec_blocked",
            {"command": command, "reason": exc.reason, "segment": exc.segment},
        )
        return {"blocked": True, "reason": exc.reason, "segment": exc.segment}

    try:
        result = subprocess.run(
            command,
            shell=True,
            executable="/bin/bash",
            text=True,
            capture_output=True,
            timeout=timeout,
            cwd=cwd or None,
            check=False,
        )
        log_audit(
            "mcp_exec",
            {"command": command, "returncode": result.returncode, "cwd": cwd, "timeout": timeout},
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": truncate_output(result.stdout),
            "stderr": truncate_output(result.stderr),
        }
    except subprocess.TimeoutExpired:
        log_audit("mcp_exec_timeout", {"command": command, "timeout": timeout})
        return {"error": f"command timed out after {timeout}s", "command": command}
    except OSError as exc:
        log_audit("mcp_exec_error", {"command": command, "error": str(exc)})
        return {"error": str(exc), "command": command}


@mcp.tool()
def get_exec_policy() -> dict:
    """ดูรายละเอียด policy ของ run_command() — binary/verb ที่ถูกบล็อก และ pattern ที่ถูกบล็อก"""
    return exec_policy()
