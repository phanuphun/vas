from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from pytest import MonkeyPatch

from display import TouchDevice, parse_xinput_device_map
from server import (
    DisplayDevices,
    build_display_commands,
    build_install_commands,
    build_reset_commands,
    build_server_commands,
    build_wireguard_commands,
    create_app,
    parse_xinput_touch_devices,
    parse_xrandr_outputs,
    validate_display_apply,
)
from status import GdmWaylandStatus

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
    display_commands = build_display_commands()
    wireguard_commands = build_wireguard_commands()
    server_commands = build_server_commands()

    assert any(command.command == "sudo vas install --component all" for command in install_commands)
    assert any(command.command == "sudo vas install --component anydesk" for command in install_commands)
    assert any(command.command == "sudo vas reset --component docker" for command in reset_commands)
    assert any(command.command == "sudo vas reset --component anydesk" for command in reset_commands)
    assert any(command.command == "vas display status --display :0" for command in display_commands)
    assert any(command.command == "sudo vas display disable-wayland" for command in display_commands)
    assert any(command.command == "sudo vas display enable-wayland" for command in display_commands)
    assert any(command.command.startswith("sudo vas display persist-xorg") for command in display_commands)
    assert any(command.command == "sudo vas wireguard sync --name wg0" for command in wireguard_commands)
    assert any(command.command == "sudo vas server start --host 0.0.0.0 --port 8888" for command in server_commands)
    assert all(
        ";" not in command.command
        for command in (*install_commands, *reset_commands, *display_commands, *wireguard_commands, *server_commands)
    )


def test_home_route_renders_monitor_page() -> None:
    app = create_app()

    response = app.test_client().get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "System Monitor" in body
    assert "/api/monitor/metrics" in body
    assert "sudo vas install --component all" not in body


def test_monitor_route_redirects_to_home() -> None:
    app = create_app()

    response = app.test_client().get("/monitor", follow_redirects=False)

    assert response.status_code in (301, 302)
    assert response.headers["Location"] == "/"


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
    assert "GDM Wayland" in body
    assert 'data-wayland-action="disable"' in body
    assert 'data-wayland-action="enable"' in body
    assert "Command Preview" in body


def test_display_wayland_api_runs_requested_action() -> None:
    app = create_app()

    with patch("server.DisplayConfigurator.disable_wayland") as disable:
        with patch("server.collect_gdm_wayland_status") as collect_status:
            collect_status.return_value = GdmWaylandStatus(
                path=Path("/etc/gdm3/custom.conf"),
                exists=True,
                readable=True,
                disabled=True,
                value="false",
            )
            response = app.test_client().post("/api/display/wayland", json={"action": "disable"})

    assert response.status_code == 200
    response_json = cast(dict[str, Any], response.json)
    assert response_json["status"] == "ok"
    assert cast(dict[str, Any], response_json["gdmWayland"])["disabled"] is True
    disable.assert_called_once()


def test_command_docs_route_renders_command_sections() -> None:
    response = create_app().test_client().get("/commands")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Command Docs" in body
    assert "sudo vas install --component all" in body
    assert "sudo vas reset --component docker" in body
    assert "vas display status --display :0" in body
    assert "sudo vas display disable-wayland" in body
    assert "sudo vas display enable-wayland" in body
    assert "sudo vas wireguard sync --name wg0" in body
    assert "sudo vas server start --host 0.0.0.0 --port 8888" in body


def test_logs_route_renders_system_snapshot_section(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))

    response = create_app().test_client().get("/logs")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "System Log Snapshots" in body
    assert "Program Usage Logs" not in body


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


