from __future__ import annotations

import glob
import json
import os
import threading
from dataclasses import dataclass
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
# Config
# ---------------------------------------------------------------------------

@dataclass
class QrConfig:
    device_path: str | None = None  # None = auto-detect

    def to_dict(self) -> dict[str, object]:
        return {"device_path": self.device_path}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "QrConfig":
        return cls(device_path=data.get("device_path") or None)


def load_qr_config() -> QrConfig:
    """
    โหลด config จาก qr_config_path()
    ถ้าไฟล์ไม่มีหรืออ่านไม่ได้ -> return QrConfig() (defaults)
    ถ้า JSON parse error -> return QrConfig() (defaults) -- ไม่ raise
    """
    from config import qr_config_path
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
    from config import qr_config_path
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
        scan = thread.last_scan   # thread-safe
        thread.stop()
        thread.join(timeout=2.0)
    """

    def __init__(self, device_path: str) -> None:
        super().__init__(daemon=True, name="qr-reader")
        self.device_path = device_path
        self._stop_event = threading.Event()
        self._last_scan: str | None = None
        self._lock = threading.Lock()

    @property
    def last_scan(self) -> str | None:
        """Scan string ล่าสุด หรือ None ถ้ายังไม่เคย scan"""
        with self._lock:
            return self._last_scan

    def stop(self) -> None:
        """Signal ให้ thread หยุด"""
        self._stop_event.set()

    def run(self) -> None:
        """
        Main loop:
        1. open(self.device_path, "rb") as fd
        2. วน loop จนกว่า _stop_event.is_set()
        3. os.read(fd.fileno(), REPORT_SIZE) -> bytes
        4. ถ้า len(report) < 3 -> continue
        5. ตรวจ Enter keycode -> flush buffer -> set _last_scan
        6. ไม่งั้น decode_hid_report(report) -> append chars to buffer
        7. OSError / IOError -> break (device disconnected)
        """
        buffer = ""
        try:
            with open(self.device_path, "rb") as fd:
                while not self._stop_event.is_set():
                    try:
                        report = os.read(fd.fileno(), REPORT_SIZE)
                    except (OSError, IOError):
                        break
                    if len(report) < 3:
                        continue
                    has_enter = ENTER_KEYCODE in report[2:8]
                    chars = decode_hid_report(report)
                    buffer += chars
                    if has_enter and buffer:
                        with self._lock:
                            self._last_scan = buffer.strip()
                        buffer = ""
        except (OSError, IOError):
            pass


# ---------------------------------------------------------------------------
# Module-level singleton management
# ---------------------------------------------------------------------------

_reader_thread: QrReaderThread | None = None
_reader_lock = threading.Lock()


def get_reader() -> QrReaderThread | None:
    """Return running reader thread หรือ None"""
    with _reader_lock:
        return _reader_thread


def start_reader(device_path: str | None = None) -> QrReaderThread:
    """
    เริ่ม QrReaderThread global singleton

    Args:
        device_path: ถ้า None -> auto-detect จาก find_zkteco_hidraw_devices()[0]

    Raises:
        RuntimeError: ถ้าไม่พบ device และ device_path=None
        OSError: ถ้าเปิด device ไม่ได้

    ถ้า thread กำลัง run อยู่แล้ว -> return thread เดิม (idempotent)
    """
    global _reader_thread
    with _reader_lock:
        if _reader_thread is not None and _reader_thread.is_alive():
            return _reader_thread
        if device_path is None:
            devices = find_zkteco_hidraw_devices()
            if not devices:
                raise RuntimeError("No ZKTeco QR500-BM device found")
            device_path = devices[0]
        thread = QrReaderThread(device_path=device_path)
        thread.start()
        _reader_thread = thread
        return thread


def stop_reader() -> None:
    """หยุด global reader thread ถ้ากำลัง run"""
    global _reader_thread
    with _reader_lock:
        if _reader_thread is not None:
            thread = _reader_thread
            thread.stop()
            _reader_thread = None
    # join นอก lock เพื่อไม่ให้ deadlock กับ thread ที่กำลัง run
    if "thread" in dir():
        thread.join(timeout=2.0)
