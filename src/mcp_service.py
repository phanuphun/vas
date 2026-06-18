from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

from runner import CommandRunner


MCP_PORT = 8899
MCP_RUNTIME_PACKAGES = ("fastmcp", "uvicorn")

MCP_SERVICE_NAME = "vending-auto-setup-mcp"
MCP_SERVICE_UNIT = f"{MCP_SERVICE_NAME}.service"
MCP_SERVICE_PATH = Path("/etc/systemd/system") / MCP_SERVICE_UNIT
MCP_BIN = "/usr/local/bin/vas"


@dataclass(frozen=True)
class McpConfig:
    host: str
    port: int

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def default_mcp_config() -> McpConfig:
    return McpConfig(host="0.0.0.0", port=MCP_PORT)


class McpServiceManager:
    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def ensure_runtime_packages(self) -> None:
        for package in MCP_RUNTIME_PACKAGES:
            print(f"ensure {package}")
        if self.runner.dry_run:
            return
        _ensure_pip(self.runner)
        missing = [p for p in MCP_RUNTIME_PACKAGES if not _can_import(p)]
        if missing:
            self.runner.run([sys.executable, "-m", "pip", "install", *missing])

    def install(self, config: McpConfig) -> None:
        self.ensure_runtime_packages()
        print(f"write {MCP_SERVICE_PATH.as_posix()}")
        print("systemctl daemon-reload")
        print(f"systemctl enable {MCP_SERVICE_UNIT}")
        if self.runner.dry_run:
            return
        MCP_SERVICE_PATH.write_text(render_mcp_service_file(config), encoding="utf-8")
        MCP_SERVICE_PATH.chmod(0o644)
        self.runner.run(["systemctl", "daemon-reload"])
        self.runner.run(["systemctl", "enable", MCP_SERVICE_UNIT])

    def start(self, config: McpConfig) -> None:
        self.install(config)
        print(f"systemctl restart {MCP_SERVICE_UNIT}")
        if self.runner.dry_run:
            return
        self.runner.run(["systemctl", "restart", MCP_SERVICE_UNIT])
        print(f"MCP server started at {config.url}")

    def stop(self) -> None:
        self.runner.run(["systemctl", "disable", "--now", MCP_SERVICE_UNIT], check=False)

    def status(self) -> None:
        result = self.runner.run(["systemctl", "status", MCP_SERVICE_UNIT, "--no-pager"], check=False)
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip())


def render_mcp_service_file(config: McpConfig | None = None) -> str:
    cfg = config or default_mcp_config()
    return (
        "[Unit]\n"
        "Description=Vending Auto Setup MCP server\n"
        "After=network.target vending-auto-setup-server.service\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={MCP_BIN} mcp run --host {cfg.host} --port {cfg.port}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def _ensure_pip(runner: CommandRunner) -> None:
    """Bootstrap pip if it is not available as a module."""
    result = runner.run([sys.executable, "-m", "pip", "--version"], check=False)
    if result.returncode == 0:
        return
    # Try ensurepip first (no network required)
    result = runner.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=False)
    if result.returncode == 0:
        return
    # Fall back to apt-get
    runner.run(["apt-get", "install", "-y", "python3-pip"])


def _can_import(package: str) -> bool:
    return importlib.util.find_spec(package) is not None
