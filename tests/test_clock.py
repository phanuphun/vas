from typing import Any

from clock import ClockDrift, SystemClockPreflight
from runner import CommandRunner


def test_clock_drift_detects_large_difference() -> None:
    drift = ClockDrift(local_epoch=1000, network_epoch=2000)

    assert drift.seconds == 1000
    assert drift.too_large


def test_clock_preflight_dry_run_prints_check(capsys: Any) -> None:
    SystemClockPreflight(CommandRunner(dry_run=True)).ensure_reasonable_clock()

    output = capsys.readouterr().out
    assert "check system clock" in output
    assert "archive.ubuntu.com" in output
