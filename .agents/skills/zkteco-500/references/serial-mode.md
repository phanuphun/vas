# RS485 Serial Mode — Adapter Discovery, Idle-Timeout Framing

## Prerequisite: device setting (Windows, ZKTeco DEMO software)

**Basic Setting-1** → set both:

- `RS485 function switch` = **Open**
- `RS485 automatic upload` = **Open** (this is what makes the device push data on its own,
  without needing to be polled/queried)

Write configuration, then power-cycle and re-verify — this setting has been observed to revert
after a power cycle on at least one unit, which looks identical to a wiring fault from the
Linux/adapter side (both present as "zero bytes ever arrive"). If a previously-working setup
suddenly stops receiving anything, re-check this setting on the device itself before assuming a
software regression.

## Hardware notes

The QR500-BM talks RS485 (A/B differential pair) — it does not appear as its own USB device.
What Linux sees is the **USB-to-RS485/RS232 adapter** in between. Confirmed working with an FTDI
FT232R-based adapter (`VendorID:ProductID = 0403:6001`, default baud `115200`).

⚠️ FT232R is a plain TTL/RS232 UART chip, **not an RS485 transceiver by itself** — if your
adapter doesn't have a transceiver (e.g. MAX485) between the UART chip and the actual A/B lines,
the differential signal may not be read correctly. If you're seeing garbage or nothing at all
with a different adapter brand, check its datasheet for this first.

## Device discovery (adapter, not the QR500 itself)

Same instability problem as `hidrawN` — `ttyUSBn` numbers change on reboot/replug. For a
`ttyUSB` node, the vendor/product ID files live **two directory levels above** the device
symlink (because the immediate parent is the USB *interface*, not the USB *device*):

```python
import glob
from pathlib import Path

ADAPTER_VENDOR_ID, ADAPTER_PRODUCT_ID = "0403", "6001"  # FTDI FT232R

def find_serial_adapter_devices() -> list[str]:
    results = []
    for tty_path in sorted(glob.glob("/sys/class/tty/ttyUSB*")):
        vendor_file = Path(tty_path) / "device" / ".." / ".." / "idVendor"
        product_file = Path(tty_path) / "device" / ".." / ".." / "idProduct"
        try:
            vendor_id = vendor_file.read_text(encoding="utf-8").strip().lower()
            product_id = product_file.read_text(encoding="utf-8").strip().lower()
        except OSError:
            continue
        if vendor_id == ADAPTER_VENDOR_ID and product_id == ADAPTER_PRODUCT_ID:
            results.append(f"/dev/{tty_path.split('/')[-1]}")
    return results
```

Verify against real hardware with `udevadm info -a` before trusting this path — composite/
multi-interface adapters can complicate which sysfs level actually holds the IDs.

## Capture raw bytes before writing any parser

ZKTeco does not publish the RS485 frame spec — always capture and inspect raw bytes on the
actual unit before writing a parser, the same way you would for HID mode:

```bash
sudo usermod -aG dialout $USER   # once, then log out/in
sudo stty -F /dev/ttyUSB0 115200 cs8 -cstopb -parenb raw
sudo timeout 30 cat /dev/ttyUSB0 > /tmp/capture.bin   # scan a few times during this window
xxd /tmp/capture.bin
```

## Why idle-timeout framing (not a terminator)

Confirmed by capturing 150+ raw bytes across multiple scans and checking every single byte for
CR, LF, NUL, STX, ETX: **none are present, anywhere, for either QR text or RFID frames.** There
is no character that reliably marks "this scan is done." The workable signal instead is timing:
during one scan the device writes bytes back-to-back with only a few milliseconds of gap
(observed: ~12ms between chunks of the same scan), but between two separate scans there's a much
longer silence (observed: >1.6s for a human tapping/scanning at a normal pace).

**Idle-timeout framing:** buffer every byte that arrives; if the buffer has data and no new byte
arrives within a configurable window (default `150ms`), treat the buffer as one complete scan
and flush it.

```python
import os, select, termios, threading

def configure_raw_serial(fd: int, baud_const: int) -> None:
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(fd)
    cflag = (cflag & ~termios.CSIZE) | termios.CS8
    cflag &= ~termios.PARENB
    cflag &= ~termios.CSTOPB
    cflag |= termios.CLOCAL | termios.CREAD
    iflag = oflag = lflag = 0
    ispeed = ospeed = baud_const
    cc[termios.VMIN] = 0
    cc[termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, ispeed, ospeed, cc])

def read_loop(device_path: str, baud_const: int, idle_timeout_seconds: float, on_scan):
    buffer = bytearray()
    fd = os.open(device_path, os.O_RDONLY | os.O_NOCTTY)
    configure_raw_serial(fd, baud_const)
    while True:
        readable, _, _ = select.select([fd], [], [], idle_timeout_seconds)
        if fd in readable:
            chunk = os.read(fd, 4096)
            if chunk:
                buffer.extend(chunk)
            continue
        # select() timed out with no new byte -> idle window elapsed
        if buffer:
            on_scan(bytes(buffer))
            buffer.clear()
```

This uses only `termios`/`select`/`os` — no `pyserial` dependency needed, matching the same
"stdlib-only" approach as the HID mode's `os.read()` loop.

⚠️ **Not yet verified:** whether `150ms` correctly separates two scans of the exact same QR code
(or two RFID taps) done very quickly back-to-back, faster than the idle window. Test this
specifically before relying on the default in a high-throughput scenario — a too-short timeout
risks splitting one scan into two; a too-long timeout risks merging two fast scans into one
(which the RFID frame parser in `references/scan-source-detection.md` would then reject outright
since the combined buffer would still be a clean multiple of the 16-byte frame size, so this
specific failure mode is more of a QR-mode risk than an RFID-mode one).

## What comes out — no keycode/HID-report concept exists here

Unlike HID mode, this mode never produces "keycodes" or "HID reports" — the closest analog to
"the most raw layer available" is the hex dump of the byte buffer right before it gets decoded/
stripped, kept around in case something in it doesn't survive a UTF-8 decode cleanly (see
`references/scan-source-detection.md` — this is exactly the case for RFID frames).
