from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError
from email.message import Message

from clock import ClockDrift, SystemClockPreflight, read_network_epoch
from runner import CommandRunner


def test_clock_drift_detects_large_difference() -> None:
    drift = ClockDrift(local_epoch=1000, network_epoch=2000)

    assert drift.seconds == 1000
    assert drift.too_large


def test_clock_preflight_dry_run_prints_check(capsys: Any) -> None:
    SystemClockPreflight(CommandRunner(dry_run=True)).ensure_reasonable_clock()

    output = capsys.readouterr().out
    assert "check system clock" in output


def test_read_network_epoch_uses_http_error_date_header() -> None:
    headers = Message()
    headers["Date"] = "Thu, 04 Jun 2026 15:00:00 GMT"
    error = HTTPError("http://example.test", 403, "Forbidden", headers, None)

    with patch("clock.urllib.request.urlopen", side_effect=error):
        epoch = read_network_epoch("http://example.test")

    assert epoch == 1780585200
