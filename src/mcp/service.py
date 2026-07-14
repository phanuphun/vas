from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

from core.runner import CommandRunner


MCP_PORT = 8899
MCP_RUNTIME_PACKAGES = ("fastmcp", "uvicorn")

MCP_SERVICE_NAME = "vending-auto-setup-mcp"
MCP_SERVICE_UNIT = f"{MCP_SERVICE_NAME}.service"
MCP_SERVICE_PATH = Path("/etc/systemd/system") / MCP_SERVICE_UNIT
MCP_BIN = "/usr/local/bin/vas"

# action ที่หน้าเว็บ /mcp เรียกผ่าน POST /api/mcp/action ได้ — "enable" ทำ install+enable+start
# ครบในตัว (ดู McpServiceManager.start), "disable" คือ systemctl disable --now, "restart" เรียก
# start() ซ้ำ (idempotent — เขียน unit file/ensure package ซ้ำได้ปลอดภัย แล้ว restart จริง)
MCP_VALID_ACTIONS = ("enable", "disable", "restart")


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
            self.runner.run([sys.executable, "-m", "pip", "install", *missing], stream=True)

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
    runner.run(["apt-get", "install", "-y", "python3-pip"], stream=True)


def _can_import(package: str) -> bool:
    return importlib.util.find_spec(package) is not None


def runtime_ready() -> bool:
    """True ถ้า MCP_RUNTIME_PACKAGES (fastmcp, uvicorn) ติดตั้งครบแล้ว — เรียกจาก
    system.status.collect_mcp_status() เพื่อแสดงสถานะในหน้าเว็บ ไม่ต้อง import fastmcp จริง
    (แค่เช็คว่ามี module spec เท่านั้น) จึงไม่โดน collision กับ pip package "mcp" ที่ fastmcp พึ่งพา
    (ดู docstring บนสุดของ core/exec_guard.py สำหรับรายละเอียดปัญหานั้น)"""
    return all(_can_import(package) for package in MCP_RUNTIME_PACKAGES)


def service_action(runner: CommandRunner, action: str, config: McpConfig | None = None) -> tuple[bool, str]:
    """Web-friendly wrapper รอบ McpServiceManager — ใช้กับปุ่มควบคุม service ในหน้า /mcp

    action ต้องเป็นหนึ่งใน MCP_VALID_ACTIONS — raise ValueError ถ้าไม่ใช่ (pattern เดียวกับ
    features.remote.openssh.service_action) คืน (True, ข้อความสำเร็จ) เสมอถ้าไม่มี exception —
    ความล้มเหลวจริง (systemctl/pip ล้มเหลว) จะ propagate เป็น CommandExecutionError ให้ route
    handler จับแทน (ดู openssh_action_api ใน server.py เป็นตัวอย่าง)
    """
    if action not in MCP_VALID_ACTIONS:
        raise ValueError(f"Unknown MCP action: {action}")

    cfg = config or default_mcp_config()
    manager = McpServiceManager(runner)

    if action == "enable":
        manager.start(cfg)
        return True, f"เปิดใช้งาน MCP server เรียบร้อย — {cfg.url}"
    if action == "disable":
        manager.stop()
        return True, "ปิดใช้งาน MCP server เรียบร้อย"
    # action == "restart" — start() เขียน unit file/ensure package ซ้ำได้แบบ idempotent
    # แล้วค่อย systemctl restart จริงท้ายสุด จึงใช้แทน restart เดี่ยวๆ ได้ปลอดภัย
    manager.start(cfg)
    return True, "รีสตาร์ท MCP server เรียบร้อย"
