from __future__ import annotations

import glob
import json
import os
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

EVDEV_DEVICE_NAMES = ["ZKRFID", "ZK", "QR500"]


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
# Config
# ---------------------------------------------------------------------------

@dataclass
class QrConfig:
    device_path: str | None = None  # None = auto-detect
    mode: str = "auto"              # "auto" | "evdev" | "hidraw"

    def to_dict(self) -> dict[str, object]:
        return {"device_path": self.device_path, "mode": self.mode}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "QrConfig":
        return cls(
            device_path=data.get("device_path") or None,
            mode=str(data.get("mode") or "auto"),
        )


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
        scan     = thread.last_scan      # decoded text  e.g. "3833401723"
        scan_raw = thread.last_scan_raw  # raw keycodes  e.g. [39,30,30,32,...]
        thread.stop()
        thread.join(timeout=2.0)
    """

    def __init__(self, device_path: str) -> None:
        super().__init__(daemon=True, name="qr-reader")
        self.device_path = device_path
        self._stop_event = threading.Event()
        self._last_scan: str | None = None
        self._last_scan_raw: list[int] | None = None  # raw HID keycodes ก่อน decode
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

    def stop(self) -> None:
        """Signal ให้ thread หยุด"""
        self._stop_event.set()

    def run(self) -> None:
        """
        Main loop — เก็บทั้ง decoded text และ raw keycodes ควบคู่กัน
        raw_buf: list[int] เก็บ keycode จาก byte[2:8] ของแต่ละ report (ไม่รวม 0 และ Enter)
        """
        buffer = ""
        raw_buf: list[int] = []
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
                    # เก็บ keycodes ดิบ (ไม่รวม 0 และ Enter)
                    for kc in report[2:8]:
                        if kc != 0 and kc != ENTER_KEYCODE:
                            raw_buf.append(int(kc))
                    if has_enter and buffer:
                        with self._lock:
                            self._last_scan = buffer.strip()
                            self._last_scan_raw = list(raw_buf)
                        buffer = ""
                        raw_buf = []
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
        thread.last_scan      -> str | None         decoded text
        thread.last_scan_raw  -> list[int] | None   raw evdev scancodes
        thread.device_path    -> str
        thread.stop()
        thread.join(timeout)
    """

    def __init__(self, device_path: str) -> None:
        super().__init__(daemon=True, name="qr-reader-evdev")
        self.device_path = device_path
        self._stop_event = threading.Event()
        self._last_scan: str | None = None
        self._last_scan_raw: list[int] | None = None  # raw evdev scancodes ก่อน decode
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
        try:
            for event in device.read_loop():
                if self._stop_event.is_set():
                    break
                if event.type != evdev.ecodes.EV_KEY:
                    continue
                key = evdev.categorize(event)
                if key.keystate != evdev.KeyEvent.key_down:
                    continue
                if key.scancode == 28:  # KEY_ENTER = จบ QR
                    if buffer:
                        with self._lock:
                            self._last_scan = "".join(buffer).strip()
                            self._last_scan_raw = list(raw_buf)
                        buffer.clear()
                        raw_buf = []
                elif key.scancode in EVDEV_KEYMAP:
                    buffer.append(EVDEV_KEYMAP[key.scancode])
                    raw_buf.append(key.scancode)  # เก็บ raw scancode ควบคู่
        except (OSError, IOError):
            pass
        finally:
            try:
                device.ungrab()
            except Exception:
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


def start_reader(device_path: str | None = None) -> "QrReaderThread | EvdevQrReaderThread":
    """
    เริ่ม QR reader global singleton

    Auto-detect mode:
      1. ลอง evdev ก่อน (HID keyboard = Open) — ค้นหา /dev/input/event*
      2. Fallback hidraw (HID keyboard = Close) — ค้นหา /dev/hidraw*

    Args:
        device_path: ถ้า None -> auto-detect
                     ถ้าขึ้นต้น /dev/input/ -> ใช้ evdev
                     อื่นๆ -> ใช้ hidraw

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
            # ลอง evdev ก่อน (HID keyboard = Open)
            evdev_devices = find_zkteco_evdev_devices()
            if evdev_devices:
                thread: QrReaderThread | EvdevQrReaderThread = EvdevQrReaderThread(device_path=evdev_devices[0])
                thread.start()
                _reader_thread = thread
                return thread
            # Fallback: hidraw (HID keyboard = Close)
            hidraw_devices = find_zkteco_hidraw_devices()
            if not hidraw_devices:
                raise RuntimeError("No ZKTeco QR500-BM device found (tried evdev and hidraw)")
            device_path = hidraw_devices[0]

        # explicit device_path
        if device_path.startswith("/dev/input/"):
            thread = EvdevQrReaderThread(device_path=device_path)
        else:
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
