---
name: zkteco-qr500
description: >
  Expert skill for reading the ZKTeco QR500-BM QR/RFID reader on Linux, covering both of its
  wire-level reading modes: USB HID (/dev/hidraw*) and RS485 Serial (/dev/ttyUSB*), plus how to
  tell an RFID card tap apart from a QR code scan when reading over RS485. Use this skill
  whenever the user asks about: reading from /dev/hidraw*, HID keyboard mode, decoding HID
  keyboard reports, reading from /dev/ttyUSB* or a USB-to-RS485/RS232 adapter, idle-timeout
  framing for a serial stream with no terminator, distinguishing RFID vs QR (scan_source),
  Mifare UID extraction from a binary frame, or ZKTeco QR500-BM device discovery/permissions
  (udev rules, plugdev/dialout groups). Also triggers on keywords: QR500, hidraw, ttyUSB,
  RS485, Mifare, RFID frame, STX frame, ZKTeco DEMO software.
---

# ZKTeco QR500-BM — Reading QR Codes and RFID Cards on Linux

This skill covers **reading raw scan data from the device only** — device discovery, opening
the device, and turning raw bytes into a scan string (plus, for RS485, telling RFID apart from
QR). It does not cover what you do with the scan afterwards (HTTP webhook, MQTT, etc.) — that's
a separate, downstream concern.

The device exposes **two independent wire-level reading modes** picked via a setting on the
device itself (ZKTeco DEMO software, Windows-only, connect over USB-HID first to configure).
Each mode needs a completely different Linux-side implementation:

| | USB HID | RS485 Serial |
|---|---|---|
| Linux device path | `/dev/hidraw*` | `/dev/ttyUSB*` (via USB-to-RS485/RS232 adapter) |
| Device setting required | `HID keyboard` = **Close** | `RS485 function switch` = **Open**, `RS485 automatic upload` = **Open** |
| End-of-scan marker | Enter keycode (`0x28`) in the report | **None at all** — must use idle-timeout framing |
| Can separate RFID vs QR? | **No, never** | **Yes** — see "Scan source detection" below |
| Full detail | `references/hid-mode.md` | `references/serial-mode.md` |

---

## Mode 1 — USB HID (`/dev/hidraw*`)

The device presents as a USB HID device. With `HID keyboard = Close` it sends raw HID keyboard
reports instead of emulating a real keyboard — read them directly with `os.read()`, no root/
native library needed.

Quick facts (see `references/hid-mode.md` for the full byte layout, keycode map, and device
discovery code):

- Confirmed VendorID:ProductID for this device family: `0416:5020` (verify with
  `cat /sys/class/hidraw/hidrawN/device/uevent`, look for `HID_ID=0003:00000416:00005020` —
  other firmware batches/resellers have been reported with different IDs, e.g. `1b55:0c45`,
  so always verify against the actual unit rather than assuming)
- Read 64-byte reports with blocking `os.read(fd, 64)` in a background thread
- `report[0]` = shift modifier bitmask, `report[2:8]` = up to 6 simultaneous keycodes, keycode
  `40` = Enter = end of one scan
- ⚠️ **Byte offsets vary by firmware revision.** A conflicting convention (`report[2]`=modifier,
  `report[4:10]`=keycodes) has also been seen on nominally-identical hardware. Never assume —
  capture with `sudo hexdump -C /dev/hidrawN` while scanning before trusting either layout.
- `hidrawN` numbering is **not stable** across reboot/replug — resolve the path via a persistent
  udev symlink or by matching VendorID/ProductID at startup, never hardcode a number

### Hard limitation: RFID and QR are indistinguishable in this mode

A card tap and a QR scan produce the **exact same kind of keycode report stream** — there is no
field, flag, or byte anywhere in a HID report that says which one it was. If a caller needs to
know the scan source, **this mode cannot provide it, period** — the RS485 Serial mode must be
used instead (see below), or an external signal (e.g. a second physical RFID-only reader) is
needed.

---

## Mode 2 — RS485 Serial (`/dev/ttyUSB*`)

The device speaks over RS485 (A/B lines) through a USB-to-RS485/RS232 adapter — the Linux device
node that appears is the **adapter's**, not the QR500-BM's own. Requires the device's `RS485
function switch` and `RS485 automatic upload` both set to `Open` via DEMO software first.

Quick facts (see `references/serial-mode.md` for the full idle-timeout framing implementation
and adapter discovery code):

- Confirmed adapter chip in this project: FTDI FT232R, `VendorID:ProductID = 0403:6001` — this
  identifies the **adapter**, not the QR500-BM; a different adapter brand/chip needs different
  IDs matched against `idVendor`/`idProduct` two directory levels up from `/sys/class/tty/ttyUSBn`
- Default baud: `115200`, `8N1`, no parity, no flow control — configure via `termios` directly
  (no `pyserial` needed)
- ⚠️ **There is no terminator character anywhere in the stream** — not for QR text, not for RFID
  frames. Confirmed by capturing 155+ raw bytes and checking every byte for CR/LF/NUL/STX/ETX:
  none present. The only reliable way to know one scan has ended is **idle-timeout framing**:
  if no new byte arrives within a configurable window (default `150ms`) and the buffer has data,
  treat it as one complete scan and flush.
- `ttyUSBn` numbering is **not stable** either — same caveat as `hidrawN` above, resolve via
  symlink or adapter VendorID/ProductID match

### Scan source detection (RFID vs QR) — RS485 mode only

Confirmed from a real hardware capture (2026-07-27, via a serial terminal tool connected directly
to the RS485 line): the two scan types are **byte-level distinguishable**, not just by
length/character-set guessing:

- **QR scans** arrive as plain printable ASCII/UTF-8 text (e.g. a UUID string, a ticket number,
  a URL — whatever the QR content is)
- **RFID card taps** arrive as a **fixed 16-byte binary frame per tap**, always starting with
  **STX (`0x02`)**, containing a 4-byte card UID at a fixed offset. Bytes in this frame (e.g.
  `0x83`, `0xF6`, `0xB3`) are not valid UTF-8, so the two are trivially distinguishable at the
  byte level — check "does this buffer look like N×16 bytes, each chunk starting with STX?"
  rather than trying to interpret decoded text.

Full frame layout, the classifier function, and confirmed test data → `references/scan-source-detection.md`

⚠️ **Verified against only 4 physical Mifare cards and 1 QR sample (a UUID string) so far.**
Before relying on this in production, test more QR content types — especially QR payloads that
are pure digits or pure hex, since a coincidental match starting with byte `0x02` is the one
scenario that could fool the classifier. Also not yet verified: whether the idle-timeout window
correctly separates two RFID taps done in very rapid succession (faster than the timeout).

---

## Reference

- `references/hid-mode.md` — HID device discovery, exact byte layout, full keycode map
- `references/serial-mode.md` — RS485 adapter discovery, idle-timeout framing, termios raw config
- `references/scan-source-detection.md` — RFID frame byte layout, classifier logic, confirmed test data, caveats
- `references/demo-software-params.md` — ZKTeco DEMO software (Windows) parameter reference for configuring the device before any Linux integration
