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
    delete_system_snapshot,
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
    collect_vpn_status,
    collect_xorg_touchscreen_config_status,
)
from features.remote.anydesk import (
    VALID_SERVICE_ACTIONS as ANYDESK_SERVICE_ACTIONS,
    service_action as anydesk_service_action,
    set_unattended_password as anydesk_set_unattended_password,
)
from features.remote import openssh as openssh_manager
from features.remote.openssh import (
    VALID_SERVICE_ACTIONS as OPENSSH_SERVICE_ACTIONS,
    SshdConfigValues as OpenSshConfigValues,
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
from features.docker import manager as docker_manager


def _current_session_user() -> dict[str, Any] | None:
    from flask import session as _sess
    from core.auth import get_user_by_id
    user_id = _sess.get("vas_user_id")
    return get_user_by_id(int(user_id)) if user_id else None


def _require_admin_user() -> dict[str, Any] | None:
    """คืน current_user ถ้า role เป็น root/admin — คืน None ถ้าไม่ login หรือสิทธิ์ไม่พอ

    ใช้กับ endpoint ที่กระทบระบบจริง (เช่น เขียน sshd_config, จัดการ SSH key)
    """
    user = _current_session_user()
    if user is None or user["role"] not in ("root", "admin"):
        return None
    return user


WEB_DIR = Path(__file__).parent / "web"
INSTALL_COMPONENTS = ("all", "git", "node", "docker", "wireguard", "anydesk", "openssh", "qr-udev")
LIFECYCLE_COMPONENTS = ("all", "git", "node", "docker", "wireguard", "anydesk", "openssh", "qr-udev")
WIREGUARD_ACTIONS = (
    (
        "Install",
        "sudo vas wireguard install",
        "ติดตั้งแพ็กเกจ WireGuard และ wireguard-tools ผ่าน apt",
    ),
    (
        "Create template",
        "vas wireguard init-config --name wg0 --output ./wg0.conf",
        "สร้างไฟล์ config ตัวอย่างสำหรับ interface ที่ระบุ ไว้แก้ไขก่อนใช้งานจริง",
    ),
    (
        "Validate config",
        "vas wireguard validate --config ./wg0.conf",
        "ตรวจสอบ syntax และค่าที่จำเป็นในไฟล์ config ก่อนนำไปใช้",
    ),
    (
        "Save config",
        "vas wireguard save --name wg0 --config ./wg0.conf",
        "บันทึก config ที่ผ่านการตรวจสอบแล้วเข้าประวัติของระบบ",
    ),
    (
        "Sync config",
        "sudo vas wireguard sync --name wg0",
        "นำ config ที่บันทึกไว้ไปเขียนทับที่ /etc/wireguard และเริ่ม service ให้ตรงกัน",
    ),
    (
        "Show status",
        "vas wireguard status --name wg0",
        "แสดงสถานะการเชื่อมต่อและ service ปัจจุบันของ interface นี้",
    ),
    (
        "List history",
        "vas wireguard history --name wg0",
        "แสดงรายการ config เวอร์ชันก่อนหน้าที่เคยบันทึกไว้",
    ),
    (
        "Unsync config",
        "sudo vas wireguard unsync --name wg0",
        "หยุด service และถอด config ออกจาก /etc/wireguard โดยไม่ลบประวัติ",
    ),
)
DISPLAY_ACTIONS = (
    (
        "Show display status",
        "vas display status --display :0",
        "แสดงค่าจอแสดงผลปัจจุบัน (ความละเอียด ตำแหน่ง การหมุนจอ) ของ display ที่ระบุ",
    ),
    (
        "List touchscreens",
        "vas display list-touch --display :0",
        "แสดงรายชื่ออุปกรณ์ touchscreen ที่ตรวจพบบน display นี้",
    ),
    (
        "Disable GDM Wayland",
        "sudo vas display disable-wayland",
        "ปิดใช้งาน Wayland ใน GDM เพื่อบังคับให้ desktop session ใช้ Xorg แทน",
    ),
    (
        "Enable GDM Wayland",
        "sudo vas display enable-wayland",
        "เปิดใช้งาน Wayland ใน GDM กลับคืน (ยกเลิกการบังคับ Xorg)",
    ),
    (
        "Apply runtime",
        "vas display apply --display :0 --output Virtual1 --touch 'Vending Virtual Touchscreen' --rotate normal",
        "ปรับ output, touch mapping และการหมุนจอทันทีในเซสชันปัจจุบัน (ไม่ถาวร)",
    ),
    (
        "Persist session",
        "vas display persist-session --display :0 --output Virtual1 --touch 'Vending Virtual Touchscreen' --rotate normal",
        "บันทึกค่าการตั้งค่าจอ/ทัชให้รันอัตโนมัติทุกครั้งที่ desktop session เริ่มทำงาน",
    ),
    (
        "Persist touch in Xorg",
        "sudo vas display persist-xorg --touch 'Vending Virtual Touchscreen' --rotate normal",
        "เขียนค่าการหมุนจอทัชลงไฟล์ Xorg config ให้มีผลถาวรระดับระบบ",
    ),
)
SERVER_ACTIONS = (
    (
        "Start background service",
        "sudo vas server start --host 0.0.0.0 --port 8888",
        "ติดตั้ง systemd service และเริ่มรัน VAS web server เป็น background process",
    ),
    (
        "Show service status",
        "vas server status",
        "แสดงสถานะ systemd service ของ VAS server (running/stopped, uptime)",
    ),
    (
        "Run foreground",
        "vas server run --host 0.0.0.0 --port 8888",
        "รัน VAS web server แบบ foreground ในเทอร์มินัลปัจจุบัน เหมาะสำหรับ debug",
    ),
    (
        "Stop service",
        "sudo vas server stop",
        "หยุด systemd service ของ VAS server",
    ),
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
    description: str = ""


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
    def monitor_page() -> str:
        return render_template("monitor.html")

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

    @app.get("/anydesk")
    def anydesk_page() -> str:
        return render_template("anydesk.html", remote=collect_remote_access_status())

    @app.get("/openssh")
    def openssh_page() -> str:
        runner = CommandRunner()
        return render_template(
            "openssh.html",
            ssh=collect_openssh_status(),
            config=openssh_manager.collect_config(runner),
            host_keys=openssh_manager.collect_host_keys(runner),
            authorized_keys=openssh_manager.collect_authorized_keys(runner),
            manageable_users=openssh_manager.list_manageable_usernames(),
            fail2ban=openssh_manager.collect_fail2ban_status(runner),
            recent_attempts=openssh_manager.collect_recent_login_attempts(runner),
        )

    @app.get("/docker")
    def docker_page() -> str:
        ctx = docker_manager.collect_docker_status()
        return render_template("docker.html", **ctx)

    # ── Docker: Containers ──────────────────────────────────────
    @app.post("/api/docker/containers/<name>/action")
    def docker_container_action_api(name: str) -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "")).strip()
        try:
            result = docker_manager.container_action(CommandRunner(), name, action)
        except ValueError as error:
            return {"status": "error", "errors": [str(error)]}, 400
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "คำสั่งล้มเหลว").strip()]}, 500
        return {"status": "ok", "action": action, "name": name}

    @app.post("/api/docker/containers/<name>/remove")
    def docker_container_remove_api(name: str) -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        force = bool(payload.get("force", False))
        result = docker_manager.remove_container(CommandRunner(), name, force=force)
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "ลบไม่สำเร็จ").strip()]}, 500
        return {"status": "ok", "name": name}

    @app.get("/api/docker/containers/<name>/logs")
    def docker_container_logs_api(name: str) -> dict[str, object]:
        try:
            tail = int(request.args.get("tail", 200))
        except (TypeError, ValueError):
            tail = 200
        return {"status": "ok", "name": name, "logs": docker_manager.get_container_logs(name, tail=tail)}

    # ── Docker: Images ───────────────────────────────────────────
    @app.post("/api/docker/images/pull")
    def docker_image_pull_api() -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        ref = str(payload.get("ref", "")).strip()
        if not ref:
            return {"status": "error", "errors": ["กรุณาระบุ image (เช่น nginx:latest)"]}, 400
        result = docker_manager.pull_image(CommandRunner(), ref)
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "pull ล้มเหลว").strip()]}, 500
        return {"status": "ok", "ref": ref}

    @app.post("/api/docker/images/remove")
    def docker_image_remove_api() -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        ref = str(payload.get("ref", "")).strip()
        if not ref:
            return {"status": "error", "errors": ["ไม่พบ image reference"]}, 400
        result = docker_manager.remove_image(CommandRunner(), ref, force=bool(payload.get("force", False)))
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "ลบไม่สำเร็จ").strip()]}, 500
        return {"status": "ok", "ref": ref}

    @app.post("/api/docker/images/prune")
    def docker_image_prune_api() -> tuple[dict[str, object], int] | dict[str, object]:
        result = docker_manager.prune_images(CommandRunner())
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "prune ล้มเหลว").strip()]}, 500
        return {"status": "ok", "output": result.stdout.strip()}

    # ── Docker: Networks ─────────────────────────────────────────
    @app.post("/api/docker/networks")
    def docker_network_create_api() -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name", "")).strip()
        driver = str(payload.get("driver", "bridge")).strip() or "bridge"
        try:
            result = docker_manager.create_network(CommandRunner(), name, driver=driver)
        except ValueError as error:
            return {"status": "error", "errors": [str(error)]}, 400
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "สร้าง network ไม่สำเร็จ").strip()]}, 500
        return {"status": "ok", "name": name}

    # ── Docker: Volumes ──────────────────────────────────────────
    @app.post("/api/docker/volumes")
    def docker_volume_create_api() -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name", "")).strip()
        try:
            result = docker_manager.create_volume(CommandRunner(), name)
        except ValueError as error:
            return {"status": "error", "errors": [str(error)]}, 400
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "สร้าง volume ไม่สำเร็จ").strip()]}, 500
        return {"status": "ok", "name": name}

    @app.post("/api/docker/volumes/prune")
    def docker_volume_prune_api() -> tuple[dict[str, object], int] | dict[str, object]:
        result = docker_manager.prune_volumes(CommandRunner())
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "prune ล้มเหลว").strip()]}, 500
        return {"status": "ok", "output": result.stdout.strip()}

    # ── Docker: Compose ──────────────────────────────────────────
    @app.post("/api/docker/compose/<name>/save")
    def docker_compose_save_api(name: str) -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        content = str(payload.get("content", ""))
        try:
            path = docker_manager.save_compose_file(name, content)
        except (OSError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 400
        return {"status": "ok", "name": name, "path": path.as_posix()}

    @app.post("/api/docker/compose/<name>/action")
    def docker_compose_action_api(name: str) -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "")).strip()
        try:
            result = docker_manager.compose_action(CommandRunner(), name, action)
        except (FileNotFoundError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 400
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "คำสั่งล้มเหลว").strip()]}, 500
        return {"status": "ok", "name": name, "action": action}

    # ── Docker: Swarm ────────────────────────────────────────────
    @app.post("/api/docker/swarm/init")
    def docker_swarm_init_api() -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        payload = request.get_json(silent=True) or {}
        advertise_addr = str(payload.get("advertise_addr", "")).strip() or None
        result = docker_manager.swarm_init(CommandRunner(), advertise_addr=advertise_addr)
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "swarm init ล้มเหลว").strip()]}, 500
        return {"status": "ok", "output": result.stdout.strip()}

    @app.post("/api/docker/swarm/join")
    def docker_swarm_join_api() -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        payload = request.get_json(silent=True) or {}
        token = str(payload.get("token", "")).strip()
        remote_addr = str(payload.get("remote_addr", "")).strip()
        if not token or not remote_addr:
            return {"status": "error", "errors": ["กรุณาระบุ token และ remote address"]}, 400
        result = docker_manager.swarm_join(CommandRunner(), token, remote_addr)
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "swarm join ล้มเหลว").strip()]}, 500
        return {"status": "ok"}

    @app.post("/api/docker/swarm/leave")
    def docker_swarm_leave_api() -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        result = docker_manager.swarm_leave(CommandRunner())
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "swarm leave ล้มเหลว").strip()]}, 500
        return {"status": "ok"}

    @app.post("/api/docker/swarm/rotate-tokens")
    def docker_swarm_rotate_tokens_api() -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        result = docker_manager.rotate_join_tokens(CommandRunner())
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "rotate token ล้มเหลว").strip()]}, 500
        return {"status": "ok"}

    @app.post("/api/docker/swarm/nodes/<node>/promote")
    def docker_swarm_promote_node_api(node: str) -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        result = docker_manager.promote_node(CommandRunner(), node)
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "promote ล้มเหลว").strip()]}, 500
        return {"status": "ok", "node": node}

    @app.post("/api/docker/swarm/nodes/<node>/availability")
    def docker_swarm_node_availability_api(node: str) -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        payload = request.get_json(silent=True) or {}
        availability = str(payload.get("availability", "")).strip()
        try:
            result = docker_manager.set_node_availability(CommandRunner(), node, availability)
        except ValueError as error:
            return {"status": "error", "errors": [str(error)]}, 400
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "อัปเดตไม่สำเร็จ").strip()]}, 500
        return {"status": "ok", "node": node, "availability": availability}

    @app.delete("/api/docker/swarm/nodes/<node>")
    def docker_swarm_remove_node_api(node: str) -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        result = docker_manager.remove_node(CommandRunner(), node)
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "ลบ node ไม่สำเร็จ").strip()]}, 500
        return {"status": "ok", "node": node}

    @app.post("/api/docker/swarm/services/<service>/scale")
    def docker_swarm_scale_service_api(service: str) -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        try:
            replicas = int(payload.get("replicas", 0))
        except (TypeError, ValueError):
            return {"status": "error", "errors": ["จำนวน replicas ไม่ถูกต้อง"]}, 400
        if replicas < 0:
            return {"status": "error", "errors": ["จำนวน replicas ต้องไม่ติดลบ"]}, 400
        result = docker_manager.scale_service(CommandRunner(), service, replicas)
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "scale ไม่สำเร็จ").strip()]}, 500
        return {"status": "ok", "service": service, "replicas": replicas}

    @app.delete("/api/docker/swarm/stacks/<stack>")
    def docker_swarm_remove_stack_api(stack: str) -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        result = docker_manager.remove_stack(CommandRunner(), stack)
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "ลบ stack ไม่สำเร็จ").strip()]}, 500
        return {"status": "ok", "stack": stack}

    @app.post("/api/docker/swarm/stacks/<stack>/redeploy")
    def docker_swarm_redeploy_stack_api(stack: str) -> tuple[dict[str, object], int] | dict[str, object]:
        try:
            result = docker_manager.redeploy_stack(CommandRunner(), stack)
        except FileNotFoundError as error:
            return {"status": "error", "errors": [str(error)]}, 400
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "redeploy ไม่สำเร็จ").strip()]}, 500
        return {"status": "ok", "stack": stack}

    # ── Docker: Settings ─────────────────────────────────────────
    @app.post("/api/docker/daemon-json")
    def docker_daemon_json_save_api() -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        payload = request.get_json(silent=True) or {}
        content = str(payload.get("content", ""))
        ok, message = docker_manager.save_daemon_json(content)
        if not ok:
            return {"status": "error", "errors": [message]}, 400
        restart_result = docker_manager.restart_daemon(CommandRunner())
        if restart_result.returncode != 0:
            return {"status": "error", "errors": [message + " — แต่ restart daemon ไม่สำเร็จ: " + (restart_result.stderr or restart_result.stdout or "").strip()]}, 500
        return {"status": "ok", "message": message}

    @app.post("/api/docker/daemon/restart")
    def docker_daemon_restart_api() -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        result = docker_manager.restart_daemon(CommandRunner())
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "restart ไม่สำเร็จ").strip()]}, 500
        return {"status": "ok"}

    @app.post("/api/docker/system-prune")
    def docker_system_prune_api() -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        result = docker_manager.system_prune(CommandRunner())
        if result.returncode != 0:
            return {"status": "error", "errors": [(result.stderr or result.stdout or "prune ล้มเหลว").strip()]}, 500
        return {"status": "ok", "output": result.stdout.strip()}

    @app.post("/api/docker/uninstall")
    def docker_uninstall_api() -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        try:
            docker_manager.uninstall_docker(CommandRunner())
        except (CommandExecutionError, OSError) as error:
            return {"status": "error", "errors": [str(error)]}, 500
        try:
            from core.database import log_audit as _db_audit

            _db_audit("docker_uninstalled", {})
        except Exception:
            pass
        return {"status": "ok"}

    @app.get("/pm2")
    def pm2_page() -> str:
        # TODO(pm2-real-impl): แทนที่ _collect_pm2_status_mock() ด้วยการอ่านค่าจริง
        # ผ่าน `pm2` CLI (แนะนำสร้าง src/mcp/tools/pm2.py ตามตัวอย่าง subprocess pattern
        # ของ src/mcp/tools/docker.py) — ใช้ `pm2 jlist` (JSON) สำหรับ process list,
        # `pm2 describe <id>` สำหรับ detail, `pm2 logs <name> --lines N --nostream`
        # สำหรับ logs, และอ่านไฟล์ ecosystem.config.js ตรงๆ ด้วย pathlib
        # เมื่อพร้อม — เก็บ shape ของ context variables ให้เหมือนเดิมเพื่อไม่ต้องแก้ pm2.html
        ctx = _collect_pm2_status_mock()
        return render_template("pm2.html", **ctx)

    @app.get("/api/openssh/status")
    def openssh_status_api() -> dict[str, object]:
        ssh = collect_openssh_status()
        fail2ban = openssh_manager.collect_fail2ban_status(CommandRunner())
        return {
            "status": "ok",
            "installed": ssh.installed,
            "version": ssh.version,
            "service_enabled": ssh.service_enabled,
            "service_active": ssh.service_active,
            "fail2ban_service_active": fail2ban.service_active,
            "fail2ban_banned_count": fail2ban.banned_count,
        }

    @app.post("/api/openssh/config")
    def openssh_config_api() -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        payload = request.get_json(silent=True) or {}
        try:
            values = _openssh_values_from_payload(payload)
        except (TypeError, ValueError) as error:
            return {"status": "error", "errors": [f"ข้อมูลไม่ถูกต้อง: {error}"]}, 400
        ok, message = openssh_manager.save_config(CommandRunner(), values)
        if not ok:
            return {"status": "error", "errors": [message]}, 400
        try:
            from core.database import log_audit as _db_audit
            _db_audit("openssh_config_save", {"port": values.port, "permit_root_login": values.permit_root_login})
        except Exception:
            pass
        return {"status": "ok", "message": message}

    @app.post("/api/openssh/action")
    def openssh_action_api() -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "")).strip()
        if action not in OPENSSH_SERVICE_ACTIONS:
            return {"status": "error", "errors": [f"Unknown OpenSSH action: {action}"]}, 400
        try:
            result = openssh_manager.service_action(CommandRunner(), action)
        except (CommandExecutionError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 500
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip() or f"systemctl {action} ssh ล้มเหลว"
            return {"status": "error", "errors": [detail]}, 500
        try:
            from core.database import log_audit as _db_audit
            _db_audit("openssh_service_action", {"action": action})
        except Exception:
            pass
        return {"status": "ok", "action": action}

    @app.post("/api/openssh/keys")
    def openssh_keys_add_api() -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        payload = request.get_json(silent=True) or {}
        user = str(payload.get("user", "")).strip()
        key_line = str(payload.get("key", "")).strip()
        if not user:
            return {"status": "error", "errors": ["กรุณาเลือก user"]}, 400
        ok, message = openssh_manager.add_authorized_key(user, key_line)
        if not ok:
            return {"status": "error", "errors": [message]}, 400
        try:
            from core.database import log_audit as _db_audit
            _db_audit("openssh_key_add", {"user": user})
        except Exception:
            pass
        return {"status": "ok", "message": message}

    @app.post("/api/openssh/keys/revoke")
    def openssh_keys_revoke_api() -> tuple[dict[str, object], int] | dict[str, object]:
        if _require_admin_user() is None:
            return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
        payload = request.get_json(silent=True) or {}
        user = str(payload.get("user", "")).strip()
        fingerprint = str(payload.get("fingerprint", "")).strip()
        if not user or not fingerprint:
            return {"status": "error", "errors": ["ข้อมูลไม่ครบ"]}, 400
        ok, message = openssh_manager.revoke_authorized_key(user, fingerprint)
        if not ok:
            return {"status": "error", "errors": [message]}, 400
        try:
            from core.database import log_audit as _db_audit
            _db_audit("openssh_key_revoke", {"user": user, "fingerprint": fingerprint})
        except Exception:
            pass
        return {"status": "ok", "message": message}

    @app.get("/logs")
    def logs() -> str:
        from flask import abort
        abort(404)  # ปิดหน้าไว้ก่อน — รอแก้ไข feature
        return render_template(
            "logs.html",
            system_snapshots=list_system_snapshots(),
            system_snapshot_dir=_system_snapshot_dir_label(),
        )

    @app.get("/api/logs/system")
    def logs_system_api() -> dict[str, object]:
        from flask import abort
        abort(404)  # ปิดหน้าไว้ก่อน — รอแก้ไข feature
        return {"status": "ok", "snapshots": list(list_system_snapshots())}

    @app.post("/api/logs/system/snapshot")
    def logs_system_snapshot_api() -> tuple[dict[str, object], int] | dict[str, object]:
        from flask import abort
        abort(404)  # ปิดหน้าไว้ก่อน — รอแก้ไข feature
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
        from flask import abort
        abort(404)  # ปิดหน้าไว้ก่อน — รอแก้ไข feature
        try:
            snapshot = read_system_snapshot(snapshot_id)
        except (FileNotFoundError, OSError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 404
        return {"status": "ok", "snapshot": snapshot}

    @app.delete("/api/logs/system/<snapshot_id>")
    def logs_system_delete_api(snapshot_id: str) -> tuple[dict[str, object], int] | dict[str, object]:
        from flask import abort
        abort(404)  # ปิดหน้าไว้ก่อน — รอแก้ไข feature
        try:
            deleted = delete_system_snapshot(snapshot_id)
        except (FileNotFoundError, OSError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 404
        try:
            from core.database import log_audit as _db_audit
            _db_audit("snapshot_deleted", {"id": deleted.get("id"), "path": deleted.get("path")})
        except Exception:
            pass
        return {"status": "ok", "snapshot": deleted}

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

    @app.get("/api/anydesk/status")
    def anydesk_status_api() -> dict[str, object]:
        remote = collect_remote_access_status()
        return {
            "status": "ok",
            "installed": remote.anydesk_installed,
            "version": remote.anydesk_version,
            "id": remote.anydesk_id,
            "online_status": remote.anydesk_status,
            "service_enabled": remote.service_enabled,
            "service_active": remote.service_active,
        }

    @app.post("/api/anydesk/action")
    def anydesk_action_api() -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "")).strip()
        if action not in ANYDESK_SERVICE_ACTIONS:
            return {"status": "error", "errors": [f"Unknown AnyDesk action: {action}"]}, 400
        try:
            result = anydesk_service_action(CommandRunner(), action)
        except (CommandExecutionError, ValueError) as error:
            return {"status": "error", "errors": [str(error)]}, 500
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip() or f"systemctl {action} anydesk ล้มเหลว"
            return {"status": "error", "errors": [detail]}, 500
        try:
            from core.database import log_audit as _db_audit
            _db_audit("anydesk_service_action", {"action": action})
        except Exception:
            pass
        return {"status": "ok", "action": action}

    @app.post("/api/anydesk/password")
    def anydesk_password_api() -> tuple[dict[str, object], int] | dict[str, object]:
        payload = request.get_json(silent=True) or {}
        password = str(payload.get("password", ""))
        ok, message = anydesk_set_unattended_password(password)
        if not ok:
            return {"status": "error", "errors": [message]}, 400
        try:
            from core.database import log_audit as _db_audit
            _db_audit("anydesk_password_set", {})
        except Exception:
            pass
        return {"status": "ok", "message": message}

    @app.get("/commands")
    def commands() -> str:
        reset_all = build_reset_commands()
        return render_template(
            "command_docs.html",
            install_commands=build_install_commands(),
            uninstall_commands=[c for c in reset_all if c.command.startswith("sudo vas uninstall")],
            reset_only_commands=[c for c in reset_all if c.command.startswith("sudo vas reset")],
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

    # ── Database version check (read-only — ไม่เขียน schema ตอน boot อีกต่อไป) ──
    from core.database import init_db as _init_db, SchemaOutOfDateError as _SchemaOutOfDateError
    try:
        _init_db()
    except _SchemaOutOfDateError as exc:
        print(f"[FATAL] {exc}")
        raise

    import atexit
    from features.qr.reader import stop_reader as _stop_qr_reader
    from features.mqtt.client import stop_mqtt as _stop_mqtt
    atexit.register(_stop_qr_reader)
    atexit.register(_stop_mqtt)

    # Auto-start QR reader เมื่อ server boot (ถ้ามี device ต่ออยู่ และยังไม่ถูกถอนการติดตั้ง)
    try:
        from features.qr.reader import get_reader as _get_qr_reader, start_reader as _auto_start_qr
        from features.qr.registry import is_installed as _qr_is_installed
        if _get_qr_reader() is None and _qr_is_installed("zkteco-qr500"):
            _auto_start_qr()
    except Exception:
        pass  # ยังไม่มี device หรือถูกถอนการติดตั้งไว้ — reader จะ start เมื่อกด restart หรือเสียบ USB ใหม่

    # Auto-start ทุก MQTT broker ที่ enabled=1 ใน DB (แยก try/except ต่อ broker อยู่ภายใน)
    try:
        from features.mqtt.client import start_all_enabled_brokers as _auto_start_brokers
        _auto_start_brokers()
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

    @app.get("/api/qr/scans")
    def qr_scans_list_api() -> dict[str, object]:
        """
        ประวัติการสแกน QR จาก DB ทั้งหมด (ไม่ใช่แค่ session ของ browser) — รองรับ pagination
        Query params: limit (100|250|500, default 100), offset (default 0)
        Return: {"status":"ok","rows":[...],"total":<int>,"limit":<int>,"offset":<int>}
        """
        from core.database import list_qr_scans
        try:
            limit = int(request.args.get("limit", 100))
        except (TypeError, ValueError):
            limit = 100
        if limit not in (100, 250, 500):
            limit = 100
        try:
            offset = max(0, int(request.args.get("offset", 0)))
        except (TypeError, ValueError):
            offset = 0
        result = list_qr_scans(limit=limit, offset=offset)
        return {"status": "ok", **result}

    @app.get("/api/qr/scans/stats")
    def qr_scans_stats_api() -> dict[str, object]:
        """Return: {"status":"ok","today_count":<int>}"""
        from core.database import count_qr_scans_today
        return {"status": "ok", "today_count": count_qr_scans_today()}

    @app.post("/api/qr/start")
    def qr_start_api() -> tuple[dict[str, object], int] | dict[str, object]:
        """
        Payload (optional): {"device": "/dev/hidraw0"}
        200: {"status":"ok","device":<path>,"running":true}
        400: {"status":"error","errors":[...]}  -- device not found / ยังไม่ได้ติดตั้ง
        500: {"status":"error","errors":[...]}  -- OS error
        """
        from features.qr.reader import start_reader
        from features.qr.registry import is_installed as _qr_is_installed
        # TODO: ตอนนี้ catalog มีแค่ zkteco-qr500 device เดียว — ถ้าเพิ่ม device อื่นในอนาคต
        # endpoint นี้ต้องรับ device_id มาระบุด้วย แทนการ hardcode
        if not _qr_is_installed("zkteco-qr500"):
            return {"status": "error", "errors": ["อุปกรณ์ถูกถอนการติดตั้งแล้ว กรุณาติดตั้งก่อนเริ่มอ่าน"]}, 400
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
            data: {"scan": "<value>", "device": "<path>", "ts": "<ISO8601-UTC>",
                   "raw_keycode": [<int>,...]|null, "raw_report": [<hex str>,...]|null,
                   "read_mode": "hidraw"|"evdev"|null,
                   "mqtt": {"enabled": bool, "connected": bool, "published": bool, "error": str|null},
                   "pipe": {"enabled": bool, "connected": bool, "published": bool, "error": str|null}}

            event: status
            data: {"running": <bool>, "device": "<path>"|null}

            event: heartbeat
            data: {}

        หมายเหตุ: การตรวจจับ "scan ใหม่" ใช้ reader.last_scan_seq (ตัวนับที่เพิ่มทุกครั้งที่
        scan เสร็จ แม้ค่าจะซ้ำกับครั้งก่อน) แทนการเทียบค่า string เดิม — เพื่อให้สแกน QR code
        เดิมซ้ำๆ ยังคง publish/log ทุกครั้ง ไม่ถูกข้ามเพราะค่าไม่เปลี่ยน
        """
        from flask import stream_with_context, Response
        import time
        from datetime import datetime, timezone

        def generate():
            from features.qr.reader import get_reader, start_reader
            from features.qr.registry import is_installed as _qr_is_installed

            def _try_start():
                """
                Auto-start reader ถ้ายังไม่ทำงาน — ไม่ raise
                ไม่ start ถ้า device ถูกถอนการติดตั้งไปแล้ว (registry) — ป้องกัน SSE loop
                นี้ resurrect reader กลับมาเองทุก RESTART_INTERVAL หลังกด "ถอน"
                """
                r = get_reader()
                if r is not None and r.is_alive():
                    return r
                if not _qr_is_installed("zkteco-qr500"):
                    return None
                try:
                    return start_reader()
                except Exception:
                    return None

            # Auto-start ทันทีที่ client เชื่อมต่อ
            reader = _try_start()
            running = reader is not None and reader.is_alive()
            device = reader.device_path if running else None
            yield f"event: status\ndata: {_json_dumps({'running': running, 'device': device})}\n\n"

            last_seq = -1  # -1 = sentinel เพื่อให้ scan ล่าสุดที่มีอยู่แล้ว (ถ้ามี) ถูกส่งครั้งแรกตอน connect
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
                        seq = getattr(reader, "last_scan_seq", None)
                        # เทียบ seq (ไม่ใช่ค่า string) — scan ค่าเดิมซ้ำก็ต้องนับเป็น scan ใหม่
                        # ทุกครั้งที่ seq เปลี่ยน ไม่ถูกข้ามเพราะค่าไม่เปลี่ยน (ตามที่ผู้ใช้ต้องการ)
                        if scan is not None and seq is not None and seq != last_seq:
                            last_seq = seq
                            ts = datetime.now(timezone.utc).isoformat()
                            scan_raw_keycode = getattr(reader, "last_scan_raw", None)
                            scan_raw_report = getattr(reader, "last_scan_raw_report", None)
                            read_mode = getattr(reader, "read_mode", None)

                            # Log QR scan ลง DB (ทำก่อน publish เพื่อไม่ให้ log หายถ้า publish error)
                            try:
                                from core.database import log_qr_scan as _db_log_qr
                                _db_log_qr(
                                    scan, reader.device_path, ts,
                                    raw_keycode=scan_raw_keycode,
                                    raw_report=scan_raw_report,
                                    read_mode=read_mode,
                                )
                            except Exception:
                                pass

                            # Publish ออก MQTT (device-aware routing ตาม device_integrations —
                            # คนละ code path จาก publish_qr_scan() ที่ใช้กับ `vas mqtt test` /
                            # `/api/mqtt/test`) — ทำก่อน yield event เพื่อแนบผลลัพธ์จริงไปกับ
                            # SSE payload ให้ frontend โชว์สีสถานะ (เขียว/แดง/เหลือง) ได้ถูกต้อง
                            mqtt_status: dict[str, object] = {
                                "enabled": False, "connected": False, "published": False, "error": None,
                            }
                            try:
                                from features.mqtt.client import publish_qr_scan_for_device as _mqtt_publish
                                mqtt_status = _mqtt_publish(
                                    "zkteco-qr500",
                                    scan, reader.device_path, ts,
                                    scan_raw_keycode=scan_raw_keycode,
                                    scan_raw_report=scan_raw_report,
                                    read_mode=read_mode,
                                )
                            except Exception as exc:
                                mqtt_status = {
                                    "enabled": True, "connected": False, "published": False, "error": str(exc),
                                }

                            # เขียนออก Named Pipe (device-aware ตาม device_integrations เหมือน MQTT
                            # ด้านบน) — เขียนก็ต่อเมื่อ toggle "Pipe I/O" enabled เท่านั้น เขียนแบบ
                            # non-blocking (features/qr/pipe_io.py) จึงไม่ทำให้ SSE loop ค้างแม้ไม่มี
                            # reader เปิด pipe รออยู่ฝั่งตรงข้าม
                            pipe_status: dict[str, object] = {
                                "enabled": False, "connected": False, "published": False, "error": None,
                            }
                            try:
                                from features.qr.pipe_io import publish_qr_scan_to_pipe_for_device as _pipe_publish
                                pipe_status = _pipe_publish("zkteco-qr500", scan)
                            except Exception as exc:
                                pipe_status = {
                                    "enabled": True, "connected": False, "published": False, "error": str(exc),
                                }

                            yield f"event: scan\ndata: {_json_dumps({'scan': scan, 'device': reader.device_path, 'ts': ts, 'raw_keycode': scan_raw_keycode, 'raw_report': scan_raw_report, 'read_mode': read_mode, 'mqtt': mqtt_status, 'pipe': pipe_status})}\n\n"
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
        # Auto-start reader ทันทีหลังติดตั้ง (ถ้ามี device ต่ออยู่จริง) — ไม่ raise ถ้าหาไม่เจอ
        if device_id == "zkteco-qr500":
            try:
                from features.qr.reader import get_reader as _get_qr_reader, start_reader as _qr_start
                if _get_qr_reader() is None:
                    _qr_start()
            except Exception:
                pass
        return {"status": "ok", "device_id": device_id}

    @app.post("/api/qr/devices/<device_id>/uninstall")
    def qr_device_uninstall_api(device_id: str) -> dict[str, object]:
        from features.qr.registry import uninstall_device
        try:
            uninstall_device(device_id)
        except Exception as e:
            return {"status": "error", "error": str(e)}, 500
        # หยุด reader thread ทันที — "ถอนการติดตั้ง" ต้องแปลว่าเลิกอ่าน/เลิก publish จริงๆ
        # ไม่ใช่แค่ซ่อนเมนู (ก่อนหน้านี้ reader ยังทำงานต่อเพราะ auto-detect จาก USB ID
        # ตรงๆ ไม่เคยเช็ค registry เลย)
        if device_id == "zkteco-qr500":
            try:
                from features.qr.reader import stop_reader as _qr_stop
                _qr_stop()
            except Exception:
                pass
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

    # ── Pipe Tester routes (หน้าแยกต่างหาก — ทดสอบอ่าน named pipe ใดๆ ในระบบ ไม่ว่าจะ
    #    เขียนมาจาก VAS เอง (Pipe I/O integration ของ QR500 ด้านบน) หรือจาก third-party
    #    process ภายนอก) ─────────────────────────────────────────

    @app.get("/pipe-tester")
    def pipe_tester_page() -> str:
        from core.database import list_pipe_integrations
        return render_template(
            "pipe_tester.html",
            known_pipes=list_pipe_integrations(),
        )

    @app.get("/api/pipes")
    def pipes_list_api() -> dict[str, object]:
        """รายการ pipe ที่ตั้งค่าไว้แล้วในระบบ (ทุก device) — ใช้เติม dropdown ในหน้า Pipe Tester"""
        from core.database import list_pipe_integrations
        return {"status": "ok", "pipes": list_pipe_integrations()}

    @app.post("/api/pipe/start")
    def pipe_start_api() -> tuple[dict[str, object], int] | dict[str, object]:
        from features.qr.pipe_io import start_pipe_reader
        payload = request.get_json(silent=True) or {}
        path = str(payload.get("path", "")).strip()
        if not path:
            return {"status": "error", "error": "path required"}, 400
        try:
            reader = start_pipe_reader(path)
        except OSError as e:
            return {"status": "error", "error": str(e)}, 500
        return {"status": "ok", "path": reader.path}

    @app.post("/api/pipe/stop")
    def pipe_stop_api() -> dict[str, object]:
        from features.qr.pipe_io import stop_pipe_reader
        stop_pipe_reader()
        return {"status": "ok"}

    @app.get("/api/pipe/stream")
    def pipe_stream_api():  # type: ignore[return]
        """
        Server-Sent Events stream ของหน้า Pipe Tester — poll PipeReaderThread ทุก 0.2s
        (กลไกเดียวกับ /api/qr/stream ด้านบน: เทียบ last_seq แทนค่า string เพื่อให้บรรทัด
        ซ้ำกันติดๆ กันยังถูกส่งออกทุกครั้ง ไม่ถูกข้ามเพราะค่าไม่เปลี่ยน)

            event: line
            data: {"line": "<str>", "ts": "<ISO8601-UTC>"}

            event: status
            data: {"running": bool, "path": "<str>"|null, "connected": bool, "error": str|null}

            event: heartbeat
            data: {}
        """
        from flask import stream_with_context, Response
        import time
        from datetime import datetime, timezone
        from features.qr.pipe_io import get_pipe_reader

        def _status_payload(reader: object) -> dict[str, object]:
            return {
                "running": reader is not None and reader.is_alive(),  # type: ignore[attr-defined]
                "path": reader.path if reader else None,  # type: ignore[attr-defined]
                "connected": reader.connected if reader else False,  # type: ignore[attr-defined]
                "error": reader.error if reader else None,  # type: ignore[attr-defined]
            }

        def generate():
            last_seq = -1
            last_heartbeat = time.monotonic()
            HEARTBEAT_INTERVAL = 5.0
            POLL_INTERVAL = 0.2

            reader = get_pipe_reader()
            running = reader is not None and reader.is_alive()
            yield f"event: status\ndata: {_json_dumps(_status_payload(reader))}\n\n"

            try:
                while True:
                    time.sleep(POLL_INTERVAL)
                    now = time.monotonic()

                    if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                        yield "event: heartbeat\ndata: {}\n\n"
                        last_heartbeat = now

                    reader = get_pipe_reader()
                    currently_alive = reader is not None and reader.is_alive()
                    if currently_alive != running:
                        running = currently_alive
                        yield f"event: status\ndata: {_json_dumps(_status_payload(reader))}\n\n"

                    if reader is not None and reader.is_alive():
                        seq = reader.last_seq
                        if seq > 0 and seq != last_seq:
                            last_seq = seq
                            ts = datetime.now(timezone.utc).isoformat()
                            yield f"event: line\ndata: {_json_dumps({'line': reader.last_line, 'ts': ts})}\n\n"
            except GeneratorExit:
                return

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ── MQTT routes ─────────────────────────────────────────────

    @app.get("/mqtt")
    def mqtt_page() -> str:
        from core.database import list_mqtt_brokers
        from features.mqtt.client import get_mqtt_client
        c = get_mqtt_client()  # primary broker client (ถ้ามี)
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

    @app.get("/api/mqtt/events")
    def mqtt_events_list_api() -> dict[str, object]:
        """
        ประวัติการ publish MQTT จาก DB — รองรับ pagination
        Query params: limit (100|250|500, default 100), offset (default 0)
        Return: {"status":"ok","rows":[...],"total":<int>,"limit":<int>,"offset":<int>}
        """
        from core.database import list_mqtt_events
        try:
            limit = int(request.args.get("limit", 100))
        except (TypeError, ValueError):
            limit = 100
        if limit not in (100, 250, 500):
            limit = 100
        try:
            offset = max(0, int(request.args.get("offset", 0)))
        except (TypeError, ValueError):
            offset = 0
        result = list_mqtt_events(limit=limit, offset=offset)
        return {"status": "ok", **result}

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
        from features.mqtt.client import start_mqtt_broker, stop_mqtt_broker
        payload = request.get_json(silent=True) or {}
        try:
            ok = update_mqtt_broker(broker_id, payload)
            if not ok:
                return {"status": "error", "errors": ["update ไม่สำเร็จ"]}, 500
            broker = get_mqtt_broker(broker_id)
            if broker:
                # reload connection ของ broker นี้เท่านั้น (ไม่กระทบ broker ตัวอื่นที่ connect อยู่)
                stop_mqtt_broker(broker_id)
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
        from features.mqtt.client import stop_mqtt_broker
        broker = get_mqtt_broker(broker_id)
        if broker:
            stop_mqtt_broker(broker_id)
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
        from features.mqtt.client import stop_mqtt_broker
        stop_mqtt_broker(broker_id)
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
        c = get_mqtt_client(broker_id)
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
    # อ่าน/เขียน mqtt_brokers (primary broker) แทน config.json

    @app.post("/api/mqtt/config")
    def mqtt_config_save_api() -> tuple[dict[str, object], int] | dict[str, object]:
        from features.mqtt.client import (
            MqttConfig, broker_db_to_config, start_mqtt_broker, stop_mqtt_broker,
        )
        from core.database import (
            get_primary_broker_id, get_mqtt_broker, create_mqtt_broker, update_mqtt_broker,
        )
        payload = request.get_json(silent=True) or {}
        try:
            config = MqttConfig.from_dict(payload)
            primary_id = get_primary_broker_id()
            if primary_id is not None:
                old_broker = get_mqtt_broker(primary_id)
                old_config = broker_db_to_config(old_broker) if old_broker else MqttConfig()
                update_mqtt_broker(primary_id, {**(old_broker or {}), **config.to_dict(), "is_primary": True})
                broker_id = primary_id
            else:
                old_config = MqttConfig()
                broker_id = create_mqtt_broker({
                    **config.to_dict(),
                    "name": "Primary broker",
                    "is_primary": True,
                })
            # mqtt_brokers ไม่มี column "topic" โดยตรง — sync เข้า mqtt_broker_topics แทน
            if config.topic:
                from core.database import list_mqtt_topics, add_mqtt_topic, update_mqtt_topic
                existing_topics = list_mqtt_topics(broker_id)
                match = next((t for t in existing_topics if t["topic"] == config.topic), None)
                if match is not None:
                    update_mqtt_topic(match["id"], {"topic": config.topic, "label": match.get("label", ""), "enabled": True})
                else:
                    add_mqtt_topic(broker_id, config.topic)
            stop_mqtt_broker(broker_id)
            if config.enabled:
                start_mqtt_broker(broker_id)
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
        c = get_mqtt_client()  # primary broker
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
        from features.mqtt.client import stop_mqtt_broker
        from core.database import get_primary_broker_id
        primary_id = get_primary_broker_id()
        if primary_id is not None:
            stop_mqtt_broker(primary_id)
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
        from system.utils import dev_fake_installed
        installed_devices = {d["id"]: True for d in load_installed_devices()}
        fake = dev_fake_installed()
        return {
            "status": "ok",
            "installed": {
                "wireguard": fake or _shutil.which("wg") is not None,
                "anydesk":   fake or _shutil.which("anydesk") is not None,
                "openssh":   fake or _shutil.which("sshd") is not None,
                "docker":    fake or _shutil.which("docker") is not None,
                "pm2":       fake or _shutil.which("pm2") is not None,
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
        from features.packages.settings import get_install_queue
        return _stream_pkg_action_queue(get_install_queue, pkg_id, "Install queue not found")

    @app.post("/api/settings/uninstall/<pkg_id>")
    def settings_uninstall_api(pkg_id: str) -> tuple[dict[str, object], int] | dict[str, object]:
        from features.packages.settings import start_uninstall
        ok, err = start_uninstall(pkg_id)
        if not ok:
            return {"status": "error", "errors": [err]}, 400
        return {"status": "ok", "pkg_id": pkg_id}

    @app.get("/api/settings/uninstall/<pkg_id>/stream")
    def settings_uninstall_stream_api(pkg_id: str):  # type: ignore[return]
        """SSE stream ของ uninstall output"""
        from features.packages.settings import get_uninstall_queue
        return _stream_pkg_action_queue(get_uninstall_queue, pkg_id, "Uninstall queue not found")

    # ── System Monitor routes ────────────────────────────────────
    # Monitor is now the home page (see "/" route above); keep the old
    # /monitor URL working as a redirect for existing bookmarks/links.

    @app.get("/monitor")
    def monitor_page_redirect():  # type: ignore[no-untyped-def]  # matches auth_setup/auth_login redirect-only handlers below
        from flask import redirect as _redir, url_for as _url_for
        return _redir(_url_for("monitor_page"))

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
        from flask import abort
        abort(404)  # ปิดหน้าไว้ก่อน — รอแก้ไข feature
        from core.database import get_stats
        return render_template("database.html", stats=get_stats())

    @app.get("/api/database/<table>")
    def database_table_api(table: str) -> tuple[dict[str, object], int] | dict[str, object]:
        from flask import abort
        abort(404)  # ปิดหน้าไว้ก่อน — รอแก้ไข feature
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
        from flask import abort
        abort(404)  # ปิดหน้าไว้ก่อน — รอแก้ไข feature
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
        from flask import abort
        abort(404)  # ปิดหน้าไว้ก่อน — รอแก้ไข feature
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
        return _redir(_url_for("monitor_page"))

    @app.get("/login")
    def auth_login():
        from flask import redirect as _redir, url_for as _url_for, session as _sess
        from core.auth import is_first_run
        if is_first_run():
            return _redir(_url_for("auth_setup"))
        if _sess.get("vas_user_id"):
            return _redir(_url_for("monitor_page"))
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
        # Redirect to next or home (Monitor) — ป้องกัน open redirect
        if next_url and next_url.startswith("/") and not next_url.startswith("//"):
            return _redir(next_url)
        return _redir(_url_for("monitor_page"))

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

    # ── Update routes ─────────────────────────────────────────────

    @app.get("/update")
    def update_page() -> str:
        from core.config import APP_VERSION
        return render_template("update.html", current_version=APP_VERSION)

    @app.get("/api/update/check")
    def update_check_api() -> dict[str, object]:
        from services.updater import check_latest_release
        return check_latest_release()  # type: ignore[return-value]

    @app.get("/api/update/stream")
    def update_stream_api():  # type: ignore[return]
        """SSE stream ของขั้นตอนการอัปเดต — เริ่มอัปเดตทันทีถ้ายังไม่มีงานทำอยู่"""
        from flask import stream_with_context, Response
        from services.updater import start_web_update, get_update_queue, is_updating

        if not is_updating():
            ok, err = start_web_update()
            if not ok:
                def _err_only():
                    yield f"event: error-event\ndata: {_json_dumps({'msg': err})}\n\n"
                return Response(stream_with_context(_err_only()), mimetype="text/event-stream")

        def generate():
            q = get_update_queue()
            if q is None:
                yield f"event: error-event\ndata: {_json_dumps({'msg': 'Update queue not found'})}\n\n"
                return
            while True:
                try:
                    item = q.get(timeout=30)
                except Exception:
                    yield "event: heartbeat\ndata: {}\n\n"
                    continue
                ev = item.get("event")
                if ev == "progress":
                    yield f"event: progress\ndata: {_json_dumps(item)}\n\n"
                elif ev == "log":
                    yield f"event: log\ndata: {_json_dumps(item)}\n\n"
                elif ev == "done":
                    yield f"event: done\ndata: {_json_dumps({})}\n\n"
                    return
                elif ev == "error":
                    yield f"event: error-event\ndata: {_json_dumps({'msg': item.get('msg', '')})}\n\n"
                    return

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/server/restart")
    def server_restart_api() -> dict[str, object]:
        import threading as _threading
        from services.server_service import SERVICE_UNIT
        from core.runner import CommandRunner as _CommandRunner

        def _delayed_restart() -> None:
            import time as _time
            _time.sleep(0.5)  # ให้ response กลับไปถึง client ก่อน service จะ restart
            _CommandRunner(dry_run=False).run(["systemctl", "restart", SERVICE_UNIT], check=False)

        _threading.Thread(target=_delayed_restart, daemon=True).start()
        return {"status": "ok"}

    return app


import json as _json


def _json_dumps(obj: dict[str, object]) -> str:
    return _json.dumps(obj, ensure_ascii=False)


def _stream_pkg_action_queue(get_queue_fn, pkg_id: str, not_found_msg: str):  # type: ignore[no-untyped-def]
    """
    SSE stream ทั่วไปสำหรับ install/uninstall queue (ใช้ queue item shape เดียวกัน
    จาก features.packages.settings._run_commands):
        {"type": "progress", "step": int, "total": int, "cmd": str}
        {"type": "line", "text": str}
        None → จบ (sentinel)
    """
    from flask import stream_with_context, Response
    import time as _time

    def generate():
        # รอให้ queue พร้อม (อาจยังไม่ start)
        deadline = _time.monotonic() + 5.0
        while _time.monotonic() < deadline:
            q = get_queue_fn(pkg_id)
            if q is not None:
                break
            _time.sleep(0.1)
            yield "event: heartbeat\ndata: {}\n\n"
        else:
            yield f"event: error\ndata: {_json_dumps({'msg': not_found_msg})}\n\n"
            return

        while True:
            try:
                item = q.get(timeout=30)
            except Exception:
                yield "event: heartbeat\ndata: {}\n\n"
                continue
            if item is None:  # sentinel — done
                yield f"event: done\ndata: {_json_dumps({'pkg_id': pkg_id})}\n\n"
                return
            if item.get("type") == "progress":
                yield f"event: progress\ndata: {_json_dumps(item)}\n\n"
            else:
                yield f"event: line\ndata: {_json_dumps({'text': item.get('text', '')})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def run_server(host: str, port: int, debug: bool) -> None:
    create_app().run(host=host, port=port, debug=debug)


def _component_label(component: str) -> str:
    """คืนชื่อเรียกสั้นๆ ของ component จาก PACKAGES manifest, fallback เป็น component id เอง"""
    if component == "all":
        return "ทุกคอมโพเนนต์"
    from features.packages.settings import PACKAGES
    for package in PACKAGES:
        if package["id"] == component:
            return str(package.get("name", component))
    return component


def _component_description(component: str) -> str:
    """คืนคำอธิบายของ component จาก PACKAGES manifest (ใช้ข้อมูลชุดเดียวกับหน้าติดตั้งแพ็กเกจ)"""
    if component == "all":
        return (
            "ติดตั้งทุกคอมโพเนนต์ที่รองรับในคำสั่งเดียว "
            "(git, node, docker, wireguard, anydesk, openssh, qr-udev)"
        )
    from features.packages.settings import PACKAGES
    for package in PACKAGES:
        if package["id"] == component:
            return str(package.get("description", ""))
    return ""


_UNINSTALL_NOTE = "ถอนการติดตั้งแพ็กเกจ แต่เก็บไฟล์ config ที่เกี่ยวข้องไว้"
_RESET_NOTE = "ถอนการติดตั้งแพ็กเกจและลบไฟล์ config ที่เกี่ยวข้องทั้งหมด กลับสู่ค่าเริ่มต้น"


def build_install_commands() -> tuple[CommandPreview, ...]:
    return tuple(
        CommandPreview(
            label=f"Install {component}",
            command=f"sudo vas install --component {component}",
            requires_root=True,
            description=_component_description(component),
        )
        for component in INSTALL_COMPONENTS
    )


def build_reset_commands() -> tuple[CommandPreview, ...]:
    commands: list[CommandPreview] = []
    for action in ("uninstall", "reset"):
        note = _UNINSTALL_NOTE if action == "uninstall" else _RESET_NOTE
        for component in LIFECYCLE_COMPONENTS:
            commands.append(
                CommandPreview(
                    label=f"{action.title()} {component}",
                    command=f"sudo vas {action} --component {component}",
                    requires_root=True,
                    description=f"{note} ({_component_label(component)})",
                )
            )
    return tuple(commands)


def build_wireguard_commands() -> tuple[CommandPreview, ...]:
    return tuple(
        CommandPreview(
            label=label,
            command=command,
            requires_root=command.startswith("sudo "),
            description=description,
        )
        for label, command, description in WIREGUARD_ACTIONS
    )


def build_display_commands() -> tuple[CommandPreview, ...]:
    return tuple(
        CommandPreview(
            label=label,
            command=command,
            requires_root=command.startswith("sudo "),
            description=description,
        )
        for label, command, description in DISPLAY_ACTIONS
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


def _openssh_values_from_payload(payload: dict[str, Any]) -> OpenSshConfigValues:
    """แปลง JSON payload จากฟอร์มหน้า OpenSSH เป็น SshdConfigValues พร้อม type coercion

    หมายเหตุ: ฝั่ง JS ส่งค่าจาก "ทุก field ในทุกแท็บ" มาพร้อมกันเสมอไม่ว่าจะกดปุ่ม
    บันทึกจากแท็บไหน (เพราะ render_dropin เขียนไฟล์ config ใหม่ทั้งไฟล์ทุกครั้ง —
    ส่งมาไม่ครบ field ที่เหลือจะถูกรีเซ็ตเป็นค่า default แทนค่าที่ใช้งานอยู่จริง)
    """

    def _str(key: str, default: str = "") -> str:
        value = payload.get(key, default)
        return str(value) if value is not None else default

    def _int(key: str, default: int) -> int:
        try:
            return int(payload.get(key, default))
        except (TypeError, ValueError):
            return default

    def _flag(key: str, default: bool) -> bool:
        value = payload.get(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    return OpenSshConfigValues(
        port=_int("port", 22),
        listen_address=_str("listen_address", "0.0.0.0"),
        permit_root_login=_str("permit_root_login", "prohibit-password"),
        password_authentication=_flag("password_authentication", False),
        pubkey_authentication=_flag("pubkey_authentication", True),
        permit_empty_passwords=_flag("permit_empty_passwords", False),
        kbd_interactive_authentication=_flag("kbd_interactive_authentication", False),
        max_auth_tries=_int("max_auth_tries", 3),
        login_grace_time=_int("login_grace_time", 30),
        authorized_keys_file=_str("authorized_keys_file", ".ssh/authorized_keys"),
        allow_users=_str("allow_users"),
        allow_groups=_str("allow_groups"),
        deny_users=_str("deny_users"),
        deny_groups=_str("deny_groups"),
        allow_tcp_forwarding=_flag("allow_tcp_forwarding", False),
        x11_forwarding=_flag("x11_forwarding", False),
        gateway_ports=_flag("gateway_ports", False),
        client_alive_interval=_int("client_alive_interval", 300),
        client_alive_count_max=_int("client_alive_count_max", 2),
        max_sessions=_int("max_sessions", 10),
        max_startups=_str("max_startups", "10:30:60"),
        strict_modes=_flag("strict_modes", True),
        use_pam=_flag("use_pam", True),
        log_level=_str("log_level", "VERBOSE").upper(),
        banner=_str("banner"),
    )


def _collect_pm2_status_mock() -> dict[str, Any]:
    """ข้อมูล mock สำหรับหน้า PM2 — ใช้ render UI ก่อนต่อ backend จริง

    TODO(pm2-real-impl): แทนที่ด้วยการอ่านค่าจริงผ่าน `pm2` CLI (CommandRunner)
    รูปแบบเดียวกับ `_collect_docker_status_mock()` — คง shape ของ dict นี้ไว้เหมือนเดิม
    เพื่อให้ pm2.html ใช้งานต่อได้โดยไม่ต้องแก้ template:
      - pm2.*        → `pm2 --version` / `pm2 ping` / จำนวน process จาก `pm2 jlist`
      - processes[]  → `pm2 jlist` (JSON array ต่อ process — cpu, memory, restart_time, pm2_env)
      - logs[]       → `pm2 logs <name> --lines N --nostream --raw` (แยก out/err ตาม pm2_env.pm_out_log_path)
      - ecosystem.*  → อ่านไฟล์ ecosystem.config.js ตรงๆ ด้วย pathlib (ตำแหน่งจาก settings/DB)
      - modules[]    → `pm2 ls` ส่วน Module / `pm2 describe <module>` สำหรับ config
      - startup.*    → output ของ `pm2 startup` ที่ save ไว้ + mtime ของ dump.pm2
    """
    return {
        "is_mock": True,
        "pm2": {
            "daemon_running": True,
            "version": "5.4.3",
            "node_version": "v22.11.0",
            "pm2_home": "/root/.pm2",
            "daemon_uptime": "5 วัน 14 ชม.",
            "processes_total": 6,
            "processes_online": 4,
            "processes_stopped": 1,
            "processes_errored": 1,
            "cpu_total_pct": 14.8,
            "mem_total": "418 MB",
        },
        "processes": [
            {
                "id": 0, "name": "vas-api", "namespace": "default", "mode": "cluster", "instances": 2,
                "exec_mode_label": "cluster_mode", "status": "online", "status_label": "ONLINE",
                "pid": "18422, 18423", "uptime": "5d", "restarts": 3, "unstable_restarts": 0,
                "cpu_pct": "6.2", "mem": "142 MB", "mem_limit": "300M", "watch": False,
                "script": "dist/api/server.js", "cwd": "/srv/vas/api",
                "interpreter": "node", "node_args": "--max-old-space-size=512",
                "out_log_path": "/root/.pm2/logs/vas-api-out.log",
                "err_log_path": "/root/.pm2/logs/vas-api-error.log",
                "created_at": "27 มิ.ย. 2569 09:14", "autorestart": True, "user": "root",
            },
            {
                "id": 1, "name": "mqtt-bridge", "namespace": "default", "mode": "fork", "instances": 1,
                "exec_mode_label": "fork_mode", "status": "online", "status_label": "ONLINE",
                "pid": "18430", "uptime": "5d", "restarts": 0, "unstable_restarts": 0,
                "cpu_pct": "0.8", "mem": "54 MB", "mem_limit": None, "watch": True,
                "script": "dist/mqtt/bridge.js", "cwd": "/srv/vas/mqtt",
                "interpreter": "node", "node_args": "",
                "out_log_path": "/root/.pm2/logs/mqtt-bridge-out.log",
                "err_log_path": "/root/.pm2/logs/mqtt-bridge-error.log",
                "created_at": "27 มิ.ย. 2569 09:14", "autorestart": True, "user": "root",
            },
            {
                "id": 2, "name": "qr-listener", "namespace": "default", "mode": "fork", "instances": 1,
                "exec_mode_label": "fork_mode", "status": "online", "status_label": "ONLINE",
                "pid": "18441", "uptime": "5d", "restarts": 1, "unstable_restarts": 0,
                "cpu_pct": "1.1", "mem": "38 MB", "mem_limit": "150M", "watch": True,
                "script": "dist/qr/listener.js", "cwd": "/srv/vas/qr",
                "interpreter": "node", "node_args": "",
                "out_log_path": "/root/.pm2/logs/qr-listener-out.log",
                "err_log_path": "/root/.pm2/logs/qr-listener-error.log",
                "created_at": "27 มิ.ย. 2569 09:15", "autorestart": True, "user": "root",
            },
            {
                "id": 3, "name": "webhook-relay", "namespace": "default", "mode": "fork", "instances": 1,
                "exec_mode_label": "fork_mode", "status": "errored", "status_label": "ERRORED",
                "pid": "—", "uptime": "0s", "restarts": 18, "unstable_restarts": 5,
                "cpu_pct": "0", "mem": "0 MB", "mem_limit": "200M", "watch": False,
                "script": "dist/webhook/relay.js", "cwd": "/srv/vas/webhook",
                "interpreter": "node", "node_args": "",
                "out_log_path": "/root/.pm2/logs/webhook-relay-out.log",
                "err_log_path": "/root/.pm2/logs/webhook-relay-error.log",
                "created_at": "30 มิ.ย. 2569 11:02", "autorestart": True, "user": "root",
            },
            {
                "id": 4, "name": "cron-jobs", "namespace": "default", "mode": "fork", "instances": 1,
                "exec_mode_label": "fork_mode", "status": "stopped", "status_label": "STOPPED",
                "pid": "—", "uptime": "หยุดเมื่อ 2 ชม. ที่แล้ว", "restarts": 2, "unstable_restarts": 0,
                "cpu_pct": "0", "mem": "0 MB", "mem_limit": None, "watch": False,
                "script": "dist/cron/index.js", "cwd": "/srv/vas/cron",
                "interpreter": "node", "node_args": "",
                "out_log_path": "/root/.pm2/logs/cron-jobs-out.log",
                "err_log_path": "/root/.pm2/logs/cron-jobs-error.log",
                "created_at": "20 มิ.ย. 2569 08:40", "autorestart": False, "user": "root",
            },
            {
                "id": 5, "name": "log-shipper", "namespace": "default", "mode": "fork", "instances": 1,
                "exec_mode_label": "fork_mode", "status": "online", "status_label": "ONLINE",
                "pid": "18455", "uptime": "3d", "restarts": 0, "unstable_restarts": 0,
                "cpu_pct": "0.3", "mem": "31 MB", "mem_limit": None, "watch": False,
                "script": "dist/log-shipper/index.js", "cwd": "/srv/vas/log-shipper",
                "interpreter": "node", "node_args": "",
                "out_log_path": "/root/.pm2/logs/log-shipper-out.log",
                "err_log_path": "/root/.pm2/logs/log-shipper-error.log",
                "created_at": "29 มิ.ย. 2569 14:20", "autorestart": True, "user": "root",
            },
        ],
        "logs": [
            {
                "process": "vas-api",
                "lines": [
                    {"ts": "12:04:01", "stream": "out", "text": "[cluster #0] listening on :8080"},
                    {"ts": "12:04:01", "stream": "out", "text": "[cluster #1] listening on :8080"},
                    {"ts": "12:06:22", "stream": "out", "text": "GET /api/status 200 12ms"},
                    {"ts": "12:07:03", "stream": "err", "text": "DeprecationWarning: Buffer() is deprecated"},
                    {"ts": "12:09:44", "stream": "out", "text": "POST /api/devices 201 34ms"},
                ],
            },
            {
                "process": "mqtt-bridge",
                "lines": [
                    {"ts": "12:01:10", "stream": "out", "text": "connected to broker mqtt://127.0.0.1:1883"},
                    {"ts": "12:03:55", "stream": "out", "text": "published vas/status/heartbeat"},
                    {"ts": "12:08:12", "stream": "out", "text": "subscribed vas/qr/scan"},
                ],
            },
            {
                "process": "qr-listener",
                "lines": [
                    {"ts": "11:58:02", "stream": "out", "text": "watching /dev/hidraw0"},
                    {"ts": "12:02:31", "stream": "out", "text": "scan received: 8850123456789"},
                ],
            },
            {
                "process": "webhook-relay",
                "lines": [
                    {"ts": "12:10:01", "stream": "err", "text": "Error: connect ECONNREFUSED 10.0.5.9:443"},
                    {"ts": "12:10:01", "stream": "err", "text": "    at TCPConnectWrap.afterConnect [as oncomplete]"},
                    {"ts": "12:10:01", "stream": "out", "text": "[PM2] App [webhook-relay] exited with code 1"},
                    {"ts": "12:10:02", "stream": "out", "text": "[PM2] App [webhook-relay] restarting (restart #18)"},
                    {"ts": "12:10:02", "stream": "err", "text": "Error: connect ECONNREFUSED 10.0.5.9:443"},
                ],
            },
            {
                "process": "cron-jobs",
                "lines": [
                    {"ts": "09:58:40", "stream": "out", "text": "[PM2] App [cron-jobs] stopped by user"},
                ],
            },
            {
                "process": "log-shipper",
                "lines": [
                    {"ts": "12:00:00", "stream": "out", "text": "shipped 214 records to loki"},
                    {"ts": "12:05:00", "stream": "out", "text": "shipped 198 records to loki"},
                ],
            },
        ],
        "ecosystem": {
            "exists": True,
            "path": "/srv/vas/ecosystem.config.js",
            "content": (
                "module.exports = {\n"
                "  apps: [\n"
                "    {\n"
                "      name: \"vas-api\",\n"
                "      script: \"dist/api/server.js\",\n"
                "      cwd: \"/srv/vas/api\",\n"
                "      instances: 2,\n"
                "      exec_mode: \"cluster\",\n"
                "      max_memory_restart: \"300M\",\n"
                "      env: { NODE_ENV: \"production\", PORT: 8080 },\n"
                "    },\n"
                "    {\n"
                "      name: \"mqtt-bridge\",\n"
                "      script: \"dist/mqtt/bridge.js\",\n"
                "      cwd: \"/srv/vas/mqtt\",\n"
                "      watch: true,\n"
                "      env: { NODE_ENV: \"production\" },\n"
                "    },\n"
                "    {\n"
                "      name: \"qr-listener\",\n"
                "      script: \"dist/qr/listener.js\",\n"
                "      cwd: \"/srv/vas/qr\",\n"
                "      watch: true,\n"
                "      max_memory_restart: \"150M\",\n"
                "    },\n"
                "    {\n"
                "      name: \"webhook-relay\",\n"
                "      script: \"dist/webhook/relay.js\",\n"
                "      cwd: \"/srv/vas/webhook\",\n"
                "      max_memory_restart: \"200M\",\n"
                "    },\n"
                "    {\n"
                "      name: \"cron-jobs\",\n"
                "      script: \"dist/cron/index.js\",\n"
                "      cwd: \"/srv/vas/cron\",\n"
                "      autorestart: false,\n"
                "    },\n"
                "    {\n"
                "      name: \"log-shipper\",\n"
                "      script: \"dist/log-shipper/index.js\",\n"
                "      cwd: \"/srv/vas/log-shipper\",\n"
                "    },\n"
                "  ],\n"
                "};\n"
            ),
        },
        "modules": [
            {
                "name": "pm2-logrotate", "version": "2.7.0", "status": "active",
                "description": "หมุนไฟล์ log อัตโนมัติเมื่อขนาดเกินกำหนด — ป้องกัน disk เต็มจาก log สะสม",
                "config": {"max_size": "10M", "retain": "7", "compress": True, "rotate_interval": "0 0 * * *"},
            },
            {
                "name": "pm2-server-monit", "version": "1.0.5", "status": "inactive",
                "description": "ส่ง metrics CPU/RAM/Disk ของเครื่องไปยัง PM2 Plus dashboard",
                "config": None,
            },
            {
                "name": "pm2-auto-pull", "version": "0.2.7", "status": "inactive",
                "description": "Auto `git pull` + reload process เมื่อ repo มีการอัปเดตใหม่",
                "config": None,
            },
        ],
        "startup": {
            "configured": True,
            "platform": "systemd",
            "user": "root",
            "service_name": "pm2-root",
            "command": "pm2 startup systemd -u root --hp /root",
            "last_save": "2 ชม. ที่แล้ว",
            "dump_path": "/root/.pm2/dump.pm2",
            "dump_exists": True,
        },
    }


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
        CommandPreview(
            label=label,
            command=command,
            requires_root=command.startswith("sudo "),
            description=description,
        )
        for label, command, description in SERVER_ACTIONS
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
