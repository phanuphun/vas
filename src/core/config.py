import re
from dataclasses import dataclass
from pathlib import Path


_FALLBACK_VERSION = "0.1.0"


def _read_pyproject_version(fallback: str) -> str:
    """อ่าน version จาก pyproject.toml (single source of truth ที่เดียวสำหรับทั้ง

    package version, CLI --version, และเวอร์ชั่นที่แสดงในหน้า "อัปเดตระบบ")

    ใช้ regex แบบเจาะจงเฉพาะ key `version` ใต้ [project] แทนการพึ่ง `tomllib`
    (Python 3.11+) เพราะเครื่องเป้าหมาย (Ubuntu 22.04 jammy) มาพร้อม Python 3.10
    เป็นค่าเริ่มต้น — pyproject.toml ถูกก็อปปี้ไปพร้อม repo ตอน self-update อยู่แล้ว
    (`shutil.copytree(source_dir, install_dir)` ใน services/updater.py) จึงมีให้
    อ่านทั้งตอน dev และตอนติดตั้งจริงที่ /opt/vending-auto-setup
    """
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        text = pyproject_path.read_text(encoding="utf-8")
    except OSError:
        return fallback

    in_project_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project_section = stripped == "[project]"
            continue
        if in_project_section:
            match = re.match(r'version\s*=\s*"([^"]+)"', stripped)
            if match:
                return match.group(1)
    return fallback


APP_VERSION = _read_pyproject_version(_FALLBACK_VERSION)


@dataclass(frozen=True)
class InstallConfig:
    node_major: int = 22
    docker_version: str | None = None
    git_version: str | None = None
    ubuntu_codename: str = "jammy"
    docker_packages: tuple[str, ...] = (
        "docker-ce",
        "docker-ce-cli",
        "containerd.io",
        "docker-buildx-plugin",
        "docker-compose-plugin",
    )


DEFAULT_CONFIG = InstallConfig()


from pathlib import Path as _Path

QR_UDEV_RULE_PATH = _Path("/etc/udev/rules.d/99-qr500-bm.rules")
QR_UDEV_SIGNATURE = "# managed by vas"


def qr_config_dir() -> _Path:
    """Return ~/.config/vas/ ของ user จริง (รองรับ sudo)"""
    from system.status import _effective_home  # import late เพื่อหลีกเสี่ยง circular
    return _effective_home() / ".config" / "vas"


def qr_config_path() -> _Path:
    """Return ~/.config/vas/qr_config.json ของ user จริง"""
    return qr_config_dir() / "qr_config.json"
