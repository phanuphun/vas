from pathlib import Path
from unittest.mock import patch

from runner import CommandRunner
from updater import SelfUpdater, install_wrappers


def test_install_wrappers_writes_vas_alias(tmp_path: Path) -> None:
    install_dir = tmp_path / "app"
    bin_dir = tmp_path / "bin"
    install_dir.mkdir()

    install_wrappers(install_dir, bin_dir)

    vas = bin_dir / "vas"
    assert vas.exists()
    assert "python3 -m cli" in vas.read_text(encoding="utf-8")
    assert (bin_dir / "vending-auto-setup").exists()
    assert (bin_dir / "vending-status").exists()


def test_update_installs_runtime_packages_when_flask_is_missing(capsys) -> None:  # type: ignore[no-untyped-def]
    runner = CommandRunner(dry_run=False)

    with patch("updater._can_import_flask", return_value=False):
        with patch.object(runner, "run") as run_command:
            SelfUpdater(runner).ensure_runtime_packages()

    output = capsys.readouterr().out
    assert "ensure python3-flask" in output
    run_command.assert_any_call(["apt-get", "update"])
    run_command.assert_any_call(["apt-get", "install", "-y", "python3-flask"])
