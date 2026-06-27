from __future__ import annotations

import os
import re
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, cast

from system.clock import SystemClockPreflight
from core.runner import CommandRunner

try:
    import pwd as pwd_module
except ImportError:  # pragma: no cover - Windows development hosts
    pwd_module = None  # type: ignore[assignment]

PWD_MODULE = cast("Any | None", pwd_module)


REQUIRED_INTERFACE_KEYS = ("PrivateKey", "Address")
REQUIRED_PEER_KEYS = ("PublicKey", "AllowedIPs", "Endpoint")
SECRET_KEYS = {"PrivateKey", "PresharedKey"}
WIREGUARD_CONFIG_DIR = Path("/etc/wireguard")


@dataclass(frozen=True)
class WireGuardValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


class WireGuardManager:
    def __init__(
        self,
        runner: CommandRunner,
        store_dir: Path | None = None,
        wireguard_dir: Path = WIREGUARD_CONFIG_DIR,
    ) -> None:
        self.runner = runner
        self.store_dir = store_dir or default_store_dir()
        self.wireguard_dir = wireguard_dir

    def install(self) -> None:
        SystemClockPreflight(self.runner).ensure_reasonable_clock()
        self.runner.run(["apt-get", "update"])
        self.runner.run(["apt-get", "install", "-y", "wireguard"])

    def print_status(self, name: str) -> None:
        print("WireGuard Status")
        print()
        print("[Tools]")
        self._print_tool_status("wg")
        self._print_tool_status("wg-quick")
        print()
        print("[Config]")
        active_config = self.active_config_path(name)
        saved_config = self.saved_config_path(name)
        self._print_path_status("Active", active_config)
        self._print_path_status("Saved", saved_config)
        print()
        print("[Service]")
        service = service_name(name)
        enabled = self.runner.run(["systemctl", "is-enabled", service], check=False)
        active = self.runner.run(["systemctl", "is-active", service], check=False)
        print(f"{_service_marker(enabled.returncode):7} {'Enabled':10} {enabled.stdout.strip() or enabled.stderr.strip() or 'unknown'}")
        print(f"{_service_marker(active.returncode):7} {'Active':10} {active.stdout.strip() or active.stderr.strip() or 'unknown'}")

    def init_config(self, name: str, output: Path, force: bool = False) -> None:
        if output.exists() and not force:
            raise FileExistsError(f"Config already exists: {output}")

        content = render_template(name)
        print(f"write {output}")
        if self.runner.dry_run:
            print(mask_secrets(content))
            return
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        chmod_private(output)

    def validate_config(self, config: Path) -> WireGuardValidationResult:
        content = config.read_text(encoding="utf-8")
        result = validate_config_content(content)
        if result.valid:
            print(f"OK      Config     valid ({config})")
        else:
            print(f"ERROR   Config     invalid ({config})")
        for warning in result.warnings:
            print(f"WARN    {warning}")
        for error in result.errors:
            print(f"ERROR   {error}")
        return result

    def save(self, config: Path, name: str) -> None:
        result = self.validate_config(config)
        if not result.valid:
            raise ValueError("WireGuard config is invalid.")

        target = self.saved_config_path(name)
        print(f"write {target}")
        if self.runner.dry_run:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(config, target)
        chmod_private(target)

    def sync(self, name: str, config: Path | None = None, restart: bool = True) -> None:
        source = config or self.saved_config_path(name)
        result = self.validate_config(source)
        if not result.valid:
            raise ValueError("WireGuard config is invalid.")

        target = self.active_config_path(name)
        backup = self._snapshot_path(name, "pre-sync-backup")
        synced = self._snapshot_path(name, "sync")

        if target.exists():
            print(f"backup {target} -> {backup}")
        print(f"write {target}")
        print(f"history {synced}")

        if not self.runner.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            synced.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(target, backup)
                chmod_private(backup)
            shutil.copyfile(source, target)
            chmod_private(target)
            shutil.copyfile(source, synced)
            chmod_private(synced)

        service = service_name(name)
        self.runner.run(["systemctl", "enable", service])
        if restart:
            self.runner.run(["systemctl", "restart", service])

    def history(self, name: str) -> None:
        history_dir = self.history_dir(name)
        print("WireGuard Config History")
        print()
        if not history_dir.exists():
            print(f"No history for {name}.")
            return
        entries = sorted(history_dir.glob("*.conf"))
        if not entries:
            print(f"No history for {name}.")
            return
        for entry in entries:
            print(entry.stem)

    def show(self, name: str, history_id: str, reveal_secrets: bool = False) -> None:
        path = self.history_dir(name) / f"{sanitize_history_id(history_id)}.conf"
        if not path.exists():
            raise FileNotFoundError(f"History entry not found: {history_id}")
        content = path.read_text(encoding="utf-8")
        print(content if reveal_secrets else mask_secrets(content))

    def unsync(self, name: str) -> None:
        target = self.active_config_path(name)
        backup = self._snapshot_path(name, "unsync-backup")
        service = service_name(name)

        self.runner.run(["systemctl", "disable", "--now", service], check=False)
        if target.exists():
            print(f"backup {target} -> {backup}")
            print(f"remove {target}")
        else:
            print(f"skip {target} (not found)")

        if self.runner.dry_run:
            return
        if target.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, backup)
            chmod_private(backup)
            target.unlink()

    def saved_config_path(self, name: str) -> Path:
        return self.store_dir / "configs" / f"{sanitize_interface_name(name)}.conf"

    def history_dir(self, name: str) -> Path:
        return self.store_dir / "history" / sanitize_interface_name(name)

    def active_config_path(self, name: str) -> Path:
        return self.wireguard_dir / f"{sanitize_interface_name(name)}.conf"

    def _snapshot_path(self, name: str, action: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return self.history_dir(name) / f"{timestamp}-{action}.conf"

    def _print_tool_status(self, command: str) -> None:
        result = self.runner.run(["bash", "-lc", f"command -v {command}"], check=False)
        if result.returncode == 0:
            print(f"OK      {command:10} {result.stdout.strip() or 'installed'}")
        else:
            print(f"MISSING {command:10} not installed")

    def _print_path_status(self, label: str, path: Path) -> None:
        marker = "OK" if path.exists() else "WARN"
        detail = f"configured ({path})" if path.exists() else f"not found ({path})"
        print(f"{marker:7} {label:10} {detail}")


def render_template(name: str) -> str:
    return (
        "# vending-auto-config: wireguard\n"
        "# Fill the placeholder values, then run validate/save/sync.\n"
        "[Interface]\n"
        "PrivateKey = <interface-private-key>\n"
        "Address = 10.8.0.13/24\n"
        "# DNS = 1.1.1.1\n"
        "\n"
        "[Peer]\n"
        "PublicKey = <peer-public-key>\n"
        "PresharedKey = <peer-preshared-key>\n"
        "AllowedIPs = 10.8.0.0/24\n"
        "PersistentKeepalive = 25\n"
        "Endpoint = vpn.example.com:51820\n"
        f"# InterfaceName = {sanitize_interface_name(name)}\n"
    )


def validate_config_content(content: str) -> WireGuardValidationResult:
    sections = parse_wireguard_config(content)
    errors: list[str] = []
    warnings: list[str] = []

    interface = sections.get("Interface")
    peers = sections.get("Peer", [])
    if not interface:
        errors.append("missing [Interface] section")
    else:
        errors.extend(_missing_key_errors("Interface", interface[0], REQUIRED_INTERFACE_KEYS))
        warnings.extend(_placeholder_warnings("Interface", interface[0]))

    if not peers:
        errors.append("missing [Peer] section")
    else:
        for index, peer in enumerate(peers, start=1):
            errors.extend(_missing_key_errors(f"Peer #{index}", peer, REQUIRED_PEER_KEYS))
            warnings.extend(_placeholder_warnings(f"Peer #{index}", peer))

    return WireGuardValidationResult(valid=not errors, errors=tuple(errors), warnings=tuple(warnings))


def parse_wireguard_config(content: str) -> dict[str, list[dict[str, str]]]:
    sections: dict[str, list[dict[str, str]]] = {}
    current: dict[str, str] | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            current = {}
            sections.setdefault(section_name, []).append(current)
            continue
        if current is None or "=" not in line:
            continue
        key, value = line.split("=", 1)
        current[key.strip()] = _strip_inline_comment(value.strip())

    return sections


def mask_secrets(content: str) -> str:
    masked_lines = []
    for line in content.splitlines():
        match = re.match(r"^(\s*([A-Za-z]+Key)\s*=\s*)(.*)$", line)
        if match and match.group(2) in SECRET_KEYS:
            masked_lines.append(f"{match.group(1)}<hidden>")
        else:
            masked_lines.append(line)
    return "\n".join(masked_lines) + ("\n" if content.endswith("\n") else "")


def sanitize_interface_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError("WireGuard interface name may only contain letters, numbers, dot, underscore, and dash.")
    if "/" in name or name in {".", ".."}:
        raise ValueError("Invalid WireGuard interface name.")
    return name


def sanitize_history_id(history_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", history_id):
        raise ValueError("History id may only contain letters, numbers, dot, underscore, and dash.")
    return history_id


def default_store_dir() -> Path:
    home = _sudo_user_home() or Path.home()
    config_home = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config_home) if config_home else home / ".config"
    return root / "vending-auto-setup" / "wireguard"


def chmod_private(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def service_name(name: str) -> str:
    return f"wg-quick@{sanitize_interface_name(name)}"


def _missing_key_errors(section: str, values: dict[str, str], required_keys: Iterable[str]) -> list[str]:
    return [f"{section} missing {key}" for key in required_keys if not values.get(key)]


def _placeholder_warnings(section: str, values: dict[str, str]) -> list[str]:
    warnings = []
    for key, value in values.items():
        if value.startswith("<") and value.endswith(">"):
            warnings.append(f"{section} {key} still contains a placeholder")
    return warnings


def _strip_inline_comment(value: str) -> str:
    if " #" not in value:
        return value
    return value.split(" #", 1)[0].strip()


def _service_marker(returncode: int) -> str:
    return "OK" if returncode == 0 else "WARN"


def _sudo_user_home() -> Path | None:
    sudo_user = os.environ.get("SUDO_USER")
    if not sudo_user or sudo_user == "root" or PWD_MODULE is None:
        return None
    try:
        return Path(PWD_MODULE.getpwnam(sudo_user).pw_dir)
    except KeyError:
        return None
