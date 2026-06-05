from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from server import (
    DisplayDevices,
    build_install_commands,
    build_reset_commands,
    build_server_commands,
    build_wireguard_commands,
    create_app,
    parse_xinput_touch_devices,
    parse_xrandr_outputs,
    validate_display_apply,
)
from status import (
    DisplaySessionConfigStatus,
    DisplaySessionScriptStatus,
    DisplaySessionStatus,
    RemoteAccessStatus,
    ToolStatus,
    VpnStatus,
    WebServerStatus,
    XorgTouchscreenConfigStatus,
)


def test_command_previews_are_allowlisted_vas_commands() -> None:
    install_commands = build_install_commands()
    reset_commands = build_reset_commands()
    wireguard_commands = build_wireguard_commands()
    server_commands = build_server_commands()

    assert any(command.command == "sudo vas install --component all" for command in install_commands)
    assert any(command.command == "sudo vas install --component anydesk" for command in install_commands)
    assert any(command.command == "sudo vas reset --component docker" for command in reset_commands)
    assert any(command.command == "sudo vas reset --component anydesk" for command in reset_commands)
    assert any(command.command == "sudo vas wireguard sync --name wg0" for command in wireguard_commands)
    assert any(command.command == "sudo vas server start --host 0.0.0.0 --port 8888" for command in server_commands)
    assert all(";" not in command.command for command in (*install_commands, *reset_commands, *wireguard_commands, *server_commands))


def test_dashboard_route_renders_status_and_command_preview() -> None:
    app = create_app()

    with _patched_status_collectors():
        response = app.test_client().get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Core Tools" in body
    assert "VPN" in body
    assert "Remote" in body
    assert "123456789" in body
    assert "Web Server" in body
    assert "sudo vas install --component all" in body
    assert "sudo vas wireguard sync --name wg0" in body
    assert "http://0.0.0.0:8888" in body


def test_health_route_returns_ok() -> None:
    response = create_app().test_client().get("/health")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_display_route_renders_monitor_controls() -> None:
    app = create_app()

    with patch("server.collect_display_devices", return_value=DisplayDevices(("HDMI-1",), ("Vending Touchscreen",))):
        response = app.test_client().get("/display")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Monitor Setting" in body
    assert "HDMI-1" in body
    assert "Vending Touchscreen" in body
    assert "Command Preview" in body


def test_display_device_parsers_extract_outputs_and_touchscreens() -> None:
    outputs = parse_xrandr_outputs(
        "HDMI-1 connected primary 1920x1080+0+0\n"
        "DP-1 disconnected\n"
        "Virtual1 connected 1280x720+0+0\n"
    )
    touches = parse_xinput_touch_devices("Virtual core keyboard\nVending Touchscreen\nUSB Mouse\n")

    assert outputs == ("HDMI-1", "Virtual1")
    assert touches == ("Vending Touchscreen",)


def test_display_apply_validation_rejects_unknown_values() -> None:
    devices = DisplayDevices(outputs=("HDMI-1",), touch_devices=("Vending Touchscreen",))

    errors = validate_display_apply("DP-1", "Mouse", "sideways", devices)

    assert "Unsupported rotation: sideways" in errors
    assert "Display output is not connected: DP-1" in errors
    assert "Touchscreen device is not available: Mouse" in errors


def _patched_status_collectors() -> Any:
    return patch.multiple(
        "server",
        collect_status=lambda: (
            ToolStatus("Git", "git", True, "git version 2.34.1", "/usr/bin/git"),
            ToolStatus("Docker", "docker", True, "Docker version 29.5.3", "/usr/bin/docker"),
        ),
        collect_display_session_status=lambda: DisplaySessionStatus("x11", True, "XDG_SESSION_TYPE"),
        collect_display_session_config_status=lambda: DisplaySessionConfigStatus(Path("/home/first/.xprofile"), True, True),
        collect_display_session_script_status=lambda: DisplaySessionScriptStatus(
            Path("/home/first/.config/vending-auto-setup/display-session.sh"),
            True,
            True,
            True,
        ),
        collect_xorg_touchscreen_config_status=lambda: XorgTouchscreenConfigStatus(
            Path("/etc/X11/xorg.conf.d/99-vending-touchscreen.conf"),
            True,
            True,
        ),
        collect_remote_access_status=lambda: RemoteAccessStatus(
            anydesk_installed=True,
            anydesk_version="anydesk version 7.1.0",
            anydesk_id="123456789",
            anydesk_status="online",
            service_enabled="enabled",
            service_active="active",
        ),
        collect_vpn_status=lambda: VpnStatus(
            interface_name="wg0",
            wg_installed=True,
            wg_version="wireguard-tools v1.0.0",
            app_config_path=Path("/home/first/.config/vending-auto-setup/wireguard/configs/wg0.conf"),
            app_config_exists=True,
            active_config_path=Path("/etc/wireguard/wg0.conf"),
            active_config_exists=True,
            history_dir=Path("/home/first/.config/vending-auto-setup/wireguard/history/wg0"),
            history_exists=True,
            service_enabled="enabled",
            service_active="active",
            interface_exists=True,
            handshake_peers=1,
        ),
        collect_web_server_status=lambda: WebServerStatus(
            host="0.0.0.0",
            port=8888,
            url="http://0.0.0.0:8888",
            service_enabled="enabled",
            service_active="active",
        ),
    )
