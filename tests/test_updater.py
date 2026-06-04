from pathlib import Path

from updater import install_wrappers


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
