from __future__ import annotations

import subprocess

from fastmcp import FastMCP

from status import (
    collect_display_session_config_status,
    collect_display_session_script_status,
    collect_display_session_status,
    collect_gdm_wayland_status,
    collect_xorg_touchscreen_config_status,
)

mcp = FastMCP("vas-display")


@mcp.tool()
def get_display_status() -> dict:
    """สถานะ display session (X11/Wayland), GDM config และ touchscreen config"""
    try:
        session = collect_display_session_status()
        gdm = collect_gdm_wayland_status()
        touch_cfg = collect_xorg_touchscreen_config_status()
        disp_cfg = collect_display_session_config_status()
        disp_script = collect_display_session_script_status()
        return {
            "session": {
                "session_type": session.session_type,
                "is_x11": session.is_x11,
                "source": session.source,
            },
            "gdm_wayland": {
                "path": gdm.path.as_posix(),
                "exists": gdm.exists,
                "readable": gdm.readable,
                "disabled": gdm.disabled,
                "value": gdm.value,
            },
            "touchscreen_config": {
                "path": touch_cfg.path.as_posix(),
                "exists": touch_cfg.exists,
                "has_signature": touch_cfg.has_signature,
            },
            "display_config": {
                "path": disp_cfg.path.as_posix(),
                "exists": disp_cfg.exists,
                "has_signature": disp_cfg.has_signature,
            },
            "display_script": {
                "path": disp_script.path.as_posix(),
                "exists": disp_script.exists,
                "has_signature": disp_script.has_signature,
                "executable": disp_script.executable,
            },
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_usb_devices() -> dict:
    """รายการ USB devices ที่เชื่อมต่ออยู่ รวมถึง touchscreen"""
    try:
        devices = _list_usb_devices()
        touchscreen_names = _get_touchscreen_names()
        return {
            "devices": devices,
            "touchscreen_names": sorted(touchscreen_names),
        }
    except Exception as e:
        return {"error": str(e)}


def _list_usb_devices() -> list[dict]:
    try:
        result = subprocess.run(
            ["lsusb"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []

    devices = []
    for line in result.stdout.splitlines():
        # Format: Bus 001 Device 003: ID 0eef:0001 D-WAV Scientific Co., Ltd eGalax TouchScreen
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            bus = parts[1]
            device = parts[3].rstrip(":")
            device_id = parts[5]
            description = " ".join(parts[6:])
            devices.append({"bus": bus, "device": device, "id": device_id, "description": description})
        except IndexError:
            continue
    return devices


def _get_touchscreen_names() -> list[str]:
    try:
        result = subprocess.run(
            ["udevadm", "info", "--export-db"],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []

    if result.returncode != 0:
        return []

    names: set[str] = set()
    block: list[str] = []

    def _process_block(lines: list[str]) -> None:
        if any(line == "E: ID_INPUT_TOUCHSCREEN=1" for line in lines):
            for line in lines:
                if line.startswith("E: NAME="):
                    name = line[len("E: NAME="):].strip().strip('"')
                    if name:
                        names.add(name)

    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            _process_block(block)
            block = []
        else:
            block.append(stripped)

    if block:
        _process_block(block)

    return list(names)
