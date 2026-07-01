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
                "| gpg --dearmor -o /usr/share/keyrings/nodesource.gpg",
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
                "| gpg --dearmor -o /usr/share/keyrings/anydesk.gpg",
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
    },
]

# id → package dict lookup
_PKG_MAP: dict[str, dict[str, Any]] = {p["id"]: p for p in PACKAGES}

CATEGORIES: dict[str, str] = {
    "core":     "Core Tools",
    "runtime":  "Runtime",
    "network":  "Network",
    "remote":   "Remote Access",
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
        })
    return result


# ---------------------------------------------------------------------------
# Streaming installer
# ---------------------------------------------------------------------------

_active_installs: dict[str, queue.Queue[str | None]] = {}
_install_lock = threading.Lock()


def start_install(pkg_id: str) -> tuple[bool, str]:
    """
    เริ่ม install ใน background thread.
    Returns (ok, error_msg)
    """
    if pkg_id not in _PKG_MAP:
        return False, f"Unknown package: {pkg_id}"

    with _install_lock:
        if pkg_id in _active_installs:
            return False, "Installation already in progress"

    pkg = _PKG_MAP[pkg_id]

    # ตรวจ deps
    for dep_id in pkg.get("depends", []):
        dep = _PKG_MAP.get(dep_id)
        if dep:
            installed, _ = dep["check"]()
            if not installed:
                dep_name = dep["name"]
                return False, f"ต้องติดตั้ง {dep_name} ก่อน"

    q: queue.Queue[str | None] = queue.Queue()
    with _install_lock:
        _active_installs[pkg_id] = q

    def _run() -> None:
        cmds = pkg.get("install_cmds", [])
        try:
            for cmd in cmds:
                q.put(f"\n\x1b[36m$ {' '.join(cmd)}\x1b[0m")
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
                        q.put(line.rstrip())
                    proc.wait()
                    if proc.returncode != 0:
                        q.put(f"\x1b[31m✗ Exit code {proc.returncode}\x1b[0m")
                        q.put(None)  # sentinel
                        return
                except Exception as exc:
                    q.put(f"\x1b[31m[error] {exc}\x1b[0m")
                    q.put(None)
                    return
            q.put(None)  # all done — sentinel ส่งสัญญาณว่าติดตั้งครบ
        except Exception as exc:
            q.put(f"\x1b[31m[fatal] {exc}\x1b[0m")
            q.put(None)
        finally:
            with _install_lock:
                _active_installs.pop(pkg_id, None)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return True, ""


def get_install_queue(pkg_id: str) -> "queue.Queue[str | None] | None":
    with _install_lock:
        return _active_installs.get(pkg_id)


def is_installing(pkg_id: str) -> bool:
    with _install_lock:
        return pkg_id in _active_installs


def _clean_env() -> dict[str, str]:
    """Environment ที่ใช้รัน subprocess — ป้องกัน interactive prompts"""
    import os
    env = dict(os.environ)
    env["DEBIAN_FRONTEND"] = "noninteractive"
    env["APT_LISTCHANGES_FRONTEND"] = "none"
    env["TERM"] = "xterm-256color"
    return env
