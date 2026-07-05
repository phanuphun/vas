from __future__ import annotations

import os
import re
import shlex
import stat
from dataclasses import dataclass
from pathlib import Path

from core.runner import CommandRunner
from system.status import (
    DISPLAY_SESSION_SCRIPT_SIGNATURE,
    DISPLAY_SESSION_SIGNATURE,
    GDM_CUSTOM_CONFIG_PATH,
    SCREEN_BLANK_SIGNATURE,
    XORG_TOUCHSCREEN_CONFIG_PATH,
    XORG_TOUCHSCREEN_SIGNATURE,
    _effective_home_config_path,
    _effective_home_script_path,
)


@dataclass(frozen=True)
class TouchDevice:
    """Touchscreen device พร้อม xinput ID สำหรับสั่งงาน"""

    name: str
    xinput_id: "int | None"


ROTATION_MATRICES: "dict[str, tuple[str, ...]]" = {
    "normal": ("1", "0", "0", "0", "1", "0", "0", "0", "1"),
    "right": ("0", "1", "0", "-1", "0", "1", "0", "0", "1"),
    "left": ("0", "-1", "1", "1", "0", "0", "0", "0", "1"),
    "inverted": ("-1", "0", "1", "0", "-1", "1", "0", "0", "1"),
}

COORDINATE_TRANSFORMATION_MATRIX = "Coordinate Transformation Matrix"
DISPLAY_SESSION_BEGIN = f"{DISPLAY_SESSION_SIGNATURE} BEGIN"
DISPLAY_SESSION_END = f"{DISPLAY_SESSION_SIGNATURE} END"
SCREEN_BLANK_BEGIN = f"{SCREEN_BLANK_SIGNATURE} BEGIN"
SCREEN_BLANK_END = f"{SCREEN_BLANK_SIGNATURE} END"

# ค่า timeout (วินาที) + label ภาษาไทย — เทียบเท่า GNOME Settings > Power > Screen Blank
# 0 = ไม่ปิดหน้าจอ (Never) -> xset s off + xset -dpms
SCREEN_BLANK_OPTIONS: "tuple[tuple[int, str], ...]" = (
    (180, "3 นาที"),
    (240, "4 นาที"),
    (300, "5 นาที"),
    (480, "8 นาที"),
    (600, "10 นาที"),
    (720, "12 นาที"),
    (900, "15 นาที"),
    (0, "ไม่ปิดหน้าจอ (Never)"),
)

__all__ = [
    "DISPLAY_SESSION_SIGNATURE",
    "ROTATION_MATRICES",
    "SCREEN_BLANK_OPTIONS",
    "SCREEN_BLANK_SIGNATURE",
    "XORG_TOUCHSCREEN_SIGNATURE",
    "DisplayConfigurator",
    "TouchDevice",
    "build_display_session_block",
    "build_display_session_script",
    "build_gdm_wayland_config",
    "build_screen_blank_block",
    "build_screen_blank_commands",
    "build_xorg_touchscreen_config",
    "get_screen_blank_seconds",
    "get_udevadm_touchscreen_names",
    "list_touch_devices",
    "matrix_for_rotation",
    "parse_xinput_device_map",
    "parse_xset_screen_blank_seconds",
    "remove_managed_block",
    "upsert_managed_block",
]


class DisplayConfigurator:
    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def print_status(self, x_display: "str | None" = None, xauthority: "str | None" = None) -> None:
        print("[Xrandr]")
        self.runner.run(self._with_x_env(["xrandr", "--query"], x_display, xauthority), check=False)
        print()
        print("[Xinput]")
        self.runner.run(self._with_x_env(["xinput", "list"], x_display, xauthority), check=False)

    def print_touch_devices(self, x_display: "str | None" = None, xauthority: "str | None" = None) -> None:
        """แสดงรายการ touchscreen devices พร้อม xinput ID"""
        devices = list_touch_devices(self.runner, x_display=x_display, xauthority=xauthority)
        if not devices:
            print("No touchscreen devices found.")
            return
        print(f"{'ID':>4}  Name")
        print("-" * 48)
        for d in devices:
            id_str = str(d.xinput_id) if d.xinput_id is not None else "?"
            print(f"{id_str:>4}  {d.name}")

    def apply_runtime(
        self,
        output: str,
        touch: str,
        rotate: str,
        x_display: "str | None" = None,
        xauthority: "str | None" = None,
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
        x_display: "str | None" = None,
        path: "Path | None" = None,
        script_path: "Path | None" = None,
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
        # 755: executable โดย owner และ others (จำเป็นเมื่อ server root เขียนไฟล์ใน home user)
        script_path.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        _chown_to_effective_user(script_path)

        existing_content = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(upsert_managed_block(existing_content, content), encoding="utf-8")
        _chown_to_effective_user(path)

    def apply_screen_blank(
        self,
        seconds: int,
        x_display: "str | None" = None,
        xauthority: "str | None" = None,
    ) -> None:
        """Apply screensaver/DPMS blanking timeout ทันที (runtime, ไม่ persist)"""
        for args in build_screen_blank_commands(seconds):
            self.runner.run(self._with_x_env(list(args), x_display, xauthority), check=False)

    def persist_screen_blank(
        self,
        seconds: int,
        path: "Path | None" = None,
    ) -> None:
        """เขียนคำสั่ง xset ลง .xprofile เพื่อให้ apply ทุกครั้งหลัง login"""
        if path is None:
            path = _effective_home_config_path()
        content = build_screen_blank_block(seconds)
        print(f"write {path.as_posix()}")
        if self.runner.dry_run:
            print(content.rstrip())
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        existing_content = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(
            upsert_managed_block(existing_content, content, begin=SCREEN_BLANK_BEGIN, end=SCREEN_BLANK_END),
            encoding="utf-8",
        )
        _chown_to_effective_user(path)

    def remove_screen_blank_persist(self, path: "Path | None" = None) -> None:
        if path is None:
            path = _effective_home_config_path()
        if not path.exists():
            return
        existing_content = path.read_text(encoding="utf-8")
        path.write_text(
            remove_managed_block(existing_content, begin=SCREEN_BLANK_BEGIN, end=SCREEN_BLANK_END),
            encoding="utf-8",
        )
        _chown_to_effective_user(path)

    def disable_wayland(self, path: Path = GDM_CUSTOM_CONFIG_PATH) -> None:
        self._set_gdm_wayland(enabled=False, path=path)

    def enable_wayland(self, path: Path = GDM_CUSTOM_CONFIG_PATH) -> None:
        self._set_gdm_wayland(enabled=True, path=path)

    def _set_gdm_wayland(self, enabled: bool, path: Path) -> None:
        action = "enable" if enabled else "disable"
        print(f"{action} Wayland in {path.as_posix()}")

        existing_content = ""
        if path.exists():
            existing_content = path.read_text(encoding="utf-8")
        content = build_gdm_wayland_config(existing_content, enabled=enabled)

        if self.runner.dry_run:
            print(content.rstrip())
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _with_x_env(
        self,
        args: list[str],
        x_display: "str | None",
        xauthority: "str | None",
    ) -> list[str]:
        env_args: list[str] = []
        resolved_display = x_display or os.environ.get("DISPLAY")
        if resolved_display:
            env_args.append(f"DISPLAY={resolved_display}")
        if xauthority:
            env_args.append(f"XAUTHORITY={xauthority}")
        if not env_args:
            return args
        return ["env", *env_args, *args]


# ---------------------------------------------------------------------------
# Touchscreen detection helpers
# ---------------------------------------------------------------------------

def parse_xinput_device_map(output: str) -> "dict[str, int]":
    """Parse output ของ `xinput list` -> dict ของ name: xinput_id

    รองรับ format:
      <tree>  Virtual core pointer                  id=2    [master pointer  (3)]
      <tree>  Vending Virtual Touchscreen           id=13   [slave  pointer  (2)]
    """
    result: "dict[str, int]" = {}
    for line in output.splitlines():
        m = re.search(r"\bid=(\d+)\b", line)
        if not m:
            continue
        xinput_id = int(m.group(1))
        name_part = line[: m.start()]
        name_part = re.sub(r"^[^a-zA-Z0-9]+", "", name_part).rstrip()
        if name_part:
            result[name_part] = xinput_id
    return result


def get_udevadm_touchscreen_names(runner: CommandRunner) -> "frozenset[str]":
    """อ่านชื่อ touchscreen จาก udevadm (kernel-level ไม่ต้องพึ่ง X session)

    เทียบเท่า:
      udevadm info --export-db | awk '/ID_INPUT_TOUCHSCREEN=1/' RS= | grep 'E: NAME=' | cut -d'"' -f2
    """
    result = runner.run(["udevadm", "info", "--export-db"], check=False)
    if result.returncode != 0:
        return frozenset()

    names: "set[str]" = set()
    block: "list[str]" = []

    def _process_block(lines: "list[str]") -> None:
        if any(line == "E: ID_INPUT_TOUCHSCREEN=1" for line in lines):
            for line in lines:
                if line.startswith("E: NAME="):
                    name = line[8:].strip().strip('"')
                    if name:
                        names.add(name)

    for raw in result.stdout.splitlines():
        line = raw.strip()
        if line:
            block.append(line)
        elif block:
            _process_block(block)
            block = []
    if block:
        _process_block(block)

    return frozenset(names)


def list_touch_devices(
    runner: CommandRunner,
    x_display: "str | None" = None,
    xauthority: "str | None" = None,
) -> "tuple[TouchDevice, ...]":
    """คืน touchscreen devices ที่ detect ได้พร้อม xinput ID

    ลำดับการ detect:
    1. ใช้ udevadm เป็นแหล่งชื่อหลัก (kernel-level, ไม่ต้องพึ่ง session)
    2. Cross-ref กับ xinput list เพื่อให้ได้ xinput ID
    3. ถ้า udevadm ไม่มี touchscreen -> fallback กรอง xinput ด้วย "touch" ใน name
    """
    configurator = DisplayConfigurator(runner)
    xinput_result = runner.run(
        configurator._with_x_env(["xinput", "list"], x_display, xauthority),
        check=False,
    )
    xinput_map = parse_xinput_device_map(xinput_result.stdout)
    udev_names = get_udevadm_touchscreen_names(runner)

    if udev_names:
        return tuple(
            TouchDevice(name=name, xinput_id=xinput_map.get(name))
            for name in sorted(udev_names)
        )
    return tuple(
        TouchDevice(name=name, xinput_id=id_)
        for name, id_ in sorted(xinput_map.items())
        if "touch" in name.lower()
    )


# ---------------------------------------------------------------------------
# Ownership helper
# ---------------------------------------------------------------------------

def _chown_to_effective_user(path: Path) -> None:
    """chown ไฟล์ไปให้ SUDO_USER เมื่อ process รันเป็น root"""
    if not (hasattr(os, "geteuid") and os.geteuid() == 0):
        return
    sudo_user = os.environ.get("SUDO_USER", "").strip()
    if not sudo_user or sudo_user == "root":
        return
    try:
        import pwd
        pw = pwd.getpwnam(sudo_user)  # type: ignore[attr-defined]
        os.chown(path, pw.pw_uid, pw.pw_gid)  # type: ignore[attr-defined]
    except (ImportError, KeyError, OSError):
        pass


# ---------------------------------------------------------------------------
# Pure builders
# ---------------------------------------------------------------------------

def matrix_for_rotation(rotate: str) -> "tuple[str, ...]":
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
    x_display: "str | None",
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


def build_screen_blank_commands(seconds: int) -> "tuple[tuple[str, ...], ...]":
    """คืนชุดคำสั่ง xset สำหรับตั้งเวลา screen blank / DPMS

    seconds <= 0  -> ปิดการ blank ทั้งหมด (เทียบเท่า GNOME "Never")
    seconds > 0   -> ตั้ง screensaver timeout และ DPMS standby/suspend/off ที่ค่าเดียวกัน
    """
    if seconds <= 0:
        return (
            ("xset", "s", "off"),
            ("xset", "s", "noblank"),
            ("xset", "-dpms"),
        )
    value = str(int(seconds))
    return (
        ("xset", "s", value, value),
        ("xset", "s", "blank"),
        ("xset", "+dpms"),
        ("xset", "dpms", value, value, value),
    )


def build_screen_blank_block(seconds: int) -> str:
    command_lines = "\n".join(shlex.join(cmd) for cmd in build_screen_blank_commands(seconds))
    return (
        f"{SCREEN_BLANK_BEGIN}\n"
        "# Managed by vending-auto-setup. Manual edits inside this block may be overwritten.\n"
        f"{command_lines} || true\n"
        f"{SCREEN_BLANK_END}\n"
    )


def parse_xset_screen_blank_seconds(xset_query_output: str) -> "int | None":
    """Parse `xset q` output -> screensaver timeout (วินาที)

    รูปแบบที่ต้องการ:
        Screen Saver:
          prefer blanking:  yes    allow exposures:  yes
          timeout:  600    cycle:  600
    """
    match = re.search(r"timeout:\s*(\d+)\s+cycle:", xset_query_output)
    if not match:
        return None
    return int(match.group(1))


def get_screen_blank_seconds(
    runner: CommandRunner,
    x_display: "str | None" = None,
    xauthority: "str | None" = None,
) -> "int | None":
    """อ่านค่า screen blank timeout ปัจจุบันจาก `xset q`

    คืน None ถ้า `xset` ไม่มีในเครื่อง (เช่น dev บน Windows) หรือคำสั่งล้มเหลว —
    ตาม pattern เดียวกับ `_run_display_probe()` ใน server.py ที่ดักไม่ให้หน้า /display
    500 ตอนไม่มี X11 tools ให้เรียก
    """
    configurator = DisplayConfigurator(runner)
    try:
        result = runner.run(configurator._with_x_env(["xset", "q"], x_display, xauthority), check=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return parse_xset_screen_blank_seconds(result.stdout)


def build_gdm_wayland_config(existing_content: str, enabled: bool) -> str:
    lines = existing_content.splitlines()
    if not lines:
        if enabled:
            return "[daemon]\n#WaylandEnable=false\n"
        return "[daemon]\nWaylandEnable=false\n"

    daemon_start, daemon_end = _find_section_bounds(lines, "daemon")
    if daemon_start is None:
        block = ["[daemon]", "#WaylandEnable=false" if enabled else "WaylandEnable=false"]
        separator = [] if lines[-1].strip() == "" else [""]
        return "\n".join([*lines, *separator, *block]) + "\n"

    daemon_lines = lines[daemon_start + 1 : daemon_end]
    replacement = "#WaylandEnable=false" if enabled else "WaylandEnable=false"
    # หา WaylandEnable ทุกบรรทัดใน [daemon] ไม่ว่าจะ active หรือ comment อยู่ก็ตาม —
    # เดิม toggle จะมองแค่บรรทัด active แล้ว insert บรรทัดใหม่ทุกครั้งที่ไม่เจอ ทำให้
    # #WaylandEnable=false ที่ comment ไว้จากรอบก่อนหน้าค้างสะสมไม่ถูกลบ (ดู CHANGELOG)
    key_indexes = [
        index
        for index, line in enumerate(daemon_lines, start=daemon_start + 1)
        if _is_active_ini_key(line, "WaylandEnable", allow_commented=True)
    ]

    updated = list(lines)
    if key_indexes:
        first_index, *duplicate_indexes = key_indexes
        updated[first_index] = replacement
        for index in sorted(duplicate_indexes, reverse=True):
            del updated[index]
    elif not enabled:
        updated.insert(daemon_start + 1, "WaylandEnable=false")

    return "\n".join(updated) + "\n"


def _find_section_bounds(lines: list[str], section_name: str) -> tuple[int | None, int]:
    normalized_section = section_name.lower()
    start: int | None = None
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not (line.startswith("[") and line.endswith("]")):
            continue
        current_section = line[1:-1].strip().lower()
        if start is None:
            if current_section == normalized_section:
                start = index
            continue
        return start, index
    return start, len(lines)


def _is_active_ini_key(line: str, key: str, allow_commented: bool = False) -> bool:
    """เช็คว่าบรรทัดนี้เป็น `key=value` (INI) หรือไม่

    ปกติจะนับเฉพาะบรรทัด active (ไม่ได้ comment ด้วย # หรือ ;) — แต่ถ้า
    `allow_commented=True` จะ strip comment marker ออกก่อนเช็ค key ด้วย
    เพื่อใช้หาบรรทัดที่เคย comment ทิ้งไว้จาก toggle รอบก่อนๆ (กัน key สะสมซ้ำ)
    """
    stripped = line.strip()
    if allow_commented:
        while stripped.startswith(("#", ";")):
            stripped = stripped[1:].strip()
    elif stripped.startswith(("#", ";")):
        return False
    if not stripped or "=" not in stripped:
        return False
    found_key, _ = stripped.split("=", 1)
    return found_key.strip().lower() == key.lower()


def upsert_managed_block(
    existing_content: str,
    managed_block: str,
    begin: str = DISPLAY_SESSION_BEGIN,
    end: str = DISPLAY_SESSION_END,
) -> str:
    if begin not in existing_content:
        separator = "\n" if existing_content and not existing_content.endswith("\n") else ""
        return f"{existing_content}{separator}{managed_block}"

    start = existing_content.index(begin)
    end_index = existing_content.find(end, start)
    if end_index == -1:
        return f"{existing_content.rstrip()}\n{managed_block}"

    end_index += len(end)
    if end_index < len(existing_content) and existing_content[end_index : end_index + 1] == "\n":
        end_index += 1
    return f"{existing_content[:start]}{managed_block}{existing_content[end_index:]}"


def remove_managed_block(
    existing_content: str,
    begin: str = DISPLAY_SESSION_BEGIN,
    end: str = DISPLAY_SESSION_END,
) -> str:
    if begin not in existing_content:
        return existing_content

    start = existing_content.index(begin)
    end_index = existing_content.find(end, start)
    if end_index == -1:
        return existing_content

    end_index += len(end)
    if end_index < len(existing_content) and existing_content[end_index : end_index + 1] == "\n":
        end_index += 1
    return f"{existing_content[:start]}{existing_content[end_index:]}"
