from __future__ import annotations

import json as _json
import queue
import re
import shutil
import tarfile
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from core.runner import CommandRunner


DEFAULT_REPO = "phanuphun/vending-auto-setup"
DEFAULT_INSTALL_DIR = Path("/opt/vending-auto-setup")
WRAPPER_NAMES = ("vending-auto-setup", "vas", "vending-status")
RUNTIME_PACKAGES = ("python3-flask",)
GITHUB_API = "https://api.github.com"


class SelfUpdater:
    def __init__(
        self,
        runner: CommandRunner,
        repo: str = DEFAULT_REPO,
        version: str = "latest",
        branch: str = "main",
        install_dir: Path = DEFAULT_INSTALL_DIR,
        bin_dir: Path = Path("/usr/local/bin"),
    ) -> None:
        self.runner = runner
        self.repo = repo
        self.version = version
        self.branch = branch
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
            return f"https://github.com/{self.repo}/archive/refs/heads/{self.branch}.tar.gz"
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


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


def _parse_version(value: str) -> tuple[int, ...]:
    """แปลง version string (เช่น 'v1.2.0', '1.2.0-beta') ให้เป็น tuple ของตัวเลขเพื่อเทียบกัน"""
    cleaned = value.strip().lstrip("vV")
    parts = re.split(r"[.\-+]", cleaned)
    nums: list[int] = []
    for part in parts:
        match = re.match(r"\d+", part)
        nums.append(int(match.group()) if match else 0)
    return tuple(nums) if nums else (0,)


def _version_gt(a: str, b: str) -> bool:
    pa, pb = _parse_version(a), _parse_version(b)
    length = max(len(pa), len(pb))
    pa = pa + (0,) * (length - len(pa))
    pb = pb + (0,) * (length - len(pb))
    return pa > pb


# ---------------------------------------------------------------------------
# GitHub release check
# ---------------------------------------------------------------------------


def check_latest_release(repo: str = DEFAULT_REPO, current: str = "") -> dict[str, object]:
    """ตรวจสอบ release ล่าสุดบน GitHub และเทียบกับเวอร์ชั่นปัจจุบัน"""
    from core.config import APP_VERSION

    current = current or APP_VERSION
    url = f"{GITHUB_API}/repos/{repo}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "vas-updater"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        latest = str(data.get("tag_name") or "").strip() or current
        latest_clean = latest.lstrip("vV")
        return {
            "status": "ok",
            "has_update": _version_gt(latest_clean, current),
            "current": current,
            "latest": latest_clean,
            "release_url": data.get("html_url", ""),
        }
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"status": "error", "errors": ["ไม่พบ release บน GitHub repository นี้"]}
        return {"status": "error", "errors": [f"GitHub API error: {exc.code}"]}
    except urllib.error.URLError as exc:
        return {"status": "error", "errors": [f"เชื่อมต่อ GitHub ไม่ได้: {exc.reason}"]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "errors": [str(exc)]}


# ---------------------------------------------------------------------------
# Streaming self-update (used by the web UI's /api/update/stream)
# ---------------------------------------------------------------------------

_active_update: "queue.Queue[dict[str, object]] | None" = None
_update_lock = threading.Lock()


def is_updating() -> bool:
    with _update_lock:
        return _active_update is not None


def get_update_queue() -> "queue.Queue[dict[str, object]] | None":
    with _update_lock:
        return _active_update


def start_web_update(
    repo: str = DEFAULT_REPO,
    branch: str = "main",
    version: str = "latest",
) -> tuple[bool, str]:
    """เริ่มการอัปเดตใน background thread พร้อม stream progress ผ่าน queue

    Returns (ok, error_msg)
    """
    global _active_update

    with _update_lock:
        if _active_update is not None:
            return False, "กำลังอัปเดตอยู่แล้ว"
        q: "queue.Queue[dict[str, object]]" = queue.Queue()
        _active_update = q

    def emit_progress(percent: int, step: str, msg: str) -> None:
        q.put({"event": "progress", "percent": percent, "step": step, "msg": msg})

    def emit_log(msg: str) -> None:
        q.put({"event": "log", "msg": msg})

    def _run() -> None:
        global _active_update
        try:
            updater = SelfUpdater(
                runner=CommandRunner(dry_run=False),
                repo=repo,
                version=version,
                branch=branch,
            )
            emit_progress(5, "check", "เตรียมเริ่มอัปเดต...")
            archive_url = updater.archive_url()
            emit_log(f"▶ repo: {repo} ({branch if version == 'latest' else version})")
            emit_log(f"$ download {archive_url}")

            updater.ensure_runtime_packages()

            emit_progress(15, "download", "กำลังดาวน์โหลด...")
            with tempfile.TemporaryDirectory(prefix="vas-web-update-") as work_dir:
                work_path = Path(work_dir)
                archive_path = work_path / "source.tar.gz"

                def _reporthook(block_num: int, block_size: int, total_size: int) -> None:
                    if total_size > 0:
                        downloaded = block_num * block_size
                        pct = min(55, 15 + int((downloaded / total_size) * 40))
                        emit_progress(
                            pct,
                            "download",
                            f"ดาวน์โหลด {min(100, int(downloaded * 100 / total_size))}%",
                        )

                urllib.request.urlretrieve(archive_url, archive_path, reporthook=_reporthook)
                emit_log("✓ ดาวน์โหลดเสร็จสิ้น")

                emit_progress(65, "extract", "กำลังแตกไฟล์...")
                source_dir = extract_source_archive(archive_path, work_path)
                emit_log(f"✓ แตกไฟล์แล้ว: {source_dir.name}")

                emit_progress(80, "install", f"กำลังติดตั้งไปที่ {updater.install_dir}...")
                if updater.install_dir.exists():
                    shutil.rmtree(updater.install_dir)
                updater.install_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source_dir, updater.install_dir)
                install_wrappers(updater.install_dir, updater.bin_dir)
                emit_log("✓ ติดตั้งไฟล์เรียบร้อย")

            emit_progress(100, "done", "อัปเดตเสร็จสิ้น")
            q.put({"event": "done"})
        except Exception as exc:  # noqa: BLE001
            q.put({"event": "error", "msg": str(exc)})
        finally:
            with _update_lock:
                _active_update = None

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return True, ""
