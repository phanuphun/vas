from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from core.runner import CommandRunner
from mcp.service import (
    MCP_VALID_ACTIONS,
    McpConfig,
    default_mcp_config,
    runtime_ready,
    service_action,
)
from system.status import MCP_TOOL_MODULES, McpStatus, collect_mcp_status


# ---------------------------------------------------------------------------
# collect_mcp_status() — dev-fake mode (VAS_DEV_FAKE_INSTALLED=1)
# ---------------------------------------------------------------------------

def test_collect_mcp_status_dev_fake_mode_reports_everything_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAS_DEV_FAKE_INSTALLED", "1")
    status = collect_mcp_status()

    assert status.runtime_installed is True
    assert status.service_installed is True
    assert status.service_enabled == "enabled"
    assert status.service_active == "active"
    assert status.host == "0.0.0.0"
    assert status.port == 8899
    assert status.url == "http://0.0.0.0:8899"
    assert status.tool_modules == MCP_TOOL_MODULES
    assert "shell" in status.tool_modules  # run_command tool ต้องอยู่ใน catalog เสมอ


# ---------------------------------------------------------------------------
# collect_mcp_status() — real mode (ไม่มี VAS_DEV_FAKE_INSTALLED)
# ---------------------------------------------------------------------------

def test_collect_mcp_status_real_mode_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAS_DEV_FAKE_INSTALLED", raising=False)
    fake_path = Mock()
    fake_path.exists.return_value = False

    with patch("mcp.service.runtime_ready", return_value=False), \
         patch("mcp.service.MCP_SERVICE_PATH", fake_path), \
         patch("system.status._read_command_first_line", return_value="unknown"):
        status = collect_mcp_status()

    assert status.runtime_installed is False
    assert status.service_installed is False
    assert status.service_enabled == "unknown"
    assert status.service_active == "unknown"


def test_collect_mcp_status_real_mode_enabled_and_active(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAS_DEV_FAKE_INSTALLED", raising=False)
    fake_path = Mock()
    fake_path.exists.return_value = True

    def fake_first_line(args: object) -> str:
        cmd = " ".join(args)  # type: ignore[arg-type]
        if "is-enabled" in cmd:
            return "enabled"
        if "is-active" in cmd:
            return "active"
        return "unknown"

    with patch("mcp.service.runtime_ready", return_value=True), \
         patch("mcp.service.MCP_SERVICE_PATH", fake_path), \
         patch("system.status._read_command_first_line", side_effect=fake_first_line):
        status = collect_mcp_status()

    assert status.runtime_installed is True
    assert status.service_installed is True
    assert status.service_enabled == "enabled"
    assert status.service_active == "active"


def test_mcp_status_is_frozen_dataclass() -> None:
    status = McpStatus(
        runtime_installed=True, service_installed=True, service_enabled="enabled",
        service_active="active", host="0.0.0.0", port=8899, url="http://0.0.0.0:8899",
        tool_modules=("system",),
    )
    with pytest.raises(Exception):
        status.port = 9000  # type: ignore[misc]


# ---------------------------------------------------------------------------
# runtime_ready()
# ---------------------------------------------------------------------------

def test_runtime_ready_true_when_all_packages_importable() -> None:
    with patch("mcp.service._can_import", return_value=True):
        assert runtime_ready() is True


def test_runtime_ready_false_when_any_package_missing() -> None:
    with patch("mcp.service._can_import", side_effect=lambda p: p != "uvicorn"):
        assert runtime_ready() is False


# ---------------------------------------------------------------------------
# service_action()
# ---------------------------------------------------------------------------

def test_service_action_rejects_unknown_action() -> None:
    with pytest.raises(ValueError):
        service_action(CommandRunner(dry_run=True), "delete-everything")


@pytest.mark.parametrize("action", MCP_VALID_ACTIONS)
def test_service_action_accepts_all_valid_actions_in_dry_run(action: str) -> None:
    ok, message = service_action(CommandRunner(dry_run=True), action)
    assert ok is True
    assert message  # ข้อความไม่ว่าง


def test_service_action_enable_message_includes_url() -> None:
    cfg = McpConfig(host="0.0.0.0", port=8899)
    ok, message = service_action(CommandRunner(dry_run=True), "enable", config=cfg)
    assert ok is True
    assert cfg.url in message


def test_service_action_disable_calls_stop_not_start(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_stop(self: object) -> None:
        calls.append("stop")

    def fake_start(self: object, config: object) -> None:
        calls.append("start")

    with patch("mcp.service.McpServiceManager.stop", fake_stop), \
         patch("mcp.service.McpServiceManager.start", fake_start):
        service_action(CommandRunner(dry_run=True), "disable")

    assert calls == ["stop"]


def test_service_action_enable_and_restart_both_call_start(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_start(self: object, config: object) -> None:
        calls.append("start")

    with patch("mcp.service.McpServiceManager.start", fake_start):
        service_action(CommandRunner(dry_run=True), "enable")
        service_action(CommandRunner(dry_run=True), "restart")

    assert calls == ["start", "start"]


def test_default_mcp_config_matches_mcp_port() -> None:
    cfg = default_mcp_config()
    assert cfg.port == 8899
    assert cfg.host == "0.0.0.0"
    assert cfg.url == "http://0.0.0.0:8899"


# ---------------------------------------------------------------------------
# CommandRunner dry_run sanity — service_action() ต้องไม่รันคำสั่งจริงเมื่อ dry_run=True
# ---------------------------------------------------------------------------

def test_service_action_dry_run_never_executes_real_subprocess() -> None:
    runner = CommandRunner(dry_run=True)
    with patch("subprocess.run") as mock_run:
        service_action(runner, "enable")
        service_action(runner, "restart")
        service_action(runner, "disable")
    mock_run.assert_not_called()
