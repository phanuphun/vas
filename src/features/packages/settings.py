"""
VAS — Settings: Package manifest + install runner

แต่ละ Package มี:
    id          — ชื่อ unique
    name        — ชื่อแสดง
    description — คำอธิบายสั้น
    logo        — ชื่อไฟล์ภาพใน public/images/logo/ (None = fallback)
    category    — กลุ่ม (core, runtime, network, remote, hardware)
    depends     — list ของ package id ที่ต้องติดตั้งก่อน
    check       — callable คืน (installed: bool, version: str|None)
    install_cmds — list ของ command list ที่รันตามลำดับ
    children    — list ของ package id ที่ unlock หลังจากติดตั้ง
"""
from __future__ import annotations

import queue
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from system.utils import dev_fake_installed


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------

def _python_import_check(module: str):
    """คืน (installed, version_str|None) สำหรับ Python library"""
    def _check() -> tuple[bool, str | None]:
        if dev_fake_installed():
            return True, "dev-mode"
        result = subprocess.run(
            ["python3", "-c", f"import {module}; print(getattr({module}, '__version__', None))"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return False, None
        ver = result.stdout.strip()
        return True, ver if ver and ver != "None" else None
    return _check


def _which_check(cmd: str, version_args: tuple[str, ...] | None = None):
    """คืน (installed, version_str|None)"""
    def _check() -> tuple[bool, str | None]:
        if dev_fake_installed():
            return True, "dev-mode"
        path = shutil.which(cmd)
        if path is None:
            return False, None
        if version_args:
            try:
                r = subprocess.run(
                    list(version_args), capture_output=True, text=True, timeout=5
                )
                ver = (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else None
            except Exception:
                ver = None
        else:
            ver = None
        return True, ver
    return _check


def _file_check(path: str):
    def _check() -> tuple[bool, str | None]:
        if dev_fake_installed():
            return True, "dev-mode"
        exists = Path(path).exists()
        return exists, "installed" if exists else None
    return _check


def _which_any_check(cmds: tuple[str, ...]):
    """คืน (installed, version_str|None) — ลองหาทีละ command ตามลำดับ
    ใช้กับ package ที่ executable name ไม่แน่นอน (เช่น chromium / chromium-browser)"""
    def _check() -> tuple[bool, str | None]:
        if dev_fake_installed():
            return True, "dev-mode"
        for cmd in cmds:
            path = shutil.which(cmd)
            if path is None:
                continue
            try:
                r = subprocess.run(
                    [cmd, "--version"], capture_output=True, text=True, timeout=5
                )
                ver = (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else None
            except Exception:
                ver = None
            return True, ver
        return False, None
    return _check


# ---------------------------------------------------------------------------
# GNOME gesture lockdown — vendor asset path (resolve ที่นี่ครั้งเดียวตอน import โมดูล
# แทนการพึ่ง $0/readlink ใน bash ซึ่งใช้ไม่ได้จริงเวลารันผ่าน subprocess list แบบตรงๆ)
# ---------------------------------------------------------------------------

_GESTURE_LOCKDOWN_UUID = "disable-gestures-2021@verycrazydog.gmail.com"
_GESTURE_LOCKDOWN_VENDOR_DIR = Path(__file__).parent / "vendor" / "gnome-disable-gestures"
_GESTURE_LOCKDOWN_SYSTEM_DIR = f"/usr/share/gnome-shell/extensions/{_GESTURE_LOCKDOWN_UUID}"


def _gesture_lockdown_install_script() -> str:
    """สร้างคำสั่ง shell เดียวที่: (1) เช็ค GNOME Shell major version ของเครื่องจริง
    (2) เลือกโฟลเดอร์ vendor v5 (Shell 3.36-44) หรือ v9 (Shell 45-47) ให้ตรง (3) copy
    extension.js/metadata.json ไปลง path ระบบ — path ของ vendor dir resolve จาก Python
    (__file__) ตอน import แล้ว ไม่ใช่เดาจาก $0 ใน bash (ใช้ไม่ได้เวลารันผ่าน list args ตรงๆ
    ไม่ผ่าน shell file จริง)"""
    v5_dir = (_GESTURE_LOCKDOWN_VENDOR_DIR / "v5").as_posix()
    v9_dir = (_GESTURE_LOCKDOWN_VENDOR_DIR / "v9").as_posix()
    return (
        "SHELL_VER=$(gnome-shell --version | grep -oE '[0-9]+' | head -1); "
        f'if [ -n "$SHELL_VER" ] && [ "$SHELL_VER" -ge 45 ]; then SRC="{v9_dir}"; '
        f'else SRC="{v5_dir}"; fi; '
        f'mkdir -p "{_GESTURE_LOCKDOWN_SYSTEM_DIR}" && '
        f'cp "$SRC/extension.js" "$SRC/metadata.json" "{_GESTURE_LOCKDOWN_SYSTEM_DIR}/"'
    )


# ---------------------------------------------------------------------------
# Package manifest
# ---------------------------------------------------------------------------

PACKAGES: list[dict[str, Any]] = [
    # ── Core ──────────────────────────────────────────────────────
    {
        "id":          "git",
        "name":        "Git",
        "description": "Version control system — จำเป็นสำหรับ clone และ pull code",
        "logo":        "Git_icon.svg.png",
        "category":    "core",
        "depends":     [],
        "children":    [],
        "check":       _which_check("git", ("git", "--version")),
        "install_cmds": [
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "git"],
        ],
        "uninstall_cmds": [
            ["apt-get", "purge", "-y", "git"],
        ],
    },
    # ── Node.js + ecosystem ───────────────────────────────────────
    {
        "id":          "node",
        "name":        "Node.js",
        "description": "JavaScript runtime v22 LTS — รองรับ PM2, npm packages",
        "logo":        "nodejs-logo.png",
        "category":    "runtime",
        "depends":     [],
        "children":    ["pm2"],
        "check":       _which_check("node", ("node", "--version")),
        "install_cmds": [
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "ca-certificates", "curl", "gnupg"],
            [
                "bash", "-lc",
                "curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key "
                "| gpg --batch --yes --no-tty --dearmor -o /usr/share/keyrings/nodesource.gpg",
            ],
            [
                "bash", "-lc",
                "echo 'deb [signed-by=/usr/share/keyrings/nodesource.gpg] "
                "https://deb.nodesource.com/node_22.x nodistro main' "
                "> /etc/apt/sources.list.d/nodesource.list",
            ],
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "nodejs"],
        ],
        "uninstall_cmds": [
            ["apt-get", "purge", "-y", "nodejs", "npm"],
        ],
    },
    {
        "id":          "pm2",
        "name":        "PM2",
        "description": "Process manager สำหรับ Node.js — auto-restart, log management",
        "logo":        "pm-logo.webp",
        "category":    "runtime",
        "depends":     ["node"],
        "children":    [],
        "check":       _which_check("pm2", ("pm2", "--version")),
        "install_cmds": [
            ["npm", "install", "-g", "pm2"],
        ],
        "uninstall_cmds": [
            ["npm", "uninstall", "-g", "pm2"],
        ],
    },
    # ── Docker ────────────────────────────────────────────────────
    {
        "id":          "docker",
        "name":        "Docker",
        "description": "Container platform — รัน apps ใน isolated containers",
        "logo":        "docker-logo.png",
        "category":    "core",
        "depends":     [],
        "children":    [],
        "check":       _which_check("docker", ("docker", "--version")),
        "install_cmds": [
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "ca-certificates", "curl"],
            ["install", "-m", "0755", "-d", "/etc/apt/keyrings"],
            [
                "bash", "-lc",
                "curl -fsSL https://download.docker.com/linux/ubuntu/gpg "
                "-o /etc/apt/keyrings/docker.asc && chmod a+r /etc/apt/keyrings/docker.asc",
            ],
            [
                "bash", "-lc",
                ". /etc/os-release && echo "
                "\"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] "
                "https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable\" "
                "| tee /etc/apt/sources.list.d/docker.list > /dev/null",
            ],
            ["apt-get", "update"],
            ["apt-get", "install", "-y",
             "docker-ce", "docker-ce-cli", "containerd.io",
             "docker-buildx-plugin", "docker-compose-plugin"],
        ],
        "uninstall_cmds": [
            ["systemctl", "disable", "--now", "docker"],
            ["systemctl", "disable", "--now", "containerd"],
            ["apt-get", "remove", "-y",
             "docker-ce", "docker-ce-cli", "containerd.io",
             "docker-buildx-plugin", "docker-compose-plugin",
             "docker-ce-rootless-extras", "docker.io", "docker-doc",
             "docker-compose", "docker-compose-v2", "podman-docker",
             "containerd", "runc"],
        ],
    },
    # ── Network ───────────────────────────────────────────────────
    {
        "id":          "wireguard",
        "name":        "WireGuard",
        "description": "Fast, modern VPN — เชื่อมต่อ network อย่างปลอดภัย",
        "logo":        "wireguard-logo.webp",
        "category":    "network",
        "depends":     [],
        "children":    [],
        "check":       _which_check("wg", ("wg", "--version")),
        "install_cmds": [
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "wireguard", "wireguard-tools"],
        ],
        "uninstall_cmds": [
            ["apt-get", "purge", "-y", "wireguard", "wireguard-tools"],
        ],
    },
    {
        "id":          "openssh",
        "name":        "OpenSSH Server",
        "description": "SSH server — remote terminal access ผ่าน SSH",
        "logo":        "openssh-logo.png",
        "category":    "network",
        "depends":     [],
        "children":    [],
        "check":       _which_check("sshd", ("sshd", "-V")),
        "install_cmds": [
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "openssh-server"],
            ["systemctl", "enable", "--now", "ssh"],
        ],
        "uninstall_cmds": [
            ["systemctl", "disable", "--now", "ssh"],
            ["apt-get", "purge", "-y", "openssh-server"],
        ],
        "uninstall_warning": "การถอน OpenSSH อาจทำให้การเชื่อมต่อระยะไกลผ่าน SSH ใช้งานไม่ได้",
    },
    # ── Remote ────────────────────────────────────────────────────
    {
        "id":          "anydesk",
        "name":        "AnyDesk",
        "description": "Remote desktop — เข้าควบคุม desktop จากระยะไกล",
        "logo":        "anydesk-logo.png",
        "category":    "remote",
        "depends":     [],
        "children":    [],
        "check":       _which_check("anydesk", ("anydesk", "--version")),
        "install_cmds": [
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "ca-certificates", "curl"],
            [
                "bash", "-lc",
                "curl -fsSL https://keys.anydesk.com/repos/DEB-GPG-KEY "
                "| gpg --batch --yes --no-tty --dearmor -o /usr/share/keyrings/anydesk.gpg",
            ],
            [
                "bash", "-lc",
                "echo 'deb [signed-by=/usr/share/keyrings/anydesk.gpg] "
                "https://deb.anydesk.com/ all main' "
                "> /etc/apt/sources.list.d/anydesk-stable.list",
            ],
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "anydesk"],
        ],
        "uninstall_cmds": [
            ["systemctl", "disable", "--now", "anydesk"],
            ["apt-get", "purge", "-y", "anydesk"],
        ],
        "uninstall_warning": "การถอน AnyDesk จะปิดการเข้าถึง remote desktop จากระยะไกล",
    },
    # ── Kiosk Mode ────────────────────────────────────────────────
    {
        "id":          "openbox",
        "name":        "Openbox",
        "description": "Window manager แบบเบา — ใช้แสดงผล kiosk mode เต็มจอโดยไม่มี desktop UI",
        "logo":        "openbox-logo.png",
        "category":    "kiosk",
        "depends":     [],
        "children":    [],
        "check":       _which_check("openbox", ("openbox", "--version")),
        "install_cmds": [
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "openbox"],
        ],
        "uninstall_cmds": [
            ["apt-get", "purge", "-y", "openbox"],
        ],
        "uninstall_warning": "การถอน Openbox จะทำให้ session แบบ kiosk (ถ้าตั้งค่าไว้ให้ใช้ openbox) ใช้งานไม่ได้",
    },
    {
        "id":          "chromium",
        "name":        "Chromium",
        "description": "เว็บเบราว์เซอร์ — เปิดแบบ --kiosk เต็มจอเพื่อแสดง dashboard หรือหน้าเว็บที่กำหนด",
        "logo":        "chromium-logo.png",
        "category":    "kiosk",
        "depends":     [],
        "children":    [],
        "check":       _which_any_check(("chromium-browser", "chromium")),
        # เปลี่ยนจาก "apt-get install chromium-browser" (transitional package ที่ดึง snap มาแทน
        # เสมอบน Ubuntu 22.04 — ดูคอมเมนต์ยาวที่ uninstall_cmds ด้านล่างสำหรับปัญหาที่เจอจริง) มาใช้
        # PPA "xtradeb/apps" ติดตั้งเป็น .deb ตรงๆ แทน (ชื่อ package เปลี่ยนเป็น "chromium" ไม่ใช่
        # "chromium-browser") เหตุผล: (1) ไม่มี snapd auto-refresh ที่อาจรีสตาร์ท Chromium เองกลาง
        # ที่ลูกค้ากำลังใช้ตู้ (2) boot เร็วกว่า ไม่มี snap mount overhead — ยอมรับข้อแลกเปลี่ยนว่า
        # xtradeb เป็น third-party PPA ไม่ใช่ official Canonical/Google repo ตัดสินใจร่วมกับผู้ใช้
        # แล้วหลังเทียบทางเลือก snap/PPA/Google Chrome official repo (2026-07-14)
        "install_cmds": [
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "software-properties-common"],
            ["add-apt-repository", "-y", "ppa:xtradeb/apps"],
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "chromium"],
        ],
        # "chromium-browser" บน Ubuntu 22.04 เป็นแค่ transitional package — apt purge ตัวนี้
        # ลบแค่ metapackage เปล่าๆ ไม่เคยเรียก "snap remove" ให้ (ไม่มี prerm/postrm hook คู่กับ
        # postinst ที่เรียก "snap install chromium" ตอนติดตั้ง) ทำให้ snap "chromium" ตัวจริงยัง
        # ค้างอยู่เต็มเครื่อง ต้องเข้า Ubuntu Software (GUI ที่เรียก snapd ตรงๆ) ไปลบเองถึงจะหาย —
        # ยืนยันจริงจากผู้ใช้ที่ clone OS ไปตู้ vending แล้วกด uninstall ผ่านหน้า "โปรแกรมเพิ่มเติม"
        # ไม่หลุดจริงตามนี้เป๊ะ (2026-07-14) — คง "snap remove --purge chromium" ไว้เป็น safety net
        # ต่อไปแม้ install_cmds เปลี่ยนมาใช้ PPA .deb แล้ว (ข้างบน) เพราะเครื่องที่เคยติดตั้งด้วยโค้ด
        # เก่า (ก่อนเปลี่ยนมาใช้ PPA) อาจยังมี snap ค้างอยู่ — เป็น best-effort เสมอ
        # (stop_on_error=False ของ _run_commands อยู่แล้ว ถ้าเครื่องไม่มี snap ตัวนี้ติดตั้งอยู่ หรือ
        # ไม่มีคำสั่ง snap เลย คำสั่งนี้ fail แล้วข้ามไปเฉยๆ ไม่ทำให้ flow ทั้งหมดพัง)
        "uninstall_cmds": [
            ["apt-get", "purge", "-y", "chromium-browser", "chromium"],
            ["snap", "remove", "--purge", "chromium"],
        ],
        "uninstall_warning": (
            "การถอน Chromium จะทำให้หน้าจอ kiosk mode (ถ้าตั้งค่าไว้) เปิดเบราว์เซอร์ไม่ได้อีก — "
            "จะลบทั้ง apt package และ snap package (รวมข้อมูล/โปรไฟล์ที่บันทึกไว้) ให้ครบในขั้นตอนเดียว"
        ),
    },
    {
        "id":          "gnome-gesture-lockdown",
        "name":        "Disable Gestures 2021",
        "description": (
            "GNOME Shell extension — ปิด touch gesture ในตัว (ปัดขวาสลับ workspace, "
            "ปัดขึ้นยุบแอปเข้า Activities Overview) กันหลุดออกจาก kiosk mode ทาง gesture "
            "ที่ Hot Corner/Super key/Ubuntu Dock ปิดไม่ถึง"
        ),
        "logo":        None,
        "category":    "kiosk",
        "depends":     [],
        "children":    [],
        "check":       _file_check(f"{_GESTURE_LOCKDOWN_SYSTEM_DIR}/metadata.json"),
        "install_cmds": [
            ["bash", "-c", _gesture_lockdown_install_script()],
        ],
        "uninstall_cmds": [
            ["rm", "-rf", _GESTURE_LOCKDOWN_SYSTEM_DIR],
        ],
        "uninstall_warning": "การถอนจะเปิดทางให้ปัดขวา/ปัดขึ้นหลุดออกจาก kiosk ได้อีกครั้ง — ต้อง Apply/reboot ที่หน้า Kiosk ใหม่ถ้าติดตั้งซ้ำภายหลัง",
    },
    # ── Hardware ──────────────────────────────────────────────────
    {
        "id":          "qr-udev",
        "name":        "99-qr500-bm.rules",
        "description": "udev rule — อนุญาต non-root user เข้าถึง /dev/hidraw* และ /dev/input/* สำหรับ QR reader",
        "logo":        None,
        "category":    "hardware",
        "depends":     [],
        "children":    [],
        "check":       _file_check("/etc/udev/rules.d/99-qr500-bm.rules"),
        "install_cmds": [
            [
                "bash", "-lc",
                "echo '# managed by vas\n"
                "SUBSYSTEM==\"hidraw\", ATTRS{idVendor}==\"1584\", ATTRS{idProduct}==\"7000\", MODE=\"0666\"\n"
                "SUBSYSTEM==\"input\", ATTRS{idVendor}==\"1584\", MODE=\"0666\"' "
                "> /etc/udev/rules.d/99-qr500-bm.rules",
            ],
            ["udevadm", "control", "--reload-rules"],
            ["udevadm", "trigger"],
        ],
        "uninstall_cmds": [
            ["rm", "-f", "/etc/udev/rules.d/99-qr500-bm.rules"],
            ["udevadm", "control", "--reload-rules"],
            ["udevadm", "trigger"],
        ],
    },
]

def _safe_check(p: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        return p["check"]()
    except Exception:
        return False, None


# id → package dict lookup
_PKG_MAP: dict[str, dict[str, Any]] = {p["id"]: p for p in PACKAGES}

CATEGORIES: dict[str, str] = {
    "core":     "Core Tools",
    "runtime":  "Runtime",
    "network":  "Network",
    "remote":   "Remote Access",
    "kiosk":    "Kiosk Mode",
    "display":  "Display & Simulation",
    "hardware": "Hardware",
}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def get_package_status(pkg_id: str | None = None) -> list[dict[str, Any]]:
    """
    คืน list ของ package พร้อม status ปัจจุบัน
    pkg_id=None → ทั้งหมด
    """
    pkgs = [_PKG_MAP[pkg_id]] if pkg_id and pkg_id in _PKG_MAP else PACKAGES
    result = []
    for p in pkgs:
        try:
            installed, version = p["check"]()
        except Exception:
            installed, version = False, None

        # deps installed?
        deps_ok = all(
            _PKG_MAP[dep]["check"]()[0]
            for dep in p.get("depends", [])
            if dep in _PKG_MAP
        )

        # ถอนได้ไหม — ถ้ามี package อื่นที่ติดตั้งแล้วและ depends ตัวนี้อยู่ ต้องถอนตัวนั้นก่อน
        blocking_dependents = [
            other["name"]
            for other in PACKAGES
            if other["id"] != p["id"]
            and p["id"] in other.get("depends", [])
            and _safe_check(other)[0]
        ]

        # กำลังติดตั้ง/ถอนอยู่ไหม — ให้ UI แสดง state ได้ถูกต้องแม้ refresh หน้าใหม่ระหว่างดำเนินการ
        busy = "install" if is_installing(p["id"]) else ("uninstall" if is_uninstalling(p["id"]) else None)

        result.append({
            "id":          p["id"],
            "name":        p["name"],
            "description": p["description"],
            "logo":        p["logo"],
            "category":    p["category"],
            "depends":     p.get("depends", []),
            "children":    p.get("children", []),
            "installed":   installed,
            "version":     version,
            "deps_ok":     deps_ok,
            "can_uninstall":       len(blocking_dependents) == 0,
            "uninstall_blockers":  blocking_dependents,
            "uninstall_warning":   p.get("uninstall_warning"),
            "busy":        busy,
        })
    return result


# ---------------------------------------------------------------------------
# Streaming installer / uninstaller
# ---------------------------------------------------------------------------
#
# Queue item shapes (None = sentinel แปลว่า action จบแล้ว):
#   {"type": "progress", "step": int, "total": int, "cmd": str}
#   {"type": "line", "text": str}

_QueueItem = dict[str, Any] | None

_active_installs: dict[str, "queue.Queue[_QueueItem]"] = {}
_active_uninstalls: dict[str, "queue.Queue[_QueueItem]"] = {}
_install_lock = threading.Lock()


def start_install(pkg_id: str) -> tuple[bool, str]:
    """
    เริ่ม install ใน background thread.
    Returns (ok, error_msg)
    """
    if pkg_id not in _PKG_MAP:
        return False, f"Unknown package: {pkg_id}"

    with _install_lock:
        if pkg_id in _active_installs or pkg_id in _active_uninstalls:
            return False, "มีการติดตั้ง/ถอนการติดตั้งรายการนี้อยู่แล้ว"

    pkg = _PKG_MAP[pkg_id]

    # ตรวจ deps
    for dep_id in pkg.get("depends", []):
        dep = _PKG_MAP.get(dep_id)
        if dep:
            installed, _ = dep["check"]()
            if not installed:
                dep_name = dep["name"]
                return False, f"ต้องติดตั้ง {dep_name} ก่อน"

    q: "queue.Queue[_QueueItem]" = queue.Queue()
    with _install_lock:
        _active_installs[pkg_id] = q

    def _run() -> None:
        try:
            _run_commands(pkg.get("install_cmds", []), q, stop_on_error=True)
        finally:
            with _install_lock:
                _active_installs.pop(pkg_id, None)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return True, ""


def start_uninstall(pkg_id: str) -> tuple[bool, str]:
    """
    เริ่ม uninstall ใน background thread.
    Returns (ok, error_msg)
    """
    if pkg_id not in _PKG_MAP:
        return False, f"Unknown package: {pkg_id}"

    with _install_lock:
        if pkg_id in _active_installs or pkg_id in _active_uninstalls:
            return False, "มีการติดตั้ง/ถอนการติดตั้งรายการนี้อยู่แล้ว"

    pkg = _PKG_MAP[pkg_id]

    # ห้ามถอนถ้ามี package อื่นที่ติดตั้งแล้วและต้องพึ่งพาตัวนี้อยู่
    dependents = [
        other["name"]
        for other in PACKAGES
        if other["id"] != pkg_id
        and pkg_id in other.get("depends", [])
        and _safe_check(other)[0]
    ]
    if dependents:
        return False, f"ต้องถอนการติดตั้ง {', '.join(dependents)} ก่อน"

    q: "queue.Queue[_QueueItem]" = queue.Queue()
    with _install_lock:
        _active_uninstalls[pkg_id] = q

    def _run() -> None:
        try:
            _run_commands(pkg.get("uninstall_cmds", []), q, stop_on_error=False)
        finally:
            with _install_lock:
                _active_uninstalls.pop(pkg_id, None)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return True, ""


def _run_commands(cmds: list[list[str]], q: "queue.Queue[_QueueItem]", stop_on_error: bool) -> None:
    """
    รันคำสั่งทีละตัว พร้อมส่ง progress + output เข้า queue

    stop_on_error=True  → คำสั่งใดล้มเหลว หยุดทันที (install — ต้องสำเร็จทุกขั้นตอน)
    stop_on_error=False → คำสั่งใดล้มเหลว ข้ามไปขั้นถัดไป (uninstall — best-effort เหมือน `apt purge` ที่
                           ไม่ควรพังทั้ง flow แค่เพราะ package ไม่ได้ติดตั้งอยู่แล้ว)
    """
    total = len(cmds)
    try:
        for i, cmd in enumerate(cmds):
            q.put({"type": "progress", "step": i, "total": total, "cmd": " ".join(cmd)})
            q.put({"type": "line", "text": f"\n\x1b[36m$ {' '.join(cmd)}\x1b[0m"})
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=_clean_env(),
                )
                for line in proc.stdout:  # type: ignore[union-attr]
                    q.put({"type": "line", "text": line.rstrip()})
                proc.wait()
                if proc.returncode != 0:
                    if stop_on_error:
                        q.put({"type": "line", "text": f"\x1b[31m✗ Exit code {proc.returncode}\x1b[0m"})
                        q.put(None)  # sentinel
                        return
                    q.put({"type": "line", "text": f"\x1b[33m⚠ Exit code {proc.returncode} (ข้ามไปขั้นถัดไป)\x1b[0m"})
            except Exception as exc:
                if stop_on_error:
                    q.put({"type": "line", "text": f"\x1b[31m[error] {exc}\x1b[0m"})
                    q.put(None)
                    return
                q.put({"type": "line", "text": f"\x1b[33m[warn] {exc}\x1b[0m"})
        q.put({"type": "progress", "step": total, "total": total, "cmd": ""})
        q.put(None)  # all done — sentinel
    except Exception as exc:
        q.put({"type": "line", "text": f"\x1b[31m[fatal] {exc}\x1b[0m"})
        q.put(None)


def get_install_queue(pkg_id: str) -> "queue.Queue[_QueueItem] | None":
    with _install_lock:
        return _active_installs.get(pkg_id)


def get_uninstall_queue(pkg_id: str) -> "queue.Queue[_QueueItem] | None":
    with _install_lock:
        return _active_uninstalls.get(pkg_id)


def is_installing(pkg_id: str) -> bool:
    with _install_lock:
        return pkg_id in _active_installs


def is_uninstalling(pkg_id: str) -> bool:
    with _install_lock:
        return pkg_id in _active_uninstalls


def _clean_env() -> dict[str, str]:
    """Environment ที่ใช้รัน subprocess — ป้องกัน interactive prompts"""
    import os
    env = dict(os.environ)
    env["DEBIAN_FRONTEND"] = "noninteractive"
    env["APT_LISTCHANGES_FRONTEND"] = "none"
    env["TERM"] = "xterm-256color"
    return env
