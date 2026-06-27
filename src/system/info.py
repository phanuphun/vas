from __future__ import annotations

import platform
from pathlib import Path


def collect_os_info() -> dict[str, str]:
    os_release = _read_os_release()
    return {
        "name": os_release.get("PRETTY_NAME", platform.platform()),
        "id": os_release.get("ID", "unknown"),
        "version_id": os_release.get("VERSION_ID", "unknown"),
        "codename": os_release.get("VERSION_CODENAME", "unknown"),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }


def print_os_info() -> None:
    info = collect_os_info()
    print("Vending Auto Setup POC")
    print(f"OS: {info['name']}")
    print(f"ID: {info['id']}")
    print(f"Version: {info['version_id']}")
    print(f"Codename: {info['codename']}")
    print(f"Kernel: {info['kernel']}")
    print(f"Machine: {info['machine']}")
    print(f"Python: {info['python']}")


def _read_os_release() -> dict[str, str]:
    path = Path("/etc/os-release")
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key] = raw_value.strip().strip('"')
    return values
