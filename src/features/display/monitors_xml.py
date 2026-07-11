"""VAS — monitors.xml (mutter/GNOME) management

แก้ปัญหาที่บันทึกไว้ใน docs/kiosk-user-monitor-rotation-investigation.md และ
docs/monitors-xml/proof-2026-07-11-option-c-system-level.md: session แบบ GNOME (mutter
เป็น compositor) จะเขียนทับค่าที่ 98-vending-display-rotate.conf ตั้งไว้กลับเป็น "normal"
เสมอ ถ้า user ที่ login ไม่มี ~/.config/monitors.xml เป็นของตัวเอง — วิธีแก้ที่ proof แล้ว
บน VM คือเขียนไฟล์ระดับเครื่อง /etc/xdg/monitors.xml (ตัวเลือก C ในเอกสารสืบสวน) ให้เป็น
fallback สำหรับทุก user ที่ยังไม่มีไฟล์ของตัวเอง

โมดูลนี้แทนที่ขั้นตอน "เข้า GNOME Settings > Displays > Apply > Keep Changes" ด้วยการยิง
D-Bus (`org.gnome.Mutter.DisplayConfig.GetCurrentState`) ตรงๆ จาก VAS backend เอง — ไม่ต้อง
ไป trigger อะไรที่หน้า desktop จริงเลย

**คำเตือนสำคัญ**: ค่า vendor/product/serial/rate ต้อง query จาก GetCurrentState ของเครื่องนั้น
เสมอ ห้าม hardcode/copy จากเครื่องอื่นเด็ดขาด (ดูเอกสารสืบสวน หัวข้อ 5/8) — และการ parse
ผลลัพธ์ gdbus (`parse_get_current_state_output`) เป็น best-effort ยังไม่ได้ proof บนเครื่องจริง
(ดู checklist "Proof C" ที่ยังค้างอยู่ในเอกสารสืบสวน หัวข้อ 7) ต้องทดสอบกับ mutter เวอร์ชันจริง
บนเครื่อง production ก่อนพึ่งพา automation นี้แบบเต็มรูปแบบ
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core.runner import CommandRunner

try:
    import pwd as pwd_module
except ImportError:  # pragma: no cover - Windows dev hosts
    pwd_module = None  # type: ignore[assignment]

__all__ = [
    "MONITORS_XML_SIGNATURE",
    "SYSTEM_MONITORS_XML_PATH",
    "MonitorState",
    "MonitorsXmlManager",
    "MonitorsXmlSystemStatus",
    "build_monitors_xml",
    "collect_monitors_xml_system_status",
    "find_x_session_for_user",
    "parse_get_current_state_output",
    "user_has_own_monitors_xml",
    "user_monitors_xml_path",
]

SYSTEM_MONITORS_XML_PATH = Path("/etc/xdg/monitors.xml")
MONITORS_XML_SIGNATURE = "<!-- vending-auto-config: monitors-xml -->"


@dataclass(frozen=True)
class MonitorState:
    """ค่าฮาร์ดแวร์จอจริง 1 ตัว — ต้อง query มาจาก mutter D-Bus (GetCurrentState) เท่านั้น
    ห้าม hardcode ค่าพวกนี้ข้ามเครื่องเด็ดขาด (ดู docstring บนสุดของไฟล์นี้)"""

    connector: str
    vendor: str
    product: str
    serial: str
    width: int
    height: int
    rate: str  # เก็บเป็น string เพราะค่าจริงมักเป็นทศนิยมละเอียด (เช่น "59.9601") ห้าม round


@dataclass(frozen=True)
class MonitorsXmlSystemStatus:
    path: Path
    exists: bool
    has_signature: bool


def user_monitors_xml_path(home: Path) -> Path:
    return home / ".config" / "monitors.xml"


def user_has_own_monitors_xml(home: Path) -> bool:
    """เช็คว่า user นี้มี monitors.xml ของตัวเองอยู่แล้วไหม — ถ้ามี ไฟล์นั้นจะชนะ
    system-level (/etc/xdg/monitors.xml) เสมอตาม policy default ของ mutter (ดู
    docs/monitors-xml/README.md) VAS ต้องเช็คก่อนเขียน system-level เสมอ กันเข้าใจผิดว่า
    user คนนั้นจะได้ค่าจาก system-level ไปด้วยทั้งที่จริงไฟล์ของตัวเองจะชนะอยู่ดี"""
    try:
        return user_monitors_xml_path(home).exists()
    except OSError:
        return False


def collect_monitors_xml_system_status(
    path: Path = SYSTEM_MONITORS_XML_PATH,
) -> MonitorsXmlSystemStatus:
    try:
        exists = path.exists()
    except OSError:
        return MonitorsXmlSystemStatus(path=path, exists=False, has_signature=False)

    if not exists:
        return MonitorsXmlSystemStatus(path=path, exists=False, has_signature=False)

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return MonitorsXmlSystemStatus(path=path, exists=True, has_signature=False)

    return MonitorsXmlSystemStatus(
        path=path,
        exists=True,
        has_signature=MONITORS_XML_SIGNATURE in content,
    )


def find_x_session_for_user(username: str) -> "tuple[str, int] | None":
    """หา (DISPLAY, uid) จริงของ user นี้ ผ่าน /proc/<pid>/environ — ห้าม hardcode ":0"
    เด็ดขาด (พิสูจน์แล้วว่าสลับกันไปมาได้จริงระหว่าง user บนเครื่องเดียวกัน ดู
    docs/monitors-xml/proof-2026-07-11-option-c-system-level.md ขั้นที่ 6)

    แยกเป็นฟังก์ชันของตัวเองในโมดูลนี้ (ไม่ import จาก server.py) เพราะ features/* ไม่ควร
    ผูกกับ server.py — ใช้ logic เดียวกับ server.py::_find_display_for_user โดยเจตนา"""
    if pwd_module is None:
        return None
    try:
        uid = pwd_module.getpwnam(username).pw_uid
    except (KeyError, OSError):
        return None

    try:
        import os

        pids = os.listdir("/proc")
    except OSError:
        return None

    for pid in pids:
        if not pid.isdigit():
            continue
        environ_path = Path(f"/proc/{pid}/environ")
        try:
            if environ_path.stat().st_uid != uid:
                continue
            data = environ_path.read_bytes()
        except OSError:
            continue
        for field in data.split(b"\x00"):
            if field.startswith(b"DISPLAY="):
                value = field[len(b"DISPLAY=") :].decode("utf-8", "ignore").strip()
                if value:
                    return value, uid
    return None


class MonitorsXmlManager:
    """เขียน/ลบ monitors.xml — แทนที่ขั้นตอน GNOME Settings > Displays > Apply ด้วยการยิง
    D-Bus ของ mutter ตรงๆ จาก VAS backend"""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def get_current_state(
        self, username: str, x_display: str, uid: int
    ) -> "tuple[MonitorState | None, str | None]":
        """เรียก GetCurrentState ผ่าน D-Bus ของ session ที่ username เป็นเจ้าของอยู่ตอนนี้
        คืนจอตัวแรกที่เจอ (เครื่อง vending มีจอเดียวเสมอในทางปฏิบัติปัจจุบัน)

        คืน (MonitorState, None) ถ้าสำเร็จ, คืน (None, error_detail) ถ้าล้มเหลว —
        error_detail เป็นข้อความ diagnostic จริง (stderr ของ gdbus หรือเหตุผลที่ parse
        ไม่ได้) ต้องส่งกลับให้ผู้ใช้เห็นเสมอ ห้ามคืนแค่ None เฉยๆ เพราะแยกไม่ออกว่าล้มเหลว
        เพราะ session ไม่ใช่ GNOME/mutter, D-Bus service ยังไม่พร้อม, หรือ parser เอง (best-
        effort regex, ดู docstring บนสุดของไฟล์) มีปัญหา

        DBUS_SESSION_BUS_ADDRESS คำนวณจาก uid ตรงๆ ได้ (/run/user/<uid>/bus เป็น path
        มาตรฐานของ systemd user session ไม่ต้อง query แบบเดียวกับ DISPLAY)
        """
        dbus_address = f"unix:path=/run/user/{uid}/bus"
        result = self.runner.run(
            [
                "runuser", "-u", username, "--",
                "env", f"DISPLAY={x_display}", f"DBUS_SESSION_BUS_ADDRESS={dbus_address}",
                "gdbus", "call", "--session",
                "--dest", "org.gnome.Mutter.DisplayConfig",
                "--object-path", "/org/gnome/Mutter/DisplayConfig",
                "--method", "org.gnome.Mutter.DisplayConfig.GetCurrentState",
            ],
            check=False,
        )
        if self.runner.dry_run:
            return None, None
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return None, detail or f"gdbus exit code {result.returncode} (ไม่มี stderr/stdout)"
        state = parse_get_current_state_output(result.stdout)
        if state is None:
            return None, (
                "เรียก D-Bus สำเร็จ (gdbus exit code 0) แต่ parse ผลลัพธ์ไม่ได้ — "
                "parser นี้ยังเป็น best-effort regex ยังไม่เคย proof กับ output จริงบนเครื่องนี้ "
                f"(raw output: {result.stdout.strip()[:300]!r})"
            )
        return state, None

    def write_system_level(
        self,
        state: MonitorState,
        rotation: str,
        path: Path = SYSTEM_MONITORS_XML_PATH,
    ) -> None:
        content = build_monitors_xml(state, rotation)
        print(f"write {path.as_posix()}")
        if self.runner.dry_run:
            print(content.rstrip())
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(0o644)

    def remove_system_level(self, path: Path = SYSTEM_MONITORS_XML_PATH) -> None:
        print(f"remove {path.as_posix()}")
        if self.runner.dry_run:
            return
        if path.exists():
            path.unlink()


def build_monitors_xml(state: MonitorState, rotation: str) -> str:
    """ประกอบ monitors.xml ตาม schema ของ mutter (version 2) — โครงสร้างตรงกับที่ proof
    แล้วจริงใน docs/monitors-xml/proof-2026-07-11-option-c-system-level.md (ไฟล์ที่ mutter
    เขียนเองตอนกด Apply ผ่าน Settings > Displays)"""
    transform_block = ""
    if rotation != "normal":
        transform_block = (
            "      <transform>\n"
            f"        <rotation>{_xml_escape(rotation)}</rotation>\n"
            "        <flipped>no</flipped>\n"
            "      </transform>\n"
        )
    return (
        f"{MONITORS_XML_SIGNATURE}\n"
        '<monitors version="2">\n'
        "  <configuration>\n"
        "    <logicalmonitor>\n"
        "      <x>0</x>\n"
        "      <y>0</y>\n"
        "      <scale>1</scale>\n"
        "      <primary>yes</primary>\n"
        f"{transform_block}"
        "      <monitor>\n"
        "        <monitorspec>\n"
        f"          <connector>{_xml_escape(state.connector)}</connector>\n"
        f"          <vendor>{_xml_escape(state.vendor)}</vendor>\n"
        f"          <product>{_xml_escape(state.product)}</product>\n"
        f"          <serial>{_xml_escape(state.serial)}</serial>\n"
        "        </monitorspec>\n"
        "        <mode>\n"
        f"          <width>{state.width}</width>\n"
        f"          <height>{state.height}</height>\n"
        f"          <rate>{_xml_escape(state.rate)}</rate>\n"
        "        </mode>\n"
        "      </monitor>\n"
        "    </logicalmonitor>\n"
        "  </configuration>\n"
        "</monitors>\n"
    )


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def parse_get_current_state_output(output: str) -> "MonitorState | None":
    """Parse ผลลัพธ์ดิบจาก `gdbus call ... GetCurrentState` (GVariant text format)

    หา monitor ตัวแรก + mode ที่มี flag 'is-current': <true> มาเป็น MonitorState — ยัง
    เป็น best-effort regex parser (ไม่ใช่ full GVariant grammar parser) เพราะยังไม่มี
    เครื่องจริงให้ทดสอบผลลัพธ์ดิบในรอบนี้ (ดู checklist "Proof C" ที่ยังค้างอยู่ใน
    docs/kiosk-user-monitor-rotation-investigation.md หัวข้อ 7) — ต้องทดสอบกับ output
    จริงบนเครื่อง production ก่อนพึ่งพาแบบเต็มรูปแบบ คืน None ถ้า parse ไม่ได้ (caller
    ต้องรายงาน error ให้ผู้ใช้ ไม่ใช่เขียนไฟล์ด้วยค่าที่เดาไว้)
    """
    monitor_match = re.search(
        r"'([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'",
        output,
    )
    if not monitor_match:
        return None
    connector, vendor, product, serial = monitor_match.groups()

    mode_match = re.search(
        r"uint32 (\d+),\s*uint32 (\d+),\s*double ([0-9.]+)[^)]*?'is-current':\s*<true>",
        output,
        re.DOTALL,
    )
    if not mode_match:
        # fallback: เอา mode แรกที่เจอแทนถ้าหา flag 'is-current' ไม่เจอ (ยังได้ค่าที่พอใช้ได้
        # แม้ไม่การันตีว่าตรงกับ mode ที่ใช้งานอยู่จริง ณ ขณะนั้น)
        mode_match = re.search(r"uint32 (\d+),\s*uint32 (\d+),\s*double ([0-9.]+)", output)
    if not mode_match:
        return None
    width, height, rate = mode_match.groups()

    return MonitorState(
        connector=connector,
        vendor=vendor,
        product=product,
        serial=serial,
        width=int(width),
        height=int(height),
        rate=rate,
    )
