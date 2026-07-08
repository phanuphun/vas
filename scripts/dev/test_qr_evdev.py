#!/usr/bin/env python3
"""
Dev script: ทดสอบ ZKTeco ZKRFID R400 ผ่าน evdev (HID keyboard = Open mode)

ใช้ device.grab() เพื่อป้องกัน keystrokes ไม่ให้รบกวน UI / touchscreen

Usage:
    sudo python3 scripts/dev/test_qr_evdev.py

Requirements:
    sudo apt install -y python3-evdev
"""
from __future__ import annotations

import argparse
import os
import signal
import sys

try:
    import evdev
except ModuleNotFoundError:
    print("Missing dependency: python3-evdev", file=sys.stderr)
    print("Install: sudo apt update && sudo apt install -y python3-evdev", file=sys.stderr)
    raise SystemExit(1)

DEVICE_NAMES = ["ZKRFID", "ZK", "QR500"]

KEYMAP: dict[int, str] = {
    2: "1", 3: "2", 4: "3", 5: "4", 6: "5",
    7: "6", 8: "7", 9: "8", 10: "9", 11: "0",
    16: "q", 17: "w", 18: "e", 19: "r", 20: "t",
    21: "y", 22: "u", 23: "i", 24: "o", 25: "p",
    30: "a", 31: "s", 32: "d", 33: "f", 34: "g",
    35: "h", 36: "j", 37: "k", 38: "l",
    44: "z", 45: "x", 46: "c", 47: "v", 48: "b",
    49: "n", 50: "m",
    12: "-", 13: "=", 26: "[", 27: "]",
    39: ";", 40: "'", 51: ",", 52: ".", 53: "/",
}

# Shift-variant ของ KEYMAP -- ใช้เมื่อ Left/Right Shift ถูกกดค้างอยู่
SHIFT_KEYMAP: dict[int, str] = {
    2: "!", 3: "@", 4: "#", 5: "$", 6: "%",
    7: "^", 8: "&", 9: "*", 10: "(", 11: ")",
    16: "Q", 17: "W", 18: "E", 19: "R", 20: "T",
    21: "Y", 22: "U", 23: "I", 24: "O", 25: "P",
    30: "A", 31: "S", 32: "D", 33: "F", 34: "G",
    35: "H", 36: "J", 37: "K", 38: "L",
    44: "Z", 45: "X", 46: "C", 47: "V", 48: "B",
    49: "N", 50: "M",
    12: "_", 13: "+", 26: "{", 27: "}",
    39: ":", 40: '"', 51: "<", 52: ">", 53: "?",
}

# evdev scancode ของ Left/Right Shift (KEY_LEFTSHIFT=42, KEY_RIGHTSHIFT=54)
SHIFT_SCANCODES = {42, 54}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test ZKTeco ZKRFID R400 QR reader via evdev (HID keyboard mode)."
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Path to input device (e.g. /dev/input/event6). Auto-detect if omitted.",
    )
    parser.add_argument(
        "--no-grab",
        action="store_true",
        help="Do not grab device (keystrokes will reach OS — for debugging only).",
    )
    return parser


def find_qr_device() -> evdev.InputDevice:
    """ค้นหา ZKTeco device อัตโนมัติจาก /dev/input/event*"""
    devices = [evdev.InputDevice(p) for p in evdev.list_devices()]
    # เลือก device ที่มีชื่อ ZKTeco และรองรับ EV_KEY
    candidates = [
        d for d in devices
        if any(name in d.name.upper() for name in DEVICE_NAMES)
        and evdev.ecodes.EV_KEY in d.capabilities()
    ]
    if not candidates:
        raise RuntimeError(
            "ไม่พบ ZKTeco QR reader\n"
            "ตรวจสอบ:\n"
            "  1. เสียบ USB และ pass ไป VirtualBox แล้วหรือยัง\n"
            "  2. HID keyboard = Open ใน ZKTeco DEMO software\n"
            "  3. รัน: ls /dev/input/event*  และ  sudo evtest"
        )
    # เลือก interface แรก (event number ต่ำสุด)
    return sorted(candidates, key=lambda d: d.path)[0]


def run(device_path: str | None, grab: bool) -> int:
    if os.geteuid() != 0:
        print("Run as root: sudo python3 scripts/dev/test_qr_evdev.py", file=sys.stderr)
        return 1

    try:
        if device_path:
            device = evdev.InputDevice(device_path)
        else:
            device = find_qr_device()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Device : {device.name}")
    print(f"Path   : {device.path}")
    print(f"Vendor : {hex(device.info.vendor)}:{hex(device.info.product)}")
    print(f"Grab   : {'yes (keystrokes blocked from OS)' if grab else 'no (debug mode)'}")
    print()
    print("รอ scan QR... (Ctrl+C เพื่อหยุด)")
    print("-" * 50)

    if grab:
        device.grab()

    interrupted = False

    def handle_signal(_sig: int, _frame: object) -> None:
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    buffer: list[str] = []
    scan_count = 0
    shift_pressed = False

    try:
        for event in device.read_loop():
            if interrupted:
                break
            if event.type != evdev.ecodes.EV_KEY:
                continue
            key = evdev.categorize(event)
            if key.scancode in SHIFT_SCANCODES:
                if key.keystate == evdev.KeyEvent.key_down:
                    shift_pressed = True
                elif key.keystate == evdev.KeyEvent.key_up:
                    shift_pressed = False
                continue
            if key.keystate != evdev.KeyEvent.key_down:
                continue
            if key.scancode == 28:  # KEY_ENTER = จบ QR
                if buffer:
                    data = "".join(buffer)
                    scan_count += 1
                    print(f"[#{scan_count}] {data}")
                    buffer.clear()
                shift_pressed = False
            else:
                keymap = SHIFT_KEYMAP if shift_pressed else KEYMAP
                if key.scancode in keymap:
                    buffer.append(keymap[key.scancode])
    finally:
        if grab:
            try:
                device.ungrab()
            except Exception:
                pass
        print(f"\nหยุดแล้ว — scan ทั้งหมด {scan_count} ครั้ง")

    return 0


def main() -> int:
    args = build_parser().parse_args()
    return run(device_path=args.device, grab=not args.no_grab)


if __name__ == "__main__":
    raise SystemExit(main())
