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
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence, cast

from core.runner import CommandRunner
from system.status import GDM_CUSTOM_CONFIG_PATH
from system.utils import dev_fake_installed

try:
    import pwd as pwd_module
except ImportError:  # pragma: no cover - Windows dev hosts
    pwd_module = None  # type: ignore[assignment]

PWD_MODULE = cast("Any | None", pwd_module)

__all__ = [
    "ACCOUNTS_SERVICE_DIR",
    "DEFAULT_EXTRA_GROUPS",
    "DEFAULT_KIOSK_URL",
    "DEFAULT_RESTART_DELAY",
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
    "build_kiosk_launch_script",
    "collect_accounts_service_status",
    "collect_gdm_autologin_status",
    "collect_kiosk_autostart_status",
    "collect_kiosk_readiness",
    "collect_kiosk_software_status",
    "get_gdm_autologin_username",
    "kiosk_gnome_autostart_desktop_path",
    "kiosk_launch_script_path",
    "kiosk_openbox_autostart_path",
    "list_kiosk_linux_users",
    "print_kiosk_status",
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

_KIOSK_MIN_UID = 1000
_KIOSK_MAX_UID = 60000  # ไม่รวม nobody (65534)


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
    ) -> None:
        script_content = build_kiosk_launch_script(url, restart_enabled, restart_delay)

        if session_type == "openbox":
            script_path = kiosk_openbox_autostart_path(home)
            self._write_executable(script_path, script_content)
            _chown_to_user(script_path, username)
            _chown_to_user(script_path.parent, username)
            return

        script_path = kiosk_launch_script_path(home)
        self._write_executable(script_path, script_content)
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


def build_kiosk_launch_script(url: str, restart_enabled: bool, restart_delay: int) -> str:
    if restart_enabled:
        body = (
            "while true; do\n"
            f"  chromium --kiosk --noerrdialogs --disable-infobars {shlex.quote(url)}\n"
            f"  sleep {max(0, restart_delay)}\n"
            "done\n"
        )
    else:
        body = f"chromium --kiosk --noerrdialogs --disable-infobars {shlex.quote(url)}\n"

    return (
        "#!/usr/bin/env bash\n"
        f"{KIOSK_SCRIPT_SIGNATURE}\n"
        "# Managed by VAS. Manual edits may be overwritten.\n"
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


def _parse_kiosk_script(content: str) -> "tuple[str, bool, int]":
    restart_enabled = bool(re.search(r"^\s*while\s+true\s*;\s*do", content, re.MULTILINE))
    url_match = re.search(r"chromium[^\n]*?(https?://\S+)", content)
    url = url_match.group(1) if url_match else DEFAULT_KIOSK_URL
    delay_match = re.search(r"sleep\s+(\d+)", content)
    delay = int(delay_match.group(1)) if delay_match else DEFAULT_RESTART_DELAY
    return url, restart_enabled, delay


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


def collect_kiosk_autostart_status(session_type: str, home: Path) -> KioskAutostartStatus:
    if dev_fake_installed():
        return KioskAutostartStatus(
            session_type=session_type, home=home,
            url=DEFAULT_KIOSK_URL, restart_enabled=True, restart_delay=DEFAULT_RESTART_DELAY,
            configured=True,
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
        url, restart_enabled, restart_delay = _parse_kiosk_script(content_for_parse)
    else:
        url, restart_enabled, restart_delay = DEFAULT_KIOSK_URL, True, DEFAULT_RESTART_DELAY

    return KioskAutostartStatus(
        session_type=session_type, home=home,
        url=url, restart_enabled=restart_enabled, restart_delay=restart_delay,
        configured=configured,
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
