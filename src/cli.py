from __future__ import annotations

import argparse
from pathlib import Path

from config import APP_VERSION, DEFAULT_CONFIG, InstallConfig
from display import ROTATION_MATRICES, DisplayConfigurator
from installers import PhaseOneInstaller, count_install_operations
from os_info import print_os_info
from reset import (
    INSTALL_COMPONENTS,
    RESET_COMPONENTS,
    LifecycleManager,
    count_reset_operations,
    count_uninstall_operations,
)
from runner import CommandRunner
from mcp_service import McpConfig, McpServiceManager, default_mcp_config
from server_service import ServerConfig, ServerServiceManager
from status import print_status
from system import require_linux, require_root
from updater import DEFAULT_INSTALL_DIR, DEFAULT_REPO, SelfUpdater
from wireguard import WireGuardManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vending-auto-setup",
        description="Prepare Ubuntu 22.04 LTS vending machines.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")

    subcommands = parser.add_subparsers(dest="command", required=True)

    install = subcommands.add_parser("install", help="Run installation.")
    install.add_argument("--node-major", type=int, default=DEFAULT_CONFIG.node_major)
    install.add_argument("--docker-version", default=DEFAULT_CONFIG.docker_version)
    install.add_argument("--git-version", default=DEFAULT_CONFIG.git_version)
    install.add_argument(
        "--component",
        action="append",
        choices=(*INSTALL_COMPONENTS, "all"),
        help="Install only this component. Repeatable. Defaults to node, docker, and git.",
    )

    subcommands.add_parser("check", help="Show whether phase 1 tools are present.")
    subcommands.add_parser("about-os", help="Print OS information for bootstrap POC.")
    subcommands.add_parser("version", help="Print CLI version.")

    update = subcommands.add_parser("update", help="Update the installed CLI wrapper source from GitHub.")
    update.add_argument("--repo", default=DEFAULT_REPO)
    update.add_argument("--version", default="latest", help="Git tag to install, or latest for main.")
    update.add_argument("--install-dir", type=Path, default=DEFAULT_INSTALL_DIR, help=argparse.SUPPRESS)
    update.add_argument("--bin-dir", type=Path, default=Path("/usr/local/bin"), help=argparse.SUPPRESS)

    server = subcommands.add_parser("server", help="Start the local Flask HTTP dashboard.")
    server_subcommands = server.add_subparsers(dest="server_command", required=True)
    server_start = server_subcommands.add_parser("start", help="Install and start the dashboard as a background service.")
    add_server_bind_arguments(server_start)
    server_start.add_argument("--foreground", action="store_true", help="Run in the current terminal instead of systemd.")

    server_run = server_subcommands.add_parser("run", help="Run the Flask dashboard in the current process.")
    add_server_bind_arguments(server_run)
    server_run.add_argument("--debug", action="store_true")

    server_install = server_subcommands.add_parser("install-service", help="Install the dashboard systemd service.")
    add_server_bind_arguments(server_install)
    server_subcommands.add_parser("stop", help="Stop and disable the dashboard service.")
    server_subcommands.add_parser("status", help="Show the dashboard service status.")

    _default_mcp = default_mcp_config()
    mcp_cmd = subcommands.add_parser("mcp", help="Manage the MCP server (AI diagnostic interface).")
    mcp_subcommands = mcp_cmd.add_subparsers(dest="mcp_command", required=True)

    mcp_run = mcp_subcommands.add_parser("run", help="Run the MCP server in the current process.")
    add_mcp_bind_arguments(mcp_run, _default_mcp)

    mcp_start = mcp_subcommands.add_parser("start", help="Install and start the MCP server as a background service.")
    add_mcp_bind_arguments(mcp_start, _default_mcp)
    mcp_start.add_argument("--foreground", action="store_true", help="Run in the current terminal instead of systemd.")

    mcp_install = mcp_subcommands.add_parser("install-service", help="Install the MCP server systemd service.")
    add_mcp_bind_arguments(mcp_install, _default_mcp)

    mcp_subcommands.add_parser("stop", help="Stop and disable the MCP server service.")
    mcp_subcommands.add_parser("status", help="Show the MCP server service status.")

    display = subcommands.add_parser("display", help="Inspect and configure display/touchscreen settings.")
    display_subcommands = display.add_subparsers(dest="display_command", required=True)

    display_status = display_subcommands.add_parser("status", help="Show xrandr and xinput status.")
    add_x_session_arguments(display_status)

    display_list_touch = display_subcommands.add_parser(
        "list-touch",
        help="List touchscreen devices with xinput ID (detected via udevadm).",
    )
    add_x_session_arguments(display_list_touch)

    display_apply = display_subcommands.add_parser("apply", help="Apply display rotation and touchscreen mapping now.")
    add_x_session_arguments(display_apply)
    display_apply.add_argument("--output", required=True, help="xrandr output name, for example HDMI-1 or Virtual1.")
    display_apply.add_argument("--touch", required=True, help="xinput touchscreen name or id.")
    display_apply.add_argument("--rotate", choices=sorted(ROTATION_MATRICES), required=True)

    display_persist = display_subcommands.add_parser(
        "persist-xorg",
        help="Persist touchscreen coordinate mapping with an Xorg InputClass config.",
    )
    display_persist.add_argument("--touch", required=True, help="xinput touchscreen product name.")
    display_persist.add_argument("--rotate", choices=sorted(ROTATION_MATRICES), required=True)

    display_persist_session = display_subcommands.add_parser(
        "persist-session",
        help="Persist display rotation and touchscreen mapping in the user's X session profile.",
    )
    add_x_session_arguments(display_persist_session)
    display_persist_session.add_argument(
        "--output",
        required=True,
        help="xrandr output name, for example HDMI-1 or Virtual1.",
    )
    display_persist_session.add_argument("--touch", required=True, help="xinput touchscreen name or id.")
    display_persist_session.add_argument("--rotate", choices=sorted(ROTATION_MATRICES), required=True)
    display_persist_session.add_argument("--delay-seconds", type=int, default=5)
    display_persist_session.add_argument("--retries", type=int, default=30)

    display_subcommands.add_parser("disable-wayland", help="Disable Wayland in GDM so the machine logs into X11.")
    display_subcommands.add_parser("enable-wayland", help="Re-enable GDM Wayland by commenting out WaylandEnable=false.")

    wireguard = subcommands.add_parser("wireguard", help="Install, stage, sync, and inspect WireGuard configs.")
    wireguard.add_argument("--store-dir", type=Path, help="App storage directory for saved configs and history.")
    wireguard.add_argument(
        "--wireguard-dir",
        type=Path,
        default=Path("/etc/wireguard"),
        help=argparse.SUPPRESS,
    )
    wireguard_subcommands = wireguard.add_subparsers(dest="wireguard_command", required=True)

    wireguard_status = wireguard_subcommands.add_parser("status", help="Show WireGuard tool, config, and service status.")
    add_wireguard_name_argument(wireguard_status)

    wireguard_subcommands.add_parser("install", help="Install the wireguard package.")

    wireguard_init = wireguard_subcommands.add_parser("init-config", help="Create a WireGuard config template.")
    add_wireguard_name_argument(wireguard_init)
    wireguard_init.add_argument("--output", type=Path, default=Path("wg0.conf"))
    wireguard_init.add_argument("--force", action="store_true", help="Overwrite the output file if it exists.")

    wireguard_validate = wireguard_subcommands.add_parser("validate", help="Validate a WireGuard config file.")
    wireguard_validate.add_argument("--config", type=Path, required=True)

    wireguard_save = wireguard_subcommands.add_parser("save", help="Save a config into app storage without applying it.")
    add_wireguard_name_argument(wireguard_save)
    wireguard_save.add_argument("--config", type=Path, required=True)

    wireguard_sync = wireguard_subcommands.add_parser("sync", help="Apply a saved config to /etc/wireguard and restart it.")
    add_wireguard_name_argument(wireguard_sync)
    wireguard_sync.add_argument("--config", type=Path, help="Apply this config instead of the saved app config.")
    wireguard_sync.add_argument("--no-restart", action="store_true", help="Enable the service without restarting it.")

    wireguard_history = wireguard_subcommands.add_parser("history", help="List previously synced config snapshots.")
    add_wireguard_name_argument(wireguard_history)

    wireguard_show = wireguard_subcommands.add_parser("show", help="Show a synced config snapshot.")
    add_wireguard_name_argument(wireguard_show)
    wireguard_show.add_argument("--id", required=True, help="History id from wireguard history.")
    wireguard_show.add_argument("--reveal-secrets", action="store_true", help="Print private key values.")

    wireguard_unsync = wireguard_subcommands.add_parser("unsync", help="Disable service and remove the active config.")
    add_wireguard_name_argument(wireguard_unsync)

    uninstall = subcommands.add_parser("uninstall", help="Uninstall selected installed components.")
    add_component_arguments(uninstall, (*INSTALL_COMPONENTS, "all"))
    add_lifecycle_arguments(uninstall)

    reset = subcommands.add_parser(
        "reset",
        help="Uninstall selected components and remove vending-auto-setup managed configs.",
    )
    add_component_arguments(reset, (*RESET_COMPONENTS, "all"))
    add_lifecycle_arguments(reset)
    qr = subcommands.add_parser("qr", help="Manage QR code reader (ZKTeco QR500-BM).")
    qr_subcommands = qr.add_subparsers(dest="qr_command", required=True)

    qr_subcommands.add_parser("status", help="Show QR reader device and config status.")

    qr_start = qr_subcommands.add_parser("start", help="Start QR reader thread (blocking, until Ctrl+C).")
    qr_start.add_argument("--device", help="Device path (/dev/input/eventX or /dev/hidrawX). Defaults to auto-detect.")

    qr_subcommands.add_parser("stop", help="Stop the global QR reader thread.")

    qr_subcommands.add_parser("last-scan", help="Print the last scanned value.")

    qr_test = qr_subcommands.add_parser("test", help="Interactive QR reader test — scan QR and print results. (Ctrl+C to stop)")
    qr_test.add_argument("--device", help="Device path (/dev/input/eventX). Defaults to auto-detect.")
    qr_test.add_argument("--no-grab", action="store_true", help="Do not grab device (keystrokes reach OS — debug only).")

    qr_subcommands.add_parser("install-udev", help="Install udev rule so non-root users can access /dev/hidraw*.")

    qr_config_cmd = qr_subcommands.add_parser("config", help="Set QR reader config.")
    qr_config_cmd.add_argument("--device", help="Device path to pin (/dev/input/eventX or /dev/hidrawX).")
    qr_config_cmd.add_argument("--clear-device", action="store_true", help="Clear pinned device (use auto-detect).")

    # ── mqtt subcommand ─────────────────────────────────────────────
    mqtt = subcommands.add_parser("mqtt", help="Manage MQTT publish settings.")
    mqtt_subcommands = mqtt.add_subparsers(dest="mqtt_command", required=True)

    mqtt_subcommands.add_parser("status", help="Show MQTT client status and current config.")

    mqtt_cfg = mqtt_subcommands.add_parser("config", help="Set MQTT config.")
    mqtt_cfg.add_argument("--broker-url",    help="Broker URL เช่น mqtts://broker.example.com:8883")
    mqtt_cfg.add_argument("--username",      help="MQTT username")
    mqtt_cfg.add_argument("--password",      help="MQTT password")
    mqtt_cfg.add_argument("--client-id",     help="MQTT client ID (ว่าง = auto-generate)")
    mqtt_cfg.add_argument("--topic",         help="Topic ที่จะ publish QR scan")
    mqtt_cfg.add_argument("--qos",           type=int, choices=[0,1,2], help="QoS level (0/1/2)")
    mqtt_cfg.add_argument("--retain",        action="store_true", default=None, help="Enable retain flag")
    mqtt_cfg.add_argument("--no-retain",     action="store_true", help="Disable retain flag")
    mqtt_cfg.add_argument("--tls-insecure",  action="store_true", default=None, help="Skip TLS certificate verify")
    mqtt_cfg.add_argument("--no-tls-insecure", action="store_true", help="Enable TLS certificate verify")
    mqtt_cfg.add_argument("--enable",        action="store_true", default=None, help="เปิดใช้งาน MQTT publish")
    mqtt_cfg.add_argument("--disable",       action="store_true", help="ปิดใช้งาน MQTT publish")

    mqtt_subcommands.add_parser("test", help="Test publish ไปยัง broker ที่ config ไว้.")

    return parser


def add_x_session_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--display",
        "--x-display",
        dest="x_display",
        help="X display value, for example :0. Defaults to current DISPLAY.",
    )
    parser.add_argument("--xauthority", help="Optional XAUTHORITY file for controlling another user's X session.")


def add_wireguard_name_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", "--interface", default="wg0", help="WireGuard interface name. Defaults to wg0.")


def add_server_bind_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)


def add_mcp_bind_arguments(parser: argparse.ArgumentParser, defaults: McpConfig) -> None:
    parser.add_argument("--host", default=defaults.host)
    parser.add_argument("--port", type=int, default=defaults.port)


def add_component_arguments(parser: argparse.ArgumentParser, choices: tuple[str, ...]) -> None:
    parser.add_argument(
        "--component",
        action="append",
        choices=choices,
        required=True,
        help="Component to affect. Repeatable. Use all for every supported component.",
    )


def add_lifecycle_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--wireguard-name", "--wireguard-interface", default="wg0")
    parser.add_argument("--wireguard-store-dir", type=Path)
    parser.add_argument("--wireguard-dir", type=Path, default=Path("/etc/wireguard"), help=argparse.SUPPRESS)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runner = CommandRunner(dry_run=args.dry_run)
    return _run_parsed_command(args, runner, parser)


def _run_parsed_command(args: argparse.Namespace, runner: CommandRunner, parser: argparse.ArgumentParser) -> int:
    if args.command == "check":
        print_status()
        return 0

    if args.command == "about-os":
        print_os_info()
        return 0

    if args.command == "version":
        print(APP_VERSION)
        return 0

    if args.command == "update":
        if not args.dry_run:
            require_linux()
            require_root()
        SelfUpdater(
            runner,
            repo=args.repo,
            version=args.version,
            install_dir=args.install_dir,
            bin_dir=args.bin_dir,
        ).update()
        return 0

    if args.command == "server":
        if args.server_command == "run" or (args.server_command == "start" and args.foreground):
            url = f"http://{args.host}:{args.port}"
            if args.dry_run:
                print(f"start Flask server {url}")
                return 0
            try:
                from server import run_server
            except ImportError as error:
                if error.name != "flask":
                    raise
                raise RuntimeError(
                    "Flask is not installed. Run the background service setup first: "
                    "sudo vas server start"
                ) from error

            print(f"Starting vending-auto-setup dashboard at {url}")
            run_server(host=args.host, port=args.port, debug=getattr(args, "debug", False))
            return 0

        service_manager = ServerServiceManager(runner)

        if args.server_command == "install-service":
            if not args.dry_run:
                require_linux()
                require_root()
            service_manager.install(ServerConfig(host=args.host, port=args.port))
            return 0

        if args.server_command == "start":
            if args.dry_run:
                print(f"start dashboard service http://{args.host}:{args.port}")
                return 0
            require_linux()
            require_root()
            service_manager.start(ServerConfig(host=args.host, port=args.port))
            return 0

        if args.server_command == "stop":
            if not args.dry_run:
                require_linux()
                require_root()
            service_manager.stop()
            return 0

        if args.server_command == "status":
            service_manager.status()
            return 0

    if args.command == "mcp":
        if args.mcp_command == "run" or (args.mcp_command == "start" and args.foreground):
            url = f"http://{args.host}:{args.port}"
            if args.dry_run:
                print(f"start MCP server {url}")
                return 0
            try:
                from mcp_server import run_server
            except ImportError as error:
                if error.name != "fastmcp":
                    raise
                raise RuntimeError(
                    "fastmcp is not installed. Run: uv pip install -e '.[mcp]'"
                ) from error
            run_server(host=args.host, port=args.port)
            return 0

        mcp_service_manager = McpServiceManager(runner)

        if args.mcp_command == "install-service":
            if not args.dry_run:
                require_linux()
                require_root()
            mcp_service_manager.install(McpConfig(host=args.host, port=args.port))
            return 0

        if args.mcp_command == "start":
            if args.dry_run:
                print(f"start MCP service http://{args.host}:{args.port}")
                return 0
            require_linux()
            require_root()
            mcp_service_manager.start(McpConfig(host=args.host, port=args.port))
            return 0

        if args.mcp_command == "stop":
            if not args.dry_run:
                require_linux()
                require_root()
            mcp_service_manager.stop()
            return 0

        if args.mcp_command == "status":
            mcp_service_manager.status()
            return 0

    if args.command == "install":
        if not args.dry_run:
            require_linux()
            require_root()

        config = InstallConfig(
            node_major=args.node_major,
            docker_version=args.docker_version,
            git_version=args.git_version,
        )
        installer = PhaseOneInstaller(runner, config)
        components = tuple(args.component) if args.component else ("node", "docker", "git")
        if "all" in components:
            components = (*INSTALL_COMPONENTS,)
        core_components = tuple(component for component in components if component in {"node", "docker", "git", "anydesk", "openssh", "qr-udev"})
        total_operations = count_install_operations(core_components) if core_components else 0
        if "wireguard" in components:
            total_operations += 2
        runner.start_progress(total_operations)
        try:
            if core_components:
                installer.install_components(core_components)
            if "wireguard" in components:
                WireGuardManager(runner).install()
        finally:
            runner.stop_progress()
        return 0

    if args.command == "display":
        configurator = DisplayConfigurator(runner)

        if args.display_command == "status":
            configurator.print_status(x_display=args.x_display, xauthority=args.xauthority)
            return 0

        if args.display_command == "list-touch":
            configurator.print_touch_devices(x_display=args.x_display, xauthority=args.xauthority)
            return 0

        if args.display_command == "apply":
            configurator.apply_runtime(
                output=args.output,
                touch=args.touch,
                rotate=args.rotate,
                x_display=args.x_display,
                xauthority=args.xauthority,
            )
            return 0

        if args.display_command == "persist-xorg":
            if not args.dry_run:
                require_linux()
                require_root()
            configurator.persist_xorg(touch=args.touch, rotate=args.rotate)
            return 0

        if args.display_command == "persist-session":
            configurator.persist_session(
                output=args.output,
                touch=args.touch,
                rotate=args.rotate,
                x_display=args.x_display,
                delay_seconds=args.delay_seconds,
                retries=args.retries,
            )
            return 0

        if args.display_command == "disable-wayland":
            if not args.dry_run:
                require_linux()
                require_root()
            configurator.disable_wayland()
            return 0

        if args.display_command == "enable-wayland":
            if not args.dry_run:
                require_linux()
                require_root()
            configurator.enable_wayland()
            return 0

    if args.command == "wireguard":
        manager = WireGuardManager(
            runner,
            store_dir=args.store_dir,
            wireguard_dir=args.wireguard_dir,
        )

        if args.wireguard_command == "status":
            manager.print_status(name=args.name)
            return 0

        if args.wireguard_command == "install":
            if not args.dry_run:
                require_linux()
                require_root()
            runner.start_progress(2)
            try:
                manager.install()
            finally:
                runner.stop_progress()
            return 0

        if args.wireguard_command == "init-config":
            manager.init_config(name=args.name, output=args.output, force=args.force)
            return 0

        if args.wireguard_command == "validate":
            result = manager.validate_config(args.config)
            return 0 if result.valid else 1

        if args.wireguard_command == "save":
            manager.save(config=args.config, name=args.name)
            return 0

        if args.wireguard_command == "sync":
            if not args.dry_run:
                require_linux()
                require_root()
            manager.sync(name=args.name, config=args.config, restart=not args.no_restart)
            return 0

        if args.wireguard_command == "history":
            manager.history(name=args.name)
            return 0

        if args.wireguard_command == "show":
            manager.show(name=args.name, history_id=args.id, reveal_secrets=args.reveal_secrets)
            return 0

        if args.wireguard_command == "unsync":
            if not args.dry_run:
                require_linux()
                require_root()
            manager.unsync(name=args.name)
            return 0

    if args.command in {"uninstall", "reset"}:
        if not args.dry_run:
            require_linux()
            require_root()
        lifecycle_manager = LifecycleManager(
            runner,
            wireguard_store_dir=args.wireguard_store_dir,
            wireguard_dir=args.wireguard_dir,
        )
        components = tuple(args.component)
        if args.command == "uninstall":
            runner.start_progress(count_uninstall_operations(components))
            try:
                lifecycle_manager.uninstall(components=components, wireguard_name=args.wireguard_name)
            finally:
                runner.stop_progress()
            return 0
        runner.start_progress(count_reset_operations(components))
        try:
            lifecycle_manager.reset(components=components, wireguard_name=args.wireguard_name)
        finally:
            runner.stop_progress()
        return 0

    if args.command == "qr":
        from qr_reader import (
            QrConfig,
            find_zkteco_hidraw_devices,
            get_reader,
            load_qr_config,
            save_qr_config,
            start_reader,
            stop_reader,
        )
        from status import collect_qr_reader_status, _print_qr_reader_status

        if args.qr_command == "status":
            _print_qr_reader_status(collect_qr_reader_status())
            return 0

        if args.qr_command == "start":
            device = getattr(args, "device", None)
            try:
                import sys as _sys
                thread = start_reader(device_path=device)
                print(f"QR reader started on {thread.device_path}")
                import signal
                signal.pause()   # block จน Ctrl+C
            except (RuntimeError, OSError) as error:
                import sys as _sys
                print(f"Error: {error}", file=_sys.stderr)
                return 1
            return 0

        if args.qr_command == "stop":
            stop_reader()
            print("QR reader stopped.")
            return 0

        if args.qr_command == "last-scan":
            reader = get_reader()
            if reader is None or not reader.is_alive():
                import sys as _sys
                print("QR reader is not running.", file=_sys.stderr)
                return 1
            scan = reader.last_scan
            print(scan if scan is not None else "(no scan yet)")
            return 0

        if args.qr_command == "config":
            config = load_qr_config()
            if args.clear_device:
                config = QrConfig(device_path=None)
            elif getattr(args, "device", None):
                config = QrConfig(device_path=args.device)
            save_qr_config(config)
            print(f"Config saved: {config}")
            return 0

        if args.qr_command == "test":
            import signal as _signal
            from qr_reader import find_zkteco_evdev_devices, EvdevQrReaderThread, EVDEV_KEYMAP
            try:
                import evdev as _evdev  # type: ignore[import]
            except ImportError:
                import sys as _sys
                print("Error: python3-evdev is not installed.", file=_sys.stderr)
                print("Install: sudo apt install -y python3-evdev", file=_sys.stderr)
                return 1

            device_path = getattr(args, "device", None)
            if device_path is None:
                devices = find_zkteco_evdev_devices()
                if not devices:
                    import sys as _sys
                    print("Error: ไม่พบ ZKTeco evdev device", file=_sys.stderr)
                    print("ตรวจสอบ: sudo evtest", file=_sys.stderr)
                    return 1
                device_path = devices[0]

            grab = not getattr(args, "no_grab", False)
            try:
                device = _evdev.InputDevice(device_path)
                if grab:
                    device.grab()
            except OSError as error:
                import sys as _sys
                print(f"Error: {error}", file=_sys.stderr)
                return 1

            print(f"Device : {device.name}")
            print(f"Path   : {device.path}")
            print(f"Grab   : {'yes (keystrokes blocked from OS)' if grab else 'no (debug mode)'}")
            print()
            print("รอ scan QR... (Ctrl+C เพื่อหยุด)")
            print("-" * 50)

            buffer: list[str] = []
            scan_count = 0

            try:
                for event in device.read_loop():
                    if event.type != _evdev.ecodes.EV_KEY:
                        continue
                    key = _evdev.categorize(event)
                    if key.keystate != _evdev.KeyEvent.key_down:
                        continue
                    if key.scancode == 28:  # KEY_ENTER
                        if buffer:
                            data = "".join(buffer)
                            scan_count += 1
                            print(f"[#{scan_count}] {data}")
                            buffer.clear()
                    elif key.scancode in EVDEV_KEYMAP:
                        buffer.append(EVDEV_KEYMAP[key.scancode])
            except KeyboardInterrupt:
                pass  # Ctrl+C ออกจาก read_loop() ทันที
            finally:
                if grab:
                    try:
                        device.ungrab()
                    except Exception:
                        pass
                print(f"\nหยุดแล้ว — scan ทั้งหมด {scan_count} ครั้ง")
            return 0

        if args.qr_command == "install-udev":
            require_linux()
            require_root()
            from config import QR_UDEV_RULE_PATH, QR_UDEV_SIGNATURE
            rule_content = (
                f"{QR_UDEV_SIGNATURE}\n"
                "# ZKTeco QR500-BM / ZKRFID R400 — allow plugdev group access\n"
                'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5020", MODE="0666", GROUP="plugdev"\n'
                'SUBSYSTEM=="usb", ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5020", MODE="0664", GROUP="plugdev"\n'
                'KERNEL=="event*", ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5020", MODE="0664", GROUP="plugdev"\n'
            )
            QR_UDEV_RULE_PATH.parent.mkdir(parents=True, exist_ok=True)
            QR_UDEV_RULE_PATH.write_text(rule_content, encoding="utf-8")
            print(f"udev rule written: {QR_UDEV_RULE_PATH}")
            runner.run(["udevadm", "control", "--reload-rules"])
            runner.run(["udevadm", "trigger"])
            print("udev reloaded — ถอดแล้วเสียบ USB ใหม่เพื่อให้ rule มีผล")
            return 0

    if args.command == "mqtt":
        from mqtt_client import load_mqtt_config, save_mqtt_config, MqttConfig

        if args.mqtt_command == "status":
            cfg = load_mqtt_config()
            from mqtt_client import get_mqtt_status, _paho_available
            status = get_mqtt_status()
            print("[MQTT]")
            print(f"  enabled      : {'yes' if cfg.enabled else 'no'}")
            print(f"  connected    : {'yes' if status.get('connected') else 'no'}")
            print(f"  broker_url   : {cfg.broker_url}")
            print(f"  username     : {cfg.username or '(none)'}")
            print(f"  client_id    : {cfg.client_id or '(auto-generate)'}")
            print(f"  topic        : {cfg.topic}")
            print(f"  qos          : {cfg.qos}")
            print(f"  retain       : {'yes' if cfg.retain else 'no'}")
            print(f"  tls_insecure : {'yes' if cfg.tls_insecure else 'no'}")
            print(f"  paho-mqtt    : {'installed' if _paho_available() else 'NOT installed (sudo apt install -y python3-paho-mqtt)'}")
            if status.get("last_error"):
                print(f"  last_error   : {status['last_error']}")
            from config import main_config_path
            print(f"  config file  : {main_config_path().as_posix()}")
            return 0

        if args.mqtt_command == "config":
            cfg = load_mqtt_config()
            changed = False
            if getattr(args, "broker_url", None):
                cfg = MqttConfig(**{**cfg.to_dict(), "broker_url": args.broker_url})
                changed = True
            if getattr(args, "username", None) is not None:
                cfg = MqttConfig(**{**cfg.to_dict(), "username": args.username})
                changed = True
            if getattr(args, "password", None) is not None:
                cfg = MqttConfig(**{**cfg.to_dict(), "password": args.password})
                changed = True
            if getattr(args, "client_id", None) is not None:
                cfg = MqttConfig(**{**cfg.to_dict(), "client_id": args.client_id})
                changed = True
            if getattr(args, "topic", None):
                cfg = MqttConfig(**{**cfg.to_dict(), "topic": args.topic})
                changed = True
            if getattr(args, "qos", None) is not None:
                cfg = MqttConfig(**{**cfg.to_dict(), "qos": args.qos})
                changed = True
            if getattr(args, "retain", None):
                cfg = MqttConfig(**{**cfg.to_dict(), "retain": True})
                changed = True
            if getattr(args, "no_retain", False):
                cfg = MqttConfig(**{**cfg.to_dict(), "retain": False})
                changed = True
            if getattr(args, "tls_insecure", None):
                cfg = MqttConfig(**{**cfg.to_dict(), "tls_insecure": True})
                changed = True
            if getattr(args, "no_tls_insecure", False):
                cfg = MqttConfig(**{**cfg.to_dict(), "tls_insecure": False})
                changed = True
            if getattr(args, "enable", None):
                cfg = MqttConfig(**{**cfg.to_dict(), "enabled": True})
                changed = True
            if getattr(args, "disable", False):
                cfg = MqttConfig(**{**cfg.to_dict(), "enabled": False})
                changed = True
            if not changed:
                # ถ้าไม่มี flag ใดเลย แสดง current config
                print("Usage: vas mqtt config [--broker-url ...] [--topic ...] [--enable] ...")
                print("Current config:")
                for k, v in cfg.to_dict().items():
                    print(f"  {k:14}: {v}")
                return 0
            save_mqtt_config(cfg)
            from config import main_config_path
            print(f"Config saved → {main_config_path().as_posix()}")
            for k, v in cfg.to_dict().items():
                print(f"  {k:14}: {v}")
            return 0

        if args.mqtt_command == "test":
            from mqtt_client import start_mqtt, get_mqtt_client, _paho_available
            import json as _json_mod
            from datetime import datetime, timezone
            if not _paho_available():
                print("Error: paho-mqtt ไม่ได้ติดตั้ง — รัน: sudo apt install -y python3-paho-mqtt")
                return 1
            cfg = load_mqtt_config()
            if not cfg.broker_url:
                print("Error: ยังไม่ได้ตั้งค่า broker_url — รัน: vas mqtt config --broker-url ...")
                return 1
            print(f"กำลังเชื่อมต่อ {cfg.broker_url} ...")
            import time as _time
            c = start_mqtt(cfg)
            for _ in range(20):  # รอ connect max 4 วิ
                _time.sleep(0.2)
                if c.is_connected:
                    break
            if not c.is_connected:
                print(f"Error: เชื่อมต่อไม่สำเร็จ — {c.last_error or 'timeout'}")
                return 1
            ts = datetime.now(timezone.utc).isoformat()
            payload = _json_mod.dumps({"scan": "TEST-VAS-QR", "device": "test", "ts": ts}, ensure_ascii=False)
            ok = c.publish(cfg.topic, payload)
            if ok:
                print(f"✓ publish สำเร็จ")
                print(f"  topic  : {cfg.topic}")
                print(f"  payload: {payload}")
            else:
                print("Error: publish ไม่สำเร็จ")
                return 1
            return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


def _print_qr_status(status: "QrReaderStatus") -> None:
    from status import QrReaderStatus
    print("[QR Reader]")
    udev_marker = "OK" if status.udev_rule_has_signature else "WARN"
    print(f"{udev_marker:7} {'udev rule':12} {status.udev_rule_path.as_posix()}")
    dev_marker = "OK" if status.detected_devices else "WARN"
    devices_str = ", ".join(status.detected_devices) if status.detected_devices else "none detected"
    print(f"{dev_marker:7} {'devices':12} {devices_str}")
    reader_marker = "OK" if status.reader_running else "WARN"
    active = "running on " + (status.active_device or "") if status.reader_running else "stopped"
    print(f"{reader_marker:7} {'reader':12} {active}")
    if status.last_scan is not None:
        print(f"{'':7} {'last scan':12} {status.last_scan}")
