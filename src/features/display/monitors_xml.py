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

import os
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
    "TRANSFORM_FOR_ROTATION",
    "MonitorMode",
    "MonitorState",
    "MonitorsXmlManager",
    "MonitorsXmlSystemStatus",
    "build_monitors_xml",
    "collect_monitors_xml_system_status",
    "find_x_session_for_user",
    "parse_get_current_state_output",
    "parse_monitor_modes",
    "parse_serial",
    "user_has_own_monitors_xml",
    "user_monitors_xml_path",
]

SYSTEM_MONITORS_XML_PATH = Path("/etc/xdg/monitors.xml")
MONITORS_XML_SIGNATURE = "<!-- vending-auto-config: monitors-xml -->"

# แปลง rotation string (ตัวเดียวกับที่ใช้ทั่วทั้งโปรเจกต์ผ่าน ROTATION_MATRICES ใน display.py)
# เป็นค่า MetaMonitorTransform ที่ mutter's ApplyMonitorsConfig D-Bus method ต้องการ — ตาม
# convention มาตรฐานของ Wayland/mutter (wl_output.transform / meta-monitor-transform.c):
# ตัวเลข 90/180/270 หมายถึงจอถูกหมุนตามเข็มนาฬิกากี่องศา — xrandr `--rotate left` (หมุน
# ทวนเข็ม 90°) จึงเทียบเท่า transform=3 (หมุนตามเข็ม 270° ให้ผลภาพเดียวกัน), `--rotate right`
# (หมุนตามเข็ม 90°) เทียบเท่า transform=1, `inverted` (180°) เทียบเท่า transform=2 ทั้งหมด
# **ยังไม่เคย proof กับ mutter เวอร์ชันจริงบนเครื่อง production** (เหมือน parser ของ
# GetCurrentState ที่เคยผิดมาก่อน) ต้องทดสอบบนเครื่องจริงก่อนพึ่งพาแบบเต็มรูปแบบ — ถ้าจอหมุน
# ผิดทิศหลัง apply resolution ให้เช็คจุดนี้ก่อน
TRANSFORM_FOR_ROTATION: "dict[str, int]" = {
    "normal": 0,
    "right": 1,
    "inverted": 2,
    "left": 3,
}


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
class MonitorMode:
    """1 mode ที่จอรองรับ (ความละเอียด + ความถี่รีเฟรชคู่หนึ่ง) — ได้มาจาก GetCurrentState
    เหมือน MonitorState แต่เก็บ mode_id ไว้ด้วยเพื่อส่งต่อให้ ApplyMonitorsConfig ระบุ mode
    ที่ต้องการเป๊ะๆ (ห้ามคำนวณ/เดา mode_id เองจาก width/height/rate เด็ดขาด ต้องใช้ค่าที่
    mutter รายงานมาเท่านั้น เพราะ mode_id ไม่ได้มี format ตายตัวเสมอไป)"""

    mode_id: str
    width: int
    height: int
    rate: str  # เก็บเป็น string เหมือน MonitorState.rate — ห้าม round
    is_current: bool
    is_preferred: bool


@dataclass(frozen=True)
class MonitorsXmlSystemStatus:
    path: Path
    exists: bool
    has_signature: bool


def _chown_path_to_user(path: Path, username: str) -> None:
    """chown ไฟล์/โฟลเดอร์ไปให้ username ที่ระบุตรงๆ — จำเป็นเพราะ VAS server รันเป็น root/
    systemd service เขียนไฟล์เข้า home ของ kiosk user โดยตรง (write_user_level) ถ้าไม่ chown
    ไฟล์จะเป็นของ root ทำให้ GNOME session ของ kiosk user เองอ่าน/เขียนทับไม่ได้ในภายหลัง
    (สำเนา private helper เดียวกับ display.py::_chown_path_to_user โดยเจตนา — โมดูลนี้ไม่ import
    ข้าม features/display/display.py เพื่อไม่ผูก private helper ข้ามไฟล์กัน)"""
    if pwd_module is None or not (hasattr(os, "geteuid") and os.geteuid() == 0):
        return
    try:
        pw = pwd_module.getpwnam(username)
        os.chown(path, pw.pw_uid, pw.pw_gid)
    except (KeyError, OSError):
        pass


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

    def _call_dbus(
        self, username: str, x_display: str, uid: int, method: str, *args: str
    ) -> "tuple[str | None, str | None]":
        """เรียก method ใดๆ ของ org.gnome.Mutter.DisplayConfig ผ่าน gdbus ในบริบท session
        ของ username — ใช้ร่วมกันทั้ง GetCurrentState (ไม่มี args) และ ApplyMonitorsConfig
        (มี args) กัน logic การประกอบคำสั่ง runuser/env/gdbus ซ้ำซ้อนกันหลายจุด

        คืน (stdout, None) ถ้าสำเร็จ, คืน (None, error_detail) ถ้าล้มเหลว
        """
        dbus_address = f"unix:path=/run/user/{uid}/bus"
        result = self.runner.run(
            [
                "runuser", "-u", username, "--",
                "env", f"DISPLAY={x_display}", f"DBUS_SESSION_BUS_ADDRESS={dbus_address}",
                "gdbus", "call", "--session",
                "--dest", "org.gnome.Mutter.DisplayConfig",
                "--object-path", "/org/gnome/Mutter/DisplayConfig",
                "--method", f"org.gnome.Mutter.DisplayConfig.{method}",
                *args,
            ],
            check=False,
        )
        if self.runner.dry_run:
            return None, None
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return None, detail or f"gdbus exit code {result.returncode} (ไม่มี stderr/stdout)"
        return result.stdout, None

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
        """
        stdout, error = self._call_dbus(username, x_display, uid, "GetCurrentState")
        if self.runner.dry_run:
            return None, None
        if stdout is None:
            return None, error
        state = parse_get_current_state_output(stdout)
        if state is None:
            return None, (
                "เรียก D-Bus สำเร็จ (gdbus exit code 0) แต่ parse ผลลัพธ์ไม่ได้ — "
                "parser นี้ยังเป็น best-effort regex ยังไม่เคย proof กับ output จริงบนเครื่องนี้ "
                f"(raw output: {stdout.strip()[:300]!r})"
            )
        return state, None

    def get_available_modes(
        self, username: str, x_display: str, uid: int
    ) -> "tuple[int | None, str | None, tuple[MonitorMode, ...], str | None]":
        """เรียก GetCurrentState เหมือน get_current_state() แต่คืนรายการ mode ที่จอรองรับ
        ทั้งหมด (ไม่ใช่แค่ mode ปัจจุบัน) พร้อม serial number — ใช้เติม dropdown Resolution/
        Refresh Rate ในหน้าเว็บ

        คืน (serial, connector, modes, None) ถ้าสำเร็จ, คืน (None, None, (), error_detail)
        ถ้าล้มเหลว — serial ต้อง query ใหม่ทุกครั้งก่อนเรียก apply_monitors_config() จริง
        (ห้าม cache serial เก่าไว้ใช้ข้ามรอบ เพราะ mutter invalidate serial ทุกครั้งที่มีการ
        เปลี่ยน config แม้เปลี่ยนจากที่อื่นก็ตาม — ApplyMonitorsConfig จะถูกปฏิเสธถ้า serial
        ไม่ตรงกับปัจจุบัน)
        """
        stdout, error = self._call_dbus(username, x_display, uid, "GetCurrentState")
        if self.runner.dry_run:
            return None, None, (), None
        if stdout is None:
            return None, None, (), error

        serial = parse_serial(stdout)
        monitor_match = re.search(
            r"'([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'",
            stdout,
        )
        if not monitor_match:
            return serial, None, (), (
                "เรียก D-Bus สำเร็จแต่ parse connector ไม่ได้ — "
                f"(raw output: {stdout.strip()[:300]!r})"
            )
        connector = monitor_match.group(1)
        modes = parse_monitor_modes(stdout)
        if not modes:
            return serial, connector, (), (
                "เรียก D-Bus สำเร็จแต่ไม่พบ mode ใดๆ ของจอเลย — "
                f"(raw output: {stdout.strip()[:300]!r})"
            )
        return serial, connector, modes, None

    def apply_monitors_config(
        self,
        username: str,
        x_display: str,
        uid: int,
        serial: int,
        connector: str,
        mode_id: str,
        rotation: str,
        method: str = "persistent",
    ) -> "str | None":
        """เรียก ApplyMonitorsConfig ของ mutter ตรงๆ เพื่อเปลี่ยนความละเอียด/ความถี่รีเฟรชจอ
        "ผ่าน GNOME/mutter จริง" แทนการยิง `xrandr --mode` ตรงๆ — เหตุผลเดียวกับที่ต้องเขียน
        monitors.xml แทน xrandr rotate ตรงๆ (ดู docstring บนสุดของไฟล์): session แบบ GNOME มี
        mutter คอยเป็นเจ้าของ authoritative state ของจอ ถ้าตั้งผ่าน xrandr ตรงๆ มีความเสี่ยงที่
        mutter จะ "เขียนทับ" กลับเป็นค่าที่ตัวเองรู้จักอีกที (เช่นตอน mutter re-probe จอ)

        method: "verify" (0, ตรวจสอบอย่างเดียวไม่ apply จริง — ใช้ debug) / "temporary"
        (1, apply ทันทีแต่หายไปตอน logout/reboot ถ้าไม่มีใคร confirm) / "persistent"
        (2, apply แล้ว mutter เขียน ~/.config/monitors.xml ของ user คนนั้นเองถาวรด้วย — ค่า
        default เพราะต้องการให้ค่าอยู่ถาวรเหมือนกดกด "Keep Changes" ใน GNOME Settings)

        rotation ถูกแปลงเป็น mutter transform ผ่าน TRANSFORM_FOR_ROTATION เพื่อไม่ให้การ apply
        ความละเอียดใหม่ไปรีเซ็ตทิศทางจอที่ตั้งไว้อยู่แล้วกลับเป็น normal โดยไม่ตั้งใจ

        คืน None ถ้าสำเร็จ, error message (str) ถ้าล้มเหลว — **ยังไม่เคย proof กับ mutter
        เวอร์ชันจริงบนเครื่อง production** (เหมือน GetCurrentState ตอนแรกที่เคยเจอบั๊ก parser
        มาก่อน — ดู docstring บนสุดของไฟล์) ต้องทดสอบบนเครื่องจริงก่อนพึ่งพาแบบเต็มรูปแบบ
        """
        method_map = {"verify": 0, "temporary": 1, "persistent": 2}
        method_value = method_map.get(method, 2)
        transform = TRANSFORM_FOR_ROTATION.get(rotation, 0)
        logical_monitors_arg = (
            f"[(0, 0, 1.0, {transform}, true, "
            f"[('{_gvariant_escape(connector)}', '{_gvariant_escape(mode_id)}', {{}})])]"
        )
        _stdout, error = self._call_dbus(
            username, x_display, uid, "ApplyMonitorsConfig",
            str(serial), str(method_value), logical_monitors_arg, "{}",
        )
        if self.runner.dry_run:
            return None
        return error

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

    def remove_user_level(self, home: Path) -> None:
        """ลบ ~/.config/monitors.xml ของ kiosk user — **เฉพาะไฟล์ที่มี MONITORS_XML_SIGNATURE
        เท่านั้น** (คือไฟล์ที่ write_user_level() เขียนไว้เอง) กันลบไฟล์จริงของ user ที่มาจาก
        การตั้งค่าที่หน้างานผ่าน GNOME Settings เอง (ไม่มี signature นี้) โดยไม่ตั้งใจตอนปิด
        toggle Persist monitors.xml จากฝั่ง VAS — ตรง pattern เดียวกับ collect_monitors_xml_
        system_status() ที่เช็ค signature ก่อนเสมอ"""
        path = user_monitors_xml_path(home)
        if self.runner.dry_run:
            print(f"remove (if VAS-signed) {path.as_posix()}")
            return
        if not path.exists():
            return
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return
        if MONITORS_XML_SIGNATURE not in content:
            return
        print(f"remove {path.as_posix()}")
        path.unlink()

    def write_user_level(self, state: MonitorState, rotation: str, home: Path, username: str) -> None:
        """เขียน ~/.config/monitors.xml ของ kiosk user ตัวเป้าหมายให้เนื้อหาตรงกับที่เขียนลง
        /etc/xdg/monitors.xml (write_system_level) — เพราะ mutter ให้ไฟล์ระดับ user ชนะ
        ระดับเครื่องเสมอ (ดู docstring บนสุดของไฟล์นี้) VAS จึงต้อง "sync" ทั้งสองที่ให้ตรงกัน
        ทุกครั้งที่ Apply/Persist ไม่งั้นถ้า kiosk user มีไฟล์ของตัวเองอยู่ก่อนแล้ว (เช่นเคยถูก
        ตั้งค่าที่หน้างานผ่าน GNOME Settings มาก่อน) ค่าที่ตั้งจาก VAS จะไม่มีผลอะไรเลย แม้จะ
        เขียนระดับเครื่องสำเร็จก็ตาม — เรียกต่อจาก write_system_level() เสมอ ไม่ใช้แทนกัน"""
        path = user_monitors_xml_path(home)
        content = build_monitors_xml(state, rotation)
        print(f"write {path.as_posix()}")
        if self.runner.dry_run:
            print(content.rstrip())
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(0o644)
        _chown_path_to_user(path, username)
        _chown_path_to_user(path.parent, username)


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

    หา monitor ตัวแรก + mode ที่มี flag 'is-current': <true> มาเป็น MonitorState

    **proof แล้วกับ output จริงบนเครื่อง production** (2026-07-11) — เดิม parser คิดว่า
    ตัวเลขทุกตัวใน mode tuple จะมี type annotation กำกับเสมอ (เช่น `uint32 800`, `double 60.0`)
    แต่ output จริงจาก `gdbus call` ไม่ print annotation ซ้ำสำหรับสมาชิกที่ type ซ้ำกันใน
    โครงสร้างซ้อน (nested tuple) เลย ได้ตัวเลขดิบๆ ล้วน เช่น
    `('800x600@60', 800, 600, 60.0, 1.0, [1.0], {'is-preferred': <true>})` — รูปแบบจริงของ
    mode entry คือ `(mode_id, width, height, rate, preferred_scale, [supported_scales],
    {properties})` regex ด้านล่างอิง shape นี้แทน ไม่พึ่ง type annotation อีกต่อไป
    """
    monitor_match = re.search(
        r"'([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'",
        output,
    )
    if not monitor_match:
        return None
    connector, vendor, product, serial = monitor_match.groups()

    modes = parse_monitor_modes(output)
    if not modes:
        return None

    selected = next((m for m in modes if m.is_current), None)
    if selected is None:
        # fallback: เอา mode แรกที่เจอแทนถ้าหา flag 'is-current' ไม่เจอเลยในทุก mode (ยังได้
        # ค่าที่พอใช้ได้ แม้ไม่การันตีว่าตรงกับ mode ที่ใช้งานอยู่จริง ณ ขณะนั้น)
        selected = modes[0]

    return MonitorState(
        connector=connector,
        vendor=vendor,
        product=product,
        serial=serial,
        width=selected.width,
        height=selected.height,
        rate=selected.rate,
    )


def parse_monitor_modes(output: str) -> "tuple[MonitorMode, ...]":
    """Parse mode entry ทั้งหมดจาก output ของ GetCurrentState — เหมือน logic เดิมใน
    parse_get_current_state_output() แต่คืนทุก mode พร้อม mode_id/is_current/is_preferred
    (ของเดิมทิ้ง mode_id และเลือกเก็บแค่ mode เดียวที่ is-current)

    mode entry: ('<mode_id>', <width>, <height>, <rate>, <preferred_scale>,
    [<supported_scales>], {<properties>}) — ตัวเลขไม่มี "uint32"/"double" กำกับใน output จริง
    (proof แล้วกับ output จริงบนเครื่อง production, 2026-07-11 — ดู docstring ของ
    parse_get_current_state_output ด้านบน)

    หมายเหตุ: ถ้ามีจอมากกว่า 1 ตัวใน output เดียวกัน mode ของทุกจอจะถูกรวมมาเป็น list เดียวกัน
    หมด (เหมือน limitation เดิมของโมดูลนี้ทั้งไฟล์ — เครื่อง vending มีจอเดียวเสมอในทางปฏิบัติ)
    """
    mode_pattern = re.compile(
        r"'([^']*)',\s*(\d+),\s*(\d+),\s*([0-9.]+),\s*[0-9.]+,\s*\[[^\]]*\],\s*\{([^}]*)\}"
    )
    modes = []
    for mode_id, width, height, rate, props in mode_pattern.findall(output):
        modes.append(
            MonitorMode(
                mode_id=mode_id,
                width=int(width),
                height=int(height),
                rate=rate,
                is_current="'is-current': <true>" in props,
                is_preferred="'is-preferred': <true>" in props,
            )
        )
    return tuple(modes)


def parse_serial(output: str) -> "int | None":
    """Parse serial number (uint32 ตัวแรกสุดของ GetCurrentState) — gdbus พิมพ์ type
    annotation ให้เสมอเพราะเป็น element แรกสุดของ tuple ระดับบนสุด (ไม่ใช่ nested element ที่
    type ซ้ำกับตัวก่อนหน้า แบบที่ mode tuple เจอปัญหา annotation หายไป) เช่น
    `(uint32 55, [...], [...], {...})` — ต้อง query ใหม่ทุกครั้งก่อนเรียก
    apply_monitors_config() จริง ห้าม cache serial เก่าไว้ใช้ข้ามรอบ (ดู docstring ของ
    MonitorsXmlManager.get_available_modes)
    """
    match = re.match(r"^\(\s*uint32\s+(\d+)\s*,", output)
    return int(match.group(1)) if match else None


def _gvariant_escape(value: str) -> str:
    """Escape string ให้ปลอดภัยสำหรับใส่ใน GVariant text-format literal ที่ส่งเป็น argument
    ของ `gdbus call` — หนีเฉพาะ backslash และ single quote (ตัวคั่น string ของ GVariant เอง)"""
    return value.replace("\\", "\\\\").replace("'", "\\'")
