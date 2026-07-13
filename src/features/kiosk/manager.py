"""
VAS — Kiosk Mode management

จัดการ 4 ส่วนที่ประกอบกันเป็น kiosk mode:

1. Linux user แยกสำหรับ kiosk (useradd/userdel) — สร้าง user ที่ไม่ใช่ user แอดมิน
   เพื่อแยกสิทธิ์ ทำเครื่องหมายว่า "สร้างโดย VAS" ผ่าน GECOS comment
2. GDM auto-login — เขียนที่ /etc/gdm3/custom.conf คีย์ AutomaticLoginEnable/
   AutomaticLogin ใน [daemon] เดียวกับที่หน้า "จอแสดงผล" ใช้คุม WaylandEnable
   (คนละคีย์ ไม่แตะกัน — ดู build_gdm_autologin_config)
3. Session type ต่อ user — เขียนที่ /var/lib/AccountsService/users/<user> คีย์
   Session=/XSession= บอก GDM ว่า login แล้วให้เข้า session ไหน (gnome หรือ openbox)
   คนละไฟล์กับ custom.conf (custom.conf คุมแค่ "login ไหม" ไฟล์นี้คุม "login แล้วเจออะไร")
4. Autostart เบราว์เซอร์ — GNOME ใช้ ~/.config/autostart/*.desktop เรียก launch script
   แยก, Openbox ใช้ ~/.config/openbox/autostart เป็น shell script ตรงๆ (ไม่รองรับ .desktop)
"""
from __future__ import annotations

import os
import re
import shlex
import socket
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from urllib.parse import urlparse

from core.runner import CommandRunner
from features.display.display import DISPLAY_READY_MARKER_NAME
from system.status import GDM_CUSTOM_CONFIG_PATH
from system.utils import dev_fake_installed

try:
    import pwd as pwd_module
except ImportError:  # pragma: no cover - Windows dev hosts
    pwd_module = None  # type: ignore[assignment]

PWD_MODULE = cast("Any | None", pwd_module)

__all__ = [
    "ACCOUNTS_SERVICE_DIR",
    "CHROME_KIOSK_FLAG_DEFS",
    "DEFAULT_AUTO_RELOAD_MINUTES",
    "DEFAULT_CHROME_FLAGS",
    "DEFAULT_DISPLAY_WAIT_SECONDS",
    "DEFAULT_EXTRA_GROUPS",
    "DEFAULT_GNOME_LOCKDOWN_FLAGS",
    "DEFAULT_KIOSK_URL",
    "DEFAULT_NETWORK_WAIT_SECONDS",
    "DEFAULT_RESTART_DELAY",
    "GNOME_LOCKDOWN_FLAG_DEFS",
    "GNOME_XSESSION_ID",
    "KIOSK_MANAGED_COMMENT",
    "OPENBOX_XSESSION_ID",
    "AccountsServiceStatus",
    "GdmAutologinStatus",
    "KioskAutostartStatus",
    "KioskLinuxUser",
    "KioskManager",
    "KioskReadiness",
    "KioskSoftwareStatus",
    "accounts_service_path_for",
    "build_accounts_service_config",
    "build_gdm_autologin_config",
    "build_gnome_autostart_desktop",
    "build_gnome_lockdown_preamble",
    "build_kiosk_launch_script",
    "build_openbox_autostart_preamble",
    "check_url_reachable",
    "collect_accounts_service_status",
    "collect_gdm_autologin_status",
    "collect_kiosk_autostart_status",
    "collect_kiosk_heartbeat_payload",
    "collect_kiosk_readiness",
    "collect_kiosk_software_status",
    "get_gdm_autologin_username",
    "kiosk_gnome_autostart_desktop_path",
    "kiosk_launch_script_path",
    "kiosk_openbox_autostart_path",
    "list_kiosk_linux_users",
    "normalize_chrome_flags",
    "normalize_gnome_lockdown_flags",
    "print_kiosk_status",
    "resolve_kiosk_target_user",
    "stop_kiosk_mode",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCOUNTS_SERVICE_DIR = Path("/var/lib/AccountsService/users")
KIOSK_MANAGED_COMMENT = "VAS Kiosk User"
DEFAULT_EXTRA_GROUPS: tuple[str, ...] = ("video", "input", "plugdev")

GNOME_XSESSION_ID = "ubuntu-xorg"
OPENBOX_XSESSION_ID = "openbox"

DEFAULT_KIOSK_URL = "http://localhost:8888"
DEFAULT_RESTART_DELAY = 2

KIOSK_SCRIPT_SIGNATURE = "# vending-auto-config: kiosk-launch"
KIOSK_DESKTOP_SIGNATURE = "# vending-auto-config: kiosk-autostart-desktop"
KIOSK_OPENBOX_PREAMBLE_SIGNATURE = "# vending-auto-config: kiosk-openbox-preamble"

# ── Openbox autostart preamble — แก้ปัญหาจอเทาทะมึน + client-side exception ──
# Openbox ไม่มี compositor/session manager คอยจัดการเหมือน GNOME เลย ทำให้ (1) ไม่มีพื้นหลัง
# ของตัวเอง เห็นสีเทาดิบของ X root window ตรงๆ เวลา chromium ยังไม่ขึ้น และ (2) chromium
# autostart ยิงทันทีไม่รอเครือข่าย/จอหมุนเสร็จก่อนเหมือน GNOME session ทำให้บางครั้งเจอ
# client-side exception ของเว็บแอป (โหลดเร็วกว่าที่เน็ตจะพร้อม) หรือจอ/ทัชไม่ตรงกันชั่วขณะ
DEFAULT_NETWORK_WAIT_SECONDS = 20
DEFAULT_DISPLAY_WAIT_SECONDS = 10
DEFAULT_AUTO_RELOAD_MINUTES = 0  # 0 = ปิด (ไม่รีโหลดเป็นระยะ)

_KIOSK_MIN_UID = 1000
_KIOSK_MAX_UID = 60000  # ไม่รวม nobody (65534)

# ── Chromium kiosk flags ที่ปิด/เปิดได้จากหน้าเว็บ ──────────────────────────
# --kiosk เองบังคับใช้เสมอ (ไม่ใช่ toggle) — รายการนี้คือ flag เสริมที่ปิดฟีเจอร์
# ของเบราว์เซอร์ที่ไม่อยากให้ user ในโหมด kiosk แตะได้ เช่น แปลภาษา, บันทึกรหัสผ่าน
# ค่า default ทุกตัว = True เพราะ kiosk mode ควรกัน "browser action" ทุกชนิดโดยปริยาย
#
# แต่ละ item มี 2 ช่องสำหรับ command-line:
#   - "flag": switch เดี่ยวๆ ที่แปะเข้า command line ตรงๆ (เช่น --no-first-run)
#   - "features": ชื่อ Chromium feature ที่ต้องปิดผ่าน --disable-features=... — เก็บแยกจาก
#     "flag" เพราะ Chromium สนใจแค่ occurrence สุดท้ายของ --disable-features บน command line
#     เดียวกัน (ไม่ merge ให้อัตโนมัติ) ถ้าแต่ละ item ยิง --disable-features ของตัวเองแยกกัน
#     ตัวที่มาทีหลังจะทับตัวก่อนหน้าเงียบๆ — build_kiosk_launch_script() จึงรวม features จาก
#     ทุก item ที่เปิดอยู่เป็น --disable-features=A,B,C ตัวเดียวตอนท้ายคำสั่งแทน
CHROME_KIOSK_FLAG_DEFS: "tuple[dict[str, object], ...]" = (
    {
        "key": "no_first_run",
        "flag": "--no-first-run",
        "features": (),
        "label": "ปิดหน้าจอเริ่มต้นใช้งานครั้งแรก (First Run)",
        "desc": "กัน Chromium ขึ้นหน้าจอ setup/welcome ตอนรันครั้งแรกหลังสร้าง profile ใหม่",
    },
    {
        "key": "disable_translate",
        "flag": "--disable-translate",
        "features": ("Translate",),
        "label": "ปิดป๊อปอัพเสนอแปลภาษา",
        "desc": (
            "ปิดฟังก์ชัน Google Translate ที่เด้งถามเวลาเจอเว็บภาษาอื่นจากภาษาเครื่อง — ใส่ทั้ง "
            "--disable-translate (switch เดิม) และ --disable-features=Translate (วิธีที่ใช้แทนใน "
            "Chromium รุ่นที่ถอด switch เดิมออกไปแล้ว, อ้างอิง Chromium issue 41347677) เพราะไม่รู้แน่ชัด"
            "ว่าเครื่องรัน Chromium เวอร์ชันไหน ใส่ไว้ทั้งคู่ไม่มีผลเสีย — ตัวที่เครื่องไม่รู้จักจะถูกมองข้ามเฉยๆ"
        ),
    },
    {
        "key": "disable_infobars",
        "flag": "--disable-infobars",
        "features": (),
        "label": "ปิดแถบแจ้งเตือนด้านบน (Infobars)",
        "desc": "ซ่อนแถบแจ้งเตือนใต้ address bar เช่น \"Chrome is being controlled by automated software\"",
    },
    {
        "key": "noerrdialogs",
        "flag": "--noerrdialogs",
        "features": (),
        "label": "ปิด dialog แจ้ง error ของ Chromium",
        "desc": "กัน dialog เช่น \"Restore pages?\" เด้งขึ้นมาหลัง chromium ปิดไม่ปกติ/crash",
    },
    {
        "key": "disable_suggestions_service",
        "flag": "--disable-suggestions-service",
        "features": (),
        "label": "ปิดบริการแนะนำคำค้นหา",
        "desc": "ปิด suggestion service ของ Chromium ที่เรียก server ภายนอกตอนพิมพ์ในช่อง address bar",
    },
    {
        "key": "disable_save_password_bubble",
        "flag": "--disable-save-password-bubble",
        "features": (),
        "label": "ปิดป๊อปอัพถามบันทึกรหัสผ่าน",
        "desc": "กัน Chromium เด้งถามว่าจะบันทึกรหัสผ่านที่กรอกในเว็บฟอร์มไหม",
    },
    {
        "key": "start_maximized",
        "flag": "--start-maximized",
        "features": (),
        "label": "เปิดหน้าต่างแบบขยายเต็มจอ",
        "desc": "สำรองไว้เผื่อ --kiosk ไม่เต็มจอเองในบางสภาพแวดล้อม (window manager บางตัว)",
    },
    {
        "key": "disable_swipe_navigation",
        "flag": "--overscroll-history-navigation=0",
        "features": ("OverscrollHistoryNavigation", "TouchpadOverscrollHistoryNavigation"),
        "label": "ปิดปัดซ้าย/ขวาเพื่อย้อนกลับ-ไปหน้าถัดไป",
        "desc": (
            "กันนิ้ว/touchpad ปัดซ้ายขวาบนจอสัมผัสแล้วเบราว์เซอร์เผลอย้อนกลับ/ไปหน้าถัดไประหว่างใช้งานเว็บแอป — "
            "ชื่อ flag ของฟีเจอร์นี้เปลี่ยนไปมาในแต่ละเวอร์ชัน Chromium จึงใส่ไว้ทั้ง switch เดิมและ "
            "--disable-features สำรอง เผื่อเวอร์ชันบนเครื่องไม่รองรับตัวใดตัวหนึ่ง"
        ),
    },
    {
        "key": "disable_pinch_zoom",
        "flag": "--disable-pinch",
        "features": (),
        "label": "ปิด pinch-to-zoom",
        "desc": "กันนิ้วบีบ/ขยายจอสัมผัสแล้ว layout ของเว็บแอปเพี้ยนไปจากที่ออกแบบไว้",
    },
)

DEFAULT_CHROME_FLAGS: "dict[str, bool]" = {cast(str, item["key"]): True for item in CHROME_KIOSK_FLAG_DEFS}


def normalize_chrome_flags(chrome_flags: "Mapping[str, object] | None") -> "dict[str, bool]":
    """รวมค่าที่ส่งมา (เช่นจาก JSON payload) เข้ากับ default — คีย์ที่ไม่รู้จักถูกทิ้ง
    คีย์ที่ไม่ได้ส่งมาใช้ค่า default (True) เพื่อไม่ให้ payload เก่า/บางส่วนไปปิด flag อื่นโดยไม่ตั้งใจ

    รับ Mapping (ไม่ใช่ dict ตรงๆ) เพราะพารามิเตอร์นี้มักถูกเรียกด้วยค่าที่ type แคบกว่า เช่น
    dict[str, bool] จาก build_kiosk_launch_script() — dict ไม่ covariant ใน value type ทำให้
    mypy strict มองว่า dict[str, bool] ไม่ใช่ subtype ของ dict[str, object] แต่ Mapping เป็น
    covariant จึงรับได้ถูกต้องโดยไม่ต้อง cast ที่ทุก call site"""
    result = dict(DEFAULT_CHROME_FLAGS)
    if chrome_flags:
        valid_keys = {item["key"] for item in CHROME_KIOSK_FLAG_DEFS}
        for key, value in chrome_flags.items():
            if key in valid_keys:
                result[key] = bool(value)
    return result


# ── GNOME lockdown (gsettings) — ปิดทางหลุดออกจาก kiosk ที่มากับ GNOME Shell ────────
# ใช้ได้เฉพาะ session_type == "gnome" เท่านั้น (Openbox ไม่มี GNOME Shell ให้ตั้งค่าพวกนี้
# อยู่แล้วโดยธรรมชาติ — ดู build_openbox_autostart_preamble ด้านบนสำหรับ Openbox)
# รันเป็นคำสั่ง gsettings ใน preamble ของ kiosk-launch.sh (รันตอน user login เข้า GNOME
# session จริง มี D-Bus/X session ให้ gsettings เขียนค่าได้) แทนที่จะเรียกจาก VAS server
# ตรงๆ เพราะ VAS server รันเป็น root แบบไม่ผูกกับ session กราฟิกของใคร — เรียก gsettings
# จาก root โดยไม่มี DBUS_SESSION_BUS_ADDRESS/DISPLAY ของ user เป้าหมายจะ fail เงียบๆ
GNOME_LOCKDOWN_SIGNATURE = "# vending-auto-config: kiosk-gnome-lockdown"

GNOME_LOCKDOWN_FLAG_DEFS: "tuple[dict[str, str], ...]" = (
    {
        "key": "disable_hot_corner",
        "command": "gsettings set org.gnome.desktop.interface enable-hot-corners false",
        "label": "ปิด Hot Corner (มุมจอเปิด Activities Overview)",
        "desc": "กันนิ้ว/เมาส์แตะมุมจอแล้วหลุดจาก kiosk ไปหน้า Activities Overview ของ GNOME Shell",
    },
    {
        "key": "disable_terminal_shortcut",
        "command": 'gsettings set org.gnome.settings-daemon.plugins.media-keys terminal "[]"',
        "label": "ปิดคีย์ลัดเปิด Terminal (Ctrl+Alt+T)",
        "desc": "ถอดคีย์ลัดเปิด terminal เริ่มต้นของ Ubuntu กันเผลอกดหลุดออกจาก kiosk ถ้ามีคีย์บอร์ดต่ออยู่",
    },
    {
        "key": "disable_super_key",
        "command": "gsettings set org.gnome.mutter overlay-key ''",
        "label": "ปิดปุ่ม Super (เปิด Activities Overview)",
        "desc": "กันปุ่ม Super บนคีย์บอร์ดเปิดหน้า Activities Overview หลุดออกจาก kiosk",
    },
    {
        "key": "disable_ubuntu_dock",
        "command": "gnome-extensions disable ubuntu-dock@ubuntu.com",
        "label": "ปิด Ubuntu Dock (กันปัดขอบจอซ้ายโผล่ dock)",
        "desc": (
            "ปิด extension ubuntu-dock (dash-to-dock) ไม่ให้โผล่ตอนปัดนิ้ว/เมาส์ชนขอบจอซ้าย "
            "กันการกดไอคอนใน dock (เช่น Settings/Files) หลุดออกจาก kiosk — ยืนยัน UUID จริง "
            "บนเครื่อง hapymed-sterile-00 แล้วผ่าน `ls /usr/share/gnome-shell/extensions/`"
        ),
    },
)

DEFAULT_GNOME_LOCKDOWN_FLAGS: "dict[str, bool]" = {item["key"]: True for item in GNOME_LOCKDOWN_FLAG_DEFS}


def normalize_gnome_lockdown_flags(flags: "Mapping[str, object] | None") -> "dict[str, bool]":
    """เหมือน normalize_chrome_flags() แต่สำหรับชุด gsettings lockdown ของ GNOME —
    คีย์ที่ไม่รู้จักถูกทิ้ง คีย์ที่ไม่ได้ส่งมาใช้ default (True) — ใช้ Mapping ด้วยเหตุผลเดียวกับ
    normalize_chrome_flags() (ดูคอมเมนต์ที่นั่น)"""
    result = dict(DEFAULT_GNOME_LOCKDOWN_FLAGS)
    if flags:
        valid_keys = {item["key"] for item in GNOME_LOCKDOWN_FLAG_DEFS}
        for key, value in flags.items():
            if key in valid_keys:
                result[key] = bool(value)
    return result


def build_gnome_lockdown_preamble(gnome_lockdown_flags: "dict[str, bool] | None" = None) -> str:
    """สร้าง preamble ที่รัน gsettings ปิดทางหลุดออกจาก kiosk ของ GNOME Shell (hot corner,
    คีย์ลัด terminal, ปุ่ม Super) — แทรกก่อนเปิด chromium ใน kiosk-launch.sh เฉพาะตอน
    session_type == "gnome" เท่านั้น (ดู KioskManager.write_autostart)"""
    flags = normalize_gnome_lockdown_flags(gnome_lockdown_flags)
    lines = [GNOME_LOCKDOWN_SIGNATURE, "# Managed by VAS. Manual edits may be overwritten."]
    for item in GNOME_LOCKDOWN_FLAG_DEFS:
        if flags.get(item["key"], False):
            lines.append(f"{item['command']} 2>/dev/null || true")
    return "\n".join(lines) + "\n"


def _parse_gnome_lockdown_flags(content: str) -> "dict[str, bool]":
    """หา gsettings command ที่มีอยู่จริงใน preamble ของสคริปต์ — ใช้ตอนอ่านสถานะ toggle
    กลับมาแสดงในหน้าเว็บ คล้าย _parse_kiosk_flags() ด้านล่างสำหรับ Chrome flags"""
    return {item["key"]: (item["command"] in content) for item in GNOME_LOCKDOWN_FLAG_DEFS}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KioskLinuxUser:
    username: str
    uid: int
    home: Path
    managed_by_vas: bool
    is_autologin: bool


@dataclass(frozen=True)
class GdmAutologinStatus:
    path: Path
    exists: bool
    enabled: bool
    username: "str | None"


@dataclass(frozen=True)
class AccountsServiceStatus:
    path: Path
    exists: bool
    session_type: str  # "gnome" | "openbox"


@dataclass(frozen=True)
class KioskAutostartStatus:
    session_type: str
    home: Path
    url: str
    restart_enabled: bool
    restart_delay: int
    configured: bool
    chrome_flags: "dict[str, bool]"
    auto_reload_minutes: int = DEFAULT_AUTO_RELOAD_MINUTES
    # เฉพาะ session_type == "gnome" เท่านั้นที่มีความหมายจริง (ดู GNOME_LOCKDOWN_FLAG_DEFS) —
    # Openbox ไม่มี GNOME Shell ให้ตั้งค่าพวกนี้ จึงคงค่า default ไว้เฉยๆ ไม่ถูกอ่าน/เขียนจริง
    gnome_lockdown_flags: "dict[str, bool]" = field(default_factory=lambda: dict(DEFAULT_GNOME_LOCKDOWN_FLAGS))


@dataclass(frozen=True)
class KioskSoftwareStatus:
    openbox_installed: bool
    chromium_installed: bool


@dataclass(frozen=True)
class KioskReadiness:
    software_ok: bool
    user_ok: bool
    autologin_ok: bool
    autostart_ok: bool


# ---------------------------------------------------------------------------
# Manager — write actions (ต้องรันเป็น root บนเครื่องจริง)
# ---------------------------------------------------------------------------

class KioskManager:
    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def create_user(self, username: str, extra_groups: Sequence[str] = DEFAULT_EXTRA_GROUPS) -> None:
        self.runner.run(["useradd", "-m", "-c", KIOSK_MANAGED_COMMENT, "-s", "/bin/bash", username])
        if extra_groups:
            self.runner.run(["usermod", "-aG", ",".join(extra_groups), username])

    def delete_user(self, username: str) -> None:
        self.runner.run(["userdel", "-r", username])

    def set_autologin(
        self,
        username: "str | None",
        enabled: bool,
        path: Path = GDM_CUSTOM_CONFIG_PATH,
    ) -> None:
        existing_content = path.read_text(encoding="utf-8") if path.exists() else ""
        content = build_gdm_autologin_config(existing_content, username or "", enabled)
        print(f"write {path.as_posix()}")
        if self.runner.dry_run:
            print(content.rstrip())
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def set_session_type(self, username: str, session_type: str) -> None:
        path = accounts_service_path_for(username)
        existing_content = path.read_text(encoding="utf-8") if path.exists() else ""
        content = build_accounts_service_config(existing_content, session_type)
        print(f"write {path.as_posix()}")
        if self.runner.dry_run:
            print(content.rstrip())
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        _chown_to_user(path, username)

    def write_autostart(
        self,
        session_type: str,
        home: Path,
        username: str,
        url: str,
        restart_enabled: bool,
        restart_delay: int,
        chrome_flags: "dict[str, bool] | None" = None,
        auto_reload_minutes: int = DEFAULT_AUTO_RELOAD_MINUTES,
        gnome_lockdown_flags: "dict[str, bool] | None" = None,
    ) -> None:
        script_content = build_kiosk_launch_script(
            url, restart_enabled, restart_delay, chrome_flags, auto_reload_minutes,
        )

        if session_type == "openbox":
            preamble = build_openbox_autostart_preamble(url, home)
            script_path = kiosk_openbox_autostart_path(home)
            self._write_executable(script_path, _insert_after_shebang(script_content, preamble))
            _chown_to_user(script_path, username)
            _chown_to_user(script_path.parent, username)
            return

        # GNOME session เท่านั้นที่มี GNOME Shell ให้ gsettings lockdown ทำงาน — แทรก preamble
        # เข้าไปหลัง shebang เหมือน Openbox preamble ด้านบน (รูปแบบเดียวกัน) เพื่อให้ gsettings
        # รันก่อนเปิด chromium ทุกครั้งที่ script นี้ถูกเรียก (ทั้งตอน login ครั้งแรก และตอน
        # restart loop วนกลับมา — เขียนซ้ำไม่มีผลเสียเพราะเป็นแค่ gsettings set ค่าเดิม)
        gnome_preamble = build_gnome_lockdown_preamble(gnome_lockdown_flags)
        script_path = kiosk_launch_script_path(home)
        self._write_executable(script_path, _insert_after_shebang(script_content, gnome_preamble))
        _chown_to_user(script_path, username)
        _chown_to_user(script_path.parent, username)

        desktop_path = kiosk_gnome_autostart_desktop_path(home)
        desktop_content = build_gnome_autostart_desktop(script_path)
        self._write_file(desktop_path, desktop_content)
        _chown_to_user(desktop_path, username)
        _chown_to_user(desktop_path.parent, username)

    def _write_executable(self, path: Path, content: str) -> None:
        print(f"write {path.as_posix()}")
        if self.runner.dry_run:
            print(content.rstrip())
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

    def _write_file(self, path: Path, content: str) -> None:
        print(f"write {path.as_posix()}")
        if self.runner.dry_run:
            print(content.rstrip())
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def remove_autostart(self, home: Path) -> None:
        """ลบไฟล์ autostart ที่ VAS อาจเคยเขียนไว้ทั้งหมด — ทั้ง GNOME (.desktop+script)
        และ Openbox (autostart script) โดยไม่สนใจ session_type ปัจจุบัน เพื่อให้ผลลัพธ์
        เป็น 'หยุดจริง' ไม่ว่าก่อนหน้านี้จะเคยตั้งค่าไว้แบบไหน"""
        for path in (
            kiosk_openbox_autostart_path(home),
            kiosk_gnome_autostart_desktop_path(home),
            kiosk_launch_script_path(home),
        ):
            self._remove_file(path)

    def _remove_file(self, path: Path) -> None:
        print(f"remove {path.as_posix()}")
        if self.runner.dry_run:
            return
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _insert_after_shebang(script_content: str, extra: str) -> str:
    """แทรก extra (เช่น openbox preamble) เข้าไปหลัง shebang line แรกของสคริปต์เสมอ — ต้อง
    รักษา '#!/usr/bin/env bash' ให้เป็นบรรทัดแรกสุดของไฟล์ ไม่งั้น exec ตรงๆ (เช่น
    Openbox เรียก ./autostart แบบ executable) จะหา interpreter ไม่เจอ"""
    if script_content.startswith("#!"):
        first_newline = script_content.index("\n") + 1
        return script_content[:first_newline] + extra + "\n" + script_content[first_newline:]
    return extra + "\n" + script_content


def _chown_to_user(path: Path, username: str) -> None:
    """chown ไฟล์/โฟลเดอร์ให้ user ที่กำหนด — เงียบถ้าไม่ใช่ root หรือหา user ไม่เจอ"""
    if not (hasattr(os, "geteuid") and os.geteuid() == 0):
        return
    if PWD_MODULE is None:
        return
    try:
        pw = PWD_MODULE.getpwnam(username)
        os.chown(path, pw.pw_uid, pw.pw_gid)
    except (KeyError, OSError):
        pass


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def accounts_service_path_for(username: str) -> Path:
    return ACCOUNTS_SERVICE_DIR / username


def kiosk_openbox_autostart_path(home: Path) -> Path:
    return home / ".config" / "openbox" / "autostart"


def kiosk_gnome_autostart_desktop_path(home: Path) -> Path:
    return home / ".config" / "autostart" / "vas-kiosk.desktop"


def kiosk_launch_script_path(home: Path) -> Path:
    return home / ".config" / "vending-auto-setup" / "kiosk-launch.sh"


# ---------------------------------------------------------------------------
# Pure builders (ini/script content — ไม่มี I/O)
# ---------------------------------------------------------------------------

def _find_section_bounds(lines: list[str], section_name: str) -> "tuple[int | None, int]":
    normalized_section = section_name.lower()
    start: "int | None" = None
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not (line.startswith("[") and line.endswith("]")):
            continue
        current_section = line[1:-1].strip().lower()
        if start is None:
            if current_section == normalized_section:
                start = index
            continue
        return start, index
    return start, len(lines)


def _ini_key_name(line: str) -> "str | None":
    stripped = line.strip()
    if stripped.startswith(("#", ";")):
        stripped = stripped.lstrip("#;").strip()
    if not stripped or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip().lower()


def _read_ini_key_in_section(content: str, section: str, key: str) -> "str | None":
    lines = content.splitlines()
    start, end = _find_section_bounds(lines, section)
    if start is None:
        return None
    normalized_key = key.lower()
    result: "str | None" = None
    for raw_line in lines[start + 1 : end]:
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        found_key, value = line.split("=", 1)
        if found_key.strip().lower() == normalized_key:
            result = value.strip()
    return result


def build_gdm_autologin_config(existing_content: str, username: str, enabled: bool) -> str:
    """เขียนคีย์ AutomaticLoginEnable/AutomaticLogin ใน [daemon] — ไม่แตะ WaylandEnable
    หรือคีย์อื่นที่มีอยู่แล้ว (ไฟล์นี้ใช้ร่วมกับหน้า จอแสดงผล)"""
    lines = existing_content.splitlines()
    if not lines:
        lines = ["[daemon]"]

    daemon_start, daemon_end = _find_section_bounds(lines, "daemon")
    if daemon_start is None:
        separator = [] if not lines or lines[-1].strip() == "" else [""]
        lines = [*lines, *separator, "[daemon]"]
        daemon_start, daemon_end = _find_section_bounds(lines, "daemon")

    assert daemon_start is not None
    daemon_body = lines[daemon_start + 1 : daemon_end]
    remove_keys = {"automaticloginenable", "automaticlogin"}
    filtered_body = [line for line in daemon_body if _ini_key_name(line) not in remove_keys]
    if enabled and username:
        filtered_body = [*filtered_body, "AutomaticLoginEnable=true", f"AutomaticLogin={username}"]

    new_lines = [*lines[: daemon_start + 1], *filtered_body, *lines[daemon_end:]]
    return "\n".join(new_lines) + "\n"


def build_accounts_service_config(existing_content: str, session_type: str) -> str:
    """เขียนคีย์ Session=/XSession= ใน [User] — คนละไฟล์กับ custom.conf ด้านบน"""
    session_id = OPENBOX_XSESSION_ID if session_type == "openbox" else GNOME_XSESSION_ID
    lines = existing_content.splitlines()
    if not lines:
        return f"[User]\nSession={session_id}\nXSession={session_id}\nSystemAccount=false\n"

    user_start, user_end = _find_section_bounds(lines, "user")
    if user_start is None:
        separator = [] if not lines or lines[-1].strip() == "" else [""]
        block = ["[User]", f"Session={session_id}", f"XSession={session_id}", "SystemAccount=false"]
        return "\n".join([*lines, *separator, *block]) + "\n"

    body = lines[user_start + 1 : user_end]
    remove_keys = {"session", "xsession"}
    filtered = [line for line in body if _ini_key_name(line) not in remove_keys]
    filtered = [*filtered, f"Session={session_id}", f"XSession={session_id}"]
    new_lines = [*lines[: user_start + 1], *filtered, *lines[user_end:]]
    return "\n".join(new_lines) + "\n"


def build_openbox_autostart_preamble(
    url: str,
    home: Path,
    network_wait_seconds: int = DEFAULT_NETWORK_WAIT_SECONDS,
    display_wait_seconds: int = DEFAULT_DISPLAY_WAIT_SECONDS,
) -> str:
    """Preamble ที่ใส่ไว้ก่อนเปิด chromium เฉพาะ session แบบ Openbox เท่านั้น (GNOME ไม่ต้อง
    เพราะ gnome-session/mutter จัดการเรื่องพวกนี้ให้อยู่แล้ว) แก้ 3 อาการที่พบกับ Openbox:

    1. `xsetroot -solid` — Openbox ไม่ paint พื้นหลังของตัวเองเลย ถ้าไม่ตั้งไว้จะเห็นสีเทาดิบ
       ของ X root window ตอน chromium ยังไม่ขึ้นจอ/กำลังรอ restart
    2. รอไฟล์ marker ที่ display-session.sh (features/display/display.py) touch ไว้หลังหมุน
       จอ+ปรับ touch สำเร็จ — กัน chromium เปิด fullscreen ไปก่อนจอจะหมุนเสร็จ (ไม่มี
       session manager คอยรอเหมือน GNOME) มี timeout กันค้างถ้า marker ไม่มาเลย
    3. รอ DNS/เครือข่ายพร้อมก่อน (เช็คว่า resolve hostname ของ URL ที่จะเปิดได้ไหม) — กัน
       เว็บแอปฝั่ง client เจอ error เพราะ chromium โหลดเร็วกว่าที่เน็ตจะพร้อมตอน boot
    """
    marker_path = (home / ".config" / "vending-auto-setup" / DISPLAY_READY_MARKER_NAME).as_posix()
    hostname = urlparse(url).hostname or ""

    network_wait_block = ""
    if hostname:
        network_wait_block = (
            f"# รอ DNS/เครือข่ายพร้อมก่อนเปิดเบราว์เซอร์ (โฮสต์: {hostname}) สูงสุด "
            f"{network_wait_seconds} วิ\n"
            f"for _i in $(seq 1 {network_wait_seconds}); do\n"
            f"  getent hosts {shlex.quote(hostname)} >/dev/null 2>&1 && break\n"
            "  sleep 1\n"
            "done\n"
        )

    return (
        f"{KIOSK_OPENBOX_PREAMBLE_SIGNATURE}\n"
        "# Managed by VAS. Manual edits may be overwritten.\n"
        'xsetroot -solid "#000000" 2>/dev/null || true\n'
        "\n"
        f"# รอไฟล์ marker ที่ display-session.sh เขียนตอนหมุนจอเสร็จ (ถ้ามี) สูงสุด "
        f"{display_wait_seconds} วิ\n"
        f"for _i in $(seq 1 {display_wait_seconds}); do\n"
        f"  [ -f {shlex.quote(marker_path)} ] && break\n"
        "  sleep 1\n"
        "done\n"
        "\n"
        f"{network_wait_block}"
    )


def build_kiosk_launch_script(
    url: str,
    restart_enabled: bool,
    restart_delay: int,
    chrome_flags: "dict[str, bool] | None" = None,
    auto_reload_minutes: int = DEFAULT_AUTO_RELOAD_MINUTES,
) -> str:
    flags = normalize_chrome_flags(chrome_flags)
    enabled_defs = [item for item in CHROME_KIOSK_FLAG_DEFS if flags.get(cast(str, item["key"]), False)]
    flag_tokens = ["--kiosk"] + [cast(str, item["flag"]) for item in enabled_defs]
    # รวม "features" ของทุก item ที่เปิดอยู่เป็น --disable-features=A,B,C ตัวเดียวตอนท้าย —
    # ห้ามให้แต่ละ item ยิง --disable-features ของตัวเองแยกกันหลายครั้ง เพราะ Chromium ใช้แค่
    # occurrence สุดท้ายของ switch ซ้ำบน command line เดียวกัน (ดูคอมเมนต์ที่ CHROME_KIOSK_FLAG_DEFS)
    feature_names = [name for item in enabled_defs for name in cast("Sequence[str]", item["features"])]
    if feature_names:
        flag_tokens.append("--disable-features=" + ",".join(feature_names))
    command = "chromium " + " ".join(flag_tokens) + " " + shlex.quote(url)
    # auto_reload_minutes: ปิด chromium เองเป็นระยะแม้ไม่ crash จริง ให้ restart loop ด้านล่าง
    # เปิดใหม่ให้ — เป็นตาข่ายรองสุดท้ายกันเคส client-side exception ที่ไม่ทำให้ chromium
    # process ตาย (restart_enabled เดิมช่วยไม่ได้เพราะ process ยังรันอยู่ปกติ) มีผลเฉพาะตอน
    # restart_enabled เปิดอยู่เท่านั้น — ถ้าปิด restart ไว้ การ kill โดยไม่มีอะไรมาเปิดใหม่ให้
    # จะยิ่งแย่กว่าเดิม จึงไม่ wrap ให้
    if restart_enabled and auto_reload_minutes > 0:
        command = f"timeout {int(auto_reload_minutes) * 60}s {command}"

    # เครื่องบางเครื่อง binary ชื่อ chromium-browser (apt) ไม่ใช่ chromium (snap) —
    # collect_kiosk_software_status() ยอมรับทั้งคู่เป็น "ติดตั้งแล้ว" แต่ก่อนหน้านี้สคริปต์
    # hardcode เรียก "chromium" ตรงๆ เสมอ ถ้าเครื่องมีแค่ chromium-browser คำสั่งจะ fail
    # แบบเงียบๆ ทุกครั้ง (ไม่มี error โผล่ที่จอเลย เพราะ Openbox ไม่มี UI ให้เห็น dialog ใดๆ)
    # แก้โดย define shell function ชื่อ chromium ให้ forward ไป chromium-browser ถ้า chromium
    # ตัวจริงไม่มีใน PATH — ไม่แตะ "command" ด้านบนเลย เพื่อไม่ให้กระทบ regex parser ด้านล่าง
    # (_parse_kiosk_script / _parse_kiosk_flags) ที่ต้องอ่านค่ากลับมาแสดงในหน้าเว็บ
    preamble = (
        "LOG_FILE=\"$HOME/.config/vending-auto-setup/kiosk-launch.log\"\n"
        "mkdir -p \"$(dirname \"$LOG_FILE\")\"\n"
        "if ! command -v chromium >/dev/null 2>&1 && command -v chromium-browser >/dev/null 2>&1; then\n"
        "  chromium() { chromium-browser \"$@\"; }\n"
        "fi\n"
        "if ! command -v chromium >/dev/null 2>&1; then\n"
        "  echo \"$(date -Iseconds) ERROR: ไม่พบคำสั่ง chromium หรือ chromium-browser ใน PATH\" >> \"$LOG_FILE\"\n"
        "fi\n"
    )

    if restart_enabled:
        body = (
            "while true; do\n"
            "  echo \"$(date -Iseconds) เปิด chromium (kiosk mode)\" >> \"$LOG_FILE\"\n"
            f"  {command}\n"
            "  echo \"$(date -Iseconds) chromium ออกแล้ว (exit code $?) — จะเปิดใหม่ใน "
            f"{max(0, restart_delay)} วิ\" >> \"$LOG_FILE\"\n"
            f"  sleep {max(0, restart_delay)}\n"
            "done\n"
        )
    else:
        body = (
            "echo \"$(date -Iseconds) เปิด chromium (kiosk mode, restart ปิดอยู่)\" >> \"$LOG_FILE\"\n"
            f"{command}\n"
            "echo \"$(date -Iseconds) chromium ออกแล้ว (exit code $?) — restart ปิดอยู่ ไม่เปิดใหม่ให้\" >> \"$LOG_FILE\"\n"
        )

    return (
        "#!/usr/bin/env bash\n"
        f"{KIOSK_SCRIPT_SIGNATURE}\n"
        "# Managed by VAS. Manual edits may be overwritten.\n"
        f"{preamble}"
        f"{body}"
    )


def build_gnome_autostart_desktop(script_path: Path) -> str:
    return (
        f"{KIOSK_DESKTOP_SIGNATURE}\n"
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=VAS Kiosk\n"
        f"Exec={shlex.quote(script_path.as_posix())}\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def _parse_kiosk_script(content: str) -> "tuple[str, bool, int, dict[str, bool], int]":
    # ตัด Openbox preamble (build_openbox_autostart_preamble) ออกก่อนเสมอถ้ามี — preamble มี
    # for-loop รอ marker/เครือข่ายที่มีบรรทัด "sleep 1" ของตัวเอง ถ้าไม่ตัดออกก่อน regex ด้านล่าง
    # (โดยเฉพาะ delay_match) อาจไปจับ "sleep 1" ของ preamble แทนที่จะเป็น restart delay จริง
    sig_index = content.find(KIOSK_SCRIPT_SIGNATURE)
    if sig_index != -1:
        content = content[sig_index:]

    restart_enabled = bool(re.search(r"^\s*while\s+true\s*;\s*do", content, re.MULTILINE))
    # ใช้ "--kiosk" เป็นจุดยึดแทน "chromium" ตรงๆ เพราะ preamble ของ build_kiosk_launch_script()
    # มีหลายบรรทัดที่ขึ้นต้นด้วยคำว่า chromium เช่นกัน (shell function fallback, log lines) —
    # "--kiosk" การันตีว่ามีแค่บรรทัดคำสั่งจริงบรรทัดเดียวเท่านั้นที่มี (บังคับใช้เสมอ ดู CHROME_KIOSK_FLAG_DEFS ด้านบน)
    url_match = re.search(r"--kiosk[^\n]*?(https?://\S+)", content)
    url = url_match.group(1) if url_match else DEFAULT_KIOSK_URL
    delay_match = re.search(r"sleep\s+(\d+)", content)
    delay = int(delay_match.group(1)) if delay_match else DEFAULT_RESTART_DELAY
    chrome_flags = _parse_kiosk_flags(content)
    # auto_reload_minutes: อ่านกลับจาก "timeout <seconds>s chromium --kiosk ..." ที่บรรทัดเดียวกับ
    # --kiosk (ดู build_kiosk_launch_script) — หาไม่เจอ = ปิดอยู่ (ค่า default)
    reload_match = re.search(r"timeout\s+(\d+)s\s+chromium[^\n]*--kiosk", content)
    auto_reload_minutes = int(reload_match.group(1)) // 60 if reload_match else DEFAULT_AUTO_RELOAD_MINUTES
    return url, restart_enabled, delay, chrome_flags, auto_reload_minutes


def _parse_kiosk_flags(content: str) -> "dict[str, bool]":
    """หา flag ที่มีอยู่จริงในบรรทัดคำสั่ง chromium ของ script — ใช้ตอนอ่านสถานะ toggle
    กลับมาแสดงในหน้าเว็บ ให้ตรงกับสิ่งที่เขียนไว้บนดิสก์จริง ไม่ใช่ default เสมอ
    หาโดยยึด "--kiosk" ไม่ใช่คำว่า "chromium" ที่ขึ้นต้นบรรทัด เพราะ preamble ของ
    build_kiosk_launch_script() มีบรรทัด shell function/log ที่ขึ้นต้นด้วย "chromium" เหมือนกัน"""
    chromium_line_match = re.search(r"^.*--kiosk.*$", content, re.MULTILINE)
    chromium_line = chromium_line_match.group(0) if chromium_line_match else ""
    return {
        cast(str, item["key"]): (cast(str, item["flag"]) in chromium_line)
        for item in CHROME_KIOSK_FLAG_DEFS
    }


# ---------------------------------------------------------------------------
# Status collectors (read-only)
# ---------------------------------------------------------------------------

def get_gdm_autologin_username(path: Path = GDM_CUSTOM_CONFIG_PATH) -> "str | None":
    if not _path_exists(path):
        return None
    content = _read_or_none(path)
    if content is None:
        return None
    enabled_value = _read_ini_key_in_section(content, "daemon", "AutomaticLoginEnable")
    if (enabled_value or "").strip().lower() != "true":
        return None
    username = _read_ini_key_in_section(content, "daemon", "AutomaticLogin")
    return username.strip() if username else None


def collect_gdm_autologin_status(path: Path = GDM_CUSTOM_CONFIG_PATH) -> GdmAutologinStatus:
    if dev_fake_installed():
        return GdmAutologinStatus(path=path, exists=True, enabled=True, username="kiosk-user")

    if not _path_exists(path):
        return GdmAutologinStatus(path=path, exists=False, enabled=False, username=None)

    content = _read_or_none(path)
    if content is None:
        return GdmAutologinStatus(path=path, exists=True, enabled=False, username=None)

    enabled_value = _read_ini_key_in_section(content, "daemon", "AutomaticLoginEnable")
    enabled = (enabled_value or "").strip().lower() == "true"
    username = _read_ini_key_in_section(content, "daemon", "AutomaticLogin") if enabled else None
    return GdmAutologinStatus(path=path, exists=True, enabled=enabled, username=username)


def collect_accounts_service_status(username: str) -> AccountsServiceStatus:
    path = accounts_service_path_for(username)
    if dev_fake_installed():
        return AccountsServiceStatus(path=path, exists=True, session_type="gnome")

    if not _path_exists(path):
        return AccountsServiceStatus(path=path, exists=False, session_type="gnome")

    content = _read_or_none(path)
    if content is None:
        return AccountsServiceStatus(path=path, exists=True, session_type="gnome")

    xsession = _read_ini_key_in_section(content, "User", "XSession")
    session_type = "openbox" if (xsession or "").strip().lower() == OPENBOX_XSESSION_ID else "gnome"
    return AccountsServiceStatus(path=path, exists=True, session_type=session_type)


def list_kiosk_linux_users() -> "tuple[KioskLinuxUser, ...]":
    if dev_fake_installed():
        return (
            KioskLinuxUser(
                username="kiosk-user", uid=1001, home=Path("/home/kiosk-user"),
                managed_by_vas=True, is_autologin=True,
            ),
            KioskLinuxUser(
                username="vending-admin", uid=1000, home=Path("/home/vending-admin"),
                managed_by_vas=False, is_autologin=False,
            ),
        )

    if PWD_MODULE is None:
        return ()

    autologin_username = get_gdm_autologin_username()
    users: list[KioskLinuxUser] = []
    for entry in PWD_MODULE.getpwall():
        if not (_KIOSK_MIN_UID <= entry.pw_uid < _KIOSK_MAX_UID):
            continue
        managed = entry.pw_gecos.strip().split(",")[0].strip() == KIOSK_MANAGED_COMMENT
        users.append(
            KioskLinuxUser(
                username=entry.pw_name,
                uid=entry.pw_uid,
                home=Path(entry.pw_dir),
                managed_by_vas=managed,
                is_autologin=(entry.pw_name == autologin_username),
            )
        )
    return tuple(sorted(users, key=lambda u: (not u.is_autologin, u.username)))


def resolve_kiosk_target_user(users: "tuple[KioskLinuxUser, ...]") -> "KioskLinuxUser | None":
    """หา user ที่หน้า Kiosk ควรใช้เป็น 'target' สำหรับอ่าน/plan session type, autostart
    path และ config file — เดิมโค้ดฝั่งเว็บผูกกับ is_autologin ตรงๆ ทำให้พอปิด auto-login
    (หรือยังไม่เคยเปิดเลย) หน้าเว็บจะมองไม่เห็น user และ fallback ไปที่ home/session
    ปลอมๆ ('/home/kiosk-user', 'gnome') ทั้งที่จริงมี user + ค่าที่เคยตั้งไว้อยู่แล้ว
    บนดิสก์ — ลำดับความสำคัญ: user ที่ auto-login อยู่ปัจจุบัน > user ที่ VAS สร้างให้
    (managed_by_vas) > user แรกสุดในลิสต์ > ไม่มี user เลย"""
    autologin_user = next((u for u in users if u.is_autologin), None)
    if autologin_user is not None:
        return autologin_user
    managed_user = next((u for u in users if u.managed_by_vas), None)
    if managed_user is not None:
        return managed_user
    return users[0] if users else None


def collect_kiosk_heartbeat_payload() -> dict[str, object]:
    """สรุปสถานะ kiosk ปัจจุบันเป็น flat dict สำหรับส่งเป็น MQTT heartbeat payload —
    เขียนแยกจาก server._kiosk_page_context() เพราะตัวนั้นผูกกับ Flask request context
    (เรียก url_for) ส่วนอันนี้ต้องเรียกได้จาก background thread ที่ไม่มี request context ให้ใช้"""
    users = list_kiosk_linux_users()
    autologin = collect_gdm_autologin_status()
    software = collect_kiosk_software_status()
    target_user = resolve_kiosk_target_user(users)

    session_type = "gnome"
    if target_user is not None:
        session_type = collect_accounts_service_status(target_user.username).session_type
    home = target_user.home if target_user is not None else Path("/home/kiosk-user")

    autostart = collect_kiosk_autostart_status(session_type, home)
    readiness = collect_kiosk_readiness(users, autologin, autostart, software)

    try:
        hostname = socket.gethostname()
    except OSError:
        hostname = "unknown"

    return {
        "hostname": hostname,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kiosk_user": target_user.username if target_user is not None else None,
        "session_type": session_type,
        "autologin_enabled": autologin.enabled,
        "autostart_url": autostart.url if autostart.configured else None,
        "readiness": {
            "software_ok": readiness.software_ok,
            "user_ok": readiness.user_ok,
            "autologin_ok": readiness.autologin_ok,
            "autostart_ok": readiness.autostart_ok,
        },
    }


def collect_kiosk_autostart_status(session_type: str, home: Path) -> KioskAutostartStatus:
    if dev_fake_installed():
        return KioskAutostartStatus(
            session_type=session_type, home=home,
            url=DEFAULT_KIOSK_URL, restart_enabled=True, restart_delay=DEFAULT_RESTART_DELAY,
            configured=True, chrome_flags=dict(DEFAULT_CHROME_FLAGS),
            gnome_lockdown_flags=dict(DEFAULT_GNOME_LOCKDOWN_FLAGS),
        )

    if session_type == "openbox":
        script_path = kiosk_openbox_autostart_path(home)
        script_content = _read_or_none(script_path)
        configured = (
            script_content is not None
            and KIOSK_SCRIPT_SIGNATURE in script_content
            and os.access(script_path, os.X_OK)
        )
        content_for_parse = script_content
    else:
        desktop_path = kiosk_gnome_autostart_desktop_path(home)
        script_path = kiosk_launch_script_path(home)
        desktop_content = _read_or_none(desktop_path)
        script_content = _read_or_none(script_path)
        configured = (
            desktop_content is not None
            and KIOSK_DESKTOP_SIGNATURE in desktop_content
            and script_content is not None
            and KIOSK_SCRIPT_SIGNATURE in script_content
            and os.access(script_path, os.X_OK)
        )
        content_for_parse = script_content

    if content_for_parse:
        url, restart_enabled, restart_delay, chrome_flags, auto_reload_minutes = _parse_kiosk_script(content_for_parse)
    else:
        url, restart_enabled, restart_delay = DEFAULT_KIOSK_URL, True, DEFAULT_RESTART_DELAY
        chrome_flags = dict(DEFAULT_CHROME_FLAGS)
        auto_reload_minutes = DEFAULT_AUTO_RELOAD_MINUTES

    # gnome_lockdown_flags มีความหมายเฉพาะ session_type == "gnome" เท่านั้น (Openbox ไม่มี
    # preamble นี้เลย เพราะ write_autostart ไม่แทรกให้ — ดู KioskManager.write_autostart)
    if session_type == "gnome" and content_for_parse:
        gnome_lockdown_flags = _parse_gnome_lockdown_flags(content_for_parse)
    else:
        gnome_lockdown_flags = dict(DEFAULT_GNOME_LOCKDOWN_FLAGS)

    return KioskAutostartStatus(
        session_type=session_type, home=home,
        url=url, restart_enabled=restart_enabled, restart_delay=restart_delay,
        configured=configured, chrome_flags=chrome_flags,
        auto_reload_minutes=auto_reload_minutes,
        gnome_lockdown_flags=gnome_lockdown_flags,
    )


def collect_kiosk_software_status() -> KioskSoftwareStatus:
    if dev_fake_installed():
        return KioskSoftwareStatus(openbox_installed=True, chromium_installed=True)

    import shutil as _shutil
    return KioskSoftwareStatus(
        openbox_installed=_shutil.which("openbox") is not None,
        chromium_installed=_shutil.which("chromium-browser") is not None or _shutil.which("chromium") is not None,
    )


def collect_kiosk_readiness(
    users: "tuple[KioskLinuxUser, ...]",
    autologin: GdmAutologinStatus,
    autostart: KioskAutostartStatus,
    software: KioskSoftwareStatus,
) -> KioskReadiness:
    autologin_user_exists = any(u.username == autologin.username for u in users) if autologin.username else False
    return KioskReadiness(
        software_ok=software.openbox_installed and software.chromium_installed,
        user_ok=len(users) > 0,
        autologin_ok=autologin.enabled and autologin_user_exists,
        autostart_ok=autostart.configured,
    )


def stop_kiosk_mode(runner: CommandRunner, home: Path) -> None:
    """หยุด kiosk mode ในคลิกเดียว: ปิด GDM auto-login และลบไฟล์ autostart ทั้งหมด
    ของ user ที่ระบุ (ทั้ง GNOME และ Openbox variant) — ไม่ลบ Linux user หรือ
    AccountsService session-type config, เผื่อผู้ใช้จะกลับมาเปิด kiosk mode ใหม่ทีหลัง"""
    manager = KioskManager(runner)
    manager.set_autologin(None, enabled=False)
    manager.remove_autostart(home)


def check_url_reachable(url: str, timeout: int = 10) -> dict[str, object]:
    """เช็คว่า URL ที่จะใช้เป็น autostart target เปิดได้จริงไหม (HTTP GET แบบสั้นๆ) — กันเคส
    พิมพ์ URL ผิด/เข้าไม่ถึง แล้วจอ kiosk ขึ้นขาวตอน boot โดยไม่มีทางรู้จนกว่าจะเดินไปดูจอจริง
    ใช้ urllib.request ตาม convention เดิมของโปรเจกต์ (ดู system/clock.py, services/updater.py)
    ไม่เพิ่ม dependency ใหม่ (requests/httpx) — คืน dict เสมอ ไม่ raise

    HTTPError ที่ status < 500 (เช่น 401/403/404) ยังถือว่า "เข้าถึงได้" เพราะ server ตอบกลับจริง
    แค่ route/auth อาจไม่ตรง ไม่ใช่ URL เข้าไม่ถึงเลย — 5xx ถือว่า error เพราะฝั่งปลายทางมีปัญหาเอง
    """
    import urllib.error
    import urllib.request

    if not url or not url.strip():
        return {"ok": False, "status_code": None, "error": "ไม่ได้ระบุ URL"}

    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "VAS-Kiosk-Check/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 — URL มาจาก admin ตั้งเอง ไม่ใช่ user input จากภายนอก
            return {"ok": True, "status_code": resp.status, "error": None}
    except urllib.error.HTTPError as exc:
        ok = exc.code < 500
        return {"ok": ok, "status_code": exc.code, "error": None if ok else f"เซิร์ฟเวอร์ปลายทางตอบกลับ HTTP {exc.code}"}
    except urllib.error.URLError as exc:
        return {"ok": False, "status_code": None, "error": str(exc.reason)}
    except ValueError as exc:
        return {"ok": False, "status_code": None, "error": f"URL ไม่ถูกต้อง: {exc}"}
    except Exception as exc:  # noqa: BLE001 — กันทุกกรณีที่ไม่คาดคิด ไม่ให้ endpoint 500 เปล่าๆ
        return {"ok": False, "status_code": None, "error": str(exc)}


def print_kiosk_status() -> None:
    users = list_kiosk_linux_users()
    autologin = collect_gdm_autologin_status()
    software = collect_kiosk_software_status()
    autologin_user = next((u for u in users if u.is_autologin), None)

    session_type = "gnome"
    if autologin_user is not None:
        session_type = collect_accounts_service_status(autologin_user.username).session_type
    home = autologin_user.home if autologin_user is not None else Path("/home/kiosk-user")
    autostart = collect_kiosk_autostart_status(session_type, home)
    readiness = collect_kiosk_readiness(users, autologin, autostart, software)

    print("[Kiosk Software]")
    print(f"{'OK' if software.openbox_installed else 'MISSING':7} {'Openbox':10}")
    print(f"{'OK' if software.chromium_installed else 'MISSING':7} {'Chromium':10}")
    print()

    print("[Kiosk Users]")
    if not users:
        print("  (none)")
    for u in users:
        marker = "OK" if u.is_autologin else "  "
        tags = []
        if u.is_autologin:
            tags.append("auto-login")
        if u.managed_by_vas:
            tags.append("vas")
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        print(f"{marker:7} {u.username:16} uid={u.uid} home={u.home.as_posix()}{tag_str}")
    print()

    print("[GDM Auto-login]")
    autologin_marker = "OK" if autologin.enabled else "WARN"
    print(f"{autologin_marker:7} enabled={autologin.enabled} username={autologin.username or '-'} ({autologin.path.as_posix()})")
    print()

    print("[Session Type]")
    print(f"{session_type} (user={autologin_user.username if autologin_user is not None else '-'})")
    print()

    print("[Autostart]")
    autostart_marker = "OK" if autostart.configured else "WARN"
    print(
        f"{autostart_marker:7} configured={autostart.configured} url={autostart.url} "
        f"restart={autostart.restart_enabled} delay={autostart.restart_delay}s"
    )
    print()

    ready_count = sum([readiness.software_ok, readiness.user_ok, readiness.autologin_ok, readiness.autostart_ok])
    print(f"Readiness: {ready_count}/4")


def _read_or_none(path: Path) -> "str | None":
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False
