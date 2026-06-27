from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path

from core.runner import CommandRunner


SERVICE_NAME = "vending-auto-setup-server"
SERVICE_UNIT = f"{SERVICE_NAME}.service"
SERVICE_PATH = Path("/etc/systemd/system") / SERVICE_UNIT
ENV_PATH = Path("/etc/default/vending-auto-setup-server")
RUNTIME_PACKAGES = ("python3-flask",)


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def default_server_config() -> ServerConfig:
    return ServerConfig(host="127.0.0.1", port=8080)


class ServerServiceManager:
    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def ensure_runtime_packages(self) -> None:
        for package in RUNTIME_PACKAGES:
            print(f"ensure {package}")
        if self.runner.dry_run:
            return
        if not can_import_flask():
            self.runner.run(["apt-get", "update"])
            self.runner.run(["apt-get", "install", "-y", *RUNTIME_PACKAGES])

    def install(self, config: ServerConfig) -> None:
        self.ensure_runtime_packages()
        print(f"write {ENV_PATH.as_posix()}")
        print(f"write {SERVICE_PATH.as_posix()}")
        print("systemctl daemon-reload")
        print(f"systemctl enable {SERVICE_UNIT}")
        if self.runner.dry_run:
            return

        ENV_PATH.write_text(render_env_file(config), encoding="utf-8")
        ENV_PATH.chmod(0o644)
        SERVICE_PATH.write_text(render_service_file(), encoding="utf-8")
        SERVICE_PATH.chmod(0o644)
        self.runner.run(["systemctl", "daemon-reload"])
        self.runner.run(["systemctl", "enable", SERVICE_UNIT])

    def start(self, config: ServerConfig) -> None:
        self.install(config)
        print(f"systemctl restart {SERVICE_UNIT}")
        if self.runner.dry_run:
            return
        self.runner.run(["systemctl", "restart", SERVICE_UNIT])
        print(f"Dashboard service started at {config.url}")

    def stop(self) -> None:
        self.runner.run(["systemctl", "disable", "--now", SERVICE_UNIT], check=False)

    def status(self) -> None:
        result = self.runner.run(["systemctl", "status", SERVICE_UNIT, "--no-pager"], check=False)
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip())


def can_import_flask() -> bool:
    return importlib.util.find_spec("flask") is not None


def render_env_file(config: ServerConfig) -> str:
    return (
        "# Managed by vending-auto-setup. Manual edits may be overwritten.\n"
        f"HOME={_service_home().as_posix()}\n"
        f"VAS_SERVER_HOST={config.host}\n"
        f"VAS_SERVER_PORT={config.port}\n"
    )


def render_service_file() -> str:
    return (
        "[Unit]\n"
        "Description=Vending Auto Setup dashboard\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        "Environment=HOME=/root\n"
        "Environment=VAS_SERVER_HOST=127.0.0.1\n"
        "Environment=VAS_SERVER_PORT=8080\n"
        f"EnvironmentFile=-{ENV_PATH.as_posix()}\n"
        "ExecStart=/usr/local/bin/vas server run --host ${VAS_SERVER_HOST} --port ${VAS_SERVER_PORT}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def _service_home() -> Path:
    sudo_user = os.environ.get("SUDO_USER", "").strip()
    if sudo_user and sudo_user != "root":
        try:
            import pwd

            return Path(pwd.getpwnam(sudo_user).pw_dir)  # type: ignore[attr-defined]
        except (ImportError, KeyError):
            pass
    return Path.home()
