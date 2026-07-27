from __future__ import annotations

import base64
import glob
import json
import os
import select
import threading
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KEYCODE_MAP: dict[int, str] = {
    4: "a",  5: "b",  6: "c",  7: "d",  8: "e",  9: "f",
    10: "g", 11: "h", 12: "i", 13: "j", 14: "k", 15: "l",
    16: "m", 17: "n", 18: "o", 19: "p", 20: "q", 21: "r",
    22: "s", 23: "t", 24: "u", 25: "v", 26: "w", 27: "x",
    28: "y", 29: "z",
    30: "1", 31: "2", 32: "3", 33: "4", 34: "5",
    35: "6", 36: "7", 37: "8", 38: "9", 39: "0",
    40: "\n",   # Enter -- end-of-scan marker
    44: " ",    # Space
    45: "-",
    46: "=",    # HID 0x2E = equals sign (unshifted)
    47: "[",
    48: "]",
    49: "\\",   # HID 0x31 = backslash
    51: ";",
    52: "'",
    53: "`",
    54: ",",
    55: ".",
    56: "/",    # HID 0x38 = forward slash (unshifted)
    57: "",     # CapsLock -- skip
}

KEYCODE_SHIFT_MAP: dict[int, str] = {
    4: "A",  5: "B",  6: "C",  7: "D",  8: "E",  9: "F",
    10: "G", 11: "H", 12: "I", 13: "J", 14: "K", 15: "L",
    16: "M", 17: "N", 18: "O", 19: "P", 20: "Q", 21: "R",
    22: "S", 23: "T", 24: "U", 25: "V", 26: "W", 27: "X",
    28: "Y", 29: "Z",
    30: "!", 31: "@", 32: "#", 33: "$", 34: "%",
    35: "^", 36: "&", 37: "*", 38: "(", 39: ")",
    45: "_",
    46: "+",    # Shift+= → +
    47: "{",
    48: "}",
    49: "|",    # Shift+backslash → |
    51: ":",
    52: '"',
    53: "~",
    54: "<",
    55: ">",
    56: "?",    # Shift+/ → ?
}

SHIFT_MASK = 0x22   # left shift=0x02, right shift=0x20
ENTER_KEYCODE = 40
REPORT_SIZE = 64

# ---------------------------------------------------------------------------
# evdev keycode map (HID keyboard = Open mode)
# ---------------------------------------------------------------------------

EVDEV_KEYMAP: dict[int, str] = {
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

# Shift-variant ของ EVDEV_KEYMAP -- ใช้เมื่อ Left/Right Shift ถูกกดค้างอยู่
EVDEV_SHIFT_KEYMAP: dict[int, str] = {
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

# evdev scancode ของ Left/Right Shift (Linux input-event-codes.h: KEY_LEFTSHIFT=42, KEY_RIGHTSHIFT=54)
EVDEV_SHIFT_SCANCODES = {42, 54}

EVDEV_DEVICE_NAMES = ["ZKRFID", "ZK", "QR500"]


# ---------------------------------------------------------------------------
# RS485 Serial mode (HID keyboard ปิด, ต่อผ่าน USB-to-RS485 adapter) — ดู
# .agents/skills/zkteco-500/references/serial-mode.md และ scan-source-detection.md
# ---------------------------------------------------------------------------

# VendorID:ProductID ของ "adapter" USB-to-RS485 (FTDI FT232R ที่ยืนยันแล้วในโปรเจกต์นี้) —
# คนละตัวกับ QR500-BM เอง (ตัวอุปกรณ์ไม่ได้ enumerate เป็น USB device ของตัวเองในโหมดนี้)
SERIAL_ADAPTER_VENDOR_ID = "0403"
SERIAL_ADAPTER_PRODUCT_ID = "6001"

SERIAL_IDLE_TIMEOUT_SEC = 0.15       # idle-timeout framing default (150ms) -- ไม่มี terminator character ในสตรีมเลย

RFID_FRAME_SIZE = 16
RFID_STX = 0x02
RFID_UID_OFFSET = 5
RFID_UID_LENGTH = 4

# Persistent udev symlink -- สร้างโดย `sudo vas qr install-udev` (ดู core/config.py) --
# เสถียรกว่า hidrawN/ttyUSBn ที่เลขเปลี่ยนได้ทุกครั้งที่ reboot/ถอดเสียบใหม่
SYMLINK_HIDRAW_PATH = "/dev/zkteco-qr500"
SYMLINK_SERIAL_PATH = "/dev/zkteco-qr500-serial"


def find_zkteco_serial_devices() -> list[str]:
    """
    ค้นหา /dev/ttyUSB* ของ USB-to-RS485 adapter ที่ต่อกับ ZKTeco QR500-BM (RS485 mode)

    หมายเหตุ: vendor/product id ที่เช็คเป็นของ "adapter" ไม่ใช่ตัว QR500-BM เอง เพราะโหมดนี้
    อุปกรณ์สื่อสารผ่าน RS485 (A/B) ผ่าน adapter — Linux เห็นแค่ adapter เป็น USB device
    ไฟล์ id อยู่ 2 ระดับเหนือ /sys/class/tty/ttyUSBn (parent ตัวแรกคือ USB *interface*
    ไม่ใช่ USB *device*) ดู references/serial-mode.md ใน skill zkteco-500

    Returns:
        list[str]: paths เรียงตามชื่อ เช่น ["/dev/ttyUSB0"]
        คืน list ว่างถ้าไม่พบ adapter ที่ vendor/product id ตรงกัน
    """
    try:
        tty_paths = sorted(glob.glob("/sys/class/tty/ttyUSB*"))
    except OSError:
        return []

    results: list[str] = []
    for tty_path in tty_paths:
        vendor_file = Path(tty_path) / "device" / ".." / ".." / "idVendor"
        product_file = Path(tty_path) / "device" / ".." / ".." / "idProduct"
        try:
            vendor_id = vendor_file.read_text(encoding="utf-8").strip().lower()
            product_id = product_file.read_text(encoding="utf-8").strip().lower()
        except OSError:
            continue
        if vendor_id == SERIAL_ADAPTER_VENDOR_ID.lower() and product_id == SERIAL_ADAPTER_PRODUCT_ID.lower():
            results.append(f"/dev/{Path(tty_path).name}")
    return results


def classify_scan_source(buffer: bytes) -> tuple[str, list[str] | None]:
    """
    แยกว่า raw byte buffer จาก RS485 serial mode เป็น RFID card tap หรือ QR code text
    (เฉพาะโหมด serial เท่านั้น -- โหมด USB HID แยกไม่ได้เลย ไม่มี field บอกที่มา)

    RFID: buffer เป็นจำนวนเต็มเท่าของ 16-byte frame และทุก frame ขึ้นต้นด้วย STX (0x02)
        frame layout: 02 <addr> 01 09 00 [UID 4 bytes] <addr> 1A 88 39 05 [suffix 2 bytes]
    QR: กรณีอื่นทั้งหมด (fallback ปลอดภัยเสมอ -- ไม่เดาว่าเป็น RFID ถ้าไม่ match pattern เป๊ะ)

    ดู .agents/skills/zkteco-500/references/scan-source-detection.md สำหรับที่มาของ pattern นี้
    (ยืนยันจาก hardware capture จริง 4 บัตร Mifare + 1 QR sample)

    Returns:
        ("RFID", [uid_hex, ...]) หรือ ("QR_CODE", None)
    """
    if not buffer or len(buffer) % RFID_FRAME_SIZE != 0 or buffer[0] != RFID_STX:
        return "QR_CODE", None

    uids: list[str] = []
    for i in range(0, len(buffer), RFID_FRAME_SIZE):
        frame = buffer[i : i + RFID_FRAME_SIZE]
        if frame[0] != RFID_STX:
            return "QR_CODE", None  # sub-frame หนึ่งไม่ match -- ทั้ง buffer ไม่ใช่ RFID
        uid = frame[RFID_UID_OFFSET : RFID_UID_OFFSET + RFID_UID_LENGTH]
        uids.append(uid.hex().upper())
    return "RFID", uids


def _resolve_hidraw_path() -> str | None:
    """
    Resolve hidraw device path ตามลำดับ: persistent udev symlink ก่อน (เสถียรข้าม
    reboot/replug) แล้ว fallback ไป auto-detect scan สด (เผื่อยังไม่ได้รัน
    `sudo vas qr install-udev`)
    """
    if os.path.exists(SYMLINK_HIDRAW_PATH):
        return SYMLINK_HIDRAW_PATH
    devices = find_zkteco_hidraw_devices()
    return devices[0] if devices else None


def _resolve_serial_path() -> str | None:
    """Resolve RS485 serial adapter path -- symlink ก่อน, fallback auto-detect scan /dev/ttyUSB*"""
    if os.path.exists(SYMLINK_SERIAL_PATH):
        return SYMLINK_SERIAL_PATH
    devices = find_zkteco_serial_devices()
    return devices[0] if devices else None


# ---------------------------------------------------------------------------
# Device discovery
# ---------------------------------------------------------------------------

def _parse_hid_id(uevent_content: str) -> tuple[str, str] | None:
    """
    Parse HID_ID line จาก uevent content.
    Input:  "HID_ID=0003:00000416:00005020\\nHID_NAME=..."
    Return: ("0416", "5020") หรือ None ถ้า parse ไม่ได้

    Format: HID_ID=<bus>:<vendorId padded 8 hex>:<productId padded 8 hex>
    """
    for line in uevent_content.splitlines():
        line = line.strip()
        if not line.startswith("HID_ID="):
            continue
        value = line[len("HID_ID="):]
        parts = value.split(":")
        if len(parts) != 3:
            return None
        try:
            vendor_id = format(int(parts[1], 16), "04x")
            product_id = format(int(parts[2], 16), "04x")
        except ValueError:
            return None
        return (vendor_id, product_id)
    return None


def find_zkteco_evdev_devices() -> list[str]:
    """
    ค้นหา /dev/input/eventX paths ของ ZKTeco QR reader
    ใช้เมื่อ HID keyboard = Open (evdev mode)

    Returns:
        list[str]: paths เรียงตามชื่อ เช่น ["/dev/input/event6"]
        คืน list ว่างถ้าไม่พบ หรือ python3-evdev ไม่ได้ติดตั้ง
    """
    try:
        import evdev  # type: ignore[import]
    except ImportError:
        return []

    results: list[str] = []
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
            if any(name in d.name.upper() for name in EVDEV_DEVICE_NAMES):
                if evdev.ecodes.EV_KEY in d.capabilities():
                    results.append(path)
        except Exception:
            continue
    return sorted(results)


def find_zkteco_hidraw_devices() -> list[str]:
    """
    ค้นหา hidraw paths ของ ZKTeco QR500-BM (vendorId=0416, productId=5020)
    โดยอ่านจาก /sys/class/hidraw/*/device/uevent

    Returns:
        list[str]: paths เรียงตามชื่อ เช่น ["/dev/hidraw0"]
        คืน list ว่างถ้าไม่พบอุปกรณ์หรือ /sys/class/hidraw ไม่มี
    """
    try:
        uevent_paths = sorted(glob.glob("/sys/class/hidraw/*/device/uevent"))
    except OSError:
        return []

    results: list[str] = []
    for uevent_path in uevent_paths:
        try:
            content = Path(uevent_path).read_text(encoding="utf-8")
        except OSError:
            continue
        parsed = _parse_hid_id(content)
        if parsed is None:
            continue
        vendor_id, product_id = parsed
        if vendor_id.lower() != "0416" or product_id.lower() != "5020":
            continue
        # แปลง path: /sys/class/hidraw/hidraw0/device/uevent -> /dev/hidraw0
        # parts: ['', 'sys', 'class', 'hidraw', 'hidraw0', 'device', 'uevent']
        parts = uevent_path.split("/")
        if len(parts) >= 5:
            hidraw_name = parts[4]  # e.g. "hidraw0"
            results.append(f"/dev/{hidraw_name}")
    return results


# ---------------------------------------------------------------------------
# HID report decoding
# ---------------------------------------------------------------------------

def decode_hid_report(report: bytes) -> str:
    """
    แปลง 64-byte HID keyboard report เป็น string

    Report format:
        byte[0]  = modifier bitmask (0x02=left shift, 0x20=right shift)
        byte[1]  = reserved
        byte[2..7] = keycodes (up to 6 simultaneous keys; 0 = no key)

    Rules:
        - shift pressed ถ้า byte[0] & SHIFT_MASK != 0
        - keycode 40 (Enter) = end marker -- ข้าม (caller จัดการ)
        - keycode 0 = empty slot -- ข้าม
        - keycode ที่ไม่รู้จัก -- skip silently
        - ใช้ KEYCODE_SHIFT_MAP ถ้า shift, ไม่งั้นใช้ KEYCODE_MAP

    Returns:
        str: characters ที่ decode ได้จาก report นี้ (ไม่รวม Enter)
    """
    if len(report) < 3:
        return ""
    shift = bool(report[0] & SHIFT_MASK)
    chars: list[str] = []
    keymap = KEYCODE_SHIFT_MAP if shift else KEYCODE_MAP
    for keycode in report[2:8]:
        if keycode == 0:
            continue
        if keycode == ENTER_KEYCODE:
            continue  # caller ตรวจ Enter เอง
        char = keymap.get(keycode)
        if char is None:
            # ไม่รู้จัก keycode -- skip silently
            continue
        chars.append(char)
    return "".join(chars)


# ---------------------------------------------------------------------------
# QR content decoder
# ---------------------------------------------------------------------------

def decode_qr_content(raw: str) -> object:
    """
    ลอง decode QR content เป็น structured data

    ลำดับการลอง:
    1. JSON string  → parse เป็น dict/list/value
    2. URL (http/https) → {"url": ..., "params": {...query params...}}
    3. Base64 JSON  → decode base64 แล้วลอง parse JSON
    4. Fallback     → {"value": raw}

    Returns:
        dict หรือ list หรือ primitive ที่ parse ได้
        ถ้า parse ไม่ได้เลย → {"value": raw}
    """
    stripped = raw.strip()

    # 1. Try JSON
    try:
        parsed = json.loads(stripped)
        return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Try URL with query params
    try:
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(stripped)
        if parsed_url.scheme in ("http", "https") and parsed_url.netloc:
            params: dict[str, object] = {}
            for k, v in parse_qs(parsed_url.query).items():
                params[k] = v[0] if len(v) == 1 else v
            result: dict[str, object] = {"url": stripped}
            if params:
                result["params"] = params
            return result
    except Exception:
        pass

    # 3. Try Base64 → JSON
    try:
        # เติม padding ถ้าขาด
        padded = stripped + "=" * (-len(stripped) % 4)
        decoded_bytes = base64.b64decode(padded, validate=True)
        decoded_str = decoded_bytes.decode("utf-8")
        parsed_b64 = json.loads(decoded_str)
        return parsed_b64
    except Exception:
        pass

    # 4. Fallback
    return {"value": raw}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

QR_INTERFACES = ("usb", "serial")


@dataclass
class QrConfig:
    device_path: str | None = None  # None = auto-detect
    mode: str = "auto"              # "auto" | "evdev" | "hidraw"
    interface: str = "usb"          # "usb" (evdev/hidraw) | "serial" (RS485) -- ใช้เมื่อ device_path=None

    def to_dict(self) -> dict[str, object]:
        return {"device_path": self.device_path, "mode": self.mode, "interface": self.interface}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "QrConfig":
        interface = str(data.get("interface") or "usb")
        if interface not in QR_INTERFACES:
            interface = "usb"
        return cls(
            device_path=data.get("device_path") or None,
            mode=str(data.get("mode") or "auto"),
            interface=interface,
        )


def load_qr_config() -> QrConfig:
    """
    โหลด config จาก qr_config_path()
    ถ้าไฟล์ไม่มีหรืออ่านไม่ได้ -> return QrConfig() (defaults)
    ถ้า JSON parse error -> return QrConfig() (defaults) -- ไม่ raise
    """
    from core.config import qr_config_path
    path = qr_config_path()
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return QrConfig()
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return QrConfig()
    if not isinstance(data, dict):
        return QrConfig()
    return QrConfig.from_dict(data)


def save_qr_config(config: QrConfig) -> None:
    """
    บันทึก config ลง qr_config_path()
    สร้าง parent directories ถ้ายังไม่มี (parents=True, exist_ok=True)
    เขียน JSON indent=2 + newline ท้าย
    Raises: OSError ถ้าเขียนไม่ได้
    """
    from core.config import qr_config_path
    path = qr_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# QrReaderThread
# ---------------------------------------------------------------------------

class QrReaderThread(threading.Thread):
    """
    Background thread ที่อ่าน HID raw input จาก QR scanner อย่างต่อเนื่อง
    เก็บ scan string ล่าสุดใน memory

    Usage:
        thread = QrReaderThread(device_path="/dev/hidraw0")
        thread.start()
        scan            = thread.last_scan             # decoded text  e.g. "3833401723"
        scan_raw        = thread.last_scan_raw          # raw keycodes  e.g. [39,30,30,32,...]
        scan_raw_report = thread.last_scan_raw_report    # raw HID byte report (hex) ทุก frame
        thread.stop()
        thread.join(timeout=2.0)
    """

    read_mode: str = "hidraw"

    def __init__(self, device_path: str) -> None:
        super().__init__(daemon=True, name="qr-reader")
        self.device_path = device_path
        self.read_mode = "hidraw"
        self._stop_event = threading.Event()
        self._last_scan: str | None = None
        self._last_scan_raw: list[int] | None = None  # raw HID keycodes ก่อน decode
        self._last_scan_raw_report: list[str] | None = None  # raw HID byte report (hex) ทุก frame
        self._scan_seq: int = 0  # เพิ่มทุกครั้งที่ scan เสร็จ (แม้ค่าเดิมซ้ำ) — ให้ caller แยกแยะ scan ใหม่ vs เดิมได้โดยไม่ต้องเทียบค่า
        self._lock = threading.Lock()

    @property
    def last_scan(self) -> str | None:
        """Scan string ล่าสุด (decoded) หรือ None ถ้ายังไม่เคย scan"""
        with self._lock:
            return self._last_scan

    @property
    def last_scan_raw(self) -> list[int] | None:
        """Raw HID keycode sequence ของ scan ล่าสุด หรือ None"""
        with self._lock:
            return self._last_scan_raw

    @property
    def last_scan_raw_report(self) -> list[str] | None:
        """
        Raw HID byte report (hex string ต่อ frame) ของ scan ล่าสุด หรือ None
        เก็บ**ทุก**report ที่อ่านได้ในรอบ scan รวมถึง key-up/all-zero frame ด้วย
        (ไม่ filter เหมือน last_scan_raw) เพื่อให้เห็นข้อมูลดิบตรงตามที่อุปกรณ์ส่งมาจริง
        """
        with self._lock:
            return self._last_scan_raw_report

    @property
    def last_scan_seq(self) -> int:
        """
        ตัวนับที่เพิ่มขึ้นทุกครั้งที่ scan เสร็จสมบูรณ์ (กด Enter) ไม่ว่าค่าที่ scan ได้จะซ้ำกับ
        ครั้งก่อนหรือไม่ — ใช้แทนการเทียบ last_scan == last_seen ที่ทำให้สแกนค่าเดิมซ้ำแล้ว
        ถูกข้าม (ไม่ publish/log) เพราะค่าไม่เปลี่ยน ผู้เรียกควรเทียบ seq แทนค่า string
        """
        with self._lock:
            return self._scan_seq

    def stop(self) -> None:
        """Signal ให้ thread หยุด"""
        self._stop_event.set()

    def run(self) -> None:
        """
        Main loop — เก็บทั้ง decoded text, raw keycodes, และ raw byte report ควบคู่กัน
        raw_buf:        list[int] เก็บ keycode จาก byte[2:8] ของแต่ละ report (ไม่รวม 0 และ Enter)
        raw_report_buf: list[str] เก็บ report.hex() ของ**ทุก**os.read() ที่อ่านได้ในรอบ scan
                        (รวม key-up/all-zero frame ด้วย -- ไม่ filter เหมือน raw_buf)
        """
        buffer = ""
        raw_buf: list[int] = []
        raw_report_buf: list[str] = []
        try:
            with open(self.device_path, "rb") as fd:
                while not self._stop_event.is_set():
                    try:
                        report = os.read(fd.fileno(), REPORT_SIZE)
                    except (OSError, IOError):
                        break
                    if len(report) < 3:
                        continue
                    # เก็บ raw byte report ดิบทุก frame (รวม all-zero key-up frame)
                    raw_report_buf.append(report.hex())
                    has_enter = ENTER_KEYCODE in report[2:8]
                    chars = decode_hid_report(report)
                    buffer += chars
                    # เก็บ keycodes ดิบ (ไม่รวม 0 และ Enter)
                    for kc in report[2:8]:
                        if kc != 0 and kc != ENTER_KEYCODE:
                            raw_buf.append(int(kc))
                    if has_enter and buffer:
                        with self._lock:
                            self._last_scan = buffer.strip()
                            self._last_scan_raw = list(raw_buf)
                            self._last_scan_raw_report = list(raw_report_buf)
                            self._scan_seq += 1
                        buffer = ""
                        raw_buf = []
                        raw_report_buf = []
        except (OSError, IOError):
            pass


# ---------------------------------------------------------------------------
# EvdevQrReaderThread  (HID keyboard = Open mode)
# ---------------------------------------------------------------------------

class EvdevQrReaderThread(threading.Thread):
    """
    Background thread อ่าน QR ผ่าน evdev (HID keyboard = Open)
    ใช้ device.grab() เพื่อป้องกัน keystrokes ไม่ให้ถึง OS / UI

    Interface เหมือน QrReaderThread:
        thread.last_scan            -> str | None         decoded text
        thread.last_scan_raw        -> list[int] | None   raw evdev scancodes
        thread.last_scan_raw_report -> None (คงที่เสมอ -- evdev ไม่มี raw byte report)
        thread.read_mode            -> "evdev" (คงที่)
        thread.device_path          -> str
        thread.stop()
        thread.join(timeout)
    """

    read_mode: str = "evdev"

    def __init__(self, device_path: str) -> None:
        super().__init__(daemon=True, name="qr-reader-evdev")
        self.device_path = device_path
        self.read_mode = "evdev"
        self._stop_event = threading.Event()
        self._last_scan: str | None = None
        self._last_scan_raw: list[int] | None = None  # raw evdev scancodes ก่อน decode
        self._scan_seq: int = 0  # เพิ่มทุกครั้งที่ scan เสร็จ (แม้ค่าเดิมซ้ำ) — ดู QrReaderThread.last_scan_seq
        self._lock = threading.Lock()

    @property
    def last_scan(self) -> str | None:
        with self._lock:
            return self._last_scan

    @property
    def last_scan_raw(self) -> list[int] | None:
        """Raw evdev scancode sequence ของ scan ล่าสุด หรือ None"""
        with self._lock:
            return self._last_scan_raw

    @property
    def last_scan_raw_report(self) -> None:
        """
        Evdev mode ไม่มี raw HID byte report ให้เก็บ (ไม่ได้อ่านจาก /dev/hidraw โดยตรง)
        Return None เสมอ เพื่อให้ caller เขียน code เดียวกันได้ทั้งสอง reader class
        โดยไม่ต้อง isinstance check
        """
        return None

    @property
    def last_scan_seq(self) -> int:
        """ตัวนับที่เพิ่มขึ้นทุกครั้งที่ scan เสร็จ แม้ค่าเดิมซ้ำ — ดู QrReaderThread.last_scan_seq"""
        with self._lock:
            return self._scan_seq

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            import evdev  # type: ignore[import]
        except ImportError:
            return

        try:
            device = evdev.InputDevice(self.device_path)
            device.grab()
        except (OSError, Exception):
            return

        buffer: list[str] = []
        raw_buf: list[int] = []
        shift_pressed = False
        try:
            for event in device.read_loop():
                if self._stop_event.is_set():
                    break
                if event.type != evdev.ecodes.EV_KEY:
                    continue
                key = evdev.categorize(event)
                # Track Shift modifier state จาก key_down/key_up (ไม่สนใจ key_hold)
                if key.scancode in EVDEV_SHIFT_SCANCODES:
                    if key.keystate == evdev.KeyEvent.key_down:
                        shift_pressed = True
                    elif key.keystate == evdev.KeyEvent.key_up:
                        shift_pressed = False
                    continue
                if key.keystate != evdev.KeyEvent.key_down:
                    continue
                if key.scancode == 28:  # KEY_ENTER = จบ QR
                    if buffer:
                        with self._lock:
                            self._last_scan = "".join(buffer).strip()
                            self._last_scan_raw = list(raw_buf)
                            self._scan_seq += 1
                        buffer.clear()
                        raw_buf = []
                    shift_pressed = False
                else:
                    keymap = EVDEV_SHIFT_KEYMAP if shift_pressed else EVDEV_KEYMAP
                    if key.scancode in keymap:
                        buffer.append(keymap[key.scancode])
                        raw_buf.append(key.scancode)  # เก็บ raw scancode ควบคู่ (ไม่รวม shift state)
        except (OSError, IOError):
            pass
        finally:
            try:
                device.ungrab()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# SerialQrReaderThread  (RS485 Serial mode -- /dev/ttyUSB* ผ่าน USB-to-RS485 adapter)
# ---------------------------------------------------------------------------

class SerialQrReaderThread(threading.Thread):
    """
    Background thread อ่าน QR/RFID ผ่าน RS485 Serial adapter (/dev/ttyUSB*)

    ไม่มี terminator character ในสตรีมเลย (ยืนยันจาก hardware capture จริง -- ดู
    .agents/skills/zkteco-500/references/serial-mode.md) จึงใช้ **idle-timeout framing**
    แทน: buffer ทุก byte ที่เข้ามา ถ้าไม่มี byte ใหม่ภายใน idle_timeout วินาที (default 150ms)
    และ buffer มีข้อมูล -> ถือว่าจบ 1 scan แล้ว flush

    แยก RFID card tap ออกจาก QR code text ด้วย classify_scan_source() -- RFID เป็น 16-byte
    binary frame ขึ้นต้นด้วย STX เสมอ, QR เป็น UTF-8 text ธรรมดา ทั้งสองแบบ publish เป็น
    "scan" event เหมือนกัน (RFID แสดงเป็น UID คั่นด้วย comma) -- ดู last_scan_source/
    last_scan_rfid_uid ถ้า caller ต้องการแยกแยะ

    ใช้ termios/select/os เท่านั้น (ไม่พึ่ง pyserial) -- baud 115200, 8N1, no parity, no flow
    control -- ตาม skill zkteco-500 (ยืนยันบน hardware จริงของโปรเจกต์นี้)

    Interface เหมือน QrReaderThread/EvdevQrReaderThread:
        thread.last_scan             -> str | None        ข้อความที่ decode แล้ว
                                         (QR: text ตรงๆ, RFID: UID คั่นด้วย ", ")
        thread.last_scan_raw         -> None เสมอ (serial ไม่มี keycode concept แบบ HID)
        thread.last_scan_raw_report  -> list[str] | None   hex ของ raw byte buffer ดิบก่อน decode
        thread.last_scan_source      -> "QR_CODE" | "RFID" | None
        thread.last_scan_rfid_uid    -> list[str] | None   เฉพาะตอน source="RFID"
        thread.read_mode             -> "serial" (คงที่)
        thread.device_path           -> str
        thread.stop()
        thread.join(timeout=2.0)
    """

    read_mode: str = "serial"

    def __init__(self, device_path: str, idle_timeout: float = SERIAL_IDLE_TIMEOUT_SEC) -> None:
        super().__init__(daemon=True, name="qr-reader-serial")
        self.device_path = device_path
        self.read_mode = "serial"
        self.idle_timeout = idle_timeout
        self._stop_event = threading.Event()
        self._last_scan: str | None = None
        self._last_scan_source: str | None = None
        self._last_scan_rfid_uid: list[str] | None = None
        self._last_scan_raw_report: list[str] | None = None
        self._scan_seq: int = 0
        self._lock = threading.Lock()

    @property
    def last_scan(self) -> str | None:
        with self._lock:
            return self._last_scan

    @property
    def last_scan_raw(self) -> None:
        """Serial mode ไม่มี keycode concept (ต่างจาก HID) -- return None เสมอเพื่อให้ caller ใช้ interface เดียวกันได้"""
        return None

    @property
    def last_scan_raw_report(self) -> list[str] | None:
        """Hex string ของ raw byte buffer ดิบทั้งก้อนก่อน decode/classify (1 element ต่อ 1 scan)"""
        with self._lock:
            return self._last_scan_raw_report

    @property
    def last_scan_source(self) -> str | None:
        """"QR_CODE" | "RFID" | None (ยังไม่เคย scan) -- ดู classify_scan_source()"""
        with self._lock:
            return self._last_scan_source

    @property
    def last_scan_rfid_uid(self) -> list[str] | None:
        """UID (hex, uppercase) ของบัตรที่ tap -- มีค่าเฉพาะตอน last_scan_source == "RFID" """
        with self._lock:
            return self._last_scan_rfid_uid

    @property
    def last_scan_seq(self) -> int:
        with self._lock:
            return self._scan_seq

    def stop(self) -> None:
        self._stop_event.set()

    def _configure_raw_serial(self, fd: int) -> None:
        """ตั้งค่า termios แบบ raw mode: 115200 8N1, no parity, no flow control, non-canonical read"""
        import termios
        iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(fd)
        cflag = (cflag & ~termios.CSIZE) | termios.CS8
        cflag &= ~termios.PARENB
        cflag &= ~termios.CSTOPB
        cflag |= termios.CLOCAL | termios.CREAD
        iflag = oflag = lflag = 0
        ispeed = ospeed = termios.B115200
        cc[termios.VMIN] = 0
        cc[termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, ispeed, ospeed, cc])

    def run(self) -> None:
        """
        Idle-timeout framing loop: select() รอ byte ใหม่ภายใน idle_timeout วินาที
        ถ้า timeout (ไม่มี byte ใหม่) และ buffer มีข้อมูล -> flush เป็น 1 scan ที่สมบูรณ์
        """
        buffer = bytearray()
        fd: int | None = None
        try:
            fd = os.open(self.device_path, os.O_RDONLY | os.O_NOCTTY)
            self._configure_raw_serial(fd)
            while not self._stop_event.is_set():
                try:
                    readable, _, _ = select.select([fd], [], [], self.idle_timeout)
                except OSError:
                    break
                if readable:
                    try:
                        chunk = os.read(fd, 4096)
                    except (OSError, IOError):
                        break
                    if chunk:
                        buffer.extend(chunk)
                    continue
                # select() timeout -- ไม่มี byte ใหม่เข้ามาภายใน idle window
                if buffer:
                    self._flush_scan(bytes(buffer))
                    buffer = bytearray()
        except (OSError, IOError):
            pass
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def _flush_scan(self, raw: bytes) -> None:
        source, uids = classify_scan_source(raw)
        if source == "RFID" and uids:
            text = ", ".join(uids)
        else:
            text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return
        with self._lock:
            self._last_scan = text
            self._last_scan_source = source
            self._last_scan_rfid_uid = uids
            self._last_scan_raw_report = [raw.hex()]
            self._scan_seq += 1


# ---------------------------------------------------------------------------
# Module-level singleton management
# ---------------------------------------------------------------------------

_reader_thread: QrReaderThread | EvdevQrReaderThread | SerialQrReaderThread | None = None
_reader_lock = threading.Lock()

# True หลังจากผู้ใช้กด "หยุด Reader" (stop_reader()) โดยตั้งใจ -- ป้องกันไม่ให้
# ScanPublisherThread (features/qr/scan_publisher.py) auto-restart reader กลับมาให้ทุก
# RESTART_INTERVAL วินาที (เดิม 8 วิ) ทั้งที่ผู้ใช้เพิ่งสั่งหยุดไปเอง (บั๊กที่เจอจริง: กด
# "หยุด Reader" แล้วสแกนไม่เข้าแป๊บนึง แต่สักพักกลับมาอ่านได้อีก เพราะ background thread
# เข้าใจว่า reader "ตาย" เอง (เหมือนอุปกรณ์หลุด) เลย auto-restart ให้ตามปกติ ไม่ได้แยกแยะ
# "ตายเอง" กับ "ผู้ใช้สั่งหยุด") เคลียร์ค่ากลับเป็น False ทุกครั้งที่มีการเรียก start_reader()
# ไม่ว่าจากที่ไหน (หมายความว่า "ตอนนี้มีคนต้องการให้ reader ทำงาน")
_auto_restart_suspended = False


def get_reader() -> QrReaderThread | EvdevQrReaderThread | SerialQrReaderThread | None:
    """Return running reader thread หรือ None"""
    with _reader_lock:
        return _reader_thread


def is_auto_restart_suspended() -> bool:
    """True ถ้าผู้ใช้กด "หยุด Reader" ไปล่าสุด (ยังไม่ได้ start ใหม่) -- ดู _auto_restart_suspended"""
    with _reader_lock:
        return _auto_restart_suspended


def start_reader(device_path: str | None = None) -> "QrReaderThread | EvdevQrReaderThread | SerialQrReaderThread":
    """
    เริ่ม QR reader global singleton

    Auto-detect mode (device_path=None) เลือกตาม interface ที่ตั้งค่าไว้ใน QrConfig
    (load_qr_config().interface — default "usb"):

      interface="usb"    1. ลอง evdev ก่อน (HID keyboard = Open) — ค้นหา /dev/input/event*
                          2. Fallback hidraw (HID keyboard = Close) — symlink /dev/zkteco-qr500
                             ก่อน แล้วค่อย auto-detect scan /dev/hidraw*
      interface="serial" ใช้ RS485 serial adapter — symlink /dev/zkteco-qr500-serial ก่อน
                          แล้วค่อย auto-detect scan /dev/ttyUSB*

    Args:
        device_path: ถ้า None -> auto-detect ตาม interface ใน config
                     ถ้าขึ้นต้น /dev/input/ -> ใช้ evdev
                     ถ้าขึ้นต้น /dev/ttyUSB หรือเป็น symlink serial -> ใช้ serial (RS485)
                     อื่นๆ -> ใช้ hidraw

    Raises:
        RuntimeError: ถ้าไม่พบ device และ device_path=None
        OSError: ถ้าเปิด device ไม่ได้

    ถ้า thread กำลัง run อยู่แล้ว -> return thread เดิม (idempotent)
    """
    global _reader_thread, _auto_restart_suspended
    with _reader_lock:
        _auto_restart_suspended = False  # มีคนสั่ง start จริงจัง -- เคลียร์ suspend flag เสมอ

        if _reader_thread is not None and _reader_thread.is_alive():
            return _reader_thread

        if device_path is None:
            config = load_qr_config()
            if config.interface == "serial":
                device_path = _resolve_serial_path()
                if device_path is None:
                    raise RuntimeError(
                        "No ZKTeco QR500-BM RS485 serial adapter found (tried symlink and ttyUSB scan)"
                    )
            else:
                # usb: ลอง evdev ก่อน (HID keyboard = Open)
                evdev_devices = find_zkteco_evdev_devices()
                if evdev_devices:
                    thread: QrReaderThread | EvdevQrReaderThread | SerialQrReaderThread = EvdevQrReaderThread(
                        device_path=evdev_devices[0]
                    )
                    thread.start()
                    _reader_thread = thread
                    return thread
                # Fallback: hidraw (HID keyboard = Close) -- symlink ก่อน, แล้วค่อย auto-detect
                device_path = _resolve_hidraw_path()
                if device_path is None:
                    raise RuntimeError("No ZKTeco QR500-BM device found (tried evdev and hidraw)")

        # explicit หรือ resolved device_path -- เลือก reader class จาก path
        if device_path.startswith("/dev/input/"):
            thread = EvdevQrReaderThread(device_path=device_path)
        elif device_path == SYMLINK_SERIAL_PATH or device_path.startswith("/dev/ttyUSB"):
            thread = SerialQrReaderThread(device_path=device_path)
        else:
            thread = QrReaderThread(device_path=device_path)
        thread.start()
        _reader_thread = thread
        return thread


def stop_reader() -> None:
    """
    หยุด global reader thread ถ้ากำลัง run -- ตั้ง _auto_restart_suspended=True เสมอ
    (แม้ตอนกดตอนนั้นจะไม่มี thread รันอยู่แล้วก็ตาม) เพื่อกัน ScanPublisherThread
    auto-restart ให้กลับมาเอง จนกว่าจะมีการเรียก start_reader() อีกครั้ง
    """
    global _reader_thread, _auto_restart_suspended
    with _reader_lock:
        _auto_restart_suspended = True
        if _reader_thread is not None:
            thread = _reader_thread
            thread.stop()
            _reader_thread = None
    # join นอก lock เพื่อไม่ให้ deadlock กับ thread ที่กำลัง run
    if "thread" in dir():
        thread.join(timeout=2.0)
