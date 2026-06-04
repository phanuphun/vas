from __future__ import annotations

from pathlib import Path

from clock import SystemClockPreflight
from config import InstallConfig
from runner import CommandRunner
from system import detect_ubuntu_codename


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

    def print_versions(self, components: tuple[str, ...]) -> None:
        commands: list[str] = []
        if "node" in components:
            commands.extend(("node", "npm"))
        if "docker" in components:
            commands.append("docker")
        if "git" in components:
            commands.append("git")
        for command in commands:
            self.runner.run([command, "--version"], check=False)

    def _write_file(self, path: str, content: str) -> None:
        print(f"write {path}")
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
