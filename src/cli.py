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
        core_components = tuple(component for component in components if component in {"node", "docker", "git", "anydesk"})
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

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
