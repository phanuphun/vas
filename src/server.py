from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from flask import Flask, render_template, request

from audit_log import (
    create_system_log_snapshot,
    list_system_snapshots,
    read_system_snapshot,
    system_snapshot_dir,
)
from display import (
    DisplayConfigurator,
    ROTATION_MATRICES,
    TouchDevice,
    get_udevadm_touchscreen_names,
    parse_xinput_device_map,
)
from runner import CommandExecutionError, CommandRunner
from status import (
    ToolStatus,
    VpnStatus,
    collect_display_session_config_status,
    collect_display_session_script_status,
    collect_display_session_status,
    collect_remote_access_status,
    collect_status,
    collect_vpn_status,
    collect_web_server_status,
    collect_xorg_touchscreen_config_status,
)
from wireguard import (
    WireGuardValidationResult,
    WireGuardManager,
    chmod_private,
    mask_secrets,
    render_template as render_wireguard_template,
    sanitize_history_id,
    sanitize_interface_name,
    validate_config_content,
)


WEB_DIR = Path(__file__).parent / "web"
INSTALL_COMPONENTS = ("all", "git", "node", "docker", "wireguard", "anydesk")
LIFECYCLE_COMPONENTS = ("all", "git", "node", "docker", "wireguard", "anydesk")
WIREGUARD_ACTIONS = (
    ("Install", "sudo vas wireguard install"),
    ("Create template", "vas wireguard init-config --name wg0 --output ./wg0.conf"),
    ("Validate config", "vas wireguard validate --config ./wg0.conf"),
    ("Save config", "vas wireguard save --name wg0 --config ./wg0.conf"),
    ("Sync config", "sudo vas wireguard sync --name wg0"),
    ("Show status", "vas wireguard status --name wg0"),
    ("List history", "vas wireguard history --name wg0"),
    ("Unsync config", "sudo vas wireguard unsync --name wg0"),
)
DISPLAY_ACTIONS = (
    ("Show display status", "vas display status --display :0"),
    ("List touchscreens", "vas display list-touch --display :0"),
    (
        "Apply runtime",
        "vas display apply --display :0 --output Virtual1 --touch 'Vending Virtual Touchscreen' --rotate normal",
    ),
    (
        "Persist session",
        "vas display persist-session --display :0 --output Virtual1 --touch 'Vending Virtual Touchscreen' --rotate normal",
    ),
    (
        "Persist touch in Xorg",
        "sudo vas display persist-xorg --touch 'Vending Virtual Touchscreen' --rotate normal",
    ),
)
SERVER_ACTIONS = (
    ("Start background service", "sudo vas server start --host 0.0.0.0 --port 8888"),
    ("Show service status", "vas server status"),
    ("Run foreground", "vas server run --host 0.0.0.0 --port 8888"),
    ("Stop service", "sudo vas server stop"),
)
ROTATION_LABELS = (
    ("normal", "Normal"),
    ("left", "Left"),
    ("right", "Right"),
    ("inverted", "Revert"),
)


@dataclass(frozen=True)
class CommandPreview:
    label: str
    command: str
    requires_root: bool


@dataclass(frozen=True)
class WireGuardHistoryEntry:
    id: str
    path: str
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(WEB_DIR / "templates"),
        static_folder=str(WEB_DIR / "static"),
    )
    app.jinja_env.globals["vpn_connection_label"] = vpn_connection_label

    @app.get("/")
    def dashboard() -> str:
        return render_template(
            "dashboard.html",
            tools=collect_status(),
            session=collect_display_session_status(),
            display_config=collect_display_session_config_status(),
            display_script=collect_display_session_script_status(),
            touchscreen=collect_xorg_touchscreen_config_status(),
            remote=collect_remote_access_status(),
            vpn=collect_vpn_status(),
            web_server=collect_web_server_status(),
        )

    @app.get("/install")
    def install() -> str:
        return render_template("commands.html", title="Install", commands=build_install_commands())

    @app.get("/reset")
    def reset() -> str:
        return render_template("commands.html", title="Reset", commands=build_reset_commands())

    @app.get("/wireguard")
    def wireguard() -> str:
        vpn = collect_vpn_status()
        return render_template(
            "wireguard.html",
            vpn=vpn,
            config_content=_read_wireguard_config(vpn.app_config_path),
            config_validation=_validate_wireguard_path(vpn.app_config_path),
            history_entries=collect_wireguard_history(vpn.interface_name),
        )

    @app.get("/logs")
    def logs() -> str:
        return render_template(
            "logs.html",
            system_snapshots=list_system_snapshots(),
            system_snapshot_dir=_system_snapshot_dir_label(),
        )

    @app.get("/api/logs/system")
    def logs_system_api() -> dict[str, object]:
        return {"status": "ok", "snapshots": list(list_system_snapshots())}

    @app.post("/api/logs/system/snapshot")
    def logs_system_snapshot_api() -> tuple[dict[str, object], int] | dict[str, object]:
        try:
            snapshot = create_system_log_snapshot()
        except OSError as error:
            return {"status": "error", "errors": [str(error)]}, 500
        return {"status": "ok", "snapshot": snapshot}

    @app.get("/api/logs/system/<snapshot_id>")
    def logs_system_show_api(snapshot_id: str) -> tuple[dict[str, object], int] | dict[str, object]:
        try:
            snapshot = read_system_snapshot(snapshot_id)
        except (FileNotFoundError, OSError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 404
        return {"status": "ok", "snapshot": snapshot}

    @app.get("/api/wireguard/config")
    def wireguard_config() -> dict[str, object]:
        name = _wireguard_name_from_request()
        manager = WireGuardManager(CommandRunner())
        path = manager.saved_config_path(name)
        return {
            "name": name,
            "path": path.as_posix(),
            "exists": path.exists(),
            "content": _read_wireguard_config(path),
            "validation": _validation_payload(_validate_wireguard_path(path)),
        }

    @app.post("/api/wireguard/template")
    def wireguard_template_api() -> tuple[dict[str, object], int] | dict[str, object]:
        try:
            name = _wireguard_name_from_payload()
            content = render_wireguard_template(name)
        except ValueError as error:
            return {"status": "error", "errors": [str(error)]}, 400
        return {"status": "ok", "name": name, "content": content, "validation": _validation_payload(validate_config_content(content))}

    @app.post("/api/wireguard/validate")
    def wireguard_validate_api() -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        content = str(payload.get("content", ""))
        result = validate_config_content(content)
        return {"status": "ok" if result.valid else "invalid", "validation": _validation_payload(result)}

    @app.post("/api/wireguard/config")
    def wireguard_save_config_api() -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        content = str(payload.get("content", ""))
        try:
            name = _wireguard_name_from_payload()
            result = validate_config_content(content)
            if not result.valid:
                return {"status": "invalid", "validation": _validation_payload(result)}, 400
            path = WireGuardManager(CommandRunner()).saved_config_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            chmod_private(path)
        except (OSError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 400
        return {
            "status": "ok",
            "name": name,
            "path": path.as_posix(),
            "validation": _validation_payload(result),
        }

    @app.delete("/api/wireguard/config")
    def wireguard_delete_config_api() -> tuple[dict[str, object], int] | dict[str, object]:
        try:
            name = _wireguard_name_from_request()
            path = WireGuardManager(CommandRunner()).saved_config_path(name)
            if path.exists():
                path.unlink()
        except (OSError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 400
        return {"status": "ok", "name": name, "path": path.as_posix(), "exists": path.exists()}

    @app.post("/api/wireguard/action")
    def wireguard_action_api() -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "")).strip()
        try:
            name = _wireguard_name_from_payload()
            manager = WireGuardManager(CommandRunner())
            if action == "sync":
                manager.sync(name=name)
            elif action == "unsync":
                manager.unsync(name=name)
            else:
                return {"status": "error", "errors": [f"Unknown WireGuard action: {action}"]}, 400
        except (CommandExecutionError, OSError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 500
        return {"status": "ok", "action": action, "name": name}

    @app.get("/api/wireguard/history")
    def wireguard_history_api() -> tuple[dict[str, object], int] | dict[str, object]:
        try:
            name = _wireguard_name_from_request()
        except ValueError as error:
            return {"status": "error", "errors": [str(error)]}, 400
        return {"status": "ok", "name": name, "entries": [entry.__dict__ for entry in collect_wireguard_history(name)]}

    @app.get("/api/wireguard/history/<history_id>")
    def wireguard_history_show_api(history_id: str) -> tuple[dict[str, object], int] | dict[str, object]:
        try:
            name = _wireguard_name_from_request()
            path = _wireguard_history_path(name, history_id)
            if not path.exists():
                return {"status": "error", "errors": [f"History entry not found: {history_id}"]}, 404
            content = path.read_text(encoding="utf-8")
            validation = validate_config_content(content)
        except (OSError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 400
        return {
            "status": "ok",
            "id": sanitize_history_id(history_id),
            "path": path.as_posix(),
            "content": mask_secrets(content),
            "validation": _validation_payload(validation),
        }

    @app.delete("/api/wireguard/history/<history_id>")
    def wireguard_history_delete_api(history_id: str) -> tuple[dict[str, object], int] | dict[str, object]:
        try:
            name = _wireguard_name_from_request()
            path = _wireguard_history_path(name, history_id)
            if path.exists():
                path.unlink()
        except (OSError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 400
        return {"status": "ok", "id": sanitize_history_id(history_id), "deleted": not path.exists()}

    @app.get("/commands")
    def commands() -> str:
        return render_template(
            "command_docs.html",
            install_commands=build_install_commands(),
            reset_commands=build_reset_commands(),
            display_commands=build_display_commands(),
            wireguard_commands=build_wireguard_commands(),
            server_commands=build_server_commands(),
        )

    @app.get("/display")
    def display_settings() -> str:
        default_display = _default_x_display()
        devices = collect_display_devices(x_display=default_display)
        return render_template(
            "display.html",
            outputs=devices.outputs,
            touch_devices=devices.touch_devices,
            rotations=ROTATION_LABELS,
            default_display=default_display,
            session=collect_display_session_status(),
            display_config=collect_display_session_config_status(),
            display_script=collect_display_session_script_status(),
            xorg_touchscreen=collect_xorg_touchscreen_config_status(),
        )

    @app.get("/api/display/config-content")
    def display_config_content() -> "tuple[dict[str, object], int] | dict[str, object]":
        key = request.args.get("key", "").strip()
        allowed = _allowed_config_paths()
        if key not in allowed:
            return {"error": f"Unknown config key: {key}"}, 400
        path = allowed[key]
        if not path.exists():
            return {"exists": False, "content": None, "path": path.as_posix()}
        try:
            content = path.read_text(encoding="utf-8")
            return {"exists": True, "content": content, "path": path.as_posix()}
        except OSError as e:
            return {"error": str(e)}, 500

    @app.get("/api/display/devices")
    def display_devices() -> dict[str, object]:
        x_display = request.args.get("display") or _default_x_display()
        devices = collect_display_devices(x_display=x_display)
        return {
            "outputs": devices.outputs,
            "touchDevices": [{"name": d.name, "id": d.xinput_id} for d in devices.touch_devices],
            "defaultDisplay": x_display,
        }

    @app.post("/api/display/apply")
    def display_apply() -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        output = str(payload.get("output", "")).strip()
        touch = str(payload.get("touch", "")).strip()
        rotate = str(payload.get("rotate", "normal")).strip()
        x_display = str(payload.get("display", "")).strip() or None
        persist_session = bool(payload.get("persistSession", True))
        persist_xorg = bool(payload.get("persistXorg", False))

        devices = collect_display_devices(x_display=x_display)
        errors = validate_display_apply(output, touch, rotate, devices)
        if errors:
            return {"status": "error", "errors": errors}, 400

        runner = DisplayCommandRunner()
        configurator = DisplayConfigurator(runner)
        try:
            configurator.apply_runtime(output=output, touch=touch, rotate=rotate, x_display=x_display)
            if persist_session:
                configurator.persist_session(output=output, touch=touch, rotate=rotate, x_display=x_display)
            if persist_xorg:
                configurator.persist_xorg(touch=touch, rotate=rotate)
        except (CommandExecutionError, OSError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 500

        return {
            "status": "ok",
            "output": output,
            "touch": touch,
            "rotate": rotate,
            "display": x_display,
            "persistSession": persist_session,
            "persistXorg": persist_xorg,
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def run_server(host: str, port: int, debug: bool) -> None:
    create_app().run(host=host, port=port, debug=debug)


def build_install_commands() -> tuple[CommandPreview, ...]:
    return tuple(
        CommandPreview(
            label=f"Install {component}",
            command=f"sudo vas install --component {component}",
            requires_root=True,
        )
        for component in INSTALL_COMPONENTS
    )


def build_reset_commands() -> tuple[CommandPreview, ...]:
    commands: list[CommandPreview] = []
    for action in ("uninstall", "reset"):
        for component in LIFECYCLE_COMPONENTS:
            commands.append(
                CommandPreview(
                    label=f"{action.title()} {component}",
                    command=f"sudo vas {action} --component {component}",
                    requires_root=True,
                )
            )
    return tuple(commands)


def build_wireguard_commands() -> tuple[CommandPreview, ...]:
    return tuple(
        CommandPreview(label=label, command=command, requires_root=command.startswith("sudo "))
        for label, command in WIREGUARD_ACTIONS
    )


def build_display_commands() -> tuple[CommandPreview, ...]:
    return tuple(
        CommandPreview(label=label, command=command, requires_root=command.startswith("sudo "))
        for label, command in DISPLAY_ACTIONS
    )


def collect_wireguard_history(name: str = "wg0") -> tuple[WireGuardHistoryEntry, ...]:
    manager = WireGuardManager(CommandRunner())
    history_dir = manager.history_dir(name)
    if not history_dir.exists():
        return ()

    entries: list[WireGuardHistoryEntry] = []
    for path in sorted(history_dir.glob("*.conf"), reverse=True):
        result = _validate_wireguard_path(path)
        entries.append(
            WireGuardHistoryEntry(
                id=path.stem,
                path=path.as_posix(),
                valid=result.valid,
                errors=result.errors,
                warnings=result.warnings,
            )
        )
    return tuple(entries)


def _read_wireguard_config(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        return ""


def _validate_wireguard_path(path: Path) -> WireGuardValidationResult:
    try:
        if not path.exists():
            return validate_config_content("")
        return validate_config_content(path.read_text(encoding="utf-8"))
    except OSError as error:
        return validate_config_content(f"# read error: {error}")


def _validation_payload(result: WireGuardValidationResult) -> dict[str, object]:
    return {
        "valid": result.valid,
        "errors": result.errors,
        "warnings": result.warnings,
    }


def _wireguard_name_from_request() -> str:
    return sanitize_interface_name((request.args.get("name") or "wg0").strip() or "wg0")


def _wireguard_name_from_payload() -> str:
    payload = request.get_json(silent=True) or {}
    return sanitize_interface_name(str(payload.get("name") or "wg0").strip() or "wg0")


def _wireguard_history_path(name: str, history_id: str) -> Path:
    manager = WireGuardManager(CommandRunner())
    return manager.history_dir(name) / f"{sanitize_history_id(history_id)}.conf"


def build_server_commands() -> tuple[CommandPreview, ...]:
    return tuple(
        CommandPreview(label=label, command=command, requires_root=command.startswith("sudo "))
        for label, command in SERVER_ACTIONS
    )


@dataclass(frozen=True)
class DisplayDevices:
    outputs: tuple[str, ...]
    touch_devices: tuple[TouchDevice, ...]


def collect_display_devices(x_display: str | None = None) -> DisplayDevices:
    runner = CommandRunner()
    configurator = DisplayConfigurator(runner)
    resolved_display = x_display or _default_x_display()
    xauthority = _default_xauthority()

    xrandr = runner.run(configurator._with_x_env(["xrandr", "--query"], resolved_display, xauthority), check=False)
    xinput = runner.run(configurator._with_x_env(["xinput", "list"], resolved_display, xauthority), check=False)

    outputs = parse_xrandr_outputs(xrandr.stdout)
    xinput_map = parse_xinput_device_map(xinput.stdout)

    if not outputs:
        desktop_user = _desktop_user()
        if desktop_user:
            env_args = ["env", f"DISPLAY={resolved_display}"]
            if xauthority:
                env_args.append(f"XAUTHORITY={xauthority}")
            xrandr = runner.run(["runuser", "-u", desktop_user, "--", *env_args, "xrandr", "--query"], check=False)
            xinput = runner.run(["runuser", "-u", desktop_user, "--", *env_args, "xinput", "list"], check=False)
            outputs = parse_xrandr_outputs(xrandr.stdout)
            xinput_map = parse_xinput_device_map(xinput.stdout)

    touch_devices = _resolve_touch_devices(runner, xinput_map)
    return DisplayDevices(outputs=outputs, touch_devices=touch_devices)


def _resolve_touch_devices(runner: CommandRunner, xinput_map: dict[str, int]) -> tuple[TouchDevice, ...]:
    """หา touchscreen devices โดยใช้ udevadm เป็นหลัก fallback ด้วย "touch" ใน name"""
    udev_names = get_udevadm_touchscreen_names(runner)
    if udev_names:
        return tuple(
            TouchDevice(name=name, xinput_id=xinput_map.get(name))
            for name in sorted(udev_names)
        )
    return tuple(
        TouchDevice(name=name, xinput_id=id_)
        for name, id_ in sorted(xinput_map.items())
        if "touch" in name.lower()
    )


def parse_xrandr_outputs(output: str) -> tuple[str, ...]:
    outputs = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "connected":
            outputs.append(parts[0])
    return tuple(outputs)


def parse_xinput_touch_devices(output: str) -> tuple[str, ...]:
    """Legacy: กรอง touchscreen จาก xinput --name-only output ด้วย 'touch' ใน name
    ใช้ parse_xinput_device_map + get_udevadm_touchscreen_names แทนใน production code
    """
    names = tuple(line.strip() for line in output.splitlines() if line.strip())
    return tuple(name for name in names if "touch" in name.lower())


def validate_display_apply(output: str, touch: str, rotate: str, devices: DisplayDevices) -> list[str]:
    errors = []
    if rotate not in ROTATION_MATRICES:
        errors.append(f"Unsupported rotation: {rotate}")
    if not output:
        errors.append("Display output is required.")
    elif output not in devices.outputs:
        errors.append(f"Display output is not connected: {output}")
    if not touch:
        errors.append("Touchscreen device is required.")
    elif touch not in (d.name for d in devices.touch_devices):
        errors.append(f"Touchscreen device is not available: {touch}")
    return errors


def _allowed_config_paths() -> dict[str, Path]:
    """Allowlist ของ config files ที่อ่านได้ผ่าน API"""
    from display import _effective_home_config_path, _effective_home_script_path  # type: ignore[attr-defined]
    from status import XORG_TOUCHSCREEN_CONFIG_PATH
    return {
        "xprofile": _effective_home_config_path(),
        "display_script": _effective_home_script_path(),
        "xorg_touchscreen": Path(XORG_TOUCHSCREEN_CONFIG_PATH),
    }


def _system_snapshot_dir_label() -> str:
    return system_snapshot_dir().as_posix()


def _default_x_display() -> str:
    return ":0"


def _default_xauthority() -> str | None:
    xauthority = Path.home() / ".Xauthority"
    return xauthority.as_posix() if xauthority.exists() else None


def _desktop_user() -> str | None:
    if os.name != "posix" or not hasattr(os, "geteuid") or os.geteuid() != 0:
        return None
    sudo_user = os.environ.get("SUDO_USER", "").strip()
    if sudo_user and sudo_user != "root":
        return sudo_user
    home_name = Path.home().name
    if home_name and home_name != "root":
        return home_name
    return None


class DisplayCommandRunner(CommandRunner):
    def run(self, args, check: bool = True):  # type: ignore[no-untyped-def]
        desktop_user = _desktop_user()
        if desktop_user and _is_display_command(args):
            return super().run(["runuser", "-u", desktop_user, "--", *args], check=check)
        return super().run(args, check=check)


def _is_display_command(args) -> bool:  # type: ignore[no-untyped-def]
    if not args:
        return False
    if args[0] in {"xrandr", "xinput"}:
        return True
    return args[0] == "env" and any(part in {"xrandr", "xinput"} for part in args)


def tool_marker(status: ToolStatus) -> str:
    return "OK" if status.installed else "MISSING"


def vpn_connection_label(vpn: VpnStatus) -> str:
    if vpn.service_active == "active" and vpn.interface_exists:
        if vpn.handshake_peers is None:
            return "Active, handshake unknown"
        if vpn.handshake_peers > 0:
            return f"Connected with {vpn.handshake_peers} peer(s)"
        return "Active, waiting for peer handshake"
    return f"Service {vpn.service_active}"
