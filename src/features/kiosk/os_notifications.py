"""
VAS — OS-level notification suppression สำหรับ kiosk mode

ปิด popup/แจ้งเตือนระดับ Ubuntu ที่ user อาจกดโต้ตอบได้ระหว่างใช้งาน kiosk (แยกจาก
chrome_flags/gnome_lockdown_flags ใน manager.py ซึ่งเป็น flag ที่ถูกแทรกเข้า
kiosk-launch.sh แล้วรันซ้ำทุกครั้งที่ login — สิ่งที่นี่คือ **system-wide config
ที่เขียนครั้งเดียวมีผลกับทุก user บนเครื่อง** ไม่ผูกกับ user คนใดคนหนึ่ง จึงไม่มี
พารามิเตอร์ username/home ในฟังก์ชันด้านล่างเลย):

1. Release upgrade prompt — /etc/update-manager/release-upgrades คีย์ Prompt
2. update-notifier autostart icon — /etc/xdg/autostart/update-notifier.desktop
3. needrestart interactive prompt — /etc/needrestart/needrestart.conf
4. apt-mark hold บน update-notifier/update-manager กันพฤติกรรมเปลี่ยนตอน apt upgrade
5. gnome-initial-setup (First Login Wizard) — /etc/xdg/autostart/gnome-initial-setup-first-login.desktop
6. apport/whoopsie crash report popup ("Report a problem...") — /etc/default/apport คีย์ enabled

ทุกไฟล์เป็น system config ที่มาจาก apt package อยู่แล้ว — ถ้าไฟล์ไม่มีอยู่จริง (เช่น
ยังไม่ได้ติดตั้ง package) ฟังก์ชันจะไม่พยายามสร้างไฟล์ปลอมขึ้นมาเอง แค่ถือว่า
"ไม่มีผลอะไรต้องปิดอยู่แล้ว" (no-op) เพื่อไม่ให้เขียน config ที่ไม่ตรงกับของจริงที่ package
จะสร้างให้ตอนติดตั้ง

หมายเหตุ toggle 6 (apport): ปิดแค่ enabled=0 ใน /etc/default/apport เท่านั้น — ไม่ได้ไปสั่ง
systemctl disable whoopsie.service/whoopsie.path หรือลบไฟล์เก่าใน /var/crash เพราะเมื่อ apport
ปิด (enabled=0) เคอร์เนลจะไม่ route crash เข้า apport อีกต่อไป จึงไม่มีไฟล์ .crash ใหม่เกิดขึ้นให้
whoopsie เจอ — whoopsie เองไม่มีอะไรต้อง "ปิด" เพิ่ม เป็นแค่ตัวเฝ้าดูโฟลเดอร์ที่ apport เติมไฟล์ให้
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from core.runner import CommandRunner
from system.utils import dev_fake_installed

__all__ = [
    "APPORT_DEFAULT_PATH",
    "GNOME_INITIAL_SETUP_AUTOSTART_PATH",
    "HELD_PACKAGE_NAMES",
    "NEEDRESTART_CONF_PATH",
    "OS_NOTIFY_FLAG_DEFS",
    "RELEASE_UPGRADES_PATH",
    "UPDATE_NOTIFIER_AUTOSTART_PATH",
    "OsNotificationManager",
    "OsNotificationStatus",
    "collect_os_notification_status",
    "normalize_os_notify_flags",
]

RELEASE_UPGRADES_PATH = Path("/etc/update-manager/release-upgrades")
UPDATE_NOTIFIER_AUTOSTART_PATH = Path("/etc/xdg/autostart/update-notifier.desktop")
NEEDRESTART_CONF_PATH = Path("/etc/needrestart/needrestart.conf")
GNOME_INITIAL_SETUP_AUTOSTART_PATH = Path("/etc/xdg/autostart/gnome-initial-setup-first-login.desktop")
APPORT_DEFAULT_PATH = Path("/etc/default/apport")
HELD_PACKAGE_NAMES: "tuple[str, ...]" = ("update-notifier", "update-manager")

# ── คำจำกัดความ 6 toggle — ใช้ทั้งฝั่ง template (loop แสดงผล) และฝั่ง API (validate key) ──
OS_NOTIFY_FLAG_DEFS: "tuple[dict[str, str], ...]" = (
    {
        "key": "release_upgrade",
        "label": "ปิด popup แจ้งอัปเกรดเวอร์ชัน Ubuntu",
        "desc": "ตั้ง Prompt=never ที่ /etc/update-manager/release-upgrades",
        "path": RELEASE_UPGRADES_PATH.as_posix(),
    },
    {
        "key": "update_notifier_autostart",
        "label": "ปิด icon/แจ้งเตือน update-notifier ตอน runtime",
        "desc": "ปิด autostart entry ของ update-notifier ทั้งระบบ (ทุก user)",
        "path": UPDATE_NOTIFIER_AUTOSTART_PATH.as_posix(),
    },
    {
        "key": "needrestart_prompt",
        "label": "ปิด prompt ของ needrestart ตอน apt upgrade",
        "desc": "ตั้งค่าให้ restart service ที่จำเป็นอัตโนมัติแบบเงียบ ไม่ถามระหว่างใช้งาน",
        "path": NEEDRESTART_CONF_PATH.as_posix(),
    },
    {
        "key": "hold_packages",
        "label": "กันแพ็กเกจที่เกี่ยวข้องถูกอัปเดตพฤติกรรมเปลี่ยน",
        "desc": "apt-mark hold บน " + ", ".join(HELD_PACKAGE_NAMES),
        "path": "apt-mark hold",
    },
    {
        "key": "gnome_initial_setup",
        "label": "ปิด First Login Wizard (gnome-initial-setup)",
        "desc": "ปิด autostart entry ของ gnome-initial-setup ทั้งระบบ — กัน 'Connect Your Online Accounts' โผล่ตอนสร้าง user ใหม่",
        "path": GNOME_INITIAL_SETUP_AUTOSTART_PATH.as_posix(),
    },
    {
        "key": "apport_crash_report",
        "label": "ปิดแจ้งเตือน crash report (apport/whoopsie)",
        "desc": (
            "ตั้ง enabled=0 ที่ /etc/default/apport กัน popup \"Report a problem...\" เด้งขึ้นจอทับ "
            "หน้าเว็บ kiosk เวลามีโปรแกรมพัง (whoopsie เป็นแค่ตัวเฝ้าดู /var/crash — ปิด apport "
            "ตรงนี้แล้วจะไม่มีไฟล์ .crash ใหม่เกิดให้ whoopsie แจ้งอีกเลย)"
        ),
        "path": APPORT_DEFAULT_PATH.as_posix(),
    },
)

_VALID_KEYS = {item["key"] for item in OS_NOTIFY_FLAG_DEFS}


def normalize_os_notify_flags(flags: "Mapping[str, object] | None") -> "dict[str, bool]":
    """เหมือน normalize_chrome_flags()/normalize_gnome_lockdown_flags() ใน manager.py —
    คีย์ที่ไม่รู้จักถูกทิ้ง คีย์ที่ไม่ได้ส่งมาไม่ถูกแตะ (partial update ได้)"""
    result: "dict[str, bool]" = {}
    if flags:
        for key, value in flags.items():
            if key in _VALID_KEYS:
                result[key] = bool(value)
    return result


@dataclass(frozen=True)
class OsNotificationStatus:
    release_upgrade: bool
    update_notifier_autostart: bool
    needrestart_prompt: bool
    hold_packages: bool
    gnome_initial_setup: bool
    apport_crash_report: bool

    def as_dict(self) -> "dict[str, bool]":
        return {
            "release_upgrade": self.release_upgrade,
            "update_notifier_autostart": self.update_notifier_autostart,
            "needrestart_prompt": self.needrestart_prompt,
            "hold_packages": self.hold_packages,
            "gnome_initial_setup": self.gnome_initial_setup,
            "apport_crash_report": self.apport_crash_report,
        }


def _read_or_none(path: Path) -> "str | None":
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _autostart_disabled(path: Path) -> bool:
    """.desktop autostart ถือว่า 'ปิด' ถ้ามี X-GNOME-Autostart-enabled=false อยู่ในไฟล์
    — ถ้าไฟล์ไม่มีอยู่จริง (ไม่ได้ติดตั้ง package) ถือว่าไม่มีอะไรต้องปิด → นับเป็น 'ปิดแล้ว'"""
    content = _read_or_none(path)
    if content is None:
        return True
    return re.search(r"^\s*X-GNOME-Autostart-enabled\s*=\s*false\s*$", content, re.MULTILINE) is not None


def _release_upgrade_disabled(path: Path = RELEASE_UPGRADES_PATH) -> bool:
    content = _read_or_none(path)
    if content is None:
        return False
    match = re.search(r"^\s*Prompt\s*=\s*(\S+)\s*$", content, re.MULTILINE)
    return match is not None and match.group(1).strip().lower() == "never"


def _needrestart_auto(path: Path = NEEDRESTART_CONF_PATH) -> bool:
    content = _read_or_none(path)
    if content is None:
        return False
    match = re.search(r"\$nrconf\{restart\}\s*=\s*'([aiA-Za-z]+)'\s*;", content)
    return match is not None and match.group(1).strip().lower() == "a"


def _apport_disabled(path: Path = APPORT_DEFAULT_PATH) -> bool:
    content = _read_or_none(path)
    if content is None:
        return False
    match = re.search(r"^\s*enabled\s*=\s*(\S+)\s*$", content, re.MULTILINE)
    return match is not None and match.group(1).strip() == "0"


def _packages_held(names: "tuple[str, ...]" = HELD_PACKAGE_NAMES) -> bool:
    try:
        result = subprocess.run(
            ["apt-mark", "showhold"], check=False, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except OSError:
        return False
    held = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return all(name in held for name in names)


def collect_os_notification_status() -> OsNotificationStatus:
    if dev_fake_installed():
        return OsNotificationStatus(
            release_upgrade=True, update_notifier_autostart=True,
            needrestart_prompt=False, hold_packages=False, gnome_initial_setup=True,
            apport_crash_report=False,
        )
    return OsNotificationStatus(
        release_upgrade=_release_upgrade_disabled(),
        update_notifier_autostart=_autostart_disabled(UPDATE_NOTIFIER_AUTOSTART_PATH),
        needrestart_prompt=_needrestart_auto(),
        hold_packages=_packages_held(),
        gnome_initial_setup=_autostart_disabled(GNOME_INITIAL_SETUP_AUTOSTART_PATH),
        apport_crash_report=_apport_disabled(),
    )


# ---------------------------------------------------------------------------
# Pure builders (ไม่มี I/O) — แยกจากส่วนเขียนไฟล์จริงเพื่อ unit test ได้ง่าย
# ---------------------------------------------------------------------------

def build_release_upgrades_content(existing_content: str, disabled: bool) -> str:
    """ตั้ง/แก้ค่า Prompt= ใน /etc/update-manager/release-upgrades — ไม่แตะบรรทัดอื่น
    (comment อธิบาย never/normal/lts ที่ Ubuntu ใส่มาให้ default) ถ้าไม่เจอบรรทัด Prompt=
    เดิมเลยจะเติมต่อท้ายไฟล์แทน"""
    value = "never" if disabled else "normal"
    lines = existing_content.splitlines() if existing_content else ["[DEFAULT]"]
    pattern = re.compile(r"^(\s*)Prompt\s*=.*$")
    replaced = False
    new_lines: "list[str]" = []
    for line in lines:
        match = pattern.match(line)
        if match:
            new_lines.append(f"{match.group(1)}Prompt={value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"Prompt={value}")
    return "\n".join(new_lines) + "\n"


def build_autostart_toggle_content(existing_content: str, disabled: bool) -> str:
    """เพิ่ม/แก้/ลบบรรทัด X-GNOME-Autostart-enabled= ใน .desktop ที่มีอยู่แล้ว — ใช้ร่วมกัน
    ทั้ง update-notifier.desktop และ gnome-initial-setup-first-login.desktop (โครงสร้าง
    ไฟล์แบบเดียวกัน)"""
    lines = existing_content.splitlines()
    pattern = re.compile(r"^\s*X-GNOME-Autostart-enabled\s*=.*$")
    filtered = [line for line in lines if not pattern.match(line)]
    if disabled:
        # ใส่ไว้บรรทัดแรกหลัง [Desktop Entry] ถ้ามี ไม่งั้นต่อท้ายไฟล์
        insert_at = 1 if filtered and filtered[0].strip() == "[Desktop Entry]" else len(filtered)
        filtered.insert(insert_at, "X-GNOME-Autostart-enabled=false")
    return "\n".join(filtered) + ("\n" if filtered else "")


def build_needrestart_conf_content(existing_content: str, auto: bool) -> str:
    """ตั้งค่า $nrconf{restart} ใน /etc/needrestart/needrestart.conf — 'a' = restart
    service ที่จำเป็นอัตโนมัติแบบเงียบ, 'i' = ถามทุกครั้ง (ค่า default ของ needrestart)"""
    value = "a" if auto else "i"
    lines = existing_content.splitlines() if existing_content else []
    pattern = re.compile(r"^(\s*)\$nrconf\{restart\}\s*=\s*'[aiA-Za-z]+'\s*;(.*)$")
    replaced = False
    new_lines: "list[str]" = []
    for line in lines:
        match = pattern.match(line)
        if match:
            new_lines.append(f"{match.group(1)}$nrconf{{restart}} = '{value}';{match.group(2)}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"$nrconf{{restart}} = '{value}';")
    return "\n".join(new_lines) + "\n"


def build_apport_content(existing_content: str, disabled: bool) -> str:
    """ตั้ง/แก้ค่า enabled= ใน /etc/default/apport — ไม่แตะบรรทัด comment อื่นที่ package
    ใส่มาให้ (คำอธิบาย enabled=0/1) ถ้าไม่เจอบรรทัด enabled= เดิมเลยจะเติมต่อท้ายไฟล์แทน
    (โครงสร้างเดียวกับ build_release_upgrades_content ด้านบน — ไฟล์นี้เป็น key=value แบบเดียวกัน)"""
    value = "0" if disabled else "1"
    lines = existing_content.splitlines() if existing_content else []
    pattern = re.compile(r"^(\s*)enabled\s*=.*$")
    replaced = False
    new_lines: "list[str]" = []
    for line in lines:
        match = pattern.match(line)
        if match:
            new_lines.append(f"{match.group(1)}enabled={value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"enabled={value}")
    return "\n".join(new_lines) + "\n"


class OsNotificationManager:
    """เขียน system config จริง — ทุกเมธอดเช็ค self.runner.dry_run ก่อนเขียนเสมอ (เหมือน
    KioskManager ใน manager.py) และข้ามการเขียนถ้าไฟล์ปลายทางไม่มีอยู่จริง (ไม่สร้างไฟล์
    ปลอมแทน package ที่ยังไม่ได้ติดตั้ง)"""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def _write_if_exists(self, path: Path, build_fn, *args) -> bool:
        if not path.exists():
            return False
        existing = path.read_text(encoding="utf-8")
        content = build_fn(existing, *args)
        print(f"write {path.as_posix()}")
        if self.runner.dry_run:
            print(content.rstrip())
            return True
        path.write_text(content, encoding="utf-8")
        return True

    def set_release_upgrade(self, disabled: bool) -> bool:
        path = RELEASE_UPGRADES_PATH
        if not path.exists():
            return False
        return self._write_if_exists(path, build_release_upgrades_content, disabled)

    def set_update_notifier_autostart(self, disabled: bool) -> bool:
        return self._write_if_exists(UPDATE_NOTIFIER_AUTOSTART_PATH, build_autostart_toggle_content, disabled)

    def set_needrestart_prompt(self, auto: bool) -> bool:
        # needrestart.conf อาจไม่มีอยู่จริงถ้ายังไม่ได้ apt install needrestart — ในกรณีนั้น
        # ไม่มีอะไรต้อง suppress อยู่แล้ว (ไม่มี needrestart ให้ prompt)
        return self._write_if_exists(NEEDRESTART_CONF_PATH, build_needrestart_conf_content, auto)

    def set_gnome_initial_setup(self, disabled: bool) -> bool:
        return self._write_if_exists(GNOME_INITIAL_SETUP_AUTOSTART_PATH, build_autostart_toggle_content, disabled)

    def set_apport_crash_report(self, disabled: bool) -> bool:
        # /etc/default/apport อาจไม่มีอยู่จริงถ้ายังไม่ได้ apt install apport — ในกรณีนั้น
        # ไม่มี apport ให้ route crash เข้าอยู่แล้ว (ไม่มี popup ให้ suppress)
        return self._write_if_exists(APPORT_DEFAULT_PATH, build_apport_content, disabled)

    def set_packages_held(self, held: bool) -> None:
        if self.runner.dry_run:
            print(f"apt-mark {'hold' if held else 'unhold'} {' '.join(HELD_PACKAGE_NAMES)}")
            return
        self.runner.run(["apt-mark", "hold" if held else "unhold", *HELD_PACKAGE_NAMES], check=False)

    def apply(self, flags: "dict[str, bool]") -> None:
        """apply แบบ partial — คีย์ไหนไม่ได้ส่งมาใน flags จะไม่ถูกแตะเลย (ต่างจาก
        chrome_flags/gnome_lockdown_flags ที่ replace ทั้งชุดทุกครั้ง เพราะ toggle พวกนี้
        แต่ละตัวเป็น system config คนละไฟล์ ไม่มีเหตุผลต้อง reset ตัวที่ไม่ได้แก้)"""
        if "release_upgrade" in flags:
            self.set_release_upgrade(flags["release_upgrade"])
        if "update_notifier_autostart" in flags:
            self.set_update_notifier_autostart(flags["update_notifier_autostart"])
        if "needrestart_prompt" in flags:
            self.set_needrestart_prompt(flags["needrestart_prompt"])
        if "hold_packages" in flags:
            self.set_packages_held(flags["hold_packages"])
        if "gnome_initial_setup" in flags:
            self.set_gnome_initial_setup(flags["gnome_initial_setup"])
        if "apport_crash_report" in flags:
            self.set_apport_crash_report(flags["apport_crash_report"])
