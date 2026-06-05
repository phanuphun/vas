from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from display import DisplayConfigurator, ROTATION_MATRICES
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
            install_commands=build_install_commands(),
            reset_commands=build_reset_commands(),
            wireguard_commands=build_wireguard_commands(),
            server_commands=build_server_commands(),
        )

    @app.get("/install")
    def install() -> str:
        return render_template("commands.html", title="Install", commands=build_install_commands())

    @app.get("/reset")
    def reset() -> str:
        return render_template("commands.html", title="Reset", commands=build_reset_commands())

    @app.get("/wireguard")
    def wireguard() -> str:
        return render_template("wireguard.html", vpn=collect_vpn_status(), commands=build_wireguard_commands())

    @app.get("/display")
    def display_settings() -> str:
        devices = collect_display_devices()
        return render_template(
            "display.html",
            outputs=devices.outputs,
            touch_devices=devices.touch_devices,
            rotations=ROTATION_LABELS,
            default_display=_default_x_display(),
        )

    @app.get("/api/display/devices")
    def display_devices() -> dict[str, object]:
        devices = collect_display_devices()
        return {
            "outputs": devices.outputs,
            "touchDevices": devices.touch_devices,
            "defaultDisplay": _default_x_display(),
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

        runner = CommandRunner()
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


def build_server_commands() -> tuple[CommandPreview, ...]:
    return tuple(
        CommandPreview(label=label, command=command, requires_root=command.startswith("sudo "))
        for label, command in SERVER_ACTIONS
    )


@dataclass(frozen=True)
class DisplayDevices:
    outputs: tuple[str, ...]
    touch_devices: tuple[str, ...]


def collect_display_devices(x_display: str | None = None) -> DisplayDevices:
    runner = CommandRunner()
    configurator = DisplayConfigurator(runner)
    xrandr = runner.run(configurator._with_x_env(["xrandr", "--query"], x_display, None), check=False)
    xinput = runner.run(configurator._with_x_env(["xinput", "list", "--name-only"], x_display, None), check=False)

    outputs = parse_xrandr_outputs(xrandr.stdout)
    touch_devices = parse_xinput_touch_devices(xinput.stdout)
    return DisplayDevices(outputs=outputs, touch_devices=touch_devices)


def parse_xrandr_outputs(output: str) -> tuple[str, ...]:
    outputs = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "connected":
            outputs.append(parts[0])
    return tuple(outputs)


def parse_xinput_touch_devices(output: str) -> tuple[str, ...]:
    names = tuple(line.strip() for line in output.splitlines() if line.strip())
    touch_names = tuple(name for name in names if "touch" in name.lower())
    return touch_names or names


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
    elif touch not in devices.touch_devices:
        errors.append(f"Touchscreen device is not available: {touch}")
    return errors


def _default_x_display() -> str:
    return ":0"


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
