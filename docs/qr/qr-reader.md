# QR Reader — เอกสารระบบ

ไฟล์หลัก: `src/features/qr/reader.py`

## ภาพรวม

VAS รองรับเครื่องอ่าน QR รุ่น **ZKTeco QR500-BM** (VendorID `0416`, ProductID `5020`) ผ่าน USB HID สามารถทำงานได้สองโหมด ขึ้นอยู่กับการตั้งค่าของอุปกรณ์ — **รองรับทั้งสองโหมดพร้อมกันได้ (hybrid)** ต่อเครื่อง ไม่ได้บังคับให้ใช้โหมดใดโหมดหนึ่งเท่านั้น:

| โหมด | Device path | คลาส Thread | `read_mode` | Raw byte report |
|------|-------------|--------------|-------------|------------------|
| HID Keyboard = Close (HID Raw) | `/dev/hidraw*` | `QrReaderThread` | `"hidraw"` | มี (`last_scan_raw_report`) |
| HID Keyboard = Open (evdev) | `/dev/input/event*` | `EvdevQrReaderThread` | `"evdev"` | ไม่มี (`None` เสมอ — evdev ไม่มี raw USB byte report ให้ดัก) |

---

## Constants และ Keycode Maps

### `KEYCODE_MAP` / `KEYCODE_SHIFT_MAP`
ใช้สำหรับโหมด HID Raw — แปลง HID keycode ที่อยู่ใน byte[2..7] ของ 64-byte report เป็น ASCII character

- `KEYCODE_MAP`: keycode → character (ไม่กด shift)
- `KEYCODE_SHIFT_MAP`: keycode → character (กด shift)
- `SHIFT_MASK = 0x22` — bitmask ตรวจ left/right shift ใน byte[0] ของ report
- `ENTER_KEYCODE = 40` — keycode ของ Enter ที่ใช้เป็น end-of-scan marker
- `REPORT_SIZE = 64` — ขนาด HID report (bytes) ที่อ่านต่อครั้งด้วย `os.read()`

### `EVDEV_KEYMAP`
ใช้สำหรับโหมด evdev — แปลง Linux evdev scancode เป็น character

**หมายเหตุสำคัญ:** keycode (hidraw) กับ scancode (evdev) เป็นคนละ numbering space กัน แม้ตัวอักษรผลลัพธ์จะเหมือนกัน (เช่น "1" = keycode `30` ฝั่ง hidraw แต่ = scancode `2` ฝั่ง evdev) — ดูฟิลด์ `read_mode` เพื่อรู้ว่ากำลังตีความ raw data ชุดไหนอยู่

### `EVDEV_DEVICE_NAMES`
```python
EVDEV_DEVICE_NAMES = ["ZKRFID", "ZK", "QR500"]
```
ใช้ match ชื่ออุปกรณ์ใน evdev เพื่อค้นหา ZKTeco device

---

## Device Discovery

### `find_zkteco_hidraw_devices() → list[str]`
ค้นหา `/dev/hidraw*` ของ ZKTeco QR500-BM โดย:
1. glob `/sys/class/hidraw/*/device/uevent`
2. อ่านแต่ละ uevent และ parse บรรทัด `HID_ID=`
3. เปรียบเทียบ vendorId=`0416`, productId=`5020`
4. แปลง path: `/sys/class/hidraw/hidraw0/...` → `/dev/hidraw0`

**Returns:** `list[str]` เช่น `["/dev/hidraw0"]` หรือ `[]` ถ้าไม่พบ

### `find_zkteco_evdev_devices() → list[str]`
ค้นหา `/dev/input/event*` โดยใช้ `python3-evdev`:
1. เรียก `evdev.list_devices()`
2. กรอง device ที่มีชื่อตรง `EVDEV_DEVICE_NAMES`
3. ตรวจสอบว่า support `EV_KEY`

**Returns:** `list[str]` เช่น `["/dev/input/event6"]` หรือ `[]`

### `_parse_hid_id(uevent_content: str) → tuple[str, str] | None`
Helper ที่ parse บรรทัด `HID_ID=<bus>:<vendor8hex>:<product8hex>` และคืน `(vendor_4hex, product_4hex)`

---

## HID Report Decoding

### `decode_hid_report(report: bytes) → str`
แปลง 64-byte HID keyboard report เป็น string

**โครงสร้าง report:**
```
byte[0]   = modifier bitmask (0x02=left shift, 0x20=right shift)
byte[1]   = reserved
byte[2:8] = keycodes (สูงสุด 6 key พร้อมกัน, 0 = ไม่มี key)
```

**ขั้นตอน:**
1. ตรวจ byte[0] & `SHIFT_MASK` เพื่อรู้ว่า shift ถูกกดหรือไม่
2. วนลูป byte[2:8], ข้าม keycode=0 และ keycode=40 (Enter)
3. lookup character จาก keymap ที่เหมาะสม
4. คืน string ที่ต่อจาก characters ทั้งหมด

---

## QR Content Decoder

### `decode_qr_content(raw: str) → object`
ลอง decode QR text เป็น structured data ตามลำดับ:

1. **JSON** — `json.loads(raw)` → dict/list/primitive
2. **URL** — ถ้า scheme เป็น `http`/`https` → `{"url": ..., "params": {...}}`
3. **Base64+JSON** — decode base64 (เติม padding) แล้ว parse JSON
4. **Fallback** — `{"value": raw}`

---

## Configuration

### `QrConfig` (dataclass)
```python
@dataclass
class QrConfig:
    device_path: str | None = None  # None = auto-detect
    mode: str = "auto"              # "auto" | "evdev" | "hidraw"
```

บันทึกลงไฟล์ `~/.config/vas/qr_config.json` (path จาก `config.qr_config_path()`)

### `load_qr_config() → QrConfig`
อ่าน config จากไฟล์ คืน `QrConfig()` (defaults) ถ้าไฟล์ไม่มีหรือ parse ไม่ได้

### `save_qr_config(config: QrConfig) → None`
เขียน config เป็น JSON indent=2 สร้าง parent directory อัตโนมัติ

---

## Thread Classes

### `QrReaderThread` (โหมด HID Raw)

Background daemon thread อ่าน raw HID report จาก `/dev/hidraw*`

```python
thread = QrReaderThread(device_path="/dev/hidraw0")
thread.start()
scan            = thread.last_scan              # decoded text เช่น "3833401723"
scan_raw        = thread.last_scan_raw           # raw keycodes เช่น [39, 30, 30, 32]
scan_raw_report = thread.last_scan_raw_report     # raw HID byte report (hex) — ทุก frame
read_mode       = thread.read_mode                # "hidraw" (คงที่)
thread.stop()
thread.join(timeout=2.0)
```

**Main loop (`run`):**
1. เปิด device file ใน binary mode
2. อ่าน 64 bytes ต่อ report ด้วย `os.read()`
3. เก็บ `report.hex()` ของ**ทุก**report ที่อ่านได้ (รวม key-up/all-zero frame) เข้า `raw_report_buf` — **ไม่ filter** ต่างจาก keycode list
4. ถ้า report มี Enter keycode → flush buffer → อัปเดต `_last_scan`, `_last_scan_raw`, และ `_last_scan_raw_report`
5. วนซ้ำจนกว่า `_stop_event` จะถูก set หรือ I/O error

**Properties (thread-safe):**
- `last_scan: str | None` — scan text ล่าสุด (decoded)
- `last_scan_raw: list[int] | None` — raw HID keycode ล่าสุด (**ตัด** modifier byte, reserved byte, empty slot, และ Enter ออกแล้ว — ไม่ใช่ byte report ดิบทั้งก้อน)
- `last_scan_raw_report: list[str] | None` — raw HID byte report (hex string ต่อ frame, `report.hex()`) ของ scan ล่าสุด **รวมทุก frame ที่อุปกรณ์ส่งมาจริง** (รวม key-up all-zero frame) — นี่คือระดับ "ดิบที่สุด" ที่ vas เก็บได้
- `read_mode: str` — `"hidraw"` เสมอสำหรับ class นี้

### `EvdevQrReaderThread` (โหมด evdev)

Background daemon thread อ่าน QR ผ่าน `python3-evdev`

**ความแตกต่างสำคัญจาก `QrReaderThread`:**
- ใช้ `device.grab()` เพื่อกัน keystrokes ไม่ให้ถึง OS/UI
- อ่าน `EV_KEY` events จาก `device.read_loop()`
- scancode 28 = KEY_ENTER → end-of-scan
- `last_scan_raw` คือ evdev scancodes (ไม่ใช่ HID keycodes — คนละ numbering space กัน ดู hint ด้านบน)
- `last_scan_raw_report` **คืน `None` เสมอ** — evdev เป็น kernel abstraction ที่แปลง USB HID report เป็น key event ให้แล้วตั้งแต่ driver ระดับ kernel ไม่มีทางดัก byte report ดิบจาก evdev ได้ (คุณสมบัตินี้มีไว้เพื่อให้ caller เขียนโค้ดเดียวกันเรียกทั้งสอง class ได้โดยไม่ต้อง `isinstance` check)
- `read_mode: str` — `"evdev"` เสมอสำหรับ class นี้

---

## Global Singleton Management

### `get_reader() → QrReaderThread | EvdevQrReaderThread | None`
คืน thread ที่กำลัง run อยู่ หรือ None (thread-safe)

### `start_reader(device_path=None) → QrReaderThread | EvdevQrReaderThread`
เริ่ม global singleton thread

**Auto-detect order:**
1. ลอง evdev ก่อน (`find_zkteco_evdev_devices()`)
2. Fallback ไป hidraw (`find_zkteco_hidraw_devices()`)

**Logic:**
- ถ้า `device_path` ขึ้นต้น `/dev/input/` → ใช้ `EvdevQrReaderThread`
- อื่นๆ → ใช้ `QrReaderThread`
- ถ้า thread กำลัง run อยู่แล้ว → return thread เดิม (idempotent)

**Raises:**
- `RuntimeError` ถ้าไม่พบ device และ `device_path=None`
- `OSError` ถ้าเปิด device ไม่ได้

### `stop_reader() → None`
หยุด global thread — เรียก `thread.stop()` แล้ว join นอก lock เพื่อป้องกัน deadlock

---

## การ Integrate กับส่วนอื่น

### Flask Server (`server.py`)
- **Auto-start**: server boot เรียก `start_reader()` ทันที (ถ้ามี device) — ทำงานคู่กับการเช็ค DB schema version ตอน boot (ดู `docs/database.md`)
- **`atexit`**: ลงทะเบียน `stop_reader()` เพื่อหยุด thread เมื่อ process ปิด
- **SSE Stream (`/api/qr/stream`)**: poll `reader.last_scan` / `reader.last_scan_seq` ทุก 0.2 วินาที ตรวจจับ "scan ใหม่" ด้วยการเทียบ **`last_scan_seq`** (ตัวนับที่เพิ่มทุกครั้งที่ scan เสร็จ แม้ค่าจะซ้ำกับครั้งก่อน) — **ไม่ใช่การเทียบค่า string** เหมือนเดิม เพื่อให้สแกน QR code เดิมซ้ำๆ ติดกันยัง log/publish ทุกครั้ง ไม่ถูกข้ามเพราะค่าไม่เปลี่ยน เมื่อมี scan ใหม่จะ:
  1. บันทึกลง `qr_scans` ผ่าน `log_qr_scan()` ครบทั้ง 3 ระดับข้อมูล + `read_mode`
  2. Publish ออก MQTT ผ่าน `publish_qr_scan_for_device("zkteco-qr500", ...)` — เลือก broker ตาม `device_integrations` ที่ตั้งไว้ในหน้า `/qr/devices/zkteco-qr500` (ดู `docs/networking/mqtt.md`) — คืนค่าเป็น status dict (`enabled`/`connected`/`published`/`error`)
  3. ส่ง `event: scan` พร้อม `scan`, `device`, `ts`, `raw_keycode`, `raw_report`, `read_mode`, และ `mqtt` (ผลลัพธ์จากข้อ 2 — ใช้แสดงสีสถานะของ integration chip บนหน้าเว็บ)
  - มี auto-restart ถ้า reader ตาย

### MQTT (`features/mqtt/client.py`)
เมื่อ SSE stream ตรวจพบ scan ใหม่ จะเรียก `publish_qr_scan_for_device()` ส่งข้อมูลออก MQTT broker ที่ผูกกับ device นั้นโดยอัตโนมัติ (ถ้า integration enabled) — รูปแบบ payload (`decoded`/`raw_keycode`/`raw_report`) ขึ้นกับ `payload_mode` ที่ตั้งไว้ที่ device หรือ broker (ดู `docs/networking/mqtt.md`) — payload ที่ publish ออกจริงใช้ key `data`/`device`/`mode`/`read_mode`/`timestamp` (คนละชุดกับ SSE event ภายในที่ยังใช้ `scan`/`ts` เดิม)

---

## Web API Endpoints (QR)

| Method | Path | คำอธิบาย |
|--------|------|----------|
| `GET` | `/qr` | หน้า QR reader UI แสดงสถานะและ detected devices |
| `GET` | `/api/qr/last-scan` | ดึงค่า scan ล่าสุดใน memory |
| `POST` | `/api/qr/start` | Start reader thread (body: `{"device": "/dev/hidraw0"}`) |
| `POST` | `/api/qr/stop` | Stop reader thread |
| `GET` | `/api/qr/config` | ดู QR config ปัจจุบัน |
| `POST` | `/api/qr/config` | บันทึก QR config (body: `{"device_path": "..."}`) |
| `GET` | `/api/qr/stream` | Server-Sent Events stream (real-time scan) |
| `GET` | `/api/qr/integrations` | ดู integration config (webhook/mqtt/pipe) ของ device — เก็บใน SQLite (`device_integrations`) |
| `POST` | `/api/qr/integrations/<type>` | บันทึก integration config ของ device |

### SSE Event Types (`/api/qr/stream`)
```
event: scan
data: {
  "scan": "<decoded value>",
  "device": "<path>",
  "ts": "<ISO8601-UTC>",
  "raw_keycode": [39, 30, 30, ...] | null,
  "raw_report": ["a1000000...", "00000000..."] | null,
  "read_mode": "hidraw" | "evdev" | null,
  "mqtt": {"enabled": <bool>, "connected": <bool>, "published": <bool>, "error": "<str>"|null}
}

event: status
data: {"running": <bool>, "device": "<path>"|null}

event: heartbeat
data: {}
```
หมายเหตุ: นี่คือรูปแบบ **SSE event ภายใน** (ระหว่าง server กับหน้าเว็บ) เท่านั้น — key ยังใช้ `scan`/`ts`
เหมือนเดิม ไม่เกี่ยวกับ payload ที่ publish ออก MQTT จริง (ซึ่งใช้ key `data`/`mode`/`timestamp`
แทน ดู `docs/networking/mqtt.md`)

---

## udev Rule

ติดตั้งด้วยคำสั่ง `sudo vas qr install-udev` หรือ `sudo vas install --component qr-udev`

ไฟล์: `/etc/udev/rules.d/99-qr500-bm.rules`

```udev
# managed by vas
# ZKTeco QR500-BM / ZKRFID R400 — allow plugdev group access
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5020", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb",    ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5020", MODE="0664", GROUP="plugdev"
KERNEL=="event*",    ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5020", MODE="0664", GROUP="plugdev"
```

---

## ข้อกำหนด Dependencies

| Package | วัตถุประสงค์ | ติดตั้ง |
|---------|-------------|---------|
| `python3-evdev` | อ่าน QR โหมด evdev | `sudo apt install -y python3-evdev` |
| *(ไม่ต้องการ)* | โหมด HID Raw ใช้ built-in `os.read()` | — |

---

## Flow Diagram

```
USB QR Scanner (ZKTeco QR500-BM)
         │
         ├─ HID Keyboard = Close ──▶ /dev/hidraw0
         │                               │
         │                         QrReaderThread   read_mode="hidraw"
         │                         .run() loop
         │                         os.read(64 bytes)  ──▶ raw_report_buf (ทุก frame, hex)
         │                         decode_hid_report()
         │                               │
         └─ HID Keyboard = Open  ──▶ /dev/input/event6
                                        │
                                  EvdevQrReaderThread   read_mode="evdev"
                                  device.grab()
                                  read_loop() → EV_KEY
                                        │
                                        ▼
                                 last_scan (str)
                                 last_scan_raw (list[int])
                                 last_scan_raw_report (list[str] hex, hidraw only — null บน evdev)
                                 read_mode ("hidraw" | "evdev")
                                        │
                        ┌───────────────┼────────────────┐
                        │               │                │
                  SSE Stream       qr_scans (DB)     MQTT publish
               /api/qr/stream    log_qr_scan()   publish_qr_scan_for_device()
```
