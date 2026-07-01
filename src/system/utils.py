from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Callable, cast

from core.runner import CommandRunner


def require_linux() -> None:
    if platform.system().lower() != "linux":
        raise RuntimeError("This installer is intended for Ubuntu Linux.")


def require_root() -> None:
    geteuid = cast("Callable[[], int] | None", getattr(os, "geteuid", None))
    if geteuid is None or geteuid() != 0:
        raise RuntimeError("Run this installer as root, for example: sudo vending-auto-setup install")


def detect_ubuntu_codename() -> str:
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return "jammy"

    values: dict[str, str] = {}
    for line in os_release.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key] = raw_value.strip().strip('"')

    return values.get("VERSION_CODENAME", "jammy")


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
