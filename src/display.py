from __future__ import annotations

import os
import shlex
import stat
from pathlib import Path

from runner import CommandRunner
from status import (
    DISPLAY_SESSION_SCRIPT_SIGNATURE,
    DISPLAY_SESSION_SIGNATURE,
    XORG_TOUCHSCREEN_CONFIG_PATH,
    XORG_TOUCHSCREEN_SIGNATURE,
    _effective_home_config_path,
    _effective_home_script_path,
)

ROTATION_MATRICES: dict[str, tuple[str, ...]] = {
    "normal": ("1", "0", "0", "0", "1", "0", "0", "0", "1"),
    "right": ("0", "1", "0", "-1", "0", "1", "0", "0", "1"),
    "left": ("0", "-1", "1", "1", "0", "0", "0", "0", "1"),
    "inverted": ("-1", "0", "1", "0", "-1", "1", "0", "0", "1"),
}

COORDINATE_TRANSFORMATION_MATRIX = "Coordinate Transformation Matrix"
DISPLAY_SESSION_BEGIN = f"{DISPLAY_SESSION_SIGNATURE} BEGIN"
DISPLAY_SESSION_END = f"{DISPLAY_SESSION_SIGNATURE} END"

__all__ = [
    "DISPLAY_SESSION_SIGNATURE",
    "ROTATION_MATRICES",
    "XORG_TOUCHSCREEN_SIGNATURE",
    "DisplayConfigurator",
    "build_display_session_block",
    "build_display_session_script",
    "build_xorg_touchscreen_config",
    "matrix_for_rotation",
    "remove_managed_block",
    "upsert_managed_block",
]


class DisplayConfigurator:
    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def print_status(self, x_display: str | None = None, xauthority: str | None = None) -> None:
        print("[Xrandr]")
        self.runner.run(self._with_x_env(["xrandr", "--query"], x_display, xauthority), check=False)
        print()
        print("[Xinput]")
        self.runner.run(self._with_x_env(["xinput", "list"], x_display, xauthority), check=False)

    def apply_runtime(
        self,
        output: str,
        touch: str,
        rotate: str,
        x_display: str | None = None,
        xauthority: str | None = None,
    ) -> None:
        matrix = matrix_for_rotation(rotate)
        self.runner.run(self._with_x_env(["xrandr", "--output", output, "--rotate", rotate], x_display, xauthority))
        self.runner.run(
            self._with_x_env(
                ["xinput", "set-prop", touch, COORDINATE_TRANSFORMATION_MATRIX, *matrix],
                x_display,
                xauthority,
            )
        )

    def persist_xorg(
        self,
        touch: str,
        rotate: str,
        path: Path = XORG_TOUCHSCREEN_CONFIG_PATH,
    ) -> None:
        matrix = " ".join(matrix_for_rotation(rotate))
        content = build_xorg_touchscreen_config(touch, matrix)
        print(f"write {path.as_posix()}")
        if self.runner.dry_run:
            print(content.rstrip())
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def persist_session(
        self,
        output: str,
        touch: str,
        rotate: str,
        x_display: str | None = None,
        path: Path | None = None,
        script_path: Path | None = None,
        delay_seconds: int = 5,
        retries: int = 30,
    ) -> None:
        if path is None:
            path = _effective_home_config_path()
        if script_path is None:
            script_path = _effective_home_script_path()
        matrix = " ".join(matrix_for_rotation(rotate))
        script_content = build_display_session_script(
            output=output,
            touch=touch,
            rotate=rotate,
            matrix=matrix,
            x_display=x_display,
            delay_seconds=delay_seconds,
            retries=retries,
        )
        content = build_display_session_block(script_path=script_path)
        print(f"write {script_path.as_posix()}")
        print(f"write {path.as_posix()}")
        if self.runner.dry_run:
            print(script_content.rstrip())
            print(content.rstrip())
            return

        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_content, encoding="utf-8")
        # ใช้ 755 เพื่อให้ executable ได้ทั้ง owner และ others
        # (จำเป็นเมื่อ server รันเป็น root แต่เขียนไฟล์ไปที่ home ของ user จริง)
        script_path.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        _chown_to_effective_user(script_path)

        existing_content = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(upsert_managed_block(existing_content, content), encoding="utf-8")
        _chown_to_effective_user(path)

    def _with_x_env(
        self,
        args: list[str],
        x_display: str | None,
        xauthority: str | None,
    ) -> list[str]:
        env_args = []
        resolved_display = x_display or os.environ.get("DISPLAY")
        if resolved_display:
            env_args.append(f"DISPLAY={resolved_display}")
        if xauthority:
            env_args.append(f"XAUTHORITY={xauthority}")
        if not env_args:
            return args
        return ["env", *env_args, *args]


def _chown_to_effective_user(path: Path) -> None:
    """chown ไฟล์ไปให้ SUDO_USER เมื่อ process รันเป็น root (เพื่อแก้ ownership หลังเขียนไฟล์ใน home ของ user จริง)"""
    if not (hasattr(os, "geteuid") and os.geteuid() == 0):
        return
    sudo_user = os.environ.get("SUDO_USER", "").strip()
    if not sudo_user or sudo_user == "root":
        return
    try:
        import pwd

        pw = pwd.getpwnam(sudo_user)
        os.chown(path, pw.pw_uid, pw.pw_gid)
    except (ImportError, KeyError, OSError):
        pass


def matrix_for_rotation(rotate: str) -> tuple[str, ...]:
    try:
        return ROTATION_MATRICES[rotate]
    except KeyError as error:
        choices = ", ".join(sorted(ROTATION_MATRICES))
        raise ValueError(f"Unsupported rotation: {rotate}. Expected one of: {choices}") from error


def build_xorg_touchscreen_config(touch: str, matrix: str) -> str:
    return (
        f"{XORG_TOUCHSCREEN_SIGNATURE}\n"
        "# Managed by vending-auto-setup. Manual edits may be overwritten.\n"
        'Section "InputClass"\n'
        '    Identifier "vending-touchscreen-calibration"\n'
        f'    MatchProduct "{touch}"\n'
        f'    Option "CalibrationMatrix" "{matrix}"\n'
        "EndSection\n"
    )


def build_display_session_script(
    output: str,
    touch: str,
    rotate: str,
    matrix: str,
    x_display: str | None,
    delay_seconds: int,
    retries: int,
) -> str:
    display_line = f"export DISPLAY={shlex.quote(x_display)}\n" if x_display else ""
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"{DISPLAY_SESSION_SCRIPT_SIGNATURE}\n"
        "# Managed by vending-auto-setup. Manual edits may be overwritten.\n"
        f"sleep {delay_seconds}\n"
        f"{display_line}"
        f"OUTPUT={shlex.quote(output)}\n"
        f"TOUCH_DEVICE={shlex.quote(touch)}\n"
        f"ROTATE={shlex.quote(rotate)}\n"
        f"MATRIX={shlex.quote(matrix)}\n"
        f"RETRIES={retries}\n"
        "\n"
        "display_found=0\n"
        'for attempt in $(seq 1 "$RETRIES"); do\n'
        '  if xrandr --query | grep -q "^${OUTPUT} connected"; then\n'
        '    xrandr --output "$OUTPUT" --rotate "$ROTATE"\n'
        "    display_found=1\n"
        "    break\n"
        "  fi\n"
        '  echo "Waiting for display output ${OUTPUT} (${attempt}/${RETRIES})"\n'
        "  sleep 1\n"
        "done\n"
        'if [ "$display_found" -ne 1 ]; then\n'
        '  echo "Display output ${OUTPUT} was not found after ${RETRIES} seconds" >&2\n'
        "  exit 1\n"
        "fi\n"
        "\n"
        'for attempt in $(seq 1 "$RETRIES"); do\n'
        '  if xinput list --name-only | grep -Fxq "$TOUCH_DEVICE"; then\n'
        f'    xinput set-prop "$TOUCH_DEVICE" "{COORDINATE_TRANSFORMATION_MATRIX}" $MATRIX\n'
        "    exit 0\n"
        "  fi\n"
        '  echo "Waiting for touchscreen ${TOUCH_DEVICE} (${attempt}/${RETRIES})"\n'
        "  sleep 1\n"
        "done\n"
        "\n"
        'echo "Touchscreen ${TOUCH_DEVICE} was not found after ${RETRIES} seconds" >&2\n'
        "exit 1\n"
    )


def build_display_session_block(script_path: Path) -> str:
    return (
        f"{DISPLAY_SESSION_BEGIN}\n"
        "# Managed by vending-auto-setup. Manual edits inside this block may be overwritten.\n"
        f"{shlex.quote(script_path.as_posix())} &\n"
        f"{DISPLAY_SESSION_END}\n"
    )


def upsert_managed_block(existing_content: str, managed_block: str) -> str:
    if DISPLAY_SESSION_BEGIN not in existing_content:
        separator = "\n" if existing_content and not existing_content.endswith("\n") else ""
        return f"{existing_content}{separator}{managed_block}"

    start = existing_content.index(DISPLAY_SESSION_BEGIN)
    end = existing_content.find(DISPLAY_SESSION_END, start)
    if end == -1:
        return f"{existing_content.rstrip()}\n{managed_block}"

    end += len(DISPLAY_SESSION_END)
    if end < len(existing_content) and existing_content[end : end + 1] == "\n":
        end += 1
    return f"{existing_content[:start]}{managed_block}{existing_content[end:]}"


def remove_managed_block(existing_content: str) -> str:
    if DISPLAY_SESSION_BEGIN not in existing_content:
        return existing_content

    start = existing_content.index(DISPLAY_SESSION_BEGIN)
    end = existing_content.find(DISPLAY_SESSION_END, start)
    if end == -1:
        return existing_content

    end += len(DISPLAY_SESSION_END)
    if end < len(existing_content) and existing_content[end : end + 1] == "\n":
        end += 1
    return f"{existing_content[:start]}{existing_content[end:]}"
