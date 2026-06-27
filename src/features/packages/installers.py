from __future__ import annotations

from pathlib import Path

from system.clock import SystemClockPreflight
from core.config import InstallConfig
from core.runner import CommandRunner
from system.utils import detect_ubuntu_codename


APT_COMMON_PACKAGES = (
    "ca-certificates",
    "curl",
    "gnupg",
)

OLD_DOCKER_PACKAGES = (
    "docker.io",
    "docker-doc",
    "docker-compose",
    "docker-compose-v2",
    "podman-docker",
    "containerd",
    "runc",
)

NODE_PACKAGES_TO_PURGE = (
    "nodejs",
    "npm",
)
ANYDESK_APT_SOURCE = "deb [signed-by=/usr/share/keyrings/anydesk.gpg] https://deb.anydesk.com/ all main"


class PhaseOneInstaller:
    def __init__(self, runner: CommandRunner, config: InstallConfig) -> None:
        self.runner = runner
        self.config = config

    def install_all(self) -> None:
        self.install_components(("node", "docker", "git"))

    def install_components(self, components: tuple[str, ...]) -> None:
        SystemClockPreflight(self.runner).ensure_reasonable_clock()
        self.prepare_apt()
        for component in components:
            if component == "node":
                self.install_node()
            elif component == "docker":
                self.install_docker()
            elif component == "git":
                self.install_git()
            elif component == "anydesk":
                self.install_anydesk()
            elif component == "openssh":
                self.install_openssh()
            elif component == "qr-udev":
                self.install_qr_udev_rule()
            else:
                raise ValueError(f"Unsupported install component: {component}")
        self.print_versions(components)

    def prepare_apt(self) -> None:
        self.runner.run(["apt-get", "update"])
        self.runner.run(["apt-get", "install", "-y", *APT_COMMON_PACKAGES])

    def install_node(self) -> None:
        self.runner.run(["apt-get", "purge", "-y", *NODE_PACKAGES_TO_PURGE], check=False)
        self.runner.run(["rm", "-f", "/etc/apt/sources.list.d/nodesource.list"], check=False)
        self.runner.run(["rm", "-f", "/usr/share/keyrings/nodesource.gpg"], check=False)
        self.runner.run(
            [
                "bash",
                "-lc",
                "curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key "
                "| gpg --dearmor -o /usr/share/keyrings/nodesource.gpg",
            ]
        )
        source_line = (
            f"deb [signed-by=/usr/share/keyrings/nodesource.gpg] "
            f"https://deb.nodesource.com/node_{self.config.node_major}.x nodistro main"
        )
        self._write_file("/etc/apt/sources.list.d/nodesource.list", source_line + "\n")
        self.runner.run(["apt-get", "update"])
        self.runner.run(["apt-get", "install", "-y", "nodejs"])
        self.runner.run(["npm", "install", "-g", "pm2"])

    def install_docker(self) -> None:
        self.runner.run(["apt-get", "remove", "-y", *OLD_DOCKER_PACKAGES], check=False)
        self.runner.run(["install", "-m", "0755", "-d", "/etc/apt/keyrings"])
        self.runner.run(
            [
                "curl",
                "-fsSL",
                "https://download.docker.com/linux/ubuntu/gpg",
                "-o",
                "/etc/apt/keyrings/docker.asc",
            ]
        )
        self.runner.run(["chmod", "a+r", "/etc/apt/keyrings/docker.asc"])
        codename = detect_ubuntu_codename() or self.config.ubuntu_codename
        architecture = self._detect_dpkg_architecture()
        docker_source = (
            f"deb [arch={architecture} signed-by=/etc/apt/keyrings/docker.asc] "
            f"https://download.docker.com/linux/ubuntu {codename} stable"
        )
        self._write_file("/etc/apt/sources.list.d/docker.list", docker_source + "\n")
        self.runner.run(["apt-get", "update"])
        self.runner.run(["apt-get", "install", "-y", *self._docker_packages_to_install()])

    def install_git(self) -> None:
        self.runner.run(["apt-get", "purge", "-y", "git"], check=False)
        package = "git" if self.config.git_version is None else f"git={self.config.git_version}"
        self.runner.run(["apt-get", "install", "-y", package])

    def install_anydesk(self) -> None:
        self.runner.run(["apt-get", "purge", "-y", "anydesk"], check=False)
        self.runner.run(["rm", "-f", "/etc/apt/sources.list.d/anydesk.list"], check=False)
        self.runner.run(["rm", "-f", "/usr/share/keyrings/anydesk.gpg"], check=False)
        self.runner.run(
            [
                "bash",
                "-lc",
                "curl -fsSL https://keys.anydesk.com/repos/DEB-GPG-KEY "
                "| gpg --dearmor -o /usr/share/keyrings/anydesk.gpg",
            ]
        )
        self._write_file("/etc/apt/sources.list.d/anydesk.list", ANYDESK_APT_SOURCE + "\n")
        self.runner.run(["apt-get", "update"])
        self.runner.run(["apt-get", "install", "-y", "anydesk"])
        self.runner.run(["systemctl", "enable", "--now", "anydesk"], check=False)

    def install_openssh(self) -> None:
        self.runner.run(["apt-get", "install", "-y", "openssh-server"])
        self.runner.run(["systemctl", "enable", "--now", "ssh"], check=False)

    def print_versions(self, components: tuple[str, ...]) -> None:
        commands: list[str] = []
        if "node" in components:
            commands.extend(("node", "npm", "pm2"))
        if "docker" in components:
            commands.append("docker")
        if "git" in components:
            commands.append("git")
        if "anydesk" in components:
            commands.append("anydesk")
        for command in commands:
            self.runner.run([command, "--version"], check=False)
        if "openssh" in components:
            self.runner.run(["ssh", "-V"], check=False)

    def install_qr_udev_rule(self) -> None:
        """เขียน udev rule สำหรับ ZKTeco QR500-BM แล้ว reload udev"""
        from core.config import QR_UDEV_RULE_PATH
        self._write_file(str(QR_UDEV_RULE_PATH), QR_UDEV_RULE_CONTENT)
        self.runner.run(["udevadm", "control", "--reload-rules"])
        self.runner.run(["udevadm", "trigger"])

    def _write_file(self, path: str, content: str) -> None:
        self.runner.print_operation(f"write {path}")
        if self.runner.dry_run:
            print(content, end="" if content.endswith("\n") else "\n")
            return
        Path(path).write_text(content, encoding="utf-8")

    def _detect_dpkg_architecture(self) -> str:
        if self.runner.dry_run:
            return "amd64"
        result = self.runner.run(["dpkg", "--print-architecture"])
        return result.stdout.strip() or "amd64"

    def _docker_packages_to_install(self) -> tuple[str, ...]:
        if self.config.docker_version is None:
            return self.config.docker_packages

        versioned_packages = []
        for package in self.config.docker_packages:
            if package in {"docker-ce", "docker-ce-cli"}:
                versioned_packages.append(f"{package}={self.config.docker_version}")
            else:
                versioned_packages.append(package)
        return tuple(versioned_packages)


def count_install_operations(components: tuple[str, ...]) -> int:
    total = 2  # apt-get update and common package install
    for component in components:
        if component == "node":
            total += 8
        elif component == "docker":
            total += 7
        elif component == "git":
            total += 2
        elif component == "anydesk":
            total += 8
        elif component == "openssh":
            total += 2
        elif component == "qr-udev":
            total += 3  # write file + reload + trigger

    if "node" in components:
        total += 3  # node --version, npm --version, and pm2 --version
    if "docker" in components:
        total += 1
    if "git" in components:
        total += 1
    if "anydesk" in components:
        total += 1
    if "openssh" in components:
        total += 1
    return total


QR_UDEV_RULE_CONTENT = (
    "# managed by vas\n"
    'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5020",'
    ' MODE="0666", TAG+="uaccess"\n'
)
