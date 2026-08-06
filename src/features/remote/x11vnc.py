"""
VAS — x11vnc remote access management

รับผิดชอบ "action" ที่กระทบระบบจริงทั้งหมดของ x11vnc: apply setup (เขียน systemd unit +
daemon-reload + enable --now), service control (start/stop/restart/enable/disable), และตั้ง
รหัสผ่าน VNC ส่วนการอ่านสถานะ (installed/version/service/config ปัจจุบัน) อยู่ที่
`system.status.collect_x11vnc_status` — pattern เดียวกับ features/remote/anydesk.py

ไม่มี DB table เก็บ config — ใช้ /etc/systemd/system/x11vnc.service บนดิสก์เป็น single source
of truth เดียวกับที่ vas_mcp/service.py ใช้กับ MCP server (parse กลับมาแสดงผลตอนเปิดหน้าเว็บ
ผ่าน system.status._parse_x11vnc_unit())
"""
from __future__ import annotations

import ipaddress
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

from core.runner import CommandResult, CommandRunner
from system.utils import dev_fake_installed

try:
    import pwd as pwd_module
except ImportError:  # pragma: no cover — pwd ไม่มีบน Windows dev machine
    pwd_module = None  # type: ignore[assignment]

PWD_MODULE = cast("Any | None", pwd_module)

SERVICE_NAME = "x11vnc"
SERVICE_UNIT = f"{SERVICE_NAME}.service"
SERVICE_PATH = Path("/etc/systemd/system") / SERVICE_UNIT
PASSWORD_PATH = Path("/etc/x11vnc.pass")

DEFAULT_PORT = 5900
DEFAULT_DISPLAY = ":0"

VALID_SERVICE_ACTIONS = ("start", "stop", "restart", "enable", "disable")


def render_service_file(listen_ip: str, port: int, display: str, user: str, home: str) -> str:
    """สร้างเนื้อไฟล์ x11vnc.service ตาม template ที่ทดสอบมาแล้วเป๊ะๆ — ExecStart ต่อหลาย
    บรรทัดด้วย "\\" (ไม่ flatten เป็นบรรทัดเดียว) เพื่อให้ diff เทียบกับที่ทดสอบเองมาก่อนได้ตรง
    และให้ system.status._parse_x11vnc_unit() join กลับมา parse ได้ตาม format ที่คาดไว้"""
    return (
        "[Unit]\n"
        "Description=x11vnc mirror service\n"
        "After=multi-user.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"User={user}\n"
        f"ExecStart=/usr/bin/x11vnc -display {display} -auth {home}/.Xauthority \\\n"
        "  -forever -loop -noxdamage -repeat -shared \\\n"
        f"  -rfbauth {PASSWORD_PATH} -rfbport {port} \\\n"
        f"  -listen {listen_ip}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def _resolve_home(user: str) -> str:
    """หา home directory จริงของ user จาก /etc/passwd (ไม่เดาว่าเป็น /home/<user> เสมอไป —
    บาง user อาจมี home directory อื่น) — dev-mode คืน f"/home/{user}" ตรงๆ ไม่แตะ pwd จริง

    Raises:
        ValueError: ไม่มี user นี้จริงในเครื่อง (pwd.getpwnam ล้มเหลว) — ให้ route handler
            จับแล้วคืน 400 ที่ข้อความอ่านได้ แทนที่จะปล่อยเป็น 500 ดิบ
    """
    if dev_fake_installed():
        return f"/home/{user}"
    if PWD_MODULE is None:
        raise ValueError("ไม่รองรับการค้นหา user บนระบบนี้ (ไม่มี pwd module)")
    try:
        return cast(str, PWD_MODULE.getpwnam(user).pw_dir)
    except KeyError as exc:
        raise ValueError(f"ไม่พบ user '{user}' ในเครื่องนี้") from exc


def _validate_setup_input(listen_ip: str, port: int, display: str, user: str) -> str | None:
    """ตรวจ input ก่อนแตะ filesystem — คืนข้อความ error (str) ถ้าไม่ผ่าน, None ถ้าผ่านหมด"""
    if not listen_ip:
        return "กรุณากรอก Listen IP"
    try:
        ipaddress.ip_address(listen_ip)
    except ValueError:
        return f"Listen IP ไม่ถูกต้อง: '{listen_ip}'"
    if not (1 <= port <= 65535):
        return f"Port ต้องอยู่ระหว่าง 1-65535 (ได้รับ {port})"
    if not display.startswith(":"):
        return f"Display ต้องขึ้นต้นด้วย ':' (ได้รับ '{display}')"
    if not user:
        return "กรุณาเลือก user"
    return None


def apply_setup(runner: CommandRunner, listen_ip: str, port: int, display: str, user: str) -> tuple[bool, str]:
    """เขียน x11vnc.service ตามค่าที่ตั้ง แล้ว daemon-reload + enable --now ให้ครบในตัว

    dev-mode (VAS_DEV_FAKE_INSTALLED=1) คืนผลสำเร็จจำลองทันที ไม่แตะ filesystem/systemctl เลย —
    ตั้งใจเข้มกว่า vas_mcp.service.McpServiceManager.install() (เช็คแค่ runner.dry_run) เพื่อไม่ให้
    เผลอ PermissionError ตอน dev/test บนเครื่องที่ไม่ใช่ root หรือไม่มี /etc/systemd/system จริง
    (เช่น dev.bat บน Windows)
    """
    error = _validate_setup_input(listen_ip, port, display, user)
    if error is not None:
        return False, error

    try:
        home = _resolve_home(user)
    except ValueError as exc:
        return False, str(exc)

    if dev_fake_installed():
        return True, "บันทึกและเปิดใช้งาน x11vnc.service เรียบร้อย (dev-mode — จำลองผล ไม่ได้เขียนไฟล์จริง)"

    SERVICE_PATH.write_text(render_service_file(listen_ip, port, display, user, home), encoding="utf-8")
    SERVICE_PATH.chmod(0o644)
    runner.run(["systemctl", "daemon-reload"])
    runner.run(["systemctl", "enable", "--now", SERVICE_UNIT])
    return True, "บันทึกและเปิดใช้งาน x11vnc.service เรียบร้อย"


def service_action(runner: CommandRunner, action: str) -> CommandResult:
    """รัน `systemctl <action> x11vnc` — action ต้องเป็นหนึ่งใน VALID_SERVICE_ACTIONS"""
    if action not in VALID_SERVICE_ACTIONS:
        raise ValueError(f"Unknown x11vnc service action: {action}")
    if dev_fake_installed():
        # dev mode — ไม่มี systemd/x11vnc จริง จึงจำลองผลลัพธ์สำเร็จแทนการรันจริง
        return CommandResult(args=("systemctl", action, SERVICE_NAME), returncode=0, stdout="", stderr="")
    return runner.run(["systemctl", action, SERVICE_NAME], check=False)


def set_vnc_password(password: str) -> tuple[bool, str]:
    """
    ตั้งรหัสผ่าน VNC ผ่าน `x11vnc -storepasswd <password> /etc/x11vnc.pass`

    แก้ไข 2026-08-06: เดิมเรียก `x11vnc -storepasswd - /etc/x11vnc.pass` โดยเข้าใจผิดว่า "-"
    แปลว่าให้ x11vnc อ่านรหัสผ่านจาก stdin (เลียนแบบ pattern ของ
    features.remote.anydesk.set_unattended_password) — แต่ `x11vnc -storepasswd` จริงๆ ไม่รองรับ
    stdin เลย: ถ้าให้ 2 argument ตัวแรกจะถูกตีความเป็น**รหัสผ่านตัวอักษรตรงๆ** ไม่ใช่สัญลักษณ์พิเศษ
    ผลคือรหัสผ่านที่ถูกเก็บจริงกลายเป็นอักขระ "-" ตัวเดียวเสมอ ไม่ว่าผู้ใช้จะพิมพ์อะไรมา (แต่
    คำสั่ง exit 0 สำเร็จ หน้าเว็บเลยรายงานว่า "เรียบร้อย" ทั้งที่รหัสผ่านที่ใช้ login จริงผิด) —
    ยืนยันจาก user จริงที่ตั้งรหัสผ่านผ่านหน้าเว็บแล้ว remote เข้าไม่ได้เลยบนเครื่องจริง

    ทางแก้: ส่งรหัสผ่านเป็น argument ที่ 2 ตรงๆ — เป็นวิธีเดียวที่ x11vnc รองรับสำหรับตั้งรหัสผ่าน
    แบบ non-interactive (ไม่มี stdin mode ให้ใช้จริง) แลกกับรหัสผ่านโผล่ใน process list (`ps aux`)
    ช่วงสั้นๆ ระหว่างรันคำสั่ง — ยังคงไม่ใช้ CommandRunner ตรงนี้ (CommandRunner.print_operation()
    จะพิมพ์ argv ออก log/terminal) จึงเรียก subprocess ตรงเพื่อไม่ให้รหัสผ่านหลุดไปอยู่ใน log ถาวร
    """
    if not password:
        return False, "กรุณากรอกรหัสผ่าน"
    if len(password) < 8:
        return False, "รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร"
    if dev_fake_installed():
        return True, "ตั้งรหัสผ่าน VNC เรียบร้อย (dev-mode — จำลองผล ไม่ได้ตั้งจริง)"

    x11vnc_path = shutil.which("x11vnc")
    if x11vnc_path is None:
        return False, "x11vnc ยังไม่ได้ติดตั้ง"

    try:
        result = subprocess.run(
            [x11vnc_path, "-storepasswd", password, str(PASSWORD_PATH)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, detail or "ตั้งรหัสผ่านไม่สำเร็จ"

    try:
        PASSWORD_PATH.chmod(0o644)
    except OSError:
        pass  # best-effort — ไม่ใช่เหตุผลให้รายงาน failure ทั้งที่ x11vnc เขียนไฟล์สำเร็จแล้ว

    return True, "ตั้งรหัสผ่าน VNC เรียบร้อย"
