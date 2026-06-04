from __future__ import annotations

import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from runner import CommandRunner


DEFAULT_REPO = "phanuphun/vending-auto-setup"
DEFAULT_INSTALL_DIR = Path("/opt/vending-auto-setup")
WRAPPER_NAMES = ("vending-auto-setup", "vas", "vending-status")
RUNTIME_PACKAGES = ("python3-flask",)


class SelfUpdater:
    def __init__(
        self,
        runner: CommandRunner,
        repo: str = DEFAULT_REPO,
        version: str = "latest",
        install_dir: Path = DEFAULT_INSTALL_DIR,
        bin_dir: Path = Path("/usr/local/bin"),
    ) -> None:
        self.runner = runner
        self.repo = repo
        self.version = version
        self.install_dir = install_dir
        self.bin_dir = bin_dir

    def update(self) -> None:
        archive_url = self.archive_url()
        print(f"download {archive_url}")
        self.ensure_runtime_packages()
        print(f"replace {self.install_dir}")
        for wrapper_name in WRAPPER_NAMES:
            print(f"write {self.bin_dir / wrapper_name}")
        if self.runner.dry_run:
            return

        with tempfile.TemporaryDirectory(prefix="vending-auto-setup-update-") as work_dir:
            work_path = Path(work_dir)
            archive_path = work_path / "source.tar.gz"
            urllib.request.urlretrieve(archive_url, archive_path)
            source_dir = extract_source_archive(archive_path, work_path)

            if self.install_dir.exists():
                shutil.rmtree(self.install_dir)
            self.install_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_dir, self.install_dir)
            install_wrappers(self.install_dir, self.bin_dir)

    def archive_url(self) -> str:
        if self.version == "latest":
            return f"https://github.com/{self.repo}/archive/refs/heads/main.tar.gz"
        return f"https://github.com/{self.repo}/archive/refs/tags/{self.version}.tar.gz"

    def ensure_runtime_packages(self) -> None:
        for package in RUNTIME_PACKAGES:
            print(f"ensure {package}")
        if self.runner.dry_run:
            return
        if not _can_import_flask():
            self.runner.run(["apt-get", "update"])
            self.runner.run(["apt-get", "install", "-y", *RUNTIME_PACKAGES])


def extract_source_archive(archive_path: Path, work_path: Path) -> Path:
    with tarfile.open(archive_path, "r:gz") as archive:
        archive.extractall(work_path, filter="data")

    source_dirs = [
        path
        for path in work_path.iterdir()
        if path.is_dir() and path.name != "__MACOSX" and (path / "src" / "cli.py").exists()
    ]
    if not source_dirs:
        raise RuntimeError("Downloaded archive does not look like vending-auto-setup source.")
    return source_dirs[0]


def install_wrappers(install_dir: Path, bin_dir: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    _write_wrapper(bin_dir / "vending-auto-setup", install_dir, "cli")
    _write_wrapper(bin_dir / "vas", install_dir, "cli")
    _write_wrapper(bin_dir / "vending-status", install_dir, "status")


def _write_wrapper(path: Path, install_dir: Path, module: str) -> None:
    content = (
        "#!/usr/bin/env bash\n"
        f"PYTHONPATH={install_dir.as_posix()}/src exec python3 -m {module} \"$@\"\n"
    )
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _can_import_flask() -> bool:
    try:
        import flask  # noqa: F401
    except ImportError:
        return False
    return True
