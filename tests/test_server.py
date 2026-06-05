from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from pytest import MonkeyPatch

from display import TouchDevice, parse_xinput_device_map
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

VALID_WIREGUARD_CONFIG = """\
[Interface]
PrivateKey = interface-secret
Address = 10.8.0.13/24

[Peer]
PublicKey = peer-public
PresharedKey = peer-secret
AllowedIPs = 10.8.0.0/24
Endpoint = vpn.example.com:51820
"""


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


def test_dashboard_route_renders_status_without_command_preview() -> None:
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
    assert "sudo vas install --component all" not in body
    assert "sudo vas wireguard sync --name wg0" not in body
    assert "http://0.0.0.0:8888" in body


def test_health_route_returns_ok() -> None:
    response = create_app().test_client().get("/health")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_display_route_renders_monitor_controls() -> None:
    app = create_app()

    mock_devices = DisplayDevices(("HDMI-1",), (TouchDevice("Vending Touchscreen", 13),))
    with patch("server.collect_display_devices", return_value=mock_devices):
        response = app.test_client().get("/display")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Monitor Setting" in body
    assert "HDMI-1" in body
    assert "Vending Touchscreen" in body
    assert "id: 13" in body
    assert "Command Preview" in body


def test_command_docs_route_renders_command_sections() -> None:
    response = create_app().test_client().get("/commands")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Command Docs" in body
    assert "sudo vas install --component all" in body
    assert "sudo vas reset --component docker" in body
    assert "sudo vas wireguard sync --name wg0" in body
    assert "sudo vas server start --host 0.0.0.0 --port 8888" in body


def test_wireguard_config_api_validates_saves_and_deletes_config(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))
    app = create_app()
    client = app.test_client()

    validate_response = client.post(
        "/api/wireguard/validate",
        json={"name": "wg0", "content": VALID_WIREGUARD_CONFIG},
    )
    assert validate_response.status_code == 200
    validate_json = cast(dict[str, Any], validate_response.json)
    assert validate_json["validation"]["valid"] is True

    save_response = client.post(
        "/api/wireguard/config",
        json={"name": "wg0", "content": VALID_WIREGUARD_CONFIG},
    )
    assert save_response.status_code == 200
    save_json = cast(dict[str, Any], save_response.json)
    saved_path = Path(save_json["path"])
    assert saved_path.read_text(encoding="utf-8") == VALID_WIREGUARD_CONFIG

    get_response = client.get("/api/wireguard/config?name=wg0")
    assert get_response.status_code == 200
    get_json = cast(dict[str, Any], get_response.json)
    assert get_json["exists"] is True
    assert get_json["content"] == VALID_WIREGUARD_CONFIG

    delete_response = client.delete("/api/wireguard/config?name=wg0")
    assert delete_response.status_code == 200
    assert not saved_path.exists()


def test_wireguard_history_api_masks_and_validates_entries(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))
    history = tmp_path / "config-home" / "vending-auto-setup" / "wireguard" / "history" / "wg0"
    history.mkdir(parents=True)
    snapshot = history / "20260604T120000Z-sync.conf"
    snapshot.write_text(VALID_WIREGUARD_CONFIG, encoding="utf-8")

    client = create_app().test_client()
    response = client.get("/api/wireguard/history?name=wg0")

    assert response.status_code == 200
    history_json = cast(dict[str, Any], response.json)
    assert history_json["entries"][0]["id"] == "20260604T120000Z-sync"
    assert history_json["entries"][0]["valid"] is True

    show_response = client.get("/api/wireguard/history/20260604T120000Z-sync?name=wg0")
    assert show_response.status_code == 200
    show_json = cast(dict[str, Any], show_response.json)
    assert "PrivateKey = <hidden>" in show_json["content"]
    assert "PresharedKey = <hidden>" in show_json["content"]
    assert "interface-secret" not in show_json["content"]

    delete_response = client.delete("/api/wireguard/history/20260604T120000Z-sync?name=wg0")
    assert delete_response.status_code == 200
    assert not snapshot.exists()


def test_display_devices_api_uses_requested_x_display() -> None:
    app = create_app()

    mock_devices = DisplayDevices(("HDMI-1",), (TouchDevice("Vending Touchscreen", 13),))
    with patch("server.collect_display_devices", return_value=mock_devices) as collect:
        response = app.test_client().get("/api/display/devices?display=:1")

    assert response.status_code == 200
    assert response.json == {
        "outputs": ["HDMI-1"],
        "touchDevices": [{"name": "Vending Touchscreen", "id": 13}],
        "defaultDisplay": ":1",
    }
    collect.assert_called_once_with(x_display=":1")


def test_display_device_parsers_extract_outputs_and_touchscreens() -> None:
    outputs = parse_xrandr_outputs(
        "HDMI-1 connected primary 1920x1080+0+0\n"
        "DP-1 disconnected\n"
        "Virtual1 connected 1280x720+0+0\n"
    )
    touches = parse_xinput_touch_devices("Virtual core keyboard\nVending Touchscreen\nUSB Mouse\n")

    assert outputs == ("HDMI-1", "Virtual1")
    assert touches == ("Vending Touchscreen",)


def test_xinput_parser_does_not_fallback_to_mouse_or_keyboard() -> None:
    touches = parse_xinput_touch_devices("Virtual core pointer\nUSB Mouse\nVirtual core keyboard\n")

    assert touches == ()


def test_parse_xinput_device_map_extracts_name_and_id() -> None:
    xinput_output = (
        "\u2561 Virtual core pointer                          id=2    [master pointer  (3)]\n"
        "\u255c   \u21b3 Virtual core XTEST pointer               id=4    [slave  pointer  (2)]\n"
        "\u255c   \u21b3 Vending Virtual Touchscreen              id=13   [slave  pointer  (2)]\n"
        "\u2563 Virtual core keyboard                         id=3    [master keyboard (2)]\n"
        "    \u21b3 Virtual core XTEST keyboard              id=5    [slave  keyboard (3)]\n"
    )
    device_map = parse_xinput_device_map(xinput_output)

    assert device_map["Vending Virtual Touchscreen"] == 13
    assert device_map["Virtual core pointer"] == 2
    assert device_map["Virtual core XTEST keyboard"] == 5


def test_display_apply_validation_uses_touch_device_names() -> None:
    devices = DisplayDevices(
        outputs=("HDMI-1",),
        touch_devices=(TouchDevice("Vending Touchscreen", 13),),
    )

    errors = validate_display_apply("HDMI-1", "Vending Touchscreen", "normal", devices)
    assert not any("Touchscreen" in e for e in errors)

    errors = validate_display_apply("HDMI-1", "Unknown Device", "normal", devices)
    assert any("Touchscreen device is not available" in e for e in errors)


def test_display_apply_validation_rejects_unknown_values() -> None:
    devices = DisplayDevices(
        outputs=("HDMI-1",),
        touch_devices=(TouchDevice("Vending Touchscreen", 13),),
    )

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
