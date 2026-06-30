from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


class _IntegProxy:
    """Wrap raw integration dict so templates can do integrations.webhook.enabled etc."""
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getattr__(self, name: str) -> "_IntegEntry":
        return _IntegEntry(self._data.get(name, {}))


class _IntegEntry:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        return self._data.get(name)

from flask import Flask, render_template, request, redirect

from system.audit import (
    create_system_log_snapshot,
    list_system_snapshots,
    read_system_snapshot,
    system_snapshot_dir,
)
from features.display.display import (
    DisplayConfigurator,
    ROTATION_MATRICES,
    TouchDevice,
    get_udevadm_touchscreen_names,
    parse_xinput_device_map,
)
from core.runner import CommandExecutionError, CommandResult, CommandRunner
from system.status import (
    OpenSshStatus,
    QrReaderStatus,
    ToolStatus,
    VpnStatus,
    collect_gdm_wayland_status,
    collect_display_session_config_status,
    collect_display_session_script_status,
    collect_display_session_status,
    collect_openssh_status,
    collect_qr_reader_status,
    collect_remote_access_status,
    collect_status,
    collect_vpn_status,
    collect_web_server_status,
    collect_xorg_touchscreen_config_status,
)
from features.wireguard.manager import (
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
INSTALL_COMPONENTS = ("all", "git", "node", "docker", "wireguard", "anydesk", "openssh", "qr-udev")
LIFECYCLE_COMPONENTS = ("all", "git", "node", "docker", "wireguard", "anydesk", "openssh", "qr-udev")
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
    ("Disable GDM Wayland", "sudo vas display disable-wayland"),
    ("Enable GDM Wayland", "sudo vas display enable-wayland"),
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


def vpn_connection_label(vpn: "VpnStatus") -> str:  # type: ignore[name-defined]
    """คืน label สั้นๆ แสดงสถานะ VPN สำหรับ Jinja2 templates"""
    from system.status import VpnStatus as _VpnStatus  # noqa: F401 — used for type hint only
    if not vpn.wg_installed:
        return "ไม่ได้ติดตั้ง"
    if not vpn.app_config_exists:
        return "ยังไม่ได้ตั้งค่า"
    if not vpn.interface_exists:
        return "ไม่ได้เชื่อมต่อ"
    if vpn.handshake_peers and vpn.handshake_peers > 0:
        return f"เชื่อมต่อแล้ว ({vpn.handshake_peers} peer)"
    return "เชื่อมต่อแล้ว"


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(WEB_DIR / "templates"),
        static_folder=str(WEB_DIR / "static"),
    )
    # Secret key — ใช้ env var ถ้ามี, fallback เป็น random (dev only)
    import secrets as _secrets
    app.secret_key = os.environ.get("VAS_SECRET_KEY") or _secrets.token_hex(32)
    app.jinja_env.globals["vpn_connection_label"] = vpn_connection_label

    # ── Auth: before_request ────────────────────────────────────────
    # Routes ที่ไม่ต้อง login
    _PUBLIC_ENDPOINTS = frozenset([
        "auth_login", "auth_login_post",
        "auth_logout",
        "auth_setup", "auth_setup_post",
        "static", "serve_logo",
        "health",
    ])

    @app.before_request
    def require_login() -> object:
        from flask import session as flask_session, redirect, url_for as _url_for
        from core.auth import is_first_run, get_user_by_id
        # SSE / API prefix — allow through (checked per-route if needed)
        if request.endpoint in _PUBLIC_ENDPOINTS:
            return None
        if request.path.startswith("/api/"):
            return None  # API routes ตรวจสอบ auth เอง
        # First run
        if is_first_run():
            return redirect(_url_for("auth_setup"))
        # Check session
        user_id = flask_session.get("vas_user_id")
        if not user_id:
            return redirect(_url_for("auth_login", next=request.path))
        user = get_user_by_id(int(user_id))
        if user is None:
            flask_session.clear()
            return redirect(_url_for("auth_login"))
        return None

    @app.context_processor
    def inject_spa_context() -> dict[str, object]:
        """Inject is_partial + current_user so every template can use them."""
        from flask import session as flask_session
        from core.auth import get_user_by_id, ROLE_BADGE_CLASS, ROLE_LABELS, can_manage_user
        is_partial = request.headers.get("X-VAS-Partial") == "1"
        base_template = "base_partial.html" if is_partial else "base.html"
        current_user = None
        user_id = flask_session.get("vas_user_id")
        if user_id:
            current_user = get_user_by_id(int(user_id))
        return {
            "is_partial": is_partial,
            "base_template": base_template,
            "current_user": current_user,
            "role_badge": ROLE_BADGE_CLASS,
            "role_labels": ROLE_LABELS,
            "can_manage": can_manage_user,
        }

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
            openssh=collect_openssh_status(),
            vpn=collect_vpn_status(),
            web_server=collect_web_server_status(),
            qr_reader=collect_qr_reader_status(),
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
        try:
            from core.database import log_audit as _db_audit
            _db_audit("snapshot_created", {"id": snapshot.get("id"), "size": snapshot.get("size"), "path": snapshot.get("path")})
        except Exception:
            pass
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
            gdm_wayland=collect_gdm_wayland_status(),
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

    @app.post("/api/display/wayland")
    def display_wayland() -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "")).strip()
        configurator = DisplayConfigurator(DisplayCommandRunner())
        try:
            if action == "disable":
                configurator.disable_wayland()
            elif action == "enable":
                configurator.enable_wayland()
            else:
                return {"status": "error", "errors": [f"Unknown Wayland action: {action}"]}, 400
        except (CommandExecutionError, OSError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 500

        status = collect_gdm_wayland_status()
        return {
            "status": "ok",
            "action": action,
            "gdmWayland": {
                "disabled": status.disabled,
                "exists": status.exists,
                "readable": status.readable,
                "value": status.value,
                "path": status.path.as_posix(),
            },
        }

    # ── Display simulation (Virtual Touchscreen) ──────────────────
    _sim_proc: list["subprocess.Popen[bytes] | None"] = [None]  # mutable cell inside closure
    _SIM_SCRIPT = Path(__file__).parent.parent / "scripts" / "dev" / "virtual_touchscreen.py"

    @app.get("/api/display/sim/status")
    def display_sim_status() -> dict[str, object]:
        proc = _sim_proc[0]
        running = proc is not None and proc.poll() is None
        return {
            "lib_ok":  True,
            "running": running,
            "pid":     proc.pid if running else None,
        }

    @app.post("/api/display/sim/start")
    def display_sim_start() -> tuple[dict[str, object], int] | dict[str, object]:
        import subprocess as _sp
        proc = _sim_proc[0]
        if proc is not None and proc.poll() is None:
            return {"status": "ok", "message": "already_running", "pid": proc.pid}
        if not _SIM_SCRIPT.exists():
            return {"status": "error", "errors": ["Script not found"]}, 404
        try:
            _sim_proc[0] = _sp.Popen(
                ["sudo", "python3", str(_SIM_SCRIPT)],
                stdout=_sp.PIPE, stderr=_sp.STDOUT,
            )
            return {"status": "ok", "pid": _sim_proc[0].pid}
        except OSError as exc:
            return {"status": "error", "errors": [str(exc)]}, 500

    @app.post("/api/display/sim/stop")
    def display_sim_stop() -> dict[str, object]:
        proc = _sim_proc[0]
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            _sim_proc[0] = None
        return {"status": "ok"}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # ── Database init ────────────────────────────────────────────
    from core.database import init_db as _init_db
    _init_db()

    import atexit
    from features.qr.reader import stop_reader as _stop_qr_reader
    from features.mqtt.client import stop_mqtt as _stop_mqtt
    atexit.register(_stop_qr_reader)
    atexit.register(_stop_mqtt)

    # Auto-start QR reader เมื่อ server boot (ถ้ามี device ต่ออยู่)
    try:
        from features.qr.reader import get_reader as _get_qr_reader, start_reader as _auto_start_qr
        if _get_qr_reader() is None:
            _auto_start_qr()
    except Exception:
        pass  # ยังไม่มี device — reader จะ start เมื่อกด restart หรือเสียบ USB ใหม่

    # Auto-start MQTT ถ้า enabled
    try:
        from features.mqtt.client import load_mqtt_config as _load_mqtt_cfg, start_mqtt as _auto_start_mqtt
        _mqtt_boot_cfg = _load_mqtt_cfg()
        if _mqtt_boot_cfg.enabled:
            _auto_start_mqtt(_mqtt_boot_cfg)
    except Exception:
        pass

    @app.get("/qr")
    def qr_reader_page() -> str:
        from features.qr.reader import find_zkteco_evdev_devices, find_zkteco_hidraw_devices, load_qr_config
        evdev_devices = find_zkteco_evdev_devices()
        hidraw_devices = find_zkteco_hidraw_devices()
        # รวม evdev ก่อน hidraw (evdev = HID keyboard Open mode ที่แนะนำ)
        all_devices = evdev_devices + [d for d in hidraw_devices if d not in evdev_devices]
        return render_template(
            "qr.html",
            qr_reader=collect_qr_reader_status(),
            detected_devices=all_devices,
            evdev_devices=evdev_devices,
            hidraw_devices=hidraw_devices,
            config=load_qr_config(),
        )

    @app.get("/api/qr/last-scan")
    def qr_last_scan_api() -> dict[str, object]:
        """Return: {"status":"ok","scan":<str|null>,"device":<str|null>,"running":<bool>}"""
        from features.qr.reader import get_reader
        reader = get_reader()
        running = reader is not None and reader.is_alive()
        return {
            "status": "ok",
            "scan": reader.last_scan if running else None,
            "device": reader.device_path if running else None,
            "running": running,
        }

    @app.post("/api/qr/start")
    def qr_start_api() -> tuple[dict[str, object], int] | dict[str, object]:
        """
        Payload (optional): {"device": "/dev/hidraw0"}
        200: {"status":"ok","device":<path>,"running":true}
        400: {"status":"error","errors":[...]}  -- device not found
        500: {"status":"error","errors":[...]}  -- OS error
        """
        from features.qr.reader import start_reader
        payload = request.get_json(silent=True) or {}
        device = str(payload.get("device", "")).strip() or None
        try:
            thread = start_reader(device_path=device)
        except RuntimeError as error:
            return {"status": "error", "errors": [str(error)]}, 400
        except OSError as error:
            return {"status": "error", "errors": [str(error)]}, 500
        return {"status": "ok", "device": thread.device_path, "running": True}

    @app.post("/api/qr/stop")
    def qr_stop_api() -> dict[str, object]:
        """Return: {"status":"ok","running":false}"""
        from features.qr.reader import stop_reader
        stop_reader()
        return {"status": "ok", "running": False}

    @app.get("/api/qr/config")
    def qr_config_get_api() -> dict[str, object]:
        """Return: {"status":"ok","config":{"device_path":<str|null>},"path":<file_path>}"""
        from features.qr.reader import load_qr_config
        from core.config import qr_config_path
        config = load_qr_config()
        return {
            "status": "ok",
            "config": config.to_dict(),
            "path": qr_config_path().as_posix(),
        }

    @app.post("/api/qr/config")
    def qr_config_save_api() -> tuple[dict[str, object], int] | dict[str, object]:
        """
        Payload: {"device_path": "/dev/hidraw0"}  -- null clears to auto-detect
        200: {"status":"ok","config":{...}}
        500: {"status":"error","errors":[...]}
        """
        from features.qr.reader import QrConfig, save_qr_config, load_qr_config
        payload = request.get_json(silent=True) or {}
        device_path = payload.get("device_path") or None
        if device_path is not None:
            device_path = str(device_path).strip() or None
        old_config = load_qr_config()
        config = QrConfig(device_path=device_path)
        try:
            save_qr_config(config)
        except OSError as error:
            return {"status": "error", "errors": [str(error)]}, 500
        try:
            from core.database import log_config_change as _db_cfg
            _db_cfg("qr", "*", old_value=old_config.to_dict(), new_value=config.to_dict())
        except Exception:
            pass
        return {"status": "ok", "config": config.to_dict()}

    @app.get("/api/qr/stream")
    def qr_stream_api():  # type: ignore[return]
        """
        Server-Sent Events stream -- real-time QR scan

        SSE event format:

            event: scan
            data: {"scan": "<value>", "device": "<path>", "ts": "<ISO8601-UTC>"}

            event: status
            data: {"running": <bool>, "device": "<path>"|null}

            event: heartbeat
            data: {}
        """
        from flask import stream_with_context, Response
        import time
        from datetime import datetime, timezone

        def generate():
            from features.qr.reader import get_reader, start_reader

            def _try_start():
                """Auto-start reader ถ้ายังไม่ทำงาน — ไม่ raise"""
                r = get_reader()
                if r is not None and r.is_alive():
                    return r
                try:
                    return start_reader()
                except Exception:
                    return None

            # Auto-start ทันทีที่ client เชื่อมต่อ
            reader = _try_start()
            running = reader is not None and reader.is_alive()
            device = reader.device_path if running else None
            yield f"event: status\ndata: {_json_dumps({'running': running, 'device': device})}\n\n"

            last_seen: str | None = None
            last_heartbeat = time.monotonic()
            last_restart_try = 0.0  # ลอง restart ทันทีรอบแรกถ้า reader ตาย
            HEARTBEAT_INTERVAL = 5.0
            POLL_INTERVAL = 0.2
            RESTART_INTERVAL = 8.0  # retry ทุก 8 วิถ้า reader ไม่ทำงาน

            try:
                while True:
                    time.sleep(POLL_INTERVAL)
                    now = time.monotonic()

                    if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                        yield "event: heartbeat\ndata: {}\n\n"
                        last_heartbeat = now

                    reader = get_reader()
                    currently_alive = reader is not None and reader.is_alive()

                    # ลอง auto-restart ถ้า reader ตายและถึงเวลา retry
                    if not currently_alive and now - last_restart_try >= RESTART_INTERVAL:
                        last_restart_try = now
                        restarted = _try_start()
                        if restarted is not None and restarted.is_alive():
                            reader = restarted
                            currently_alive = True

                    # ส่ง status event เมื่อ state เปลี่ยน
                    if currently_alive != running:
                        running = currently_alive
                        d = reader.device_path if running and reader else None
                        yield f"event: status\ndata: {_json_dumps({'running': running, 'device': d})}\n\n"

                    if reader is not None and reader.is_alive():
                        scan = reader.last_scan
                        if scan is not None and scan != last_seen:
                            last_seen = scan
                            ts = datetime.now(timezone.utc).isoformat()
                            yield f"event: scan\ndata: {_json_dumps({'scan': scan, 'device': reader.device_path, 'ts': ts})}\n\n"
                            # Log QR scan ลง DB
                            try:
                                from core.database import log_qr_scan as _db_log_qr
                                _db_log_qr(scan, reader.device_path, ts)
                            except Exception:
                                pass
                            # Publish ออก MQTT ถ้า client เชื่อมต่ออยู่
                            try:
                                from features.mqtt.client import publish_qr_scan as _mqtt_publish
                                scan_raw = getattr(reader, "last_scan_raw", None)
                                _mqtt_publish(scan, reader.device_path, ts, scan_raw=scan_raw)
                            except Exception:
                                pass
            except GeneratorExit:
                # client disconnected
                return

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ── QR Device catalog & integration routes ──────────────────

    @app.get("/qr/devices")
    def qr_devices_page() -> str:
        from features.qr.registry import load_installed_devices, DEVICE_CATALOG
        installed = load_installed_devices()
        installed_ids = {d["id"] for d in installed}
        installed_list = [
            {
                "id": d["id"],
                "name": d["name"],
                "brand": d["brand"],
                "page_endpoint": d["page_endpoint"],
            }
            for d in DEVICE_CATALOG if d["id"] in installed_ids
        ]
        return render_template(
            "qr_devices.html",
            installed_devices=installed_list,
            installed_device_ids=installed_ids,
        )

    @app.get("/qr/device/zkteco/qr500")
    def qr_device_zkteco_qr500_page() -> str:
        from features.qr.reader import find_zkteco_evdev_devices, find_zkteco_hidraw_devices, load_qr_config
        from features.qr.registry import load_integrations
        from core.database import list_mqtt_brokers
        evdev_devices = find_zkteco_evdev_devices()
        hidraw_devices = find_zkteco_hidraw_devices()
        integrations_raw = load_integrations("zkteco-qr500")
        integration_count = sum(1 for v in integrations_raw.values() if v.get("enabled"))
        return render_template(
            "qr_device_zkteco_qr500.html",
            qr_reader=collect_qr_reader_status(),
            evdev_devices=evdev_devices,
            hidraw_devices=hidraw_devices,
            config=load_qr_config(),
            integrations=_IntegProxy(integrations_raw),
            integration_count=integration_count,
            mqtt_brokers=list_mqtt_brokers(),
        )

    @app.post("/api/qr/devices/<device_id>/install")
    def qr_device_install_api(device_id: str) -> tuple[dict[str, object], int] | dict[str, object]:
        from features.qr.registry import install_device, DEVICE_CATALOG
        valid_ids = {d["id"] for d in DEVICE_CATALOG}
        if device_id not in valid_ids:
            return {"status": "error", "error": "unknown device id"}, 404
        try:
            install_device(device_id)
        except Exception as e:
            return {"status": "error", "error": str(e)}, 500
        return {"status": "ok", "device_id": device_id}

    @app.post("/api/qr/devices/<device_id>/uninstall")
    def qr_device_uninstall_api(device_id: str) -> dict[str, object]:
        from features.qr.registry import uninstall_device
        try:
            uninstall_device(device_id)
        except Exception as e:
            return {"status": "error", "error": str(e)}, 500
        return {"status": "ok", "device_id": device_id}

    @app.get("/api/qr/integrations")
    def qr_integrations_get_api() -> dict[str, object]:
        from features.qr.registry import load_integrations
        raw = load_integrations("zkteco-qr500")
        integ_list: list[dict[str, object]] = []
        for t in ("webhook", "mqtt", "pipe"):
            cfg = dict(raw.get(t, {}))
            cfg["type"] = t
            integ_list.append(cfg)
        return {"status": "ok", "integrations": integ_list}

    @app.post("/api/qr/integrations/<integ_type>")
    def qr_integration_save_api(integ_type: str) -> tuple[dict[str, object], int] | dict[str, object]:
        from features.qr.registry import load_integrations, save_integrations
        if integ_type not in ("webhook", "mqtt", "pipe"):
            return {"status": "error", "error": "unknown integration type"}, 400
        payload = request.get_json(silent=True) or {}
        try:
            data = load_integrations("zkteco-qr500")
            data[integ_type] = {k: v for k, v in payload.items() if k != "type"}
            save_integrations("zkteco-qr500", data)
        except Exception as e:
            return {"status": "error", "error": str(e)}, 500
        count = sum(1 for v in data.values() if v.get("enabled"))
        return {"status": "ok", "integration_count": count}

    @app.post("/api/qr/integrations/pipe/create")
    def qr_pipe_create_api() -> tuple[dict[str, object], int] | dict[str, object]:
        import os as _os
        payload = request.get_json(silent=True) or {}
        path = str(payload.get("path", "/tmp/vas_qr_pipe")).strip()
        if not path:
            return {"status": "error", "error": "path required"}, 400
        try:
            if not _os.path.exists(path):
                _os.mkfifo(path, 0o666)
            elif not _os.path.isfifo(path):
                return {"status": "error", "error": f"{path} exists but is not a pipe"}, 400
        except OSError as e:
            return {"status": "error", "error": str(e)}, 500
        return {"status": "ok", "path": path}

    # ── MQTT routes ─────────────────────────────────────────────

    @app.get("/mqtt")
    def mqtt_page() -> str:
        from core.database import list_mqtt_brokers
        from features.mqtt.client import get_mqtt_client
        c = get_mqtt_client()
        active_url = c.config.broker_url if c else None
        brokers = list_mqtt_brokers()
        return render_template(
            "mqtt.html",
            brokers=brokers,
            active_broker_url=active_url,
            active_client=c,
        )

    @app.get("/mqtt/broker/add")
    def mqtt_broker_add_page() -> str:
        return render_template("mqtt_broker_form.html", broker=None, edit=False)

    @app.get("/mqtt/broker/<int:broker_id>")
    def mqtt_broker_detail_page(broker_id: int) -> str:
        from core.database import get_mqtt_broker, list_mqtt_topics
        from features.mqtt.client import get_broker_connection_status
        broker = get_mqtt_broker(broker_id)
        if broker is None:
            return render_template("mqtt.html", brokers=[], active_broker_url=None,
                                   active_client=None), 404  # type: ignore[return-value]
        topics = list_mqtt_topics(broker_id)
        conn_status = get_broker_connection_status(broker_id)
        return render_template(
            "mqtt_broker_detail.html",
            broker=broker,
            topics=topics,
            conn_status=conn_status,
        )

    @app.get("/mqtt/broker/<int:broker_id>/edit")
    def mqtt_broker_edit_page(broker_id: int) -> str:
        from core.database import get_mqtt_broker
        broker = get_mqtt_broker(broker_id)
        if broker is None:
            return redirect("/mqtt")  # type: ignore[return-value]
        return render_template("mqtt_broker_form.html", broker=broker, edit=True)

    # ── MQTT API ─────────────────────────────────────────────────

    @app.get("/api/mqtt/status")
    def mqtt_status_api() -> dict[str, object]:
        from features.mqtt.client import get_mqtt_status
        return {"status": "ok", **get_mqtt_status()}

    @app.post("/api/mqtt/brokers")
    def mqtt_broker_create_api() -> tuple[dict[str, object], int] | dict[str, object]:
        """สร้าง broker ใหม่"""
        from core.database import create_mqtt_broker, get_mqtt_broker
        from features.mqtt.client import start_mqtt_broker
        payload = request.get_json(silent=True) or {}
        try:
            new_id = create_mqtt_broker(payload)
            broker = get_mqtt_broker(new_id)
            if broker and broker.get("enabled") and broker.get("is_primary"):
                try:
                    start_mqtt_broker(new_id)
                except Exception:
                    pass
            return {"status": "ok", "id": new_id}
        except Exception as e:
            return {"status": "error", "errors": [str(e)]}, 500

    @app.put("/api/mqtt/brokers/<int:broker_id>")
    def mqtt_broker_update_api(broker_id: int) -> tuple[dict[str, object], int] | dict[str, object]:
        """อัปเดต broker"""
        from core.database import update_mqtt_broker, get_mqtt_broker
        from features.mqtt.client import start_mqtt_broker, stop_mqtt
        payload = request.get_json(silent=True) or {}
        try:
            ok = update_mqtt_broker(broker_id, payload)
            if not ok:
                return {"status": "error", "errors": ["update ไม่สำเร็จ"]}, 500
            broker = get_mqtt_broker(broker_id)
            if broker and broker.get("is_primary"):
                stop_mqtt()
                if broker.get("enabled"):
                    try:
                        start_mqtt_broker(broker_id)
                    except Exception:
                        pass
            return {"status": "ok", "id": broker_id}
        except Exception as e:
            return {"status": "error", "errors": [str(e)]}, 500

    @app.delete("/api/mqtt/brokers/<int:broker_id>")
    def mqtt_broker_delete_api(broker_id: int) -> tuple[dict[str, object], int] | dict[str, object]:
        """ลบ broker"""
        from core.database import delete_mqtt_broker, get_mqtt_broker
        from features.mqtt.client import stop_mqtt, get_mqtt_client
        broker = get_mqtt_broker(broker_id)
        if broker and broker.get("is_primary"):
            c = get_mqtt_client()
            if c and c.config.broker_url == broker.get("broker_url"):
                stop_mqtt()
        ok = delete_mqtt_broker(broker_id)
        if not ok:
            return {"status": "error", "errors": ["ลบไม่สำเร็จ"]}, 500
        return {"status": "ok"}

    @app.get("/api/mqtt/brokers/<int:broker_id>/status")
    def mqtt_broker_status_api(broker_id: int) -> dict[str, object]:
        from features.mqtt.client import get_broker_connection_status
        return {"status": "ok", **get_broker_connection_status(broker_id)}

    @app.post("/api/mqtt/brokers/<int:broker_id>/connect")
    def mqtt_broker_connect_api(broker_id: int) -> tuple[dict[str, object], int] | dict[str, object]:
        """เชื่อมต่อ broker ที่ระบุ (set as active)"""
        from features.mqtt.client import start_mqtt_broker
        try:
            start_mqtt_broker(broker_id)
            return {"status": "ok", "broker_id": broker_id}
        except ImportError as e:
            return {"status": "error", "errors": [str(e)]}, 500
        except Exception as e:
            return {"status": "error", "errors": [str(e)]}, 500

    @app.post("/api/mqtt/brokers/<int:broker_id>/disconnect")
    def mqtt_broker_disconnect_api(broker_id: int) -> dict[str, object]:
        from features.mqtt.client import stop_mqtt, get_mqtt_client
        from core.database import get_mqtt_broker
        broker = get_mqtt_broker(broker_id)
        c = get_mqtt_client()
        if broker and c and c.config.broker_url == broker.get("broker_url"):
            stop_mqtt()
        return {"status": "ok", "connected": False}

    @app.post("/api/mqtt/brokers/<int:broker_id>/test")
    def mqtt_broker_test_api(broker_id: int) -> tuple[dict[str, object], int] | dict[str, object]:
        """Test publish ไปยัง broker ที่ระบุ"""
        from features.mqtt.client import get_mqtt_client, get_broker_connection_status
        from core.database import get_mqtt_broker, list_mqtt_topics
        import json as _j
        from datetime import datetime, timezone
        broker = get_mqtt_broker(broker_id)
        if broker is None:
            return {"status": "error", "errors": ["ไม่พบ broker"]}, 404
        c = get_mqtt_client()
        conn = get_broker_connection_status(broker_id)
        if not conn.get("is_active") or not conn.get("connected"):
            return {"status": "error", "errors": ["broker นี้ไม่ได้ active หรือยังไม่เชื่อมต่อ"]}, 400
        topics = list_mqtt_topics(broker_id)
        test_topic = next(
            (t["topic"] for t in topics if t.get("enabled")),
            "vas/test",
        )
        payload_str = _j.dumps({
            "scan": "TEST-VAS-QR",
            "device": "test",
            "ts": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False)
        ok = c.publish(str(test_topic), payload_str)  # type: ignore[union-attr]
        if not ok:
            return {"status": "error", "errors": ["publish ไม่สำเร็จ — ตรวจสอบ connection"]}, 500
        return {"status": "ok", "topic": test_topic, "payload": payload_str}

    # ── MQTT Topic API ────────────────────────────────────────────

    @app.post("/api/mqtt/brokers/<int:broker_id>/topics")
    def mqtt_topic_add_api(broker_id: int) -> tuple[dict[str, object], int] | dict[str, object]:
        from core.database import add_mqtt_topic, get_mqtt_broker
        payload = request.get_json(silent=True) or {}
        if not get_mqtt_broker(broker_id):
            return {"status": "error", "errors": ["broker ไม่พบ"]}, 404
        topic = str(payload.get("topic") or "").strip()
        if not topic:
            return {"status": "error", "errors": ["topic ห้ามว่าง"]}, 400
        label = str(payload.get("label") or "").strip()
        new_id = add_mqtt_topic(broker_id, topic, label)
        return {"status": "ok", "id": new_id}

    @app.put("/api/mqtt/topics/<int:topic_id>")
    def mqtt_topic_update_api(topic_id: int) -> tuple[dict[str, object], int] | dict[str, object]:
        from core.database import update_mqtt_topic
        payload = request.get_json(silent=True) or {}
        ok = update_mqtt_topic(topic_id, payload)
        return {"status": "ok"} if ok else ({"status": "error", "errors": ["update ไม่สำเร็จ"]}, 500)

    @app.delete("/api/mqtt/topics/<int:topic_id>")
    def mqtt_topic_delete_api(topic_id: int) -> tuple[dict[str, object], int] | dict[str, object]:
        from core.database import delete_mqtt_topic
        ok = delete_mqtt_topic(topic_id)
        return {"status": "ok"} if ok else ({"status": "error", "errors": ["ลบไม่สำเร็จ"]}, 500)

    # ── Legacy single-config MQTT API (kept for backward compat) ──

    @app.post("/api/mqtt/config")
    def mqtt_config_save_api() -> tuple[dict[str, object], int] | dict[str, object]:
        from features.mqtt.client import MqttConfig, save_mqtt_config, start_mqtt, stop_mqtt, load_mqtt_config
        payload = request.get_json(silent=True) or {}
        try:
            old_config = load_mqtt_config()
            config = MqttConfig.from_dict(payload)
            save_mqtt_config(config)
            stop_mqtt()
            if config.enabled:
                start_mqtt(config)
        except ImportError as e:
            return {"status": "error", "errors": [str(e)]}, 500
        except Exception as e:
            return {"status": "error", "errors": [str(e)]}, 500
        try:
            from core.database import log_config_change as _db_cfg
            old_d = {k: v for k, v in old_config.to_dict().items() if k != "password"}
            new_d = {k: v for k, v in config.to_dict().items() if k != "password"}
            _db_cfg("mqtt", "*", old_value=old_d, new_value=new_d)
        except Exception:
            pass
        from features.mqtt.client import get_mqtt_status
        return {"status": "ok", "mqtt": get_mqtt_status()}

    @app.post("/api/mqtt/test")
    def mqtt_test_api() -> tuple[dict[str, object], int] | dict[str, object]:
        from features.mqtt.client import get_mqtt_client
        from datetime import datetime, timezone
        import json as _j
        c = get_mqtt_client()
        if c is None:
            return {"status": "error", "errors": ["MQTT client ยังไม่ได้เชื่อมต่อ"]}, 400
        if not c.is_connected:
            return {"status": "error", "errors": ["ยังไม่ได้เชื่อมต่อกับ broker"]}, 400
        payload = _j.dumps({
            "scan": "TEST-VAS-QR", "device": "test",
            "ts": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False)
        ok = c.publish(c.config.topic, payload)
        if not ok:
            return {"status": "error", "errors": ["publish ไม่สำเร็จ"]}, 500
        return {"status": "ok", "topic": c.config.topic, "payload": payload}

    @app.post("/api/mqtt/disconnect")
    def mqtt_disconnect_api() -> dict[str, object]:
        from features.mqtt.client import stop_mqtt
        stop_mqtt()
        return {"status": "ok", "connected": False}

    # ── MQTT Monitor (background subscriber for live testing) ─────

    @app.post("/api/mqtt/monitor/start")
    def mqtt_monitor_start_api() -> tuple[dict[str, object], int] | dict[str, object]:
        from features.mqtt.client import get_monitor_session
        data = request.get_json(silent=True) or {}
        broker_id = data.get("broker_id")
        topic = data.get("topic", "#")
        if not broker_id:
            return {"status": "error", "errors": ["broker_id required"]}, 400
        result = get_monitor_session().start(int(broker_id), topic)
        if result["ok"]:
            return {"status": "ok"}
        return {"status": "error", "errors": [result.get("error", "unknown")]}, 500

    @app.post("/api/mqtt/monitor/stop")
    def mqtt_monitor_stop_api() -> dict[str, object]:
        from features.mqtt.client import get_monitor_session
        get_monitor_session().stop()
        return {"status": "ok"}

    @app.get("/api/mqtt/monitor/status")
    def mqtt_monitor_status_api() -> dict[str, object]:
        from features.mqtt.client import get_monitor_session
        return get_monitor_session().status()

    @app.get("/api/mqtt/monitor/messages")
    def mqtt_monitor_messages_api() -> dict[str, object]:
        from features.mqtt.client import get_monitor_session
        since = int(request.args.get("since", 0))
        return {"messages": get_monitor_session().get_messages(since)}

    @app.post("/api/mqtt/monitor/clear")
    def mqtt_monitor_clear_api() -> dict[str, object]:
        from features.mqtt.client import get_monitor_session
        get_monitor_session().clear()
        return {"status": "ok"}

    # ── Logo static files ────────────────────────────────────────

    @app.get("/api/nav/status")
    def nav_status_api() -> dict[str, object]:
        import shutil as _shutil
        from features.qr.registry import load_installed_devices
        installed_devices = {d["id"]: True for d in load_installed_devices()}
        return {
            "status": "ok",
            "installed": {
                "wireguard": _shutil.which("wg") is not None,
                "anydesk":   _shutil.which("anydesk") is not None,
                "openssh":   _shutil.which("sshd") is not None,
            },
            "devices": installed_devices,
        }  # type: ignore[return-value]

    @app.get("/public/images/logo/<path:filename>")
    def serve_logo(filename: str):  # type: ignore[return]
        from flask import send_from_directory
        logo_dir = Path(__file__).parent.parent / "public" / "images" / "logo"
        return send_from_directory(str(logo_dir), filename)

    # ── Apps (โปรแกรมเพิ่มเติม) routes ──────────────────────────────

    @app.get("/apps")
    def apps_page() -> str:
        return render_template("apps.html", active_tab="software")

    @app.get("/settings")
    def settings_page() -> str:
        from flask import redirect
        return redirect("/apps", code=301)  # type: ignore[return-value]

    @app.get("/api/apps/packages")
    @app.get("/api/settings/packages")   # legacy alias
    def settings_packages_api() -> dict[str, object]:
        from features.packages.settings import get_package_status, CATEGORIES
        return {
            "status":     "ok",
            "packages":   get_package_status(),
            "categories": CATEGORIES,
        }  # type: ignore[return-value]

    @app.get("/api/settings/packages/<pkg_id>/status")
    def settings_package_status_api(pkg_id: str) -> dict[str, object]:
        from features.packages.settings import get_package_status
        pkgs = get_package_status(pkg_id)
        if not pkgs:
            return {"status": "error", "errors": [f"Unknown package: {pkg_id}"]}, 404  # type: ignore[return-value]
        return {"status": "ok", "package": pkgs[0]}  # type: ignore[return-value]

    @app.post("/api/settings/install/<pkg_id>")
    def settings_install_api(pkg_id: str) -> tuple[dict[str, object], int] | dict[str, object]:
        from features.packages.settings import start_install
        ok, err = start_install(pkg_id)
        if not ok:
            return {"status": "error", "errors": [err]}, 400
        return {"status": "ok", "pkg_id": pkg_id}

    @app.get("/api/settings/install/<pkg_id>/stream")
    def settings_install_stream_api(pkg_id: str):  # type: ignore[return]
        """SSE stream ของ install output"""
        from flask import stream_with_context, Response
        from features.packages.settings import get_install_queue, is_installing
        import time as _time

        def generate():
            # รอให้ queue พร้อม (อาจยังไม่ start)
            deadline = _time.monotonic() + 5.0
            while _time.monotonic() < deadline:
                q = get_install_queue(pkg_id)
                if q is not None:
                    break
                _time.sleep(0.1)
                yield "event: heartbeat\ndata: {}\n\n"
            else:
                yield f"event: error\ndata: {_json_dumps({'msg': 'Install queue not found'})}\n\n"
                return

            while True:
                try:
                    line = q.get(timeout=30)
                except Exception:
                    yield "event: heartbeat\ndata: {}\n\n"
                    continue
                if line is None:  # sentinel — done
                    yield f"event: done\ndata: {_json_dumps({'pkg_id': pkg_id})}\n\n"
                    return
                yield f"event: line\ndata: {_json_dumps({'text': line})}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── System Monitor routes ────────────────────────────────────

    @app.get("/monitor")
    def monitor_page() -> str:
        return render_template("monitor.html")

    @app.get("/api/monitor/metrics")
    def monitor_metrics_api() -> dict[str, object]:
        from system.monitor import collect_metrics
        try:
            return collect_metrics()  # type: ignore[return-value]
        except Exception as exc:
            return {"error": str(exc)}  # type: ignore[return-value]

    # ── Database routes ──────────────────────────────────────────

    @app.get("/database")
    def database_page() -> str:
        from core.database import get_stats
        return render_template("database.html", stats=get_stats())

    @app.get("/api/database/<table>")
    def database_table_api(table: str) -> tuple[dict[str, object], int] | dict[str, object]:
        from core.database import get_rows
        limit  = int(request.args.get("limit",  50))
        offset = int(request.args.get("offset",  0))
        search = request.args.get("search", "").strip() or None
        result = get_rows(table, limit=limit, offset=offset, search=search)
        if "error" in result:
            return result, 400  # type: ignore[return-value]
        return result  # type: ignore[return-value]

    @app.post("/api/database/<table>/clear")
    def database_clear_api(table: str) -> tuple[dict[str, object], int] | dict[str, object]:
        from core.database import clear_table, log_audit
        result = clear_table(table)
        if result.get("status") == "ok":
            try:
                log_audit("table_cleared", {"table": table})
            except Exception:
                pass
        if result.get("status") == "error":
            return result, 400  # type: ignore[return-value]
        return result  # type: ignore[return-value]

    @app.get("/api/database/stats")
    def database_stats_api() -> dict[str, object]:
        from core.database import get_stats
        return {"status": "ok", "stats": get_stats()}


    # ════════════════════════════════════════════════════════════════
    # Auth routes
    # ════════════════════════════════════════════════════════════════

    @app.get("/setup")
    def auth_setup():
        from flask import redirect as _redir, url_for as _url_for
        from core.auth import is_first_run
        if not is_first_run():
            return _redir(_url_for("auth_login"))
        return render_template("auth/setup.html")

    @app.post("/setup")
    def auth_setup_post():
        from flask import redirect as _redir, url_for as _url_for, session as _sess
        from core.auth import is_first_run, create_user, authenticate
        if not is_first_run():
            return _redir(_url_for("auth_login"))
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        if password != password_confirm:
            return render_template("auth/setup.html", error="รหัสผ่านไม่ตรงกัน",
                                   username=username, display_name=display_name)
        ok, err = create_user(username, password, display_name=display_name, role="root")
        if not ok:
            return render_template("auth/setup.html", error=err,
                                   username=username, display_name=display_name)
        user, _ = authenticate(username, password)
        if user:
            _sess["vas_user_id"] = user["id"]
        return _redir(_url_for("dashboard"))

    @app.get("/login")
    def auth_login():
        from flask import redirect as _redir, url_for as _url_for, session as _sess
        from core.auth import is_first_run
        if is_first_run():
            return _redir(_url_for("auth_setup"))
        if _sess.get("vas_user_id"):
            return _redir(_url_for("dashboard"))
        return render_template("auth/login.html", next=request.args.get("next", ""))

    @app.post("/login")
    def auth_login_post():
        from flask import redirect as _redir, url_for as _url_for, session as _sess
        from core.auth import authenticate
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        next_url = request.form.get("next", "").strip()
        user, err = authenticate(username, password)
        if user is None:
            return render_template("auth/login.html", error=err, username=username, next=next_url)
        _sess["vas_user_id"] = user["id"]
        # Redirect to next or dashboard — ป้องกัน open redirect
        if next_url and next_url.startswith("/") and not next_url.startswith("//"):
            return _redir(next_url)
        return _redir(_url_for("dashboard"))

    @app.post("/logout")
    def auth_logout():
        from flask import redirect as _redir, url_for as _url_for, session as _sess
        _sess.clear()
        return _redir(_url_for("auth_login"))

    # ════════════════════════════════════════════════════════════════
    # User management routes
    # ════════════════════════════════════════════════════════════════

    @app.get("/users")
    def users_page():
        from flask import session as _sess
        from core.auth import list_users, get_user_by_id, ROLE_BADGE_CLASS, ROLE_LABELS, can_manage_user, count_users
        user_id = _sess.get("vas_user_id")
        current_user = get_user_by_id(int(user_id)) if user_id else None
        if current_user is None or current_user["role"] not in ("root", "admin"):
            from flask import abort
            abort(403)
        users = list_users()
        # role stats
        from collections import Counter
        role_counts = Counter(u["role"] for u in users)
        stats = [
            {"label": "ทั้งหมด", "count": len(users)},
            {"label": "Admin", "count": role_counts.get("admin", 0)},
            {"label": "User", "count": role_counts.get("user", 0)},
        ]
        return render_template(
            "users.html",
            users=users,
            stats=stats,
            role_badge=ROLE_BADGE_CLASS,
            role_labels=ROLE_LABELS,
            can_manage=can_manage_user,
            current_user=current_user,
        )

    @app.get("/api/users")
    def api_users_list():
        from flask import session as _sess
        from core.auth import list_users, get_user_by_id
        user_id = _sess.get("vas_user_id")
        current_user = get_user_by_id(int(user_id)) if user_id else None
        if not current_user or current_user["role"] not in ("root", "admin"):
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        return {"status": "ok", "users": list_users()}

    @app.post("/api/users")
    def api_users_create():
        from flask import session as _sess
        from core.auth import create_user, get_user_by_id, ROLE_WEIGHT
        user_id = _sess.get("vas_user_id")
        current_user = get_user_by_id(int(user_id)) if user_id else None
        if not current_user or current_user["role"] not in ("root", "admin"):
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        body = request.get_json(silent=True) or {}
        role = str(body.get("role", "user"))
        # admin สร้างได้เฉพาะ user, root สร้างได้ admin/user
        if ROLE_WEIGHT.get(role, 0) >= ROLE_WEIGHT.get(current_user["role"], 0):
            return {"status": "error", "errors": ["ไม่สามารถสร้าง role ที่สูงกว่าหรือเท่ากับตัวเองได้"]}, 403
        ok, err = create_user(
            str(body.get("username", "")),
            str(body.get("password", "")),
            display_name=str(body.get("display_name", "")),
            role=role,
        )
        if not ok:
            return {"status": "error", "errors": [err]}, 400
        return {"status": "ok"}

    @app.put("/api/users/<int:target_id>")
    def api_users_update(target_id: int):
        from flask import session as _sess
        from core.auth import update_user, get_user_by_id, can_manage_user
        user_id = _sess.get("vas_user_id")
        current_user = get_user_by_id(int(user_id)) if user_id else None
        target = get_user_by_id(target_id)
        if not current_user or not target:
            return {"status": "error", "errors": ["ไม่พบข้อมูล"]}, 404
        if not can_manage_user(current_user["role"], target["role"]):
            return {"status": "error", "errors": ["ไม่มีสิทธิ์แก้ไขผู้ใช้งานนี้"]}, 403
        body = request.get_json(silent=True) or {}
        kwargs: dict = {}
        if "display_name" in body:
            kwargs["display_name"] = str(body["display_name"])
        if "role" in body and target["role"] != "root":
            kwargs["role"] = str(body["role"])
        ok, err = update_user(target_id, **kwargs)
        if not ok:
            return {"status": "error", "errors": [err]}, 400
        return {"status": "ok"}

    @app.delete("/api/users/<int:target_id>")
    def api_users_delete(target_id: int):
        from flask import session as _sess
        from core.auth import delete_user, get_user_by_id, can_manage_user
        user_id = _sess.get("vas_user_id")
        current_user = get_user_by_id(int(user_id)) if user_id else None
        target = get_user_by_id(target_id)
        if not current_user or not target:
            return {"status": "error", "errors": ["ไม่พบข้อมูล"]}, 404
        if not can_manage_user(current_user["role"], target["role"]):
            return {"status": "error", "errors": ["ไม่มีสิทธิ์ลบผู้ใช้งานนี้"]}, 403
        ok, err = delete_user(target_id)
        if not ok:
            return {"status": "error", "errors": [err]}, 400
        return {"status": "ok"}

    @app.post("/api/users/<int:target_id>/reset-password")
    def api_users_reset_password(target_id: int):
        from flask import session as _sess
        from core.auth import change_password, get_user_by_id, can_manage_user
        user_id = _sess.get("vas_user_id")
        current_user = get_user_by_id(int(user_id)) if user_id else None
        target = get_user_by_id(target_id)
        if not current_user or not target:
            return {"status": "error", "errors": ["ไม่พบข้อมูล"]}, 404
        # ต้องเป็นตัวเอง หรือมีสิทธิ์จัดการ target
        is_self = current_user["id"] == target_id
        if not is_self and not can_manage_user(current_user["role"], target["role"]):
            return {"status": "error", "errors": ["ไม่มีสิทธิ์รีเซ็ตรหัสผ่านผู้ใช้งานนี้"]}, 403
        body = request.get_json(silent=True) or {}
        ok, err = change_password(target_id, str(body.get("password", "")))
        if not ok:
            return {"status": "error", "errors": [err]}, 400
        return {"status": "ok"}

    # ── Profile (self) API ────────────────────────────────────────

    @app.get("/api/profile")
    def api_profile_get():
        from flask import session as _sess
        from core.auth import get_user_by_id
        user_id = _sess.get("vas_user_id")
        if not user_id:
            return {"status": "error", "errors": ["ไม่ได้เข้าสู่ระบบ"]}, 401
        user = get_user_by_id(int(user_id))
        if not user:
            return {"status": "error", "errors": ["ไม่พบผู้ใช้"]}, 404
        return {"status": "ok", "user": user}

    @app.put("/api/profile")
    def api_profile_update():
        from flask import session as _sess
        from core.auth import update_user, get_user_by_id
        user_id = _sess.get("vas_user_id")
        if not user_id:
            return {"status": "error", "errors": ["ไม่ได้เข้าสู่ระบบ"]}, 401
        body = request.get_json(silent=True) or {}
        ok, err = update_user(int(user_id), display_name=str(body.get("display_name", "")))
        if not ok:
            return {"status": "error", "errors": [err]}, 400
        return {"status": "ok"}

    @app.post("/api/profile/password")
    def api_profile_password():
        from flask import session as _sess
        from core.auth import change_password, verify_current_password, get_user_by_id
        user_id = _sess.get("vas_user_id")
        if not user_id:
            return {"status": "error", "errors": ["ไม่ได้เข้าสู่ระบบ"]}, 401
        body = request.get_json(silent=True) or {}
        current_pw = str(body.get("current_password", ""))
        new_pw = str(body.get("new_password", ""))
        if not verify_current_password(int(user_id), current_pw):
            return {"status": "error", "errors": ["รหัสผ่านปัจจุบันไม่ถูกต้อง"]}, 400
        ok, err = change_password(int(user_id), new_pw)
        if not ok:
            return {"status": "error", "errors": [err]}, 400
        return {"status": "ok"}

    return app


import json as _json


def _json_dumps(obj: dict[str, object]) -> str:
    return _json.dumps(obj, ensure_ascii=False)


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

    xrandr = _run_display_probe(
        runner,
        configurator._with_x_env(["xrandr", "--query"], resolved_display, xauthority),
    )
    xinput = _run_display_probe(
        runner,
        configurator._with_x_env(["xinput", "list"], resolved_display, xauthority),
    )

    outputs = parse_xrandr_outputs(xrandr.stdout)
    xinput_map = parse_xinput_device_map(xinput.stdout)

    if not outputs:
        desktop_user = _desktop_user()
        if desktop_user:
            env_args = ["env", f"DISPLAY={resolved_display}"]
            if xauthority:
                env_args.append(f"XAUTHORITY={xauthority}")
            xrandr = _run_display_probe(runner, ["runuser", "-u", desktop_user, "--", *env_args, "xrandr", "--query"])
            xinput = _run_display_probe(runner, ["runuser", "-u", desktop_user, "--", *env_args, "xinput", "list"])
            outputs = parse_xrandr_outputs(xrandr.stdout)
            xinput_map = parse_xinput_device_map(xinput.stdout)

    touch_devices = _resolve_touch_devices(runner, xinput_map)
    return DisplayDevices(outputs=outputs, touch_devices=touch_devices)


def _run_display_probe(runner: CommandRunner, args: Sequence[str]) -> CommandResult:
    try:
        return runner.run(args, check=False)
    except OSError as error:
        return CommandResult(tuple(args), 127, "", str(error))


def _resolve_touch_devices(runner: CommandRunner, xinput_map: dict[str, int]) -> tuple[TouchDevice, ...]:
    """หา touchscreen devices โดยใช้ udevadm เป็นหลัก fallback ด้วย "touch" ใน name"""
    try:
        udev_names = get_udevadm_touchscreen_names(runner)
    except OSError:
        udev_names = frozenset()
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
    from status import GDM_CUSTOM_CONFIG_PATH, XORG_TOUCHSCREEN_CONFIG_PATH
    return {
        "gdm_custom": Path(GDM_CUSTOM_CONFIG_PATH),
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
