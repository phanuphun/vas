from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from runner import CommandRunner


DEFAULT_TIME_URL = "http://archive.ubuntu.com/ubuntu/"
MAX_CLOCK_DRIFT_SECONDS = 300


@dataclass(frozen=True)
class ClockDrift:
    local_epoch: int
    network_epoch: int

    @property
    def seconds(self) -> int:
        return self.network_epoch - self.local_epoch

    @property
    def too_large(self) -> bool:
        return abs(self.seconds) > MAX_CLOCK_DRIFT_SECONDS


class SystemClockPreflight:
    def __init__(self, runner: CommandRunner, time_url: str = DEFAULT_TIME_URL) -> None:
        self.runner = runner
        self.time_url = time_url

    def ensure_reasonable_clock(self) -> None:
        print(f"check system clock ({self.time_url})")
        if self.runner.dry_run:
            return

        drift = self.read_clock_drift()
        if drift is None:
            print("WARN    Clock      unable to read network time; continuing")
            return
        if not drift.too_large:
            print(f"OK      Clock      drift {drift.seconds}s")
            return

        network_time = datetime.fromtimestamp(drift.network_epoch, tz=timezone.utc)
        print(f"WARN    Clock      drift {drift.seconds}s; setting UTC time to {network_time.isoformat()}")
        self.runner.run(["timedatectl", "set-ntp", "false"], check=False)
        self.runner.run(["date", "-u", "-s", f"@{drift.network_epoch}"])
        self.runner.run(["timedatectl", "set-ntp", "true"], check=False)

    def read_clock_drift(self) -> ClockDrift | None:
        network_epoch = read_network_epoch(self.time_url)
        if network_epoch is None:
            return None
        return ClockDrift(local_epoch=int(time.time()), network_epoch=network_epoch)


def read_network_epoch(url: str) -> int | None:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw_date = response.headers.get("Date")
    except OSError:
        return None

    if raw_date is None:
        return None
    network_time = parsedate_to_datetime(raw_date)
    if network_time.tzinfo is None:
        network_time = network_time.replace(tzinfo=timezone.utc)
    return int(network_time.timestamp())
