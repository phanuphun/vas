"""
scan_publisher.py — background watcher ที่ log/publish ทุก QR scan โดยไม่ต้องพึ่งว่ามี
browser เปิดหน้า SSE (`/api/qr/stream`) อยู่หรือไม่

ปัญหาเดิม: โค้ด log_qr_scan() / publish MQTT / publish pipe ทั้งหมดอยู่ *ข้างใน* generator
ของ `/api/qr/stream` (server.py) — แปลว่าทำงานก็ต่อเมื่อมี browser tab เปิดหน้า QR500 ค้างไว้
(เปิด SSE connection อยู่) เท่านั้น พอปิดหน้านั้นไป (ปิด browser/tab, network ตัด ฯลฯ)
generator จบการทำงาน (`GeneratorExit`) — reader thread (features/qr/reader.py) ยังอ่าน
scan ต่อเบื้องหลังตามปกติ แต่ไม่มีใคร log ลง DB หรือ publish ออก MQTT/pipe อีกเลย จนกว่าจะมี
browser มาเปิดหน้าใหม่อีกครั้ง — เป็นสาเหตุที่ integration "หายไปบ้าง" เวลาไม่มีคนเฝ้าหน้าเว็บ

วิธีแก้: ย้าย log/publish logic ทั้งหมดมาไว้ใน background thread ตัวนี้ที่ start ครั้งเดียว
ตอน server boot (พร้อมกับ auto-start QR reader ใน server.py) แล้วให้ทำงานตลอดอายุของ process
ไม่ผูกกับ browser connection ใดๆ — ผลลัพธ์ (scan, status ของ mqtt/pipe) จะถูกเก็บไว้ใน
in-memory holder (`get_last_event()`) ให้ `/api/qr/stream` แค่ "อ่านมาโชว์" กับ browser
ไม่ต้อง publish ซ้ำเอง (กัน publish/log ซ้ำสองรอบถ้ามีหลาย client เชื่อม SSE พร้อมกันด้วย)
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

POLL_INTERVAL = 0.2
RESTART_INTERVAL = 8.0  # retry เริ่ม reader ใหม่ทุกกี่วิ ถ้า reader ตายอยู่


class ScanPublisherThread(threading.Thread):
    """Background daemon thread เดียว อายุเท่า process — ไม่ต้อง start/stop ตาม client"""

    def __init__(self) -> None:
        super().__init__(daemon=True, name="ScanPublisherThread")
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_event: dict[str, Any] | None = None
        self._last_event_seq = 0

    def stop(self) -> None:
        self._stop_event.set()

    def get_last_event(self) -> tuple[dict[str, Any] | None, int]:
        """คืน (event dict ล่าสุด, publish_seq) — thread-safe อ่านโดย SSE endpoint หลายตัวพร้อมกันได้"""
        with self._lock:
            return self._last_event, self._last_event_seq

    def run(self) -> None:
        from features.qr.reader import get_reader, start_reader
        from features.qr.registry import is_installed as _qr_is_installed

        def _try_start():
            r = get_reader()
            if r is not None and r.is_alive():
                return r
            if not _qr_is_installed("zkteco-qr500"):
                return None
            try:
                return start_reader()
            except Exception:
                return None

        last_seq = -1
        last_restart_try = 0.0

        while not self._stop_event.is_set():
            if self._stop_event.wait(POLL_INTERVAL):
                break
            now = time.monotonic()

            reader = get_reader()
            alive = reader is not None and reader.is_alive()

            if not alive and now - last_restart_try >= RESTART_INTERVAL:
                last_restart_try = now
                restarted = _try_start()
                if restarted is not None and restarted.is_alive():
                    reader = restarted
                    alive = True

            if not (reader is not None and alive):
                continue

            scan = reader.last_scan
            seq = getattr(reader, "last_scan_seq", None)
            if scan is None or seq is None or seq == last_seq:
                continue
            last_seq = seq

            ts = datetime.now(timezone.utc).isoformat()
            scan_raw_keycode = getattr(reader, "last_scan_raw", None)
            scan_raw_report = getattr(reader, "last_scan_raw_report", None)
            read_mode = getattr(reader, "read_mode", None)

            # Log ลง DB ก่อน publish เสมอ (ไม่ให้ log หายถ้า publish error)
            try:
                from core.database import log_qr_scan as _db_log_qr
                _db_log_qr(
                    scan, reader.device_path, ts,
                    raw_keycode=scan_raw_keycode,
                    raw_report=scan_raw_report,
                    read_mode=read_mode,
                )
            except Exception:
                pass

            mqtt_status: dict[str, object] = {
                "enabled": False, "connected": False, "published": False, "error": None,
            }
            try:
                from features.mqtt.client import publish_qr_scan_for_device as _mqtt_publish
                mqtt_status = _mqtt_publish(
                    "zkteco-qr500",
                    scan, reader.device_path, ts,
                    scan_raw_keycode=scan_raw_keycode,
                    scan_raw_report=scan_raw_report,
                    read_mode=read_mode,
                )
            except Exception as exc:
                mqtt_status = {"enabled": True, "connected": False, "published": False, "error": str(exc)}

            pipe_status: dict[str, object] = {
                "enabled": False, "connected": False, "published": False, "error": None,
            }
            try:
                from features.qr.pipe_io import publish_qr_scan_to_pipe_for_device as _pipe_publish
                pipe_status = _pipe_publish("zkteco-qr500", scan)
            except Exception as exc:
                pipe_status = {"enabled": True, "connected": False, "published": False, "error": str(exc)}

            event = {
                "scan": scan,
                "device": reader.device_path,
                "ts": ts,
                "raw_keycode": scan_raw_keycode,
                "raw_report": scan_raw_report,
                "read_mode": read_mode,
                "mqtt": mqtt_status,
                "pipe": pipe_status,
            }
            with self._lock:
                self._last_event = event
                self._last_event_seq += 1


_publisher_lock = threading.Lock()
_publisher: ScanPublisherThread | None = None


def start_scan_publisher() -> ScanPublisherThread:
    """เริ่ม background publisher (idempotent — เรียกซ้ำได้ปลอดภัย คืน thread เดิมถ้ารันอยู่แล้ว)"""
    global _publisher
    with _publisher_lock:
        if _publisher is not None and _publisher.is_alive():
            return _publisher
        _publisher = ScanPublisherThread()
        _publisher.start()
        return _publisher


def get_scan_publisher() -> ScanPublisherThread | None:
    with _publisher_lock:
        return _publisher


def stop_scan_publisher() -> None:
    global _publisher
    with _publisher_lock:
        p = _publisher
        _publisher = None
    if p is not None:
        p.stop()
        p.join(timeout=2.0)
