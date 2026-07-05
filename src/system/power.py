from __future__ import annotations

from core.runner import CommandRunner


def reboot_system(runner: CommandRunner | None = None) -> None:
    """สั่งรีสตาร์ทเครื่องผ่าน `systemctl reboot`

    คำสั่งนี้ไม่ block — systemd รับคำขอแล้วคืนค่าทันที ส่วนการปิด service/reboot
    จริงเกิดขึ้นแบบ async หลังจากนี้ไม่กี่วินาที จึงยังส่ง HTTP response กลับไปให้
    ผู้ใช้ก่อนเครื่อง reboot จริงได้ตามปกติ
    """
    (runner or CommandRunner()).run(["systemctl", "reboot"], check=True)


def shutdown_system(runner: CommandRunner | None = None) -> None:
    """สั่งปิดเครื่องผ่าน `systemctl poweroff` (ดูหมายเหตุ async ที่ `reboot_system`)"""
    (runner or CommandRunner()).run(["systemctl", "poweroff"], check=True)
