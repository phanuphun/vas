from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._progress_total: int | None = None
        self._progress_current = 0

    def start_progress(self, total: int) -> None:
        self._progress_total = max(total, 1)
        self._progress_current = 0

    def stop_progress(self) -> None:
        self._progress_total = None
        self._progress_current = 0

    def print_operation(self, operation: str) -> None:
        print(self._format_operation(operation))

    def run(self, args: Sequence[str], check: bool = True, stream: bool = False) -> CommandResult:
        normalized_args = tuple(args)
        self.print_operation(format_command(normalized_args))
        if self.dry_run:
            return CommandResult(normalized_args, 0, "", "")

        if stream:
            completed = subprocess.run(normalized_args, check=False)
            result = CommandResult(normalized_args, completed.returncode, "", "")
        else:
            completed = subprocess.run(
                normalized_args,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            result = CommandResult(
                normalized_args,
                completed.returncode,
                completed.stdout,
                completed.stderr,
            )
        if check and completed.returncode != 0:
            raise CommandExecutionError(result)
        return result

    def _format_operation(self, operation: str) -> str:
        if self._progress_total is None:
            return operation

        if self._progress_total == 1:
            percent = 100
        else:
            percent = round((self._progress_current / (self._progress_total - 1)) * 100)
        self._progress_current = min(self._progress_current + 1, self._progress_total - 1)
        return f"[vending-auto-setup ({percent}%)] - {operation}"


class CommandExecutionError(RuntimeError):
    def __init__(self, result: CommandResult) -> None:
        super().__init__(
            f"Command failed with exit code {result.returncode}: "
            f"{format_command(result.args)}\n{result.stderr.strip()}"
        )
        self.result = result


def format_command(args: Sequence[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in args)
