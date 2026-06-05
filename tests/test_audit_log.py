from __future__ import annotations

from pathlib import Path
from typing import cast

import audit_log
from audit_log import create_system_log_snapshot, read_system_snapshot
from pytest import MonkeyPatch


def test_system_snapshot_copies_supported_log_sources(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    system_log = tmp_path / "auth.log"
    system_log.write_text("line 1\nline 2\n", encoding="utf-8")
    monkeypatch.setattr(audit_log, "SYSTEM_SOURCE_PATHS", (system_log,))
    monkeypatch.setattr(audit_log, "_journalctl_tail", lambda lines: None)

    snapshot = create_system_log_snapshot(log_dir=tmp_path)
    saved = read_system_snapshot(str(snapshot["id"]), log_dir=tmp_path)
    content = cast(str, saved["content"])

    assert saved["path"] == snapshot["path"]
    assert "auth.log" in content
    assert "line 2" in content
