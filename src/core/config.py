from dataclasses import dataclass


APP_VERSION = "0.1.0"


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
