"""
pipe_io.py — Named pipe (FIFO) helpers ใช้ร่วมกันระหว่างสองฟีเจอร์:

  1. Write-side — publish_qr_scan_to_pipe_for_device()
     ส่งค่า QR scan ออกไปยัง pipe path ที่ตั้งค่าไว้ใน device_integrations (type="pipe")
     เรียกจาก server.py ใน SSE loop ของ /api/qr/stream เมื่อ toggle "Pipe I/O" enabled —
     คู่ขนานกับ publish_qr_scan_for_device() (features/mqtt/client.py) ที่ทำหน้าที่เดียวกัน
     ฝั่ง MQTT

  2. Read-side — PipeReaderThread / start_pipe_reader() / stop_pipe_reader()
     ใช้กับหน้า Pipe Tester (/pipe-tester) สำหรับทดสอบว่ามี process ใด (VAS เอง หรือ
     third-party) เขียนข้อมูลลง pipe path ใดๆ ในระบบจริงหรือไม่ — ไม่ผูกกับ QR device
     เจาะจงตัวใดตัวหนึ่ง รับ path ตรงๆ จาก caller

ทั้งสองฝั่งไม่ block main thread: ฝั่งเขียนเปิดแบบ O_NONBLOCK เขียนแล้วปิดทันที
ฝั่งอ่านเปิดแบบ O_NONBLOCK + select() poll ใน background thread แยก
"""
from __future__ import annotations

import os
import select
import stat
import threading
from typing import Any

_ENXIO = 6  # errno: "No such device or address" — ไม่มี reader เปิด pipe รออยู่ฝั่งตรงข้าม


def is_fifo(path: str) -> bool:
    """
    เช็คว่า path เป็น named pipe (FIFO) จริงหรือไม่

    หมายเหตุ: `os.path` **ไม่มี** ฟังก์ชัน `isfifo()` (คนละอย่างกับ `isfile()`/`isdir()` ที่มี) —
    เข้าใจผิดกันมาตั้งแต่โค้ดเดิมก่อนหน้านี้ (`server.py: qr_pipe_create_api`) เรียก
    `os.path.isfifo()` ตรงๆ ซึ่งไม่มีอยู่จริง โยน `AttributeError` ทุกครั้งที่เรียก (เห็นจาก
    journalctl traceback จริง) ต้องเช็คผ่าน `stat.S_ISFIFO(os.stat(path).st_mode)` แทน
    """
    try:
        return stat.S_ISFIFO(os.stat(path).st_mode)
    except OSError:
        return False


# ── Write side ───────────────────────────────────────────────────────────────


def write_line_to_pipe(path: str, line: str) -> dict[str, Any]:
    """
    เขียน `line` + "\\n" ลง named pipe ที่ path แบบ non-blocking

    คืน status dict รูปแบบเดียวกับ publish_qr_scan_for_device() (mqtt) เพื่อให้ frontend
    ใช้ field เดียวกันแสดงสีของ integration chip ได้:
        {"enabled": True, "connected": bool, "published": bool, "error": str | None}

    "connected" = มี reader เปิด pipe รออยู่ฝั่งตรงข้าม ณ ขณะเขียน — ถ้าไม่มี reader
    การเปิดแบบ O_NONBLOCK จะได้ OSError(errno=ENXIO) ทันที ไม่ block loop หลักของ SSE
    """
    status: dict[str, Any] = {"enabled": True, "connected": False, "published": False, "error": None}
    if not path:
        status["error"] = "path ว่างเปล่า"
        return status

    try:
        if not os.path.exists(path):
            os.mkfifo(path, 0o666)
            os.chmod(path, 0o666)  # umask กรอง mode ที่ mkfifo() ขอไว้ — chmod ซ้ำให้ชัวร์
        elif not is_fifo(path):
            status["error"] = f"{path} มีอยู่แล้วแต่ไม่ใช่ pipe"
            return status
    except FileExistsError:
        pass  # race: อีก thread/request สร้างไปแล้ว — ไม่ใช่ error จริง
    except OSError as e:
        status["error"] = f"{type(e).__name__}: {e}"
        return status

    fd = None
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        status["connected"] = True
        os.write(fd, (line + "\n").encode("utf-8"))
        status["published"] = True
    except OSError as e:
        status["error"] = "ไม่มี reader เปิด pipe รออยู่ (ENXIO)" if e.errno == _ENXIO else str(e)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
    return status


def publish_qr_scan_to_pipe_for_device(device_id: str, scan: str) -> dict[str, Any]:
    """
    Device-aware pipe write — อ่าน integration config (enabled/path) ของ device_id จาก
    device_integrations (type="pipe") สดทุกครั้ง (ไม่ cache) เหมือน publish_qr_scan_for_device()
    ฝั่ง MQTT แล้วค่อยเขียนจริงถ้า enabled

        enabled=False → device ไม่มี integration แบบ "pipe" หรือปิดอยู่ (ไม่ใช่ error)
    """
    from core.database import list_device_integrations

    integrations = list_device_integrations(device_id)
    pipe_integ = integrations.get("pipe")
    if not pipe_integ or not pipe_integ.get("enabled"):
        return {"enabled": False, "connected": False, "published": False, "error": None}

    path = str(pipe_integ.get("path") or "/tmp/vas_qr_pipe").strip()
    return write_line_to_pipe(path, scan)


# ── Read side (Pipe Tester) ─────────────────────────────────────────────────


class PipeReaderThread(threading.Thread):
    """
    Background daemon thread อ่านทีละบรรทัดจาก named pipe path ใดก็ได้ — ใช้กับหน้า
    Pipe Tester (/pipe-tester) เพื่อทดสอบว่ามีข้อมูลถูกเขียนเข้ามาจริงหรือไม่ ไม่ว่าจะเขียน
    จาก VAS เอง (publish_qr_scan_to_pipe_for_device) หรือจาก third-party process ภายนอก

    เปิด path แบบ O_RDONLY | O_NONBLOCK เสมอ (ไม่ block ตอน open ไม่ว่าจะมี writer หรือไม่)
    แล้วใช้ select() poll ทุก 0.5s เพื่อให้ stop() ทำงานได้ทันทีโดยไม่ค้าง

    หมายเหตุสำคัญ: FIFO จะคืนค่า EOF (read ได้ 0 byte) ทันทีที่ writer ทุกตัวปิด fd ไปหมด —
    ต้องปิด fd แล้วเปิดใหม่วนซ้ำ (reopen loop) ไม่งั้นจะไม่รับข้อมูลจาก writer ตัวถัดไปอีกเลย
    """

    POLL_TIMEOUT = 0.5
    READ_CHUNK = 4096

    def __init__(self, path: str) -> None:
        super().__init__(daemon=True, name=f"PipeReaderThread({path})")
        self.path = path
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_line: str | None = None
        self._last_seq = 0
        self._error: str | None = None
        self._connected = False  # True เมื่อเปิด fd สำเร็จ (ไม่ได้แปลว่ามี writer อยู่จริง)

    def run(self) -> None:
        try:
            if not os.path.exists(self.path):
                os.mkfifo(self.path, 0o666)
                os.chmod(self.path, 0o666)  # umask กรอง mode ที่ mkfifo() ขอไว้ — chmod ซ้ำให้ชัวร์
            elif not is_fifo(self.path):
                with self._lock:
                    self._error = f"{self.path} มีอยู่แล้วแต่ไม่ใช่ pipe"
                return
        except FileExistsError:
            pass  # race: ถูกสร้างไปแล้วโดย thread/request อื่น — ไม่ใช่ error จริง
        except OSError as e:
            with self._lock:
                self._error = f"{type(e).__name__}: {e}"
            return

        buf = b""
        fd: int | None = None
        try:
            while not self._stop_event.is_set():
                if fd is None:
                    try:
                        fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
                        with self._lock:
                            self._connected = True
                            self._error = None
                    except OSError as e:
                        with self._lock:
                            self._error = f"{type(e).__name__}: {e}"
                        if self._stop_event.wait(1.0):
                            break
                        continue

                try:
                    ready, _, _ = select.select([fd], [], [], self.POLL_TIMEOUT)
                except OSError:
                    break
                if not ready:
                    continue

                try:
                    chunk = os.read(fd, self.READ_CHUNK)
                except BlockingIOError:
                    continue
                except OSError as e:
                    with self._lock:
                        self._error = f"{type(e).__name__}: {e}"
                    os.close(fd)
                    fd = None
                    continue

                if chunk == b"":
                    # EOF — คืนค่าทันทีทั้งตอน "เพิ่งมี writer ปิด fd ไป" และตอน "ยังไม่เคยมี
                    # writer เลย" (สอง state นี้แยกไม่ออกจาก read() เฉยๆ) ปิด fd นี้แล้วเปิดใหม่
                    # เพื่อรอ writer ถัดไป — หน่วงสั้นๆ ก่อน reopen กัน busy-loop กิน CPU 100%
                    # ตอนยังไม่มี writer เลย (ไม่งั้น open→EOF→close จะวนรัวๆ ไม่มีการพัก)
                    os.close(fd)
                    fd = None
                    with self._lock:
                        self._connected = False
                    if self._stop_event.wait(0.15):
                        break
                    continue

                buf += chunk
                while b"\n" in buf:
                    raw_line, buf = buf.split(b"\n", 1)
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    with self._lock:
                        self._last_line = line
                        self._last_seq += 1
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def stop(self) -> None:
        self._stop_event.set()

    @property
    def last_line(self) -> str | None:
        with self._lock:
            return self._last_line

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._last_seq

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected


_reader_lock = threading.Lock()
_reader: PipeReaderThread | None = None


def get_pipe_reader() -> PipeReaderThread | None:
    with _reader_lock:
        return _reader


def start_pipe_reader(path: str) -> PipeReaderThread:
    """เริ่ม (หรือคืน thread เดิมถ้า path เดียวกันกำลังรันอยู่แล้ว — idempotent)"""
    global _reader
    with _reader_lock:
        if _reader is not None and _reader.is_alive() and _reader.path == path:
            return _reader
        old = _reader
        _reader = PipeReaderThread(path)
        _reader.start()
    if old is not None and old.is_alive():
        old.stop()
        old.join(timeout=2.0)
    return _reader


def stop_pipe_reader() -> None:
    global _reader
    with _reader_lock:
        r = _reader
        _reader = None
    if r is not None:
        r.stop()
        r.join(timeout=2.0)


# ── System-wide FIFO scan (หน้า "รายการ Pipe" ใน Named Pipe) ────────────────


DEFAULT_SCAN_DIRS = ["/tmp", "/var/run", "/run"]


def scan_system_fifos(
    search_dirs: list[str] | None = None,
    max_depth: int = 3,
    max_results: int = 200,
) -> list[dict[str, Any]]:
    """
    สแกนหา named pipe (FIFO) ทั้งหมดที่พบในระบบ ภายใต้ path ที่กำหนด
    (default: /tmp, /var/run, /run) — ใช้สำหรับหน้า "รายการ Pipe" เพื่อ debug ว่ามี
    pipe อะไรอยู่ในระบบบ้าง ไม่ว่าจะเป็นของ VAS เองหรือของ third-party process

    ไม่รับประกันว่าจะเจอทุกตัว — ข้าม path ที่ไม่มีสิทธิ์อ่าน (root-owned dirs ฯลฯ)
    เงียบๆ และจำกัดความลึก/จำนวนผลลัพธ์กันสแกนนานหรือกิน resource เกินจำเป็น
    """
    if search_dirs is None:
        search_dirs = DEFAULT_SCAN_DIRS

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for base in search_dirs:
        if not os.path.isdir(base):
            continue
        base_depth = base.rstrip("/").count("/")
        for root, dirs, files in os.walk(base, topdown=True, onerror=lambda _e: None):
            depth = root.rstrip("/").count("/") - base_depth
            if depth >= max_depth:
                dirs[:] = []  # ไม่ลงลึกไปกว่านี้

            for name in files:
                full = os.path.join(root, name)
                # /var/run มักเป็น symlink ไป /run — resolve ก่อนกันเจอ pipe เดียวกันซ้ำสองแถว
                real = os.path.realpath(full)
                if real in seen:
                    continue
                seen.add(real)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                if not stat.S_ISFIFO(st.st_mode):
                    continue
                results.append({
                    "path": full,
                    "mode": oct(stat.S_IMODE(st.st_mode)),
                    "mtime": st.st_mtime,
                })
                if len(results) >= max_results:
                    return results
    return results
