# ZKTeco DEMO Software — Parameter Reference

Windows-only software used to configure the QR500-BM **before** any Linux integration work.
Connect over USB-HID, read the current configuration, change what's needed, then write it back.

## Basic Setting-1

| Parameter | Options | Notes |
|---|---|---|
| RS485 Address | 0–255 | 0 = broadcast (responds regardless of address) |
| Opening times | seconds | Only relevant if the reader is wired directly to a door lock |
| Serial number | read-only | Device serial number |
| RS485 function switch | Open / **Close** | Must be **Open** for RS485 Serial reading mode |
| RS485 automatic upload | Open / **Close** | Must be **Open** for the device to push scans on its own without polling |
| Work mode | **Reader mode** / Offline mode | Reader mode = used as a connected peripheral reader |
| HID keyboard | Open / **Close** | **Close** = send raw HID reports; **Open** = emulate a keyboard (types into whatever window has focus) |

## Basic Setting-2 (QR Code Parameters)

| Parameter | Options | Notes |
|---|---|---|
| QR code decryption key | string | Used only when mode = Custom encryption |
| QR code effective time | seconds (default 30) | QR code expires after this many seconds |
| Door ID | number | For multi-door access control setups |
| QR code mode | **Not encrypted** / Custom encryption / Dynamic QR code | Use Custom encryption if the QR payload has its own checksum/SALT logic |
| Light mode | Constantly bright / Intermittent / **Induction** | Induction = light only turns on during an active scan, saves power |

## Basic Setting-2 (Wiegand Parameters)

| Parameter | Options | Notes |
|---|---|---|
| Wiegand mode | W26 / **W34** / W66 | Pick based on what the connected controller supports |
| Output format | Forward / **Reverse** output | |
| Whether to check | Open / Close | Whether to output a Wiegand check digit |
| Pulse Width | 1–99 × 10ms | Default 5 (= 50ms) |
| Pulse interval | 0–89 × 100 + 1000ms | Gap between Wiegand pulses |

## Basic Setting-3 (Card Reading Parameters)

| Parameter | Notes |
|---|---|
| App ID | Directory file number of the CPU card (hex) |
| File ID | File number within the CPU card (decimal) |
| Key ID | Key identifier for external authentication |
| CPU user key | Key used to decrypt CPU card content |
| Start block | Block to start reading a MF card from (default 1) |
| Start byte | Byte offset to start reading from |
| MF user key | Sector key of a Mifare card |
| Prior choice | CPU-card priority vs MF-card priority |
| Reading Card mode | Read UID vs read Content, for CPU/MF/ISO15693 cards |

## Reader Operation (Section 4.4)

| Parameter | Notes |
|---|---|
| Read RTC | View the reader's current on-board clock |
| Write RTC | Sync the reader's clock to the PC's |
| Control door | Remotely open/close a connected door lock |
| Voice control | Play a sound from the reader (opcode 1–23 = presets, 255 = TTS) |
| Text data | Text for TTS playback, if using GB2312 encoding |
