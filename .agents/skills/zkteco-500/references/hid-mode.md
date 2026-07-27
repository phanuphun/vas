# USB HID Mode — Device Discovery, Byte Layout, Keycode Map

## Prerequisite: device setting (Windows, ZKTeco DEMO software)

1. Connect the reader via USB → open ZKTeco DEMO software → select the **USB-HID** port → OK
2. **Basic Setting-1** → set `HID keyboard` = **Close** → Write configuration

`HID keyboard = Close` makes the device send raw HID reports instead of emulating a real
keyboard. With `Open`, every scan is typed as keystrokes into whatever window currently has
focus — unusable for a headless service, since it depends on window focus and races with
anything else that might be typing.

## Device discovery

Never hardcode `/dev/hidraw0` — the number is reassigned on every reboot/USB replug. Resolve it
by walking `/sys/class/hidraw/*/device/uevent` and matching the `HID_ID` line:

```
HID_ID=<bus>:<vendorId, 8 hex digits, zero-padded>:<productId, 8 hex digits, zero-padded>
```

Confirmed for this device family: `HID_ID=0003:00000416:00005020` → VendorID `0416`, ProductID
`5020` (strip the zero-padding, compare lowercase). Example resolution order, most specific
first:

1. Explicit override (env var / config), if set
2. A persistent udev symlink you've set up (e.g. `/dev/zkteco-qr500`) — stable across reboots
3. Auto-detect: scan every `hidraw*` node's `uevent`, pick the first one whose `HID_ID` matches

```python
import glob
from pathlib import Path

VENDOR_ID, PRODUCT_ID = "0416", "5020"

def find_zkteco_hidraw_devices() -> list[str]:
    results = []
    for uevent_path in sorted(glob.glob("/sys/class/hidraw/*/device/uevent")):
        content = Path(uevent_path).read_text(encoding="utf-8")
        for line in content.splitlines():
            if not line.startswith("HID_ID="):
                continue
            _, vendor_hex, product_hex = line[len("HID_ID="):].split(":")
            vendor_id = format(int(vendor_hex, 16), "04x")
            product_id = format(int(product_hex, 16), "04x")
            if vendor_id == VENDOR_ID.lower() and product_id == PRODUCT_ID.lower():
                node_name = uevent_path.split("/")[4]  # .../hidraw2/device/uevent -> hidraw2
                results.append(f"/dev/{node_name}")
    return results
```

## udev rule (avoid needing root)

```
# /etc/udev/rules.d/99-zkteco-qr500.rules
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5020", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb",    ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5020", MODE="0664", GROUP="plugdev"
```

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG plugdev $USER   # then log out/in
```

⚠️ If the device is a **composite USB device** (multiple HID interfaces, e.g. one for raw data
and one that emulates a keyboard), a rule that only filters on `idVendor`/`idProduct` will match
*every* interface at once, since those two values are identical across all interfaces of the
same physical device. If you need to pin a specific interface, filter on `ENV{DEVPATH}` (which
encodes the USB interface number) instead of `ATTRS{}`.

## Byte layout (confirmed on real hardware for this project)

Read fixed-size reports (typically 64 bytes) with a **blocking** `os.read()` call in a background
thread — no busy-loop, no native extension needed:

```
byte[0]    = modifier bitmask  (0x02 = left shift, 0x20 = right shift)
byte[1]    = reserved
byte[2..7] = up to 6 simultaneous keycodes, 0 = empty slot
```

```python
import os

REPORT_SIZE = 64
ENTER_KEYCODE = 40
SHIFT_MASK = 0x22  # left shift (0x02) | right shift (0x20)

def decode_hid_report(report: bytes, keymap: dict[int, str], shift_keymap: dict[int, str]) -> str:
    if len(report) < 3:
        return ""
    shift = bool(report[0] & SHIFT_MASK)
    active_map = shift_keymap if shift else keymap
    chars = []
    for keycode in report[2:8]:
        if keycode in (0, ENTER_KEYCODE):
            continue
        char = active_map.get(keycode)
        if char is not None:
            chars.append(char)
    return "".join(chars)

def report_has_enter(report: bytes) -> bool:
    return ENTER_KEYCODE in report[2:8]

# Main read loop (run in a daemon thread)
with open(device_path, "rb") as fd:
    buffer = ""
    while True:
        report = os.read(fd.fileno(), REPORT_SIZE)
        if len(report) < 3:
            continue
        buffer += decode_hid_report(report, KEYCODE_MAP, KEYCODE_SHIFT_MAP)
        if report_has_enter(report) and buffer:
            last_scan = buffer.strip()   # one complete scan
            buffer = ""
```

⚠️ **This exact offset (`byte[0]`=modifier, keycodes at `byte[2:8]`) is what was confirmed on
real hardware for this project** — matches the general USB HID Boot Keyboard spec (modifier at
offset 0, keycodes starting at offset 2). A different, non-standard offset (`byte[2]`=modifier,
keycodes at `byte[4:10]`) has also been reported for nominally the same model on different
firmware/hardware batches. **Always verify with `sudo hexdump -C /dev/hidrawN` while scanning
before trusting either convention on a new unit.**

## Keycode → character map (Keyboard Usage Page 0x07)

Unshifted:

```
4-29:  a-z              30-38: 1-9    39: 0
40:    Enter (end-of-scan marker, not a character)
44:    space   45: -    46: =    47: [    48: ]    49: \
51:    ;       52: '    53: `    54: ,    55: .    56: /
57:    (CapsLock — skip, not a character)
```

Shifted (when `byte[0] & 0x22 != 0`):

```
4-29:  A-Z              30-38: ! @ # $ % ^ & * (   39: )
45: _   46: +   47: {   48: }   49: |
51: :   52: "   53: ~   54: <   55: >   56: ?
```

An unrecognized keycode should be skipped silently, not raise an error — unknown/vendor-specific
keycodes do show up occasionally and a hard failure would kill the whole reader thread over one
bad byte.

## Hard limitation: cannot distinguish RFID from QR

There is no field anywhere in this report format that indicates whether the scan came from
tapping an RFID card or scanning a QR code — both produce the identical kind of keycode stream.
If the caller needs to know the source, this mode cannot provide it; use RS485 Serial mode
instead (see `references/serial-mode.md` and `references/scan-source-detection.md`).

## Debug checklist

```bash
# Confirm the device is detected and get its VendorID/ProductID
lsusb | grep -i ZK
cat /sys/class/hidraw/hidrawN/device/uevent   # look for HID_ID=...

# Permission denied?
ls -la /dev/hidraw*        # want crw-rw-rw- or crw-rw---- with plugdev group
groups $USER                # confirm plugdev membership
sudo udevadm control --reload-rules && sudo udevadm trigger

# No data at all, or garbled data?
sudo hexdump -C /dev/hidrawN   # scan while this is running, inspect raw bytes directly
```

If nothing prints while scanning: check whether `HID keyboard` is actually set to `Close` on the
device (not just assumed) — some units default to `Open`, and a firmware setting can silently
revert after a power cycle.
