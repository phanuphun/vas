"""
VAS — AnyDesk remote access management

รับผิดชอบเฉพาะ "action" ที่กระทบระบบจริง (service control + unattended password)
ส่วนการอ่านสถานะ (installed/version/id/service) อยู่ที่ `system.status.collect_remote_access_status`
"""
from __future__ import annotations

import shutil
import subprocess

from core.runner import CommandResult, CommandRunner
from system.utils import dev_fake_installed

SERVICE_NAME = "anydesk"
VALID_SERVICE_ACTIONS = ("start", "stop", "restart", "enable", "disable")


def service_action(runner: CommandRunner, action: str) -> CommandResult:
    """รัน `systemctl <action> anydesk` — action ต้องเป็นหนึ่งใน VALID_SERVICE_ACTIONS"""
    if action not in VALID_SERVICE_ACTIONS:
        raise ValueError(f"Unknown AnyDesk service action: {action}")
    if dev_fake_installed():
        # dev mode — ไม่มี systemd/anydesk จริง จึงจำลองผลลัพธ์สำเร็จแทนการรันจริง
        return CommandResult(args=("systemctl", action, SERVICE_NAME), returncode=0, stdout="", stderr="")
    return runner.run(["systemctl", action, SERVICE_NAME], check=False)


def set_unattended_password(password: str) -> tuple[bool, str]:
    """
    ตั้งรหัสผ่านสำหรับ Unattended Access ผ่าน `anydesk --set-password` โดยส่งรหัสผ่านทาง stdin

    หมายเหตุ: จงใจไม่ใช้ CommandRunner ตรงนี้ — CommandRunner.print_operation() จะพิมพ์
    argv ทั้งหมดออก log/terminal ซึ่งจะทำให้รหัสผ่านหลุดไปอยู่ใน log ได้ ในเมื่อรหัสผ่านถูกส่ง
    ทาง stdin แทน argv จึงเรียก subprocess ตรงและไม่พิมพ์ค่า password ออกที่ใดเลย
    """
    if not password:
        return False, "กรุณากรอกรหัสผ่าน"
    if dev_fake_installed():
        # dev mode — ไม่มี anydesk binary จริง จึงจำลองผลลัพธ์สำเร็จแทนการรันจริง (ไม่บันทึกรหัสผ่านที่ใดเลย)
        return True, "ตั้งรหัสผ่าน Unattended Access เรียบร้อย (dev-mode — จำลองผล ไม่ได้ตั้งจริง)"

    anydesk_path = shutil.which("anydesk")
    if anydesk_path is None:
        return False, "AnyDesk ยังไม่ได้ติดตั้ง"

    try:
        result = subprocess.run(
            [anydesk_path, "--set-password"],
            input=password,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or "ตั้งรหัสผ่านไม่สำเร็จ"
    return True, "ตั้งรหัสผ่าน Unattended Access เรียบร้อย"
