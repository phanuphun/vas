from pathlib import Path
from typing import Any
from unittest.mock import patch

from status import (
    DISPLAY_SESSION_SCRIPT_SIGNATURE,
    DISPLAY_SESSION_SIGNATURE,
    OpenSshStatus,
    RemoteAccessStatus,
    VpnStatus,
    XORG_TOUCHSCREEN_SIGNATURE,
    collect_gdm_wayland_status,
    collect_openssh_status,
    collect_remote_access_status,
    collect_vpn_status,
    collect_display_session_status,
    collect_display_session_config_status,
    collect_display_session_script_status,
    collect_xorg_touchscreen_config_status,
    main,
    print_status,
)


def test_vending_status_returns_zero_when_all_tools_exist(capsys: Any) -> None:
    with patch("status.shutil.which", return_value="/usr/bin/tool"):
        with patch("status._read_version", return_value="tool 1.0.0"):
            exit_code = main()

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "OK" in output
    assert "Git" in output
    assert "Docker" in output


def test_vending_status_returns_one_when_a_tool_is_missing(capsys: Any) -> None:
    def fake_which(command: str) -> str | None:
        return None if command == "docker" else f"/usr/bin/{command}"

    with patch("status.shutil.which", side_effect=fake_which):
        with patch("status._read_version", return_value="tool 1.0.0"):
            exit_code = main()

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "MISSING Docker" in output


def test_display_session_status_is_ok_for_x11() -> None:
    with patch.dict("status.os.environ", {"XDG_SESSION_TYPE": "x11"}, clear=True):
        status = collect_display_session_status()

    assert status.is_x11 is True
    assert status.session_type == "x11"


def test_display_session_status_warns_for_wayland() -> None:
    with patch.dict("status.os.environ", {"XDG_SESSION_TYPE": "wayland"}, clear=True):
        status = collect_display_session_status()

    assert status.is_x11 is False
    assert status.session_type == "wayland"


def test_gdm_wayland_status_is_ok_when_disabled(tmp_path) -> None:  # type: ignore[no-untyped-def]
    config_path = tmp_path / "custom.conf"
    config_path.write_text("[daemon]\nWaylandEnable=false\n", encoding="utf-8")

    status = collect_gdm_wayland_status(config_path)

    assert status.exists is True
    assert status.readable is True
    assert status.disabled is True
    assert status.value == "false"


def test_gdm_wayland_status_warns_when_default_enabled(tmp_path) -> None:  # type: ignore[no-untyped-def]
    config_path = tmp_path / "custom.conf"
    config_path.write_text("[daemon]\n#WaylandEnable=false\n", encoding="utf-8")

    status = collect_gdm_wayland_status(config_path)

    assert status.exists is True
    assert status.readable is True
    assert status.disabled is False
    assert status.value is None


def test_xorg_touchscreen_config_status_warns_when_file_is_missing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    status = collect_xorg_touchscreen_config_status(tmp_path / "99-vending-touchscreen.conf")

    assert status.exists is False
    assert status.has_signature is False


def test_xorg_touchscreen_config_status_warns_when_signature_is_missing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    config_path = tmp_path / "99-vending-touchscreen.conf"
    config_path.write_text('Section "InputClass"\nEndSection\n', encoding="utf-8")

    status = collect_xorg_touchscreen_config_status(config_path)

    assert status.exists is True
    assert status.has_signature is False


def test_xorg_touchscreen_config_status_is_ok_when_signature_exists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    config_path = tmp_path / "99-vending-touchscreen.conf"
    config_path.write_text(f"{XORG_TOUCHSCREEN_SIGNATURE}\n", encoding="utf-8")

    status = collect_xorg_touchscreen_config_status(config_path)

    assert status.exists is True
    assert status.has_signature is True


def test_display_session_config_status_is_ok_when_signature_exists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    config_path = tmp_path / ".xprofile"
    config_path.write_text(f"{DISPLAY_SESSION_SIGNATURE}\n", encoding="utf-8")

    status = collect_display_session_config_status(config_path)

    assert status.exists is True
    assert status.has_signature is True


def test_display_session_script_status_is_ok_when_signature_exists_and_executable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    script_path = tmp_path / "display-session.sh"
    script_path.write_text(f"{DISPLAY_SESSION_SCRIPT_SIGNATURE}\n", encoding="utf-8")
    script_path.chmod(0o755)

    status = collect_display_session_script_status(script_path)

    assert status.exists is True
    assert status.has_signature is True
    assert status.executable is True


def test_vpn_status_collects_config_paths_and_connection_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store_dir = tmp_path / "store"
    active_dir = tmp_path / "etc-wireguard"
    app_config = store_dir / "configs" / "wg0.conf"
    active_config = active_dir / "wg0.conf"
    history_dir = store_dir / "history" / "wg0"
    app_config.parent.mkdir(parents=True)
    active_config.parent.mkdir(parents=True)
    history_dir.mkdir(parents=True)
    app_config.write_text("[Interface]\n", encoding="utf-8")
    active_config.write_text("[Interface]\n", encoding="utf-8")

    with patch("status.default_store_dir", return_value=store_dir):
        with patch("status.WIREGUARD_CONFIG_DIR", active_dir):
            with patch("status.shutil.which", return_value="/usr/bin/wg"):
                with patch("status._read_version", return_value="wireguard-tools v1.0.0"):
                    with patch("status._read_command_first_line", side_effect=("enabled", "active")):
                        with patch("status._command_succeeds", return_value=True):
                            with patch("status._count_handshake_peers", return_value=1):
                                status = collect_vpn_status("wg0")

    assert status.app_config_exists is True
    assert status.active_config_exists is True
    assert status.history_exists is True
    assert status.service_enabled == "enabled"
    assert status.service_active == "active"
    assert status.interface_exists is True
    assert status.handshake_peers == 1


def test_vpn_status_handles_permission_denied_paths(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with patch("status.default_store_dir", return_value=tmp_path / "store"):
        with patch("status.WIREGUARD_CONFIG_DIR", Path("/etc/wireguard")):
            with patch("status.shutil.which", return_value="/usr/bin/wg"):
                with patch("pathlib.Path.exists", side_effect=PermissionError("permission denied")):
                    with patch("status._read_version", return_value="wireguard-tools v1.0.0"):
                        with patch("status._read_command_first_line", return_value="unknown"):
                            with patch("status._command_succeeds", return_value=False):
                                with patch("status._count_handshake_peers", return_value=None):
                                    status = collect_vpn_status("wg0")

    assert status.app_config_exists is False
    assert status.active_config_exists is False
    assert status.history_exists is False


def test_remote_access_status_collects_anydesk_id_and_status() -> None:
    with patch("status.shutil.which", return_value="/usr/bin/anydesk"):
        with patch("status._read_version", return_value="anydesk version 7.1.0"):
            with patch("status._read_command_first_line_or_none", return_value="123456789"):
                with patch("status._read_command_first_line", side_effect=("online", "enabled", "active")):
                    status = collect_remote_access_status()

    assert status.anydesk_installed is True
    assert status.anydesk_version == "anydesk version 7.1.0"
    assert status.anydesk_id == "123456789"
    assert status.anydesk_status == "online"
    assert status.service_enabled == "enabled"
    assert status.service_active == "active"


def test_print_status_includes_vpn_section(capsys: Any) -> None:
    with patch("status.collect_status", return_value=()):
        with patch(
            "status.collect_remote_access_status",
            return_value=RemoteAccessStatus(
                anydesk_installed=True,
                anydesk_version="anydesk version 7.1.0",
                anydesk_id="123456789",
                anydesk_status="online",
                service_enabled="enabled",
                service_active="active",
            ),
        ):
            with patch("status.collect_vpn_status") as collect_vpn:
                collect_vpn.return_value = VpnStatus(
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
                )
                print_status()

    output = capsys.readouterr().out
    assert "[Remote]" in output
    assert "123456789" in output
    assert "[VPN]" in output
    assert "App Config" in output
    assert "Connection" in output

def test_collect_openssh_status_installed() -> None:
    # which เรียก 2 ครั้ง: sshd (server, ใช้ตรวจ installed) แล้ว ssh (client, ใช้ดู version)
    with patch("status.shutil.which", side_effect=["/usr/sbin/sshd", "/usr/bin/ssh"]):
        with patch("status._read_version", return_value="OpenSSH_8.9p1"):
            with patch("status._read_command_first_line", side_effect=("enabled", "active")):
                status = collect_openssh_status()

    assert status.installed is True
    assert status.version == "OpenSSH_8.9p1"
    assert status.service_enabled == "enabled"
    assert status.service_active == "active"


def test_collect_openssh_status_not_installed() -> None:
    with patch("status.shutil.which", return_value=None):
        with patch("status._read_command_first_line", side_effect=("disabled", "inactive")):
            status = collect_openssh_status()

    assert status.installed is False
    assert status.version is None  # ssh_path is None → version skipped
    assert status.service_enabled == "disabled"
    assert status.service_active == "inactive"
