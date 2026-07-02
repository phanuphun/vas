"""
VAS — OpenSSH server management

Effective config มาจาก `sshd -T` (ค่าที่ sshd ใช้งานจริงตอนนี้ รวม default ทั้งหมด)
การบันทึกค่าจากหน้าเว็บจะเขียนเป็น drop-in override ที่ /etc/ssh/sshd_config.d/99-vas.conf
แทนการแก้ไข /etc/ssh/sshd_config หลักตรงๆ — ปลอดภัยกว่า (revert ได้ด้วยการลบไฟล์เดียว),
ไม่ชนกับ config เดิมที่มีอยู่ก่อน รองรับบน Ubuntu 22.04+ ที่ sshd_config หลักมี
`Include /etc/ssh/sshd_config.d/*.conf` อยู่แล้วโดย default

ทุกครั้งที่บันทึก: เขียนไฟล์ -> validate ด้วย `sshd -t` -> ถ้าไม่ผ่าน rollback ทันที ->
ถ้าผ่าน `systemctl reload ssh` (reload ไม่ตัด session ที่เชื่อมต่ออยู่ ต่างจาก restart)

ไฟล์นี้ยังมี host key fingerprints, authorized_keys per user, สถานะ fail2ban (read-only),
และ recent SSH login attempts (อ่านจาก journalctl)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from core.runner import CommandResult, CommandRunner
from system.utils import dev_fake_installed

try:
    import pwd as pwd_module
except ImportError:  # pragma: no cover - Windows dev hosts
    pwd_module = None  # type: ignore[assignment]

PWD_MODULE = cast("Any | None", pwd_module)

SERVICE_NAME = "ssh"
VALID_SERVICE_ACTIONS = ("start", "stop", "restart", "reload", "enable", "disable")

SSHD_CONFIG_PATH = Path("/etc/ssh/sshd_config")
SSHD_DROPIN_DIR = Path("/etc/ssh/sshd_config.d")
SSHD_DROPIN_PATH = SSHD_DROPIN_DIR / "99-vas.conf"
SSHD_DROPIN_HEADER = (
    "# Managed by VAS — จัดการผ่านหน้า OpenSSH ในเว็บ UI\n"
    "# แก้ไขไฟล์นี้ตรงๆ ได้ แต่จะถูกเขียนทับเมื่อบันทึกผ่านหน้าเว็บอีกครั้ง"
)

_ALLOWED_PERMIT_ROOT_LOGIN = ("yes", "no", "prohibit-password", "forced-commands-only")
_ALLOWED_LOG_LEVELS = ("QUIET", "FATAL", "ERROR", "INFO", "VERBOSE", "DEBUG", "DEBUG1", "DEBUG2", "DEBUG3")
_SKIP_SHELLS = ("/usr/sbin/nologin", "/sbin/nologin", "/bin/false", "/usr/bin/false")


# ─────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SshdConfigValues:
    port: int
    listen_address: str
    permit_root_login: str
    password_authentication: bool
    pubkey_authentication: bool
    permit_empty_passwords: bool
    kbd_interactive_authentication: bool
    max_auth_tries: int
    login_grace_time: int
    authorized_keys_file: str
    allow_users: str
    allow_groups: str
    deny_users: str
    deny_groups: str
    allow_tcp_forwarding: bool
    x11_forwarding: bool
    gateway_ports: bool
    client_alive_interval: int
    client_alive_count_max: int
    max_sessions: int
    max_startups: str
    strict_modes: bool
    use_pam: bool
    log_level: str
    banner: str  # เนื้อหาข้อความ banner จริง — ระบบจัดการเขียนลงไฟล์ + ตั้ง Banner path เอง


@dataclass(frozen=True)
class HostKeyInfo:
    key_type: str
    fingerprint: str
    bits: int
    path: str


@dataclass(frozen=True)
class AuthorizedKeyEntry:
    user: str
    algo: str
    fingerprint: str
    comment: str
    added: str  # mtime ของไฟล์ authorized_keys (ไม่ใช่วันที่เพิ่ม key นี้เจาะจง)


@dataclass(frozen=True)
class Fail2banStatus:
    installed: bool
    service_active: bool
    jail_active: bool
    banned_count: int


@dataclass(frozen=True)
class SshLoginAttempt:
    user: str
    ip: str
    time: str
    result: str  # "success" | "failed"


class SshdConfigError(ValueError):
    """ค่า config ที่ผู้ใช้กรอกไม่ผ่าน validation (เช็คก่อนเขียนไฟล์เสมอ)"""


# ─────────────────────────────────────────────────────────────────────────
# Helpers — home dir / paths
# ─────────────────────────────────────────────────────────────────────────

def default_store_dir() -> Path:
    home = _sudo_user_home() or Path.home()
    config_home = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config_home) if config_home else home / ".config"
    return root / "vending-auto-setup" / "openssh"


def default_banner_path() -> Path:
    return Path("/etc/ssh/vas-banner.txt")


def _sudo_user_home() -> Path | None:
    sudo_user = os.environ.get("SUDO_USER")
    if not sudo_user or sudo_user == "root" or PWD_MODULE is None:
        return None
    try:
        return Path(PWD_MODULE.getpwnam(sudo_user).pw_dir)
    except KeyError:
        return None


# ─────────────────────────────────────────────────────────────────────────
# Effective config — `sshd -T`
# ─────────────────────────────────────────────────────────────────────────

def _b(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("yes", "true", "1", "on")


def _i(value: str | None, default: int) -> int:
    if value is None:
        return default
    stripped = value.strip()
    if stripped.isdigit():
        return int(stripped)
    match = re.match(r"^(\d+)", stripped)
    return int(match.group(1)) if match else default


def _parse_sshd_dump(output: str) -> dict[str, str]:
    """แปลง output ของ `sshd -T` (directive value ต่อบรรทัด) เป็น dict คีย์ lowercase
    — directive ที่ปรากฏซ้ำหลายบรรทัด (เช่น listenaddress) จะถูก join ด้วย space"""
    values: dict[str, list[str]] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or " " not in line:
            continue
        key, _, rest = line.partition(" ")
        values.setdefault(key.lower(), []).append(rest.strip())
    return {key: " ".join(parts) for key, parts in values.items()}


def _fake_config_values() -> SshdConfigValues:
    return SshdConfigValues(
        port=22,
        listen_address="0.0.0.0",
        permit_root_login="prohibit-password",
        password_authentication=False,
        pubkey_authentication=True,
        permit_empty_passwords=False,
        kbd_interactive_authentication=False,
        max_auth_tries=3,
        login_grace_time=30,
        authorized_keys_file=".ssh/authorized_keys",
        allow_users="deploy admin",
        allow_groups="",
        deny_users="",
        deny_groups="",
        allow_tcp_forwarding=False,
        x11_forwarding=False,
        gateway_ports=False,
        client_alive_interval=300,
        client_alive_count_max=2,
        max_sessions=10,
        max_startups="10:30:60",
        strict_modes=True,
        use_pam=True,
        log_level="VERBOSE",
        banner="",
    )


def collect_config(runner: CommandRunner) -> SshdConfigValues:
    if dev_fake_installed():
        return _fake_config_values()

    result = runner.run(["sshd", "-T"], check=False)
    if result.returncode != 0:
        # sshd -T ล้มเหลว (เช่น config พังจากการแก้ไขนอกระบบ) — คืนค่า default ที่ปลอดภัยไว้ก่อน
        # ไม่ throw เพราะหน้า status ยังต้องแสดงผลได้แม้ config จะพัง
        return _fake_config_values()

    values = _parse_sshd_dump(result.stdout)
    banner_text = ""
    banner_path = values.get("banner", "none")
    if banner_path and banner_path.lower() != "none":
        try:
            banner_text = Path(banner_path).read_text(encoding="utf-8")
        except OSError:
            banner_text = ""

    listen_raw = values.get("listenaddress", "0.0.0.0:22")
    listen_address = listen_raw.split()[0].rsplit(":", 1)[0] if listen_raw else "0.0.0.0"

    return SshdConfigValues(
        port=_i(values.get("port"), 22),
        listen_address=listen_address or "0.0.0.0",
        permit_root_login=values.get("permitrootlogin", "prohibit-password"),
        password_authentication=_b(values.get("passwordauthentication"), True),
        pubkey_authentication=_b(values.get("pubkeyauthentication"), True),
        permit_empty_passwords=_b(values.get("permitemptypasswords"), False),
        kbd_interactive_authentication=_b(
            values.get("kbdinteractiveauthentication", values.get("challengeresponseauthentication")), False
        ),
        max_auth_tries=_i(values.get("maxauthtries"), 6),
        login_grace_time=_i(values.get("logingracetime"), 120),
        authorized_keys_file=values.get("authorizedkeysfile", ".ssh/authorized_keys"),
        allow_users=values.get("allowusers", ""),
        allow_groups=values.get("allowgroups", ""),
        deny_users=values.get("denyusers", ""),
        deny_groups=values.get("denygroups", ""),
        allow_tcp_forwarding=values.get("allowtcpforwarding", "yes").lower() != "no",
        x11_forwarding=_b(values.get("x11forwarding"), False),
        gateway_ports=values.get("gatewayports", "no").lower() != "no",
        client_alive_interval=_i(values.get("clientaliveinterval"), 0),
        client_alive_count_max=_i(values.get("clientalivecountmax"), 3),
        max_sessions=_i(values.get("maxsessions"), 10),
        max_startups=values.get("maxstartups", "10:30:100"),
        strict_modes=_b(values.get("strictmodes"), True),
        use_pam=_b(values.get("usepam"), True),
        log_level=values.get("loglevel", "INFO").upper(),
        banner=banner_text,
    )


# ─────────────────────────────────────────────────────────────────────────
# Save — validate ก่อนเขียน, sshd -t ก่อน reload, rollback ถ้าพัง
# ─────────────────────────────────────────────────────────────────────────

def _y(value: bool) -> str:
    return "yes" if value else "no"


def _validate_values(values: SshdConfigValues) -> list[str]:
    errors: list[str] = []
    if not (1 <= values.port <= 65535):
        errors.append("Port ต้องอยู่ระหว่าง 1-65535")
    if values.permit_root_login not in _ALLOWED_PERMIT_ROOT_LOGIN:
        errors.append(f"PermitRootLogin ต้องเป็นหนึ่งใน {', '.join(_ALLOWED_PERMIT_ROOT_LOGIN)}")
    if values.log_level not in _ALLOWED_LOG_LEVELS:
        errors.append(f"LogLevel ต้องเป็นหนึ่งใน {', '.join(_ALLOWED_LOG_LEVELS)}")
    if values.max_auth_tries < 1:
        errors.append("MaxAuthTries ต้องมากกว่า 0")
    if values.login_grace_time < 0:
        errors.append("LoginGraceTime ต้องไม่ติดลบ")
    if values.client_alive_interval < 0 or values.client_alive_count_max < 0:
        errors.append("ClientAliveInterval / ClientAliveCountMax ต้องไม่ติดลบ")
    if values.max_sessions < 1:
        errors.append("MaxSessions ต้องมากกว่า 0")
    for label, raw in (
        ("AllowUsers", values.allow_users),
        ("AllowGroups", values.allow_groups),
        ("DenyUsers", values.deny_users),
        ("DenyGroups", values.deny_groups),
    ):
        if raw and not re.fullmatch(r"[A-Za-z0-9_.,\-*?@ ]*", raw):
            errors.append(f"{label} มีตัวอักษรที่ไม่รองรับ")
    if not re.fullmatch(r"\d+(:\d+){0,2}", values.max_startups.strip()):
        errors.append("MaxStartups ต้องเป็นรูปแบบ start[:rate[:full]] เช่น 10:30:60")
    return errors


def render_dropin(values: SshdConfigValues) -> str:
    lines = [SSHD_DROPIN_HEADER, ""]
    lines.append(f"Port {values.port}")
    if values.listen_address:
        lines.append(f"ListenAddress {values.listen_address}")
    lines.append(f"PermitRootLogin {values.permit_root_login}")
    lines.append(f"PasswordAuthentication {_y(values.password_authentication)}")
    lines.append(f"PubkeyAuthentication {_y(values.pubkey_authentication)}")
    lines.append(f"PermitEmptyPasswords {_y(values.permit_empty_passwords)}")
    lines.append(f"KbdInteractiveAuthentication {_y(values.kbd_interactive_authentication)}")
    lines.append(f"MaxAuthTries {values.max_auth_tries}")
    lines.append(f"LoginGraceTime {values.login_grace_time}")
    if values.authorized_keys_file.strip():
        lines.append(f"AuthorizedKeysFile {values.authorized_keys_file.strip()}")
    if values.allow_users.strip():
        lines.append(f"AllowUsers {values.allow_users.strip()}")
    if values.allow_groups.strip():
        lines.append(f"AllowGroups {values.allow_groups.strip()}")
    if values.deny_users.strip():
        lines.append(f"DenyUsers {values.deny_users.strip()}")
    if values.deny_groups.strip():
        lines.append(f"DenyGroups {values.deny_groups.strip()}")
    lines.append(f"AllowTcpForwarding {_y(values.allow_tcp_forwarding)}")
    lines.append(f"X11Forwarding {_y(values.x11_forwarding)}")
    lines.append(f"GatewayPorts {_y(values.gateway_ports)}")
    lines.append(f"ClientAliveInterval {values.client_alive_interval}")
    lines.append(f"ClientAliveCountMax {values.client_alive_count_max}")
    lines.append(f"MaxSessions {values.max_sessions}")
    lines.append(f"MaxStartups {values.max_startups.strip()}")
    lines.append(f"StrictModes {_y(values.strict_modes)}")
    lines.append(f"UsePAM {_y(values.use_pam)}")
    lines.append(f"LogLevel {values.log_level}")
    lines.append(f"Banner {default_banner_path().as_posix()}" if values.banner.strip() else "Banner none")
    return "\n".join(lines) + "\n"


def save_config(runner: CommandRunner, values: SshdConfigValues) -> tuple[bool, str]:
    errors = _validate_values(values)
    if errors:
        return False, " / ".join(errors)

    if dev_fake_installed():
        return True, "บันทึกและ reload OpenSSH เรียบร้อย (dev-mode — จำลองผล ไม่ได้เขียนไฟล์จริงหรือ reload service)"

    content = render_dropin(values)
    previous_content: str | None = None
    if SSHD_DROPIN_PATH.exists():
        try:
            previous_content = SSHD_DROPIN_PATH.read_text(encoding="utf-8")
        except OSError:
            previous_content = None

    try:
        # 1) banner file — เขียนเนื้อหาจริง หรือลบถ้าเว้นว่าง
        if values.banner.strip():
            default_banner_path().write_text(values.banner, encoding="utf-8")
        elif default_banner_path().exists():
            default_banner_path().unlink()

        # 2) backup ไฟล์ drop-in เดิม (ถ้ามี) ก่อนเขียนทับ — กู้คืนได้จาก store_dir/backups
        if previous_content is not None:
            backup_dir = default_store_dir() / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            (backup_dir / f"{stamp}-99-vas.conf").write_text(previous_content, encoding="utf-8")

        # 3) เขียนไฟล์ config ใหม่ทับ path จริง
        SSHD_DROPIN_DIR.mkdir(parents=True, exist_ok=True)
        SSHD_DROPIN_PATH.write_text(content, encoding="utf-8")
        SSHD_DROPIN_PATH.chmod(0o644)
    except OSError as error:
        return False, f"เขียนไฟล์ config ไม่สำเร็จ: {error}"

    # 4) validate ด้วย sshd -t ก่อน apply จริงเสมอ — ถ้าไม่ผ่าน rollback ทันที
    #    (ไฟล์ที่เขียนผิดจะไม่ถูกใช้งานจริงจนกว่าจะ reload — rollback ที่นี่จึงปลอดภัย
    #    ไม่กระทบ session ที่เชื่อมต่ออยู่)
    check = runner.run(["sshd", "-t"], check=False)
    if check.returncode != 0:
        try:
            if previous_content is not None:
                SSHD_DROPIN_PATH.write_text(previous_content, encoding="utf-8")
            else:
                SSHD_DROPIN_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        detail = (check.stderr or check.stdout or "").strip() or "sshd -t validate ไม่ผ่าน"
        return False, f"Config ไม่ถูกต้อง — ยกเลิกการบันทึก: {detail}"

    # 5) reload (ไม่ตัด session ที่เชื่อมต่ออยู่ ต่างจาก restart)
    reload_result = runner.run(["systemctl", "reload", SERVICE_NAME], check=False)
    if reload_result.returncode != 0:
        detail = (reload_result.stderr or reload_result.stdout or "").strip() or "reload ไม่สำเร็จ"
        return False, f"บันทึก config แล้วแต่ reload service ไม่สำเร็จ: {detail} (การตั้งค่าที่เขียนไว้ยังอยู่)"

    return True, "บันทึกและ reload OpenSSH เรียบร้อย"


# ─────────────────────────────────────────────────────────────────────────
# Service control
# ─────────────────────────────────────────────────────────────────────────

def service_action(runner: CommandRunner, action: str) -> CommandResult:
    """รัน `systemctl <action> ssh` — action ต้องเป็นหนึ่งใน VALID_SERVICE_ACTIONS"""
    if action not in VALID_SERVICE_ACTIONS:
        raise ValueError(f"Unknown OpenSSH service action: {action}")
    if dev_fake_installed():
        return CommandResult(args=("systemctl", action, SERVICE_NAME), returncode=0, stdout="", stderr="")
    return runner.run(["systemctl", action, SERVICE_NAME], check=False)


# ─────────────────────────────────────────────────────────────────────────
# Host keys
# ─────────────────────────────────────────────────────────────────────────

_FPR_RE = re.compile(r"^(\d+)\s+(SHA256:\S+)\s+(.*?)\s+\(([A-Za-z0-9_-]+)\)\s*$")


def _parse_keygen_fingerprint_line(line: str) -> tuple[int, str, str, str] | None:
    match = _FPR_RE.match(line)
    if not match:
        return None
    bits, fingerprint, comment, key_type = match.groups()
    return int(bits), fingerprint, comment, key_type


def collect_host_keys(runner: CommandRunner) -> tuple[HostKeyInfo, ...]:
    if dev_fake_installed():
        return (
            HostKeyInfo("ED25519", "SHA256:aB3xQvL9k2fN6wG8pR1sT4uY7zC0mD5eH2jK9lM3nO6", 256, "/etc/ssh/ssh_host_ed25519_key.pub"),
            HostKeyInfo("RSA", "SHA256:vN7mK2pQ8rS4tU6wX1yZ3aB5cD9eF0gH2iJ4kL6mN8o", 3072, "/etc/ssh/ssh_host_rsa_key.pub"),
            HostKeyInfo("ECDSA", "SHA256:hG5fE3dC1bA9zY7xW5vU3tS1rQ9pO7nM5lK3jI1hG9f", 256, "/etc/ssh/ssh_host_ecdsa_key.pub"),
        )
    keys: list[HostKeyInfo] = []
    for pub_path in sorted(Path("/etc/ssh").glob("ssh_host_*_key.pub")):
        result = runner.run(["ssh-keygen", "-lf", str(pub_path)], check=False)
        if result.returncode != 0:
            continue
        parsed = _parse_keygen_fingerprint_line(result.stdout.strip())
        if parsed is None:
            continue
        bits, fingerprint, _comment, key_type = parsed
        keys.append(HostKeyInfo(key_type=key_type, fingerprint=fingerprint, bits=bits, path=str(pub_path)))
    return tuple(keys)


# ─────────────────────────────────────────────────────────────────────────
# Authorized keys per user
# ─────────────────────────────────────────────────────────────────────────

def _list_ssh_capable_users() -> list[Any]:
    """user ที่ login ผ่าน ssh ได้จริง — ข้าม system user (nologin shell / uid ต่ำกว่า 1000 ยกเว้น root)"""
    if PWD_MODULE is None:
        return []
    users = []
    for entry in PWD_MODULE.getpwall():
        if entry.pw_shell in _SKIP_SHELLS:
            continue
        if entry.pw_uid != 0 and entry.pw_uid < 1000:
            continue
        if entry.pw_uid >= 65534:
            continue
        users.append(entry)
    return users


def list_manageable_usernames() -> tuple[str, ...]:
    if dev_fake_installed():
        return ("root", "deploy", "admin")
    return tuple(entry.pw_name for entry in _list_ssh_capable_users())


def _fingerprint_via_stdin(key_line: str) -> str | None:
    try:
        result = subprocess.run(
            ["ssh-keygen", "-lf", "-"], input=key_line, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    parsed = _parse_keygen_fingerprint_line(result.stdout.strip())
    return parsed[1] if parsed else None


def _parse_authorized_key_line(line: str) -> tuple[str, str, str] | None:
    """คืน (algo, fingerprint, comment) — คืน None ถ้า parse ไม่ได้ (บรรทัดผิดรูปแบบ)"""
    parts = line.split()
    if len(parts) < 2:
        return None
    key_start = 0
    for index, part in enumerate(parts):
        if part.startswith(("ssh-", "ecdsa-", "sk-")):
            key_start = index
            break
    key_parts = parts[key_start:]
    if len(key_parts) < 2:
        return None
    algo = key_parts[0].replace("ssh-", "")
    comment = " ".join(key_parts[2:]) if len(key_parts) > 2 else ""
    key_line = " ".join(key_parts[:2])
    fingerprint = _fingerprint_via_stdin(key_line)
    if fingerprint is None:
        return None
    return algo, fingerprint, comment


def collect_authorized_keys(runner: CommandRunner) -> tuple[AuthorizedKeyEntry, ...]:
    if dev_fake_installed():
        return (
            AuthorizedKeyEntry("deploy", "ed25519", "SHA256:pL8mN2oQ6rS0tU4vW8xY2zA6bC0dE4fG8hI2jK6lM0n", "deploy@ci-runner", "2026-05-14"),
            AuthorizedKeyEntry("admin", "rsa", "SHA256:qR9sT3uV7wX1yZ5aB9cD3eF7gH1iJ5kL9mN3oP7qR1s", "phanuphun@laptop", "2026-03-02"),
        )
    entries: list[AuthorizedKeyEntry] = []
    for pw in _list_ssh_capable_users():
        ak_path = Path(pw.pw_dir) / ".ssh" / "authorized_keys"
        if not ak_path.exists():
            continue
        try:
            mtime = datetime.fromtimestamp(ak_path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
        except OSError:
            mtime = "-"
        try:
            lines = ak_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parsed = _parse_authorized_key_line(stripped)
            if parsed is None:
                continue
            algo, fingerprint, comment = parsed
            entries.append(AuthorizedKeyEntry(user=pw.pw_name, algo=algo, fingerprint=fingerprint, comment=comment, added=mtime))
    return tuple(entries)


def _chown_path(path: Path, uid: int, gid: int) -> None:
    if not hasattr(os, "chown"):
        return
    try:
        os.chown(str(path), uid, gid)
    except OSError:
        pass


def add_authorized_key(user: str, key_line: str) -> tuple[bool, str]:
    key_line = key_line.strip()
    if not key_line:
        return False, "กรุณากรอก public key"
    if dev_fake_installed():
        return True, "เพิ่ม key เรียบร้อย (dev-mode — จำลองผล ไม่ได้เขียนไฟล์จริง)"
    if PWD_MODULE is None:
        return False, "ระบบนี้ไม่รองรับการจัดการ user (ไม่ใช่ Linux)"
    try:
        pw = PWD_MODULE.getpwnam(user)
    except KeyError:
        return False, f"ไม่พบ user: {user}"

    fingerprint = _fingerprint_via_stdin(key_line)
    if fingerprint is None:
        return False, "รูปแบบ public key ไม่ถูกต้อง"

    ssh_dir = Path(pw.pw_dir) / ".ssh"
    ak_path = ssh_dir / "authorized_keys"
    try:
        ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        existing = ak_path.read_text(encoding="utf-8") if ak_path.exists() else ""
        if fingerprint in existing:
            return False, "key นี้มีอยู่แล้ว"
        with ak_path.open("a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write(key_line + "\n")
        ak_path.chmod(0o600)
        _chown_path(ssh_dir, pw.pw_uid, pw.pw_gid)
        _chown_path(ak_path, pw.pw_uid, pw.pw_gid)
    except OSError as error:
        return False, f"เขียนไฟล์ authorized_keys ไม่สำเร็จ: {error}"
    return True, f"เพิ่ม key ({fingerprint}) ให้ {user} เรียบร้อย"


def revoke_authorized_key(user: str, fingerprint: str) -> tuple[bool, str]:
    if dev_fake_installed():
        return True, "เพิกถอน key เรียบร้อย (dev-mode — จำลองผล ไม่ได้แก้ไฟล์จริง)"
    if PWD_MODULE is None:
        return False, "ระบบนี้ไม่รองรับการจัดการ user (ไม่ใช่ Linux)"
    try:
        pw = PWD_MODULE.getpwnam(user)
    except KeyError:
        return False, f"ไม่พบ user: {user}"

    ak_path = Path(pw.pw_dir) / ".ssh" / "authorized_keys"
    if not ak_path.exists():
        return False, "ไม่พบไฟล์ authorized_keys"
    try:
        lines = ak_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return False, f"อ่านไฟล์ไม่สำเร็จ: {error}"

    kept: list[str] = []
    removed = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            kept.append(line)
            continue
        parsed = _parse_authorized_key_line(stripped)
        if parsed is not None and parsed[1] == fingerprint:
            removed = True
            continue
        kept.append(line)

    if not removed:
        return False, "ไม่พบ key นี้"

    try:
        ak_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        ak_path.chmod(0o600)
    except OSError as error:
        return False, f"เขียนไฟล์ไม่สำเร็จ: {error}"
    return True, "เพิกถอน key เรียบร้อย"


# ─────────────────────────────────────────────────────────────────────────
# Fail2ban (read-only — ไม่มี install/manage ในสโคปนี้)
# ─────────────────────────────────────────────────────────────────────────

def collect_fail2ban_status(runner: CommandRunner) -> Fail2banStatus:
    if dev_fake_installed():
        return Fail2banStatus(installed=True, service_active=True, jail_active=True, banned_count=3)
    if shutil.which("fail2ban-client") is None:
        return Fail2banStatus(installed=False, service_active=False, jail_active=False, banned_count=0)

    active = runner.run(["systemctl", "is-active", "fail2ban"], check=False)
    service_active = active.stdout.strip() == "active"
    jail_active = False
    banned_count = 0
    if service_active:
        status = runner.run(["fail2ban-client", "status", "sshd"], check=False)
        if status.returncode == 0:
            jail_active = True
            match = re.search(r"Currently banned:\s*(\d+)", status.stdout)
            if match:
                banned_count = int(match.group(1))
    return Fail2banStatus(installed=True, service_active=service_active, jail_active=jail_active, banned_count=banned_count)


# ─────────────────────────────────────────────────────────────────────────
# Recent login attempts (journalctl)
# ─────────────────────────────────────────────────────────────────────────

_JOURNAL_ACCEPTED_RE = re.compile(r"Accepted \S+ for (\S+) from (\S+)")
_JOURNAL_FAILED_RE = re.compile(r"Failed password for (?:invalid user )?(\S+) from (\S+)")
_JOURNAL_INVALID_RE = re.compile(r"Invalid user (\S+) from (\S+)")


def _parse_journal_line(line: str) -> SshLoginAttempt | None:
    time_part = line.split(" ", 1)[0].replace("T", " ")
    match = _JOURNAL_ACCEPTED_RE.search(line)
    if match:
        return SshLoginAttempt(user=match.group(1), ip=match.group(2), time=time_part, result="success")
    match = _JOURNAL_FAILED_RE.search(line)
    if match:
        return SshLoginAttempt(user=match.group(1), ip=match.group(2), time=time_part, result="failed")
    match = _JOURNAL_INVALID_RE.search(line)
    if match:
        return SshLoginAttempt(user=match.group(1), ip=match.group(2), time=time_part, result="failed")
    return None


def collect_recent_login_attempts(runner: CommandRunner, limit: int = 20) -> tuple[SshLoginAttempt, ...]:
    if dev_fake_installed():
        return (
            SshLoginAttempt("deploy", "10.0.4.21", "2026-07-02 08:14", "success"),
            SshLoginAttempt("root", "185.220.101.4", "2026-07-02 03:52", "failed"),
            SshLoginAttempt("admin", "10.0.4.9", "2026-07-01 21:03", "success"),
            SshLoginAttempt("test", "185.220.101.4", "2026-07-01 20:58", "failed"),
        )
    result = runner.run(["journalctl", "-u", SERVICE_NAME, "-n", "500", "--no-pager", "-o", "short-iso"], check=False)
    if result.returncode != 0:
        return ()
    attempts: list[SshLoginAttempt] = []
    for line in result.stdout.splitlines():
        parsed = _parse_journal_line(line)
        if parsed is not None:
            attempts.append(parsed)
    attempts.reverse()  # ใหม่สุดก่อน
    return tuple(attempts[:limit])
