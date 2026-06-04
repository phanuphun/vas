#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from dataclasses import dataclass

try:
    from evdev import AbsInfo, UInput, ecodes
except ModuleNotFoundError:
    print("Missing dependency: python3-evdev", file=sys.stderr)
    print("Install it with: sudo apt update && sudo apt install -y python3-evdev", file=sys.stderr)
    raise SystemExit(1)


@dataclass(frozen=True)
class TouchscreenConfig:
    name: str
    width: int
    height: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a virtual touchscreen through Linux uinput.")
    parser.add_argument("--name", default="Vending Virtual Touchscreen")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--tap", nargs=2, type=int, metavar=("X", "Y"), help="Emit one tap after creating the device.")
    parser.add_argument("--hold-seconds", type=float, default=0.12, help="Touch hold duration for --tap.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if os.geteuid() != 0:
        print("Run as root: sudo python3 scripts/dev/virtual_touchscreen.py", file=sys.stderr)
        return 1

    config = TouchscreenConfig(name=args.name, width=args.width, height=args.height)
    with create_virtual_touchscreen(config) as device:
        print(f"Created virtual touchscreen: {config.name}")
        print(f"Device path: {device.devnode}")
        print("Check with: xinput list")

        if args.tap is not None:
            x, y = args.tap
            emit_tap(device, x, y, args.hold_seconds)
            print(f"Emitted tap at ({x}, {y})")
            return 0

        print("Keeping device alive. Press Ctrl+C to stop.")
        wait_until_interrupted()
    return 0


def create_virtual_touchscreen(config: TouchscreenConfig) -> UInput:
    max_x = config.width - 1
    max_y = config.height - 1
    capabilities = {
        ecodes.EV_KEY: [ecodes.BTN_TOUCH],
        ecodes.EV_ABS: [
            (ecodes.ABS_X, AbsInfo(0, 0, max_x, 0, 0, 0)),
            (ecodes.ABS_Y, AbsInfo(0, 0, max_y, 0, 0, 0)),
            (ecodes.ABS_MT_POSITION_X, AbsInfo(0, 0, max_x, 0, 0, 0)),
            (ecodes.ABS_MT_POSITION_Y, AbsInfo(0, 0, max_y, 0, 0, 0)),
            (ecodes.ABS_MT_TRACKING_ID, AbsInfo(0, 0, 65535, 0, 0, 0)),
        ],
    }
    return UInput(
        capabilities,
        name=config.name,
        bustype=ecodes.BUS_USB,
        vendor=0x1209,
        product=0x0001,
        version=1,
        input_props=[ecodes.INPUT_PROP_DIRECT],
    )


def emit_tap(device: UInput, x: int, y: int, hold_seconds: float) -> None:
    tracking_id = int(time.time() * 1000) % 65535
    device.write(ecodes.EV_ABS, ecodes.ABS_X, x)
    device.write(ecodes.EV_ABS, ecodes.ABS_Y, y)
    device.write(ecodes.EV_ABS, ecodes.ABS_MT_TRACKING_ID, tracking_id)
    device.write(ecodes.EV_ABS, ecodes.ABS_MT_POSITION_X, x)
    device.write(ecodes.EV_ABS, ecodes.ABS_MT_POSITION_Y, y)
    device.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, 1)
    device.syn()
    time.sleep(hold_seconds)
    device.write(ecodes.EV_KEY, ecodes.BTN_TOUCH, 0)
    device.write(ecodes.EV_ABS, ecodes.ABS_MT_TRACKING_ID, -1)
    device.syn()


def wait_until_interrupted() -> None:
    interrupted = False

    def handle_signal(_signal_number: int, _frame: object) -> None:
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    while not interrupted:
        time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
