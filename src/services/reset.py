from __future__ import annotations

from pathlib import Path

from features.display.display import remove_managed_block
from core.runner import CommandRunner
from system.status import (
    DISPLAY_SESSION_SCRIPT_SIGNATURE,
    XORG_TOUCHSCREEN_CONFIG_PATH,
    XORG_TOUCHSCREEN_SIGNATURE,
    _effective_home_config_path,
    _effective_home_script_path,
)
from features.wireguard.manager import WIREGUARD_CONFIG_DIR, default_store_dir, sanitize_interface_name, service_name


INSTALL_COMPONENTS = ("node", "docker", "git", "wireguard", "anydesk", "openssh", "qr-udev")
RESET_COMPONENTS = ("node", "docker", "git", "wireguard", "anydesk", "openssh", "display", "qr-udev")

NODE_APT_FILES = (
    Path("/etc/apt/sources.list.d/nodesource.list"),
    Path("/usr/share/keyrings/nodesource.gpg"),
)
DOCKER_APT_FILES = (
    Path("/etc/apt/sources.list.d/docker.list"),
    Path("/etc/apt/keyrings/docker.asc"),
)
ANYDESK_APT_FILES = (
    Path("/etc/apt/sources.list.d/anydesk.list"),
    Path("/usr/share/keyrings/anydesk.gpg"),
)
DOCKER_PACKAGES = (
    "docker-ce",
    "docker-ce-cli",
    "containerd.io",
    "docker-buildx-plugin",
    "docker-compose-plugin",
    "docker-ce-rootless-extras",
    "docker.io",
    "docker-doc",
    "docker-compose",
    "docker-compose-v2",
    "podman-docker",
    "containerd",
    "runc",
)
NODE_PACKAGES = ("nodejs", "npm")
GIT_PACKAGES = ("git",)
WIREGUARD_PACKAGES = ("wireguard", "wireguard-tools")
ANYDESK_PACKAGES = ("anydesk",)


class LifecycleManager:
    def __init__(
        self,
        runner: CommandRunner,
        wireguard_store_dir: Path | None = None,
        wireguard_dir: Path = WIREGUARD_CONFIG_DIR,
    ) -> None:
        self.runner = runner
        self.wireguard_store_dir = wireguard_store_dir or default_store_dir()
        self.wireguard_dir = wireguard_dir

    def uninstall(self, components: tuple[str, ...], wireguard_name: str) -> None:
        for component in expand_components(components, INSTALL_COMPONENTS):
            if component == "node":
                self.uninstall_node(remove_config=False)
            elif component == "docker":
                self.uninstall_docker(remove_config=False)
            elif component == "git":
                self.uninstall_git()
            elif component == "wireguard":
                self.uninstall_wireguard(wireguard_name, remove_config=False)
            elif component == "anydesk":
                self.uninstall_anydesk(remove_config=False)
            elif component == "openssh":
                self.uninstall_openssh()
            elif component == "qr-udev":
                self.reset_qr_config()
            else:
                raise ValueError(f"Unsupported uninstall component: {component}")
        self.runner.run(["apt-get", "autoremove", "-y"], check=False)

    def reset(self, components: tuple[str, ...], wireguard_name: str) -> None:
        for component in expand_components(components, RESET_COMPONENTS):
            if component == "node":
                self.uninstall_node(remove_config=True)
            elif component == "docker":
                self.uninstall_docker(remove_config=True)
            elif component == "git":
                self.uninstall_git()
            elif component == "wireguard":
                self.uninstall_wireguard(wireguard_name, remove_config=True)
            elif component == "display":
                self.reset_display_config()
            elif component == "anydesk":
                self.uninstall_anydesk(remove_config=True)
            elif component == "openssh":
                self.reset_openssh()
            elif component == "qr-udev":
                self.reset_qr_config()
            else:
                raise ValueError(f"Unsupported reset component: {component}")
        self.runner.run(["apt-get", "autoremove", "-y"], check=False)

    def uninstall_node(self, remove_config: bool) -> None:
        self.runner.run(["npm", "uninstall", "-g", "pm2"], check=False)
        self.runner.run(["apt-get", "purge", "-y", *NODE_PACKAGES], check=False)
        if remove_config:
            for path in NODE_APT_FILES:
                self._remove_file(path)

    def uninstall_docker(self, remove_config: bool) -> None:
        self.runner.run(["systemctl", "disable", "--now", "docker"], check=False)
        self.runner.run(["systemctl", "disable", "--now", "containerd"], check=False)
        self.runner.run(["apt-get", "remove", "-y", *DOCKER_PACKAGES], check=False)
        if remove_config:
            for path in DOCKER_APT_FILES:
                self._remove_file(path)
        self.runner.print_operation("skip /var/lib/docker (Docker data and volumes are preserved)")

    def uninstall_git(self) -> None:
        self.runner.run(["apt-get", "purge", "-y", *GIT_PACKAGES], check=False)

    def uninstall_wireguard(self, name: str, remove_config: bool) -> None:
        interface = sanitize_interface_name(name)
        self.runner.run(["systemctl", "disable", "--now", service_name(interface)], check=False)
        self.runner.run(["apt-get", "purge", "-y", *WIREGUARD_PACKAGES], check=False)
        if remove_config:
            self._remove_file(self.wireguard_dir / f"{interface}.conf")
            self._remove_dir(self.wireguard_store_dir)

    def uninstall_anydesk(self, remove_config: bool) -> None:
        self.runner.run(["systemctl", "disable", "--now", "anydesk"], check=False)
        self.runner.run(["apt-get", "purge", "-y", *ANYDESK_PACKAGES], check=False)
        if remove_config:
            for path in ANYDESK_APT_FILES:
                self._remove_file(path)

    def uninstall_openssh(self) -> None:
        self.runner.run(["systemctl", "disable", "--now", "ssh"], check=False)

    def reset_openssh(self) -> None:
        self.runner.run(["systemctl", "disable", "--now", "ssh"], check=False)

    def reset_display_config(self) -> None:
        self._remove_file_if_has_signature(XORG_TOUCHSCREEN_CONFIG_PATH, XORG_TOUCHSCREEN_SIGNATURE)
        self._remove_file_if_has_signature(_effective_home_script_path(), DISPLAY_SESSION_SCRIPT_SIGNATURE)
        self._remove_display_session_block(_effective_home_config_path())

    def reset_qr_config(self) -> None:
        """ลบ udev rule (ถ้ามี signature) และ config file แล้ว reload udev"""
        from core.config import QR_UDEV_RULE_PATH, QR_UDEV_SIGNATURE, qr_config_path
        self._remove_file_if_has_signature(QR_UDEV_RULE_PATH, QR_UDEV_SIGNATURE)
        self._remove_file(qr_config_path())
        self.runner.run(["udevadm", "control", "--reload-rules"], check=False)
        self.runner.run(["udevadm", "trigger"], check=False)

    def _remove_display_session_block(self, path: Path) -> None:
        self.runner.print_operation(f"remove managed block {_format_path(path)}")
        if self.runner.dry_run or not path.exists():
            return
        content = path.read_text(encoding="utf-8")
        updated_content = remove_managed_block(content)
        if updated_content == content:
            self.runner.print_operation(f"skip {_format_path(path)} (managed block not found)")
            return
        path.write_text(updated_content, encoding="utf-8")

    def _remove_file_if_has_signature(self, path: Path, signature: str) -> None:
        self.runner.print_operation(f"remove {_format_path(path)}")
        if self.runner.dry_run or not path.exists():
            return
        content = path.read_text(encoding="utf-8")
        if signature not in content:
            self.runner.print_operation(f"skip {_format_path(path)} (signature missing)")
            return
        path.unlink()

    def _remove_file(self, path: Path) -> None:
        self.runner.print_operation(f"remove {_format_path(path)}")
        if self.runner.dry_run or not path.exists():
            return
        path.unlink()

    def _remove_dir(self, path: Path) -> None:
        self.runner.print_operation(f"remove {_format_path(path)}")
        if self.runner.dry_run or not path.exists():
            return
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        path.rmdir()


def expand_components(components: tuple[str, ...], valid_components: tuple[str, ...]) -> tuple[str, ...]:
    expanded: list[str] = []
    for component in components:
        if component == "all":
            expanded.extend(valid_components)
            continue
        if component not in valid_components:
            raise ValueError(f"Unsupported component: {component}")
        expanded.append(component)
    return tuple(dict.fromkeys(expanded))


def count_uninstall_operations(components: tuple[str, ...]) -> int:
    total = 1  # apt-get autoremove
    for component in expand_components(components, INSTALL_COMPONENTS):
        if component == "node":
            total += 2
        elif component == "docker":
            total += 4
        elif component == "git":
            total += 1
        elif component == "wireguard":
            total += 2
        elif component == "anydesk":
            total += 2
        elif component == "openssh":
            total += 1
        elif component == "qr-udev":
            total += 4  # remove udev + remove config + reload + trigger
    return total


def count_reset_operations(components: tuple[str, ...]) -> int:
    total = 1  # apt-get autoremove
    for component in expand_components(components, RESET_COMPONENTS):
        if component == "node":
            total += 4
        elif component == "docker":
            total += 6
        elif component == "git":
            total += 1
        elif component == "wireguard":
            total += 4
        elif component == "display":
            total += 3
        elif component == "anydesk":
            total += 4
        elif component == "openssh":
            total += 1
        elif component == "qr-udev":
            total += 4  # remove udev + remove config + reload + trigger
    return total


def _format_path(path: Path) -> str:
    return path.as_posix()
