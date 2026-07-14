from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from services.server_service import ENV_PATH, SERVICE_UNIT, ServerConfig, default_server_config
from features.wireguard.manager import WIREGUARD_CONFIG_DIR, default_store_dir, service_name
from system.utils import dev_fake_installed


@dataclass(frozen=True)
class ToolStatus:
    name: str
    command: str
    installed: bool
    version: str | None
    path: str | None


@dataclass(frozen=True)
class DisplaySessionStatus:
    session_type: str
    is_x11: bool
    source: str


@dataclass(frozen=True)
class XorgTouchscreenConfigStatus:
    path: Path
    exists: bool
    has_signature: bool


@dataclass(frozen=True)
class XorgDisplayRotateConfigStatus:
    path: Path
    exists: bool
    has_signature: bool


@dataclass(frozen=True)
class DisplaySessionConfigStatus:
    path: Path
    exists: bool
    has_signature: bool


@dataclass(frozen=True)
class DisplaySessionScriptStatus:
    path: Path
    exists: bool
    has_signature: bool
    executable: bool


@dataclass(frozen=True)
class ScreenBlankConfigStatus:
    path: Path
    exists: bool
    has_signature: bool


@dataclass(frozen=True)
class GdmWaylandStatus:
    path: Path
    exists: bool
    readable: bool
    disabled: bool
    value: str | None


@dataclass(frozen=True)
class VpnPeerStatus:
    public_key: str
    endpoint: str | None
    allowed_ips: str | None
    latest_handshake: str | None
    transfer_rx: str | None
    transfer_tx: str | None
    persistent_keepalive: str | None


@dataclass(frozen=True)
class VpnStatus:
    interface_name: str
    wg_installed: bool
    wg_version: str | None
    app_config_path: Path
    app_config_exists: bool
    active_config_path: Path
    active_config_exists: bool
    history_dir: Path
    history_exists: bool
    service_enabled: str
    service_active: str
    interface_exists: bool
    handshake_peers: int | None
    public_key: str | None = None
    listen_port: str | None = None
    peers: tuple[VpnPeerStatus, ...] = ()


@dataclass(frozen=True)
class WebServerStatus:
    host: str
    port: int
    url: str
    service_enabled: str
    service_active: str


@dataclass(frozen=True)
class RemoteAccessStatus:
    anydesk_installed: bool
    anydesk_version: str | None
    anydesk_id: str | None
    anydesk_status: str
    service_enabled: str
    service_active: str


@dataclass(frozen=True)
class OpenSshStatus:
    installed: bool
    version: str | None
    service_enabled: str
    service_active: str


@dataclass(frozen=True)
class McpStatus:
    runtime_installed: bool  # fastmcp/uvicorn ติดตั้งแล้วหรือยัง (ดู vas_mcp.service.MCP_RUNTIME_PACKAGES)
    service_installed: bool  # มี systemd unit file แล้วหรือยัง (ยังไม่เคยกด "เปิดใช้งาน" = False)
    service_enabled: str     # "enabled" | "disabled" | "unknown"
    service_active: str      # "active" | "inactive" | "unknown"
    host: str
    port: int
    url: str
    tool_modules: tuple[str, ...]


XORG_TOUCHSCREEN_CONFIG_PATH = Path("/etc/X11/xorg.conf.d/99-vending-touchscreen.conf")
# หมายเลข 98 ต้องโหลด "ก่อน" 99 เสมอ (Xorg อ่านไฟล์ใน xorg.conf.d ตามลำดับตัวเลข/ชื่อไฟล์) —
# ทั้งคู่เป็น machine-level config ที่ X server อ่านตอน start ครั้งแรก (ก่อน login ใครทั้งสิ้น)
# ไม่ผูกกับ user คนไหน ต่างจาก .xprofile/display-session.sh ที่ผูกกับ home ของ user ที่ login
# อยู่ตอนนั้นเท่านั้น — ดู docs/kiosk-display-touch-order-guide.md หัวข้อ 2 ประกอบ
XORG_DISPLAY_ROTATE_CONFIG_PATH = Path("/etc/X11/xorg.conf.d/98-vending-display-rotate.conf")
GDM_CUSTOM_CONFIG_PATH = Path("/etc/gdm3/custom.conf")
XORG_TOUCHSCREEN_SIGNATURE = "# vending-auto-config: touchscreen-xorg"
XORG_DISPLAY_ROTATE_SIGNATURE = "# vending-auto-config: display-rotate-xorg"
DISPLAY_SESSION_SIGNATURE = "# vending-auto-config: display-session"
DISPLAY_SESSION_SCRIPT_SIGNATURE = "# vending-auto-config: display-session-script"
SCREEN_BLANK_SIGNATURE = "# vending-auto-config: screen-blank"

# NOTE: อย่าใช้ Path.home() ใน module-level — ให้เรียก _effective_home() ที่ call time เสมอ
# เพราะ Path.home() resolve เป็น /root เมื่อรัน sudo (env_reset ลบ HOME ออก)


def _effective_home() -> Path:
    """Return home directory ของ desktop user จริง (คนที่ login X11 session อยู่)

    ลำดับความสำคัญ:
    1. loginctl — หา owner ของ active X11 session จริง (ดู find_x11_session_owner()) เชื่อถือ
       ได้ที่สุด เพราะไม่ขึ้นกับว่า VAS server เอง (systemd service, รันเป็น root, ไม่มี
       SUDO_USER ใน env) ถูก start มายังไง — ถ้าใช้แค่ SUDO_USER แล้ว VAS server รันเป็น
       service (ไม่ใช่ interactive `sudo vas server run`) จะ fallback ไป Path.home() = /root
       ทันที ทำให้ persist .xprofile/display-session.sh ไปผิด home (ของ root ไม่ใช่ของ
       desktop user) — สคริปต์ที่ persist ไว้เลยไม่มีวันถูก X session จริงเจอ ทำให้การตั้งค่า
       จอ (เช่น rotation) หายกลับไปเป็นค่าเดิมทุกครั้งหลัง reboot
    2. SUDO_USER — เผื่อรันแบบ `sudo vas ...` interactive และ loginctl หา session ไม่เจอ
       (เช่นทดสอบใน environment ที่ไม่มี X11 session จริง)
    3. Path.home() ของ process เอง — fallback สุดท้าย
    """
    session_owner = find_x11_session_owner()
    if session_owner:
        name, _display = session_owner
        try:
            import pwd

            return Path(pwd.getpwnam(name).pw_dir)  # type: ignore[attr-defined]
        except (ImportError, KeyError):
            pass

    sudo_user = os.environ.get("SUDO_USER", "").strip()
    if sudo_user and sudo_user != "root":
        try:
            import pwd

            return Path(pwd.getpwnam(sudo_user).pw_dir)  # type: ignore[attr-defined]
        except (ImportError, KeyError):
            pass
    return Path.home()


def _effective_home_config_path() -> Path:
    return _effective_home() / ".xprofile"


def _effective_home_script_path() -> Path:
    return _effective_home() / ".config/vending-auto-setup/display-session.sh"


TOOLS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Git", "git", ("git", "--version")),
    ("Node.js", "node", ("node", "--version")),
    ("npm", "npm", ("npm", "--version")),
    ("PM2", "pm2", ("pm2", "--version")),
    ("Docker", "docker", ("docker", "--version")),
    ("AnyDesk", "anydesk", ("anydesk", "--version")),
)


def collect_status() -> tuple[ToolStatus, ...]:
    return tuple(_check_tool(name, command, version_args) for name, command, version_args in TOOLS)


def collect_remote_access_status() -> RemoteAccessStatus:
    if dev_fake_installed():
        return RemoteAccessStatus(
            anydesk_installed=True,
            anydesk_version="anydesk 6.5.0 (dev-mode)",
            anydesk_id="123 456 789",
            anydesk_status="Online",
            service_enabled="enabled",
            service_active="active",
        )
    anydesk_path = shutil.which("anydesk")
    return RemoteAccessStatus(
        anydesk_installed=anydesk_path is not None,
        anydesk_version=_read_version((anydesk_path, "--version")) if anydesk_path is not None else None,
        anydesk_id=_read_command_first_line_or_none((anydesk_path, "--get-id")) if anydesk_path is not None else None,
        anydesk_status=_read_command_first_line((anydesk_path, "--get-status")) if anydesk_path is not None else "not installed",
        service_enabled=_read_command_first_line(("systemctl", "is-enabled", "anydesk")),
        service_active=_read_command_first_line(("systemctl", "is-active", "anydesk")),
    )


def collect_openssh_status() -> OpenSshStatus:
    if dev_fake_installed():
        return OpenSshStatus(installed=True, version="OpenSSH_9.6 (dev-mode)", service_enabled="enabled", service_active="active")

    # ใช้ sshd (server binary) ไม่ใช่ ssh (client) — openssh-client ติดตั้งมาเป็น default
    # บน Ubuntu 22.04 โดยไม่ต้อง install openssh-server
    sshd_path = shutil.which("sshd")
    ssh_path = shutil.which("ssh")
    return OpenSshStatus(
        installed=sshd_path is not None,
        version=_read_version((ssh_path, "-V")) if ssh_path is not None else None,
        service_enabled=_read_command_first_line(("systemctl", "is-enabled", "ssh")),
        service_active=_read_command_first_line(("systemctl", "is-active", "ssh")),
    )


# tool module ที่ mount เข้า MCP server จริง (ดู src/vas_mcp/server.py) — รายชื่อ hardcode ไว้ที่นี่
# เพื่อไม่ต้องดึง tool ทั้งชุดเข้ามาแค่จะ list ชื่อในหน้าเว็บ — ใช้เป็น static catalog สำหรับ
# แสดงผลเท่านั้น ไม่ได้ import จริง (เดิมชื่อ package คือ src/mcp/ ซึ่งชนกับ pip package "mcp"
# ที่ fastmcp ต้องพึ่ง — เปลี่ยนชื่อเป็น src/vas_mcp/ แล้วแก้ปัญหานี้ไปแล้ว)
MCP_TOOL_MODULES: tuple[str, ...] = ("system", "network", "display", "docker", "logs", "shell")


def collect_mcp_status() -> McpStatus:
    from vas_mcp.service import MCP_SERVICE_PATH, MCP_SERVICE_UNIT, default_mcp_config, runtime_ready

    cfg = default_mcp_config()
    if dev_fake_installed():
        return McpStatus(
            runtime_installed=True,
            service_installed=True,
            service_enabled="enabled",
            service_active="active",
            host=cfg.host,
            port=cfg.port,
            url=cfg.url,
            tool_modules=MCP_TOOL_MODULES,
        )

    return McpStatus(
        runtime_installed=runtime_ready(),
        service_installed=MCP_SERVICE_PATH.exists(),
        service_enabled=_read_command_first_line(("systemctl", "is-enabled", MCP_SERVICE_UNIT)),
        service_active=_read_command_first_line(("systemctl", "is-active", MCP_SERVICE_UNIT)),
        host=cfg.host,
        port=cfg.port,
        url=cfg.url,
        tool_modules=MCP_TOOL_MODULES,
    )


def collect_vpn_status(interface_name: str = "wg0") -> VpnStatus:
    store_dir = default_store_dir()
    app_config_path = store_dir / "configs" / f"{interface_name}.conf"
    active_config_path = WIREGUARD_CONFIG_DIR / f"{interface_name}.conf"
    history_dir = store_dir / "history" / interface_name
    fake = dev_fake_installed()
    wg_path = "/usr/bin/wg" if fake else shutil.which("wg")
    service = service_name(interface_name)

    public_key: str | None = None
    listen_port: str | None = None
    peers: tuple[VpnPeerStatus, ...] = ()
    if wg_path is not None and not fake:
        public_key, listen_port, peers = _collect_wg_dump(wg_path, interface_name)

    return VpnStatus(
        interface_name=interface_name,
        wg_installed=wg_path is not None,
        wg_version="wireguard-tools v1.0.0 (dev-mode)" if fake else (_read_version((wg_path, "--version")) if wg_path is not None else None),
        app_config_path=app_config_path,
        app_config_exists=_path_exists(app_config_path),
        active_config_path=active_config_path,
        active_config_exists=_path_exists(active_config_path),
        history_dir=history_dir,
        history_exists=_path_exists(history_dir),
        service_enabled="enabled" if fake else _read_command_first_line(("systemctl", "is-enabled", service)),
        service_active="active" if fake else _read_command_first_line(("systemctl", "is-active", service)),
        interface_exists=True if fake else _command_succeeds(("wg", "show", interface_name)),
        handshake_peers=(0 if fake else (_count_handshake_peers(interface_name) if wg_path is not None else None)),
        public_key=public_key,
        listen_port=listen_port,
        peers=peers,
    )


def collect_web_server_status() -> WebServerStatus:
    config = _read_server_config()
    return WebServerStatus(
        host=config.host,
        port=config.port,
        url=config.url,
        service_enabled=_read_command_first_line(("systemctl", "is-enabled", SERVICE_UNIT)),
        service_active=_read_command_first_line(("systemctl", "is-active", SERVICE_UNIT)),
    )


def collect_display_session_status() -> DisplaySessionStatus:
    env_session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if env_session_type:
        return DisplaySessionStatus(
            session_type=env_session_type,
            is_x11=env_session_type == "x11",
            source="XDG_SESSION_TYPE",
        )

    loginctl_session_type = _read_loginctl_session_type()
    if loginctl_session_type:
        normalized_session_type = loginctl_session_type.strip().lower()
        return DisplaySessionStatus(
            session_type=normalized_session_type,
            is_x11=normalized_session_type == "x11",
            source="loginctl",
        )

    return DisplaySessionStatus(session_type="unknown", is_x11=False, source="not detected")


def collect_xorg_touchscreen_config_status(
    path: Path = XORG_TOUCHSCREEN_CONFIG_PATH,
) -> XorgTouchscreenConfigStatus:
    if not _path_exists(path):
        return XorgTouchscreenConfigStatus(path=path, exists=False, has_signature=False)

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return XorgTouchscreenConfigStatus(path=path, exists=True, has_signature=False)

    return XorgTouchscreenConfigStatus(
        path=path,
        exists=True,
        has_signature=XORG_TOUCHSCREEN_SIGNATURE in content,
    )


def collect_xorg_display_rotate_config_status(
    path: Path = XORG_DISPLAY_ROTATE_CONFIG_PATH,
) -> XorgDisplayRotateConfigStatus:
    if not _path_exists(path):
        return XorgDisplayRotateConfigStatus(path=path, exists=False, has_signature=False)

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return XorgDisplayRotateConfigStatus(path=path, exists=True, has_signature=False)

    return XorgDisplayRotateConfigStatus(
        path=path,
        exists=True,
        has_signature=XORG_DISPLAY_ROTATE_SIGNATURE in content,
    )


def collect_display_session_config_status(
    path: Path | None = None,
) -> DisplaySessionConfigStatus:
    if path is None:
        path = _effective_home_config_path()
    if not _path_exists(path):
        return DisplaySessionConfigStatus(path=path, exists=False, has_signature=False)

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return DisplaySessionConfigStatus(path=path, exists=True, has_signature=False)

    return DisplaySessionConfigStatus(
        path=path,
        exists=True,
        has_signature=DISPLAY_SESSION_SIGNATURE in content,
    )


def collect_display_session_script_status(
    path: Path | None = None,
) -> DisplaySessionScriptStatus:
    if path is None:
        path = _effective_home_script_path()
    if not _path_exists(path):
        return DisplaySessionScriptStatus(path=path, exists=False, has_signature=False, executable=False)

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return DisplaySessionScriptStatus(
            path=path,
            exists=True,
            has_signature=False,
            executable=os.access(path, os.X_OK),
        )

    return DisplaySessionScriptStatus(
        path=path,
        exists=True,
        has_signature=DISPLAY_SESSION_SCRIPT_SIGNATURE in content,
        executable=os.access(path, os.X_OK),
    )


def collect_screen_blank_config_status(
    path: Path | None = None,
) -> ScreenBlankConfigStatus:
    if path is None:
        path = _effective_home_config_path()
    if not _path_exists(path):
        return ScreenBlankConfigStatus(path=path, exists=False, has_signature=False)

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ScreenBlankConfigStatus(path=path, exists=True, has_signature=False)

    return ScreenBlankConfigStatus(
        path=path,
        exists=True,
        has_signature=SCREEN_BLANK_SIGNATURE in content,
    )


def collect_gdm_wayland_status(path: Path = GDM_CUSTOM_CONFIG_PATH) -> GdmWaylandStatus:
    if not _path_exists(path):
        return GdmWaylandStatus(path=path, exists=False, readable=False, disabled=False, value=None)

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return GdmWaylandStatus(path=path, exists=True, readable=False, disabled=False, value=None)

    value = _read_gdm_daemon_key(content, "WaylandEnable")
    return GdmWaylandStatus(
        path=path,
        exists=True,
        readable=True,
        disabled=(value or "").lower() == "false",
        value=value,
    )


def print_status() -> None:
    print("Vending Auto Setup Status")
    print()
    _print_display_session_status(collect_display_session_status())
    print()
    _print_gdm_wayland_status(collect_gdm_wayland_status())
    print()
    _print_display_session_config_status(collect_display_session_config_status())
    _print_display_session_script_status(collect_display_session_script_status())
    print()
    _print_xorg_touchscreen_config_status(collect_xorg_touchscreen_config_status())
    _print_xorg_display_rotate_config_status(collect_xorg_display_rotate_config_status())
    print()
    print("[Core Tools]")
    for status in collect_status():
        _print_tool_status(status)
    print()
    _print_remote_access_status(collect_remote_access_status())
    _print_openssh_status(collect_openssh_status())
    print()
    _print_vpn_status(collect_vpn_status())
    print()
    _print_web_server_status(collect_web_server_status())
    print()
    _print_qr_reader_status(collect_qr_reader_status())


def main() -> int:
    statuses = collect_status()
    print("Vending Auto Setup Status")
    print()
    _print_display_session_status(collect_display_session_status())
    print()
    _print_gdm_wayland_status(collect_gdm_wayland_status())
    print()
    _print_display_session_config_status(collect_display_session_config_status())
    _print_display_session_script_status(collect_display_session_script_status())
    print()
    _print_xorg_touchscreen_config_status(collect_xorg_touchscreen_config_status())
    _print_xorg_display_rotate_config_status(collect_xorg_display_rotate_config_status())
    print()
    print("[Core Tools]")
    for status in statuses:
        _print_tool_status(status)
    print()
    _print_remote_access_status(collect_remote_access_status())
    _print_openssh_status(collect_openssh_status())
    print()
    _print_vpn_status(collect_vpn_status())
    print()
    _print_web_server_status(collect_web_server_status())
    print()
    _print_qr_reader_status(collect_qr_reader_status())

    return 0 if all(status.installed for status in statuses) else 1


def _check_tool(name: str, command: str, version_args: Sequence[str]) -> ToolStatus:
    if dev_fake_installed():
        return ToolStatus(name=name, command=command, installed=True, version="dev-mode", path=f"/usr/bin/{command}")

    path = shutil.which(command)
    if path is None:
        return ToolStatus(name=name, command=command, installed=False, version=None, path=None)

    version = _read_version((path, *version_args[1:]))
    return ToolStatus(name=name, command=command, installed=True, version=version, path=path)


def _read_version(args: Sequence[str]) -> str | None:
    completed = _run_command(args)
    if completed is None:
        return None
    if completed.returncode != 0:
        return _first_output_line(completed.stderr)
    return _first_output_line(completed.stdout) or _first_output_line(completed.stderr)


def _read_command_first_line(args: Sequence[str]) -> str:
    completed = _run_command(args)
    if completed is None:
        return "unknown"
    return _first_output_line(completed.stdout) or _first_output_line(completed.stderr) or "unknown"


def _read_command_first_line_or_none(args: Sequence[str]) -> str | None:
    completed = _run_command(args)
    if completed is None or completed.returncode != 0:
        return None
    return _first_output_line(completed.stdout) or _first_output_line(completed.stderr)


def _command_succeeds(args: Sequence[str]) -> bool:
    completed = _run_command(args)
    return completed is not None and completed.returncode == 0


def _count_handshake_peers(interface_name: str) -> int | None:
    completed = _run_command(("wg", "show", interface_name, "latest-handshakes"))
    if completed is None or completed.returncode != 0:
        return None

    peer_count = 0
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit() and int(parts[1]) > 0:
            peer_count += 1
    return peer_count


def _collect_wg_dump(wg_path: str, interface_name: str) -> tuple[str | None, str | None, tuple["VpnPeerStatus", ...]]:
    """Parse `wg show <interface> dump` เพื่อดึงข้อมูล public key, listen port, peers.

    Dump format (tab-separated):
      interface line: private-key public-key listen-port fwmark
      peer line:       public-key preshared-key endpoint allowed-ips latest-handshake transfer-rx transfer-tx persistent-keepalive
    """
    completed = _run_command((wg_path, "show", interface_name, "dump"))
    if completed is None or completed.returncode != 0:
        return None, None, ()

    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return None, None, ()

    iface_fields = lines[0].split("\t")
    public_key = iface_fields[1] if len(iface_fields) > 1 and iface_fields[1] != "(none)" else None
    listen_port = iface_fields[2] if len(iface_fields) > 2 and iface_fields[2] != "(none)" else None

    peers: list[VpnPeerStatus] = []
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) < 8:
            continue
        peer_public_key, _preshared_key, endpoint, allowed_ips, handshake, rx, tx, keepalive = fields[:8]
        peers.append(
            VpnPeerStatus(
                public_key=peer_public_key,
                endpoint=endpoint if endpoint != "(none)" else None,
                allowed_ips=allowed_ips if allowed_ips != "(none)" else None,
                latest_handshake=_format_handshake_age(handshake),
                transfer_rx=_format_bytes(rx),
                transfer_tx=_format_bytes(tx),
                persistent_keepalive=None if keepalive in ("0", "off", "(none)") else f"{keepalive}s",
            )
        )
    return public_key, listen_port, tuple(peers)


def _format_handshake_age(raw: str) -> str | None:
    try:
        handshake_ts = int(raw)
    except (TypeError, ValueError):
        return None
    if handshake_ts <= 0:
        return None

    delta = max(0, int(time.time()) - handshake_ts)
    if delta < 60:
        return f"{delta} วินาทีที่แล้ว"
    if delta < 3600:
        return f"{delta // 60} นาทีที่แล้ว"
    if delta < 86400:
        return f"{delta // 3600} ชั่วโมงที่แล้ว"
    return f"{delta // 86400} วันที่แล้ว"


def _format_bytes(raw: str) -> str | None:
    try:
        size = int(raw)
    except (TypeError, ValueError):
        return None
    if size == 0:
        return "0 B"

    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _run_command(args: Sequence[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            tuple(args),
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        return None


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _read_server_config() -> ServerConfig:
    config = default_server_config()
    if not _path_exists(ENV_PATH):
        return config

    values: dict[str, str] = {}
    try:
        for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
    except OSError:
        return config

    host = values.get("VAS_SERVER_HOST", config.host)
    try:
        port = int(values.get("VAS_SERVER_PORT", str(config.port)))
    except ValueError:
        port = config.port
    return ServerConfig(host=host, port=port)


def _first_output_line(output: str) -> str | None:
    stripped_output = output.strip()
    return stripped_output.splitlines()[0] if stripped_output else None


def _read_gdm_daemon_key(content: str, key: str) -> str | None:
    in_daemon = False
    result: str | None = None
    normalized_key = key.lower()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_daemon = line[1:-1].strip().lower() == "daemon"
            continue
        if not in_daemon or "=" not in line:
            continue
        found_key, value = line.split("=", 1)
        if found_key.strip().lower() == normalized_key:
            result = value.strip()
    return result


def _read_loginctl_session_type() -> str | None:
    session_id = os.environ.get("XDG_SESSION_ID", "").strip()
    if session_id:
        completed = _run_command(("loginctl", "show-session", session_id, "-p", "Type", "--value"))
        if completed is not None and completed.returncode == 0:
            result = _first_output_line(completed.stdout)
            if result:
                return result

    # Fallback: scan all sessions (ใช้เมื่อรัน sudo และ XDG_SESSION_ID ถูกลบออกจาก env)
    return _scan_loginctl_sessions()


def _scan_loginctl_sessions() -> str | None:
    """ค้นหา session type จาก loginctl list-sessions โดยไม่พึ่ง XDG_SESSION_ID"""
    completed = _run_command(("loginctl", "list-sessions", "--no-legend"))
    if completed is None or completed.returncode != 0:
        return None

    for line in completed.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        session_id = parts[0]
        type_result = _run_command(("loginctl", "show-session", session_id, "-p", "Type", "--value"))
        if type_result is None or type_result.returncode != 0:
            continue
        session_type = _first_output_line(type_result.stdout)
        if session_type in ("x11", "wayland", "mir"):
            return session_type

    return None


def find_x11_session_owner() -> "tuple[str, str] | None":
    """หา (username, display) ของ desktop user ที่ login หน้าจอเครื่องจริงผ่าน loginctl (live, ไม่ cache)

    ใช้แทนการเดา DISPLAY=":0" คงที่ หรือพึ่ง SUDO_USER/HOME ของ process VAS server เอง —
    ค่าพวกนั้นผิดพลาดได้เวลา VAS server รันเป็น systemd service (root, ไม่มี SUDO_USER ใน env,
    HOME ที่ persist ไว้ใน env file ตอน install อาจไม่ตรง user จริงเวลา service auto-start
    หลัง reboot)

    ใช้ "Seat" เป็นสัญญาณหลักในการแยก session — session ที่มี Seat (เช่น seat0) คือ session
    ที่ login อยู่หน้าจอ/คีย์บอร์ดเครื่องจริง ส่วน session ที่ไม่มี Seat (Seat ว่าง) คือ
    remote session (SSH pts/N) ซึ่งไม่ใช่ desktop user ที่เราต้องการเลย — เดิมใช้ Type=x11
    เป็นตัวกรองหลักแต่พบว่า kiosk session ที่ start X ผ่าน startx/xinit ตรงๆ (ไม่ผ่าน display
    manager อย่าง gdm/lightdm) มักไม่ถูก logind ติด Type=x11 ให้ ทำให้หา session ไม่เจอเลย
    แล้ว fallback ไปเจอ SSH session ของ sysadmin แทน (bug จริงที่เจอในหน้างาน)
    """
    completed = _run_command(("loginctl", "list-sessions", "--no-legend"))
    if completed is None or completed.returncode != 0:
        return None

    candidates: "list[tuple[str, str]]" = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        session_id = parts[0]
        props = _read_loginctl_session_props(session_id, ("Type", "Class", "Name", "Seat", "Display"))
        name = props.get("Name")
        if not name or name == "root":
            continue
        if not props.get("Seat"):
            # ไม่มี seat = remote/pts session (เช่น SSH ของ sysadmin) ไม่ใช่ user หน้าจอเครื่องจริง
            continue
        display = props.get("Display") or ":0"
        if props.get("Type") == "x11" and props.get("Class") == "user":
            return (name, display)  # ชัวร์สุด: x11 + user class + มี seat จริง
        candidates.append((name, display))

    return candidates[0] if candidates else None


def _read_loginctl_session_props(session_id: str, keys: "tuple[str, ...]") -> "dict[str, str]":
    """อ่านหลาย property จาก `loginctl show-session` พร้อมกันแบบ order-independent

    ห้ามใช้ --value กับหลาย -p พร้อมกัน — ค่าที่ได้เรียงตาม internal property order ของ
    systemd เอง ไม่ใช่ตามลำดับ -p ที่ระบุใน command line (เจอ bug จริงในหน้างาน: request
    ("Type","Class","Name","Seat","Display") แต่ output กลับมาเป็นลำดับ Name/Seat/Type/Class
    ทำให้ mapping ผิดค่าทั้งหมด) — ใช้ format ปกติ `Key=Value` (ไม่ใส่ --value) แทน แล้ว parse
    ด้วยชื่อ key ตรงๆ ถึงจะ map ค่าได้ถูกต้องไม่ว่า systemd จะเรียงลำดับยังไง
    """
    args: list[str] = ["loginctl", "show-session", session_id]
    for key in keys:
        args += ["-p", key]
    completed = _run_command(tuple(args))
    if completed is None or completed.returncode != 0:
        return {}
    result: "dict[str, str]" = {}
    for line in completed.stdout.splitlines():
        if "=" not in line:
            continue
        key, _sep, value = line.partition("=")
        key = key.strip()
        if key in keys:
            result[key] = value.strip()
    return result


def _print_display_session_status(status: DisplaySessionStatus) -> None:
    print("[Session]")
    marker = "OK" if status.is_x11 else "WARN"
    detail = f"{status.session_type} ({status.source})"
    print(f"{marker:7} {'Display':10} {detail}")


def _print_gdm_wayland_status(status: GdmWaylandStatus) -> None:
    print("[GDM Wayland]")
    config_path = status.path.as_posix()
    if status.disabled:
        marker = "OK"
        detail = f"disabled (WaylandEnable=false in {config_path})"
    elif status.exists and not status.readable:
        marker = "WARN"
        detail = f"unable to read {config_path}"
    elif status.value is None:
        marker = "WARN"
        detail = f"enabled by default (no WaylandEnable=false in {config_path})"
    else:
        marker = "WARN"
        detail = f"enabled (WaylandEnable={status.value} in {config_path})"
    print(f"{marker:7} {'GDM':10} {detail}")


def _print_tool_status(status: ToolStatus) -> None:
    marker = "OK" if status.installed else "MISSING"
    detail = status.version if status.version is not None else "not installed"
    print(f"{marker:7} {status.name:10} {detail}")


def _print_xorg_touchscreen_config_status(status: XorgTouchscreenConfigStatus) -> None:
    print("[Touchscreen]")
    config_path = status.path.as_posix()
    if status.has_signature:
        marker = "OK"
        detail = f"configured ({config_path})"
    elif status.exists:
        marker = "WARN"
        detail = f"file exists but signature missing ({config_path})"
    else:
        marker = "WARN"
        detail = f"not configured ({config_path})"
    print(f"{marker:7} {'Xorg':10} {detail}")


def _print_xorg_display_rotate_config_status(status: XorgDisplayRotateConfigStatus) -> None:
    print("[Display Rotate Xorg]")
    config_path = status.path.as_posix()
    if status.has_signature:
        marker = "OK"
        detail = f"configured ({config_path})"
    elif status.exists:
        marker = "WARN"
        detail = f"file exists but signature missing ({config_path})"
    else:
        marker = "WARN"
        detail = f"not configured ({config_path})"
    print(f"{marker:7} {'Xorg':10} {detail}")


def _print_display_session_config_status(status: DisplaySessionConfigStatus) -> None:
    print("[Display Config]")
    config_path = status.path.as_posix()
    if status.has_signature:
        marker = "OK"
        detail = f"configured ({config_path})"
    elif status.exists:
        marker = "WARN"
        detail = f"file exists but signature missing ({config_path})"
    else:
        marker = "WARN"
        detail = f"not configured ({config_path})"
    print(f"{marker:7} {'Session':10} {detail}")


def _print_display_session_script_status(status: DisplaySessionScriptStatus) -> None:
    script_path = status.path.as_posix()
    if status.has_signature and status.executable:
        marker = "OK"
        detail = f"configured ({script_path})"
    elif status.exists and status.has_signature:
        marker = "WARN"
        detail = f"script is not executable ({script_path})"
    elif status.exists:
        marker = "WARN"
        detail = f"file exists but signature missing ({script_path})"
    else:
        marker = "WARN"
        detail = f"not configured ({script_path})"
    print(f"{marker:7} {'Script':10} {detail}")


def _print_vpn_status(status: VpnStatus) -> None:
    print("[VPN]")
    if status.wg_installed:
        version = status.wg_version or "installed"
        print(f"{'OK':7} {'WireGuard':10} {version}")
    else:
        print(f"{'MISSING':7} {'WireGuard':10} not installed")

    _print_path_status("App Config", status.app_config_exists, status.app_config_path, "saved", "not saved")
    _print_path_status("Active", status.active_config_exists, status.active_config_path, "applied", "not applied")
    _print_path_status("History", status.history_exists, status.history_dir, "available", "not found")

    enabled_marker = "OK" if status.service_enabled == "enabled" else "WARN"
    active_marker = "OK" if status.service_active == "active" else "WARN"
    interface_marker = "OK" if status.interface_exists else "WARN"
    print(f"{enabled_marker:7} {'Service':10} {service_name(status.interface_name)} enabled={status.service_enabled}")
    print(f"{active_marker:7} {'Connection':10} service {status.service_active}")
    print(f"{interface_marker:7} {'Interface':10} {status.interface_name} {'visible' if status.interface_exists else 'not visible'}")

    if status.handshake_peers is None:
        print(f"{'WARN':7} {'Handshake':10} unable to inspect peers")
    elif status.handshake_peers > 0:
        print(f"{'OK':7} {'Handshake':10} latest handshake from {status.handshake_peers} peer(s)")
    else:
        print(f"{'WARN':7} {'Handshake':10} no peer handshake detected")


def _print_web_server_status(status: WebServerStatus) -> None:
    print("[Web Server]")
    enabled_marker = "OK" if status.service_enabled == "enabled" else "WARN"
    active_marker = "OK" if status.service_active == "active" else "WARN"
    print(f"{enabled_marker:7} {'Service':10} {SERVICE_UNIT} enabled={status.service_enabled}")
    print(f"{active_marker:7} {'Connection':10} service {status.service_active}")
    print(f"{'OK':7} {'Address':10} {status.url}")


def _print_openssh_status(status: OpenSshStatus) -> None:
    installed_marker = "OK" if status.installed else "MISSING"
    version = status.version or "not installed"
    print(f"{installed_marker:7} {'OpenSSH':10} {version}")
    enabled_marker = "OK" if status.service_enabled == "enabled" else "WARN"
    active_marker = "OK" if status.service_active == "active" else "WARN"
    print(f"{enabled_marker:7} {'Service':10} ssh enabled={status.service_enabled}")
    print(f"{active_marker:7} {'Connection':10} service {status.service_active}")


def _print_remote_access_status(status: RemoteAccessStatus) -> None:
    print("[Remote]")
    installed_marker = "OK" if status.anydesk_installed else "MISSING"
    version = status.anydesk_version or "not installed"
    print(f"{installed_marker:7} {'AnyDesk':10} {version}")

    id_marker = "OK" if status.anydesk_id else "WARN"
    anydesk_id = status.anydesk_id or "not available"
    print(f"{id_marker:7} {'ID':10} {anydesk_id}")

    status_marker = "OK" if status.anydesk_status.lower() == "online" else "WARN"
    print(f"{status_marker:7} {'Status':10} {status.anydesk_status}")

    enabled_marker = "OK" if status.service_enabled == "enabled" else "WARN"
    active_marker = "OK" if status.service_active == "active" else "WARN"
    print(f"{enabled_marker:7} {'Service':10} anydesk enabled={status.service_enabled}")
    print(f"{active_marker:7} {'Connection':10} service {status.service_active}")


def _print_path_status(label: str, exists: bool, path: Path, ok_text: str, missing_text: str) -> None:
    marker = "OK" if exists else "WARN"
    status_text = ok_text if exists else missing_text
    print(f"{marker:7} {label:10} {status_text} ({path.as_posix()})")


# ---------------------------------------------------------------------------
# QR Reader status
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QrReaderStatus:
    udev_rule_path: Path
    udev_rule_exists: bool
    udev_rule_has_signature: bool
    config_path: Path
    config_exists: bool
    detected_devices: tuple[str, ...]   # hidraw paths ที่พบ
    active_device: str | None           # device ที่ thread กำลังอ่านอยู่
    reader_running: bool
    last_scan: str | None               # in-memory ค่าล่าสุด


def collect_qr_reader_status() -> QrReaderStatus:
    """
    Collect QR reader hardware + software status

    Import qr_reader lazily เพื่อหลีกเลี่ยง import error เมื่อยังไม่ได้ install
    ถ้า ImportError -> return stub ที่ fields ทั้งหมดเป็น False/None/empty
    """
    from core.config import QR_UDEV_RULE_PATH, QR_UDEV_SIGNATURE, qr_config_path

    udev_path = QR_UDEV_RULE_PATH
    udev_exists = _path_exists(udev_path)
    udev_has_sig = False
    if udev_exists:
        try:
            udev_has_sig = QR_UDEV_SIGNATURE in udev_path.read_text(encoding="utf-8")
        except OSError:
            pass

    cfg_path = qr_config_path()
    cfg_exists = _path_exists(cfg_path)

    try:
        from features.qr.reader import find_zkteco_hidraw_devices, get_reader
        detected = tuple(find_zkteco_hidraw_devices())
        reader = get_reader()
        reader_running = reader is not None and reader.is_alive()
        active_device = reader.device_path if reader_running else None
        last_scan = reader.last_scan if reader_running else None
    except Exception:
        detected = ()
        reader_running = False
        active_device = None
        last_scan = None

    return QrReaderStatus(
        udev_rule_path=udev_path,
        udev_rule_exists=udev_exists,
        udev_rule_has_signature=udev_has_sig,
        config_path=cfg_path,
        config_exists=cfg_exists,
        detected_devices=detected,
        active_device=active_device,
        reader_running=reader_running,
        last_scan=last_scan,
    )


def _print_qr_reader_status(status: QrReaderStatus) -> None:
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
