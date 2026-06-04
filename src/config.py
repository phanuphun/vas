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
