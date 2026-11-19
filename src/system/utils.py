from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Callable, cast

from core.runner import CommandRunner


def require_linux() -> None:
    if platform.system().lower() != "linux":
        raise RuntimeError("This installer is intended for Linux (Ubuntu/Debian).")


def require_root() -> None:
    geteuid = cast("Callable[[], int] | None", getattr(os, "geteuid", None))
    if geteuid is None or geteuid() != 0:
        raise RuntimeError("Run this installer as root, for example: sudo vending-auto-setup install")


def read_os_release(path: Path | None = None) -> dict[str, str]:
    os_release = path if path is not None else Path("/etc/os-release")
    if not os_release.exists():
        return {}

    values: dict[str, str] = {}
    for line in os_release.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key] = raw_value.strip().strip('"')

    return values


def detect_os_id(path: Path | None = None) -> str:
    """Return OS identifier (e.g. 'ubuntu', 'debian'). Defaults to 'ubuntu'."""
    values = read_os_release(path)
    os_id = values.get("ID", "").lower()
    if os_id in ("ubuntu", "debian"):
        return os_id
    id_like = values.get("ID_LIKE", "").lower().split()
    if "ubuntu" in id_like:
        return "ubuntu"
    if "debian" in id_like:
        return "debian"
    return os_id or "ubuntu"


def detect_os_codename(path: Path | None = None) -> str:
    """Return OS version codename (e.g. 'jammy', 'noble', 'bookworm', 'trixie')."""
    values = read_os_release(path)
    if "VERSION_CODENAME" in values and values["VERSION_CODENAME"]:
        return values["VERSION_CODENAME"]
    os_id = detect_os_id(path)
    return "bookworm" if os_id == "debian" else "jammy"


def detect_ubuntu_codename(path: Path | None = None) -> str:
    """Backward-compatible alias for detect_os_codename."""
    return detect_os_codename(path)


def command_exists(runner: CommandRunner, command: str) -> bool:
    result = runner.run(["bash", "-lc", f"command -v {command}"], check=False)
    return result.returncode == 0


def dev_fake_installed() -> bool:
    """
    Dev-only toggle — เมื่อตั้ง env var `VAS_DEV_FAKE_INSTALLED=1` ระบบจะรายงานว่าทุก
    package/service "ติดตั้งแล้วและทำงานอยู่" โดยไม่ต้องมี binary/systemd จริงในเครื่อง

    ใช้สำหรับทดสอบหน้าเว็บ/sidebar บนเครื่อง dev (เช่น Windows ผ่าน `dev.bat`) ที่ไม่มี
    apt package หรือ systemd จริง — ห้ามตั้งค่านี้บน production (systemd service ที่รันจริง
    ไม่ได้ set env var นี้อยู่แล้ว)
    """
    return os.environ.get("VAS_DEV_FAKE_INSTALLED", "").strip().lower() in ("1", "true", "yes")
