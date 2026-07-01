from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


SYSTEM_SOURCE_PATHS = (
    Path("/var/log/auth.log"),
    Path("/var/log/syslog"),
    Path("/var/log/messages"),
    Path("/var/log/kern.log"),
)
SYSTEM_TAIL_LINES = 500


def default_log_dir() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config_home) if config_home else Path.home() / ".config"
    return root / "vending-auto-setup" / "logs"


def system_snapshot_dir(log_dir: Path | None = None) -> Path:
    return (log_dir or default_log_dir()) / "system" / "snapshots"


def create_system_log_snapshot(log_dir: Path | None = None) -> dict[str, object]:
    snapshot_dir = system_snapshot_dir(log_dir)
    snapshot_id = _utc_timestamp(compact=True)
    path = snapshot_dir / f"{snapshot_id}.log"
    body = _render_system_snapshot()
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return {
        "id": snapshot_id,
        "path": path.as_posix(),
        "size": path.stat().st_size,
        "created": _utc_timestamp(),
    }


def list_system_snapshots(limit: int = 50, log_dir: Path | None = None) -> tuple[dict[str, object], ...]:
    snapshot_dir = system_snapshot_dir(log_dir)
    if not snapshot_dir.exists():
        return ()
    snapshots: list[dict[str, object]] = []
    for path in sorted(snapshot_dir.glob("*.log"), reverse=True)[:limit]:
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshots.append(
            {
                "id": path.stem,
                "path": path.as_posix(),
                "size": stat.st_size,
            }
        )
    return tuple(snapshots)


def read_system_snapshot(snapshot_id: str, log_dir: Path | None = None) -> dict[str, object]:
    safe_id = sanitize_snapshot_id(snapshot_id)
    path = system_snapshot_dir(log_dir) / f"{safe_id}.log"
    if not path.exists():
        raise FileNotFoundError(f"System log snapshot not found: {safe_id}")
    return {
        "id": safe_id,
        "path": path.as_posix(),
        "content": path.read_text(encoding="utf-8", errors="replace"),
    }


def delete_system_snapshot(snapshot_id: str, log_dir: Path | None = None) -> dict[str, object]:
    safe_id = sanitize_snapshot_id(snapshot_id)
    path = system_snapshot_dir(log_dir) / f"{safe_id}.log"
    if not path.exists():
        raise FileNotFoundError(f"System log snapshot not found: {safe_id}")
    path.unlink()
    return {"id": safe_id, "path": path.as_posix()}


def sanitize_snapshot_id(snapshot_id: str) -> str:
    safe = "".join(char for char in snapshot_id if char.isalnum() or char in {"-", "_", "T", "Z"})
    if not safe:
        raise ValueError("Snapshot id is required.")
    return safe


def _render_system_snapshot() -> str:
    sections = [
        "# vending-auto-setup system log snapshot",
        f"# collected_at = {_utc_timestamp()}",
        "",
    ]
    found_source = False
    for path in SYSTEM_SOURCE_PATHS:
        if not path.exists():
            continue
        found_source = True
        sections.extend((f"## {path.as_posix()}", _tail_file(path, SYSTEM_TAIL_LINES), ""))

    journal = _journalctl_tail(SYSTEM_TAIL_LINES)
    if journal is not None:
        found_source = True
        sections.extend(("## journalctl", journal, ""))

    if not found_source:
        sections.append("No supported system log sources were found on this machine.")
    return "\n".join(sections)


def _tail_file(path: Path, lines: int) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        return f"# read error: {error}"
    return "\n".join(content[-lines:])


def _journalctl_tail(lines: int) -> str | None:
    try:
        completed = subprocess.run(
            ["journalctl", "-n", str(lines), "--no-pager"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 and not completed.stdout:
        return f"# journalctl error: {completed.stderr.strip()}"
    return completed.stdout.strip()


def _utc_timestamp(*, compact: bool = False) -> str:
    now = datetime.now(timezone.utc)
    if compact:
        return now.strftime("%Y%m%dT%H%M%SZ")
    return now.isoformat(timespec="seconds")
