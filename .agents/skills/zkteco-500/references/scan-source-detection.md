# Scan Source Detection — Telling RFID Apart from QR (RS485 Serial Mode Only)

This only applies to RS485 Serial mode (`/dev/ttyUSB*`) — see the SKILL.md "Mode 1" section for
why USB HID mode can never do this at all.

## Confirmed pattern (real hardware capture, 2026-07-27)

Captured via a serial terminal tool connected directly to the RS485 line at `115200` baud (not
through the read-loop code — a raw capture, to rule out any software bug before trusting the
pattern):

- **QR scans** → plain printable ASCII/UTF-8 text. Example captured value: a UUID string
  (`a5160aff-c32f-40c5-ac58-41651e70e6b4`).
- **RFID card taps** → a fixed **16-byte binary frame per tap**, always starting with **STX
  (`0x02`)**:

  ```
  02 <addr> 01 09 00 [UID, 4 bytes] <addr> 1A 88 39 05 [suffix, 2 bytes]
  ```

  `<addr>` matches the device's configured **RS485 Address** (Basic Setting-1 in DEMO software —
  observed as `0x64` = 100 decimal on the test unit; this is device-specific configuration, not
  a fixed protocol constant, so don't hardcode a specific address value in a classifier).

Four distinct UIDs were extracted from four physical Mifare cards, confirmed stable across
repeated taps of the same card:

| UID (hex) | Suffix observed |
|---|---|
| `83F638F5` | `2FEC` (stable across repeats) |
| `234949FA` | `FD27` (stable across repeats) |
| `71899A27` | `E454` first tap, `FD27` second tap — **UID stable, suffix not** |
| `B3E125FD` | `F74E` (stable across repeats) |

The trailing 2-byte suffix is **not** always stable for a repeated tap of the same physical card
(see `71899A27` above) — likely some kind of rolling counter or checksum that includes more than
just the UID. This is harmless for classification purposes since the classifier only checks for
the STX marker and frame length, never the suffix value — but don't rely on the suffix as a
stable identifier the way you can rely on the 4-byte UID.

## Why this is more reliable than a length/character-set heuristic

The bytes inside an RFID frame (e.g. `0x83`, `0xF6`, `0xB3`, `0xE1`) are not valid UTF-8 —
attempting `bytes.decode("utf-8")` on one either raises or (with `errors="replace"`) produces a
buffer full of U+FFFD replacement characters. QR content, by construction, is always clean text.
So instead of guessing from length or "looks like it could be hex," check something structural:
does the whole buffer look like N complete 16-byte frames, and does every one of them start with
STX? That's a much harder pattern to produce by accident than "8 hex characters."

## Classifier

```python
RFID_FRAME_SIZE = 16
RFID_STX = 0x02
RFID_UID_OFFSET = 5
RFID_UID_LENGTH = 4

def classify_scan_source(buffer: bytes) -> tuple[str, list[str] | None]:
    """Returns ("RFID", [uid_hex, ...]) if buffer is a whole number of 16-byte frames each
    starting with STX; otherwise ("QR_CODE", None) as a safe fallback (never guess "RFID" on
    content that doesn't match the frame pattern exactly)."""
    if not buffer or len(buffer) % RFID_FRAME_SIZE != 0 or buffer[0] != RFID_STX:
        return "QR_CODE", None

    uids: list[str] = []
    for i in range(0, len(buffer), RFID_FRAME_SIZE):
        frame = buffer[i : i + RFID_FRAME_SIZE]
        if frame[0] != RFID_STX:
            return "QR_CODE", None  # one bad sub-frame invalidates the whole buffer as RFID
        uid = frame[RFID_UID_OFFSET : RFID_UID_OFFSET + RFID_UID_LENGTH]
        uids.append(uid.hex().upper())
    return "RFID", uids
```

Multiple RFID taps that land in the same idle-timeout window concatenate into one buffer that's
still a clean multiple of 16 bytes — the loop above handles that by extracting one UID per
sub-frame. If a caller needs "how to render the RFID scan as a display string," a reasonable
choice is joining the UIDs with a comma (rather than trying to UTF-8 decode the raw frame, which
would produce garbage).

## Caveats — read before trusting this in production

1. **Only verified against 4 physical cards (all appear to be Mifare, 4-byte UID) and 1 QR
   sample (a UUID).** Test more QR content types — especially payloads that are pure digits or
   pure hex — before fully trusting this. The one realistic failure mode is a QR payload that
   coincidentally starts with byte `0x02` and happens to be a length that's a multiple of 16;
   extremely unlikely for normal QR content, but not mathematically ruled out.
2. **Different Mifare card types have different UID lengths** — this project's 4 cards all
   happened to be 4-byte UID (matches Mifare Classic S50/S70). Mifare Ultralight/NTAG/DESFire
   EV1 typically use a 7-byte UID instead, which — if the device reports it the same way — would
   likely still fit this classifier fine (it doesn't hardcode UID length as part of what makes a
   frame "RFID," only the STX+16-byte-frame-size check), but this has not been tested against a
   card of a different UID length. Confirm before assuming.
3. **The `<addr>` byte is device-specific**, taken from the unit's configured RS485 Address — if
   this address is reconfigured, or a different unit with a different address is deployed, the
   classifier still works correctly as written (it doesn't check the address value at all, only
   STX position and frame length) — this caveat exists only to warn against a *different*
   implementation choice: don't hardcode the observed `0x64` value anywhere.
4. **Idle-timeout interaction untested** — whether the default 150ms timeout ever splits or
   merges rapid consecutive RFID taps hasn't been verified through the actual read loop (only
   through a raw external capture tool, bypassing the framing logic entirely). See
   `references/serial-mode.md`.
