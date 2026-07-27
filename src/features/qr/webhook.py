"""
webhook.py — ส่ง HTTP request ไปยัง URL ที่ผู้ใช้ตั้งค่าไว้ (integration "webhook") ทุกครั้งที่
อ่าน QR/RFID ได้ -- ก่อนหน้านี้ integration นี้มีแค่ UI form + endpoint save ค่า
(`/api/qr/integrations/webhook`) แต่ไม่มี backend ส่งจริงเลย (ดู CHANGELOG.md) ไฟล์นี้คือ
ส่วนที่ขาดไป

สำคัญมาก -- ทำไมต้องมี background dispatcher thread + queue แยกต่างหาก (ไม่เรียก HTTP ตรงๆ
จาก ScanPublisherThread.run() เหมือน mqtt/pipe):

    MQTT (features/mqtt/client.py) publish แบบ async ผ่าน paho-mqtt (แค่ enqueue เข้า TCP
    send buffer แล้ว return ทันที) และ pipe (features/qr/pipe_io.py) เปิดแบบ O_NONBLOCK เขียน
    แล้วปิดทันที ทั้งสองแบบเรียกตรงๆ ใน ScanPublisherThread.run() ได้โดยไม่บล็อก loop หลัก

    Webhook เป็น HTTP round-trip เต็มรูปแบบ + retry/backoff ที่อาจกินเวลารวมหลักสิบวินาที (เช่น
    retry_max_attempts=5, backoff แบบ exponential) -- ถ้าเรียก urllib.request.urlopen() ตรงๆ
    ใน ScanPublisherThread.run() จะบล็อก loop หลักทั้งหมด (log DB, mqtt, pipe, auto-restart
    check ของ scan ถัดไปทุกตัว) จนกว่า webhook นี้จะส่งเสร็จหรือ timeout ครบทุก retry --
    เพราะงั้นต้องแยก thread+queue ต่างหาก (pattern เดียวกับ WebhookDispatcher ใน
    qr500-reader/src/qr500_reader/dispatch.py -- โปรเจกต์พี่น้องที่อ่าน QR500-BM ตัวเดียวกัน
    แต่ deploy แยกจาก VAS) publish() แค่ enqueue แล้ว return ทันที ส่งจริงใน background thread
    เรียงคิวทีละตัว (ไม่ parallel -- กันยิงหลาย request แข่งกันไปโดน rate limit ปลายทางเพิ่ม)
"""
from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.request
from typing import Any

DEVICE_ID = "zkteco-qr500"

DEFAULT_RETRY_BACKOFF_SECONDS = 1.0
DEFAULT_RETRY_MAX_BACKOFF_SECONDS = 30.0
DEFAULT_RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
QUEUE_POLL_INTERVAL = 0.5


def send_webhook_request(
    url: str,
    method: str,
    timeout_seconds: float,
    retry_max_attempts: int,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    retry_max_backoff_seconds: float = DEFAULT_RETRY_MAX_BACKOFF_SECONDS,
    retry_status_codes: frozenset[int] = DEFAULT_RETRY_STATUS_CODES,
    retry_on_network_error: bool = True,
) -> tuple[bool, int | None, str | None]:
    """
    ส่ง HTTP request พร้อม retry + exponential backoff -- คืน (ok, status_code, error)

    ใช้ urllib.request (stdlib) แทน `requests` เพื่อไม่ต้องเพิ่ม dependency ใหม่ให้โปรเจกต์
    (ตาม pattern เดียวกับ qr500_reader.webhook.WebhookClient.send())
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req_headers = {"Content-Type": "application/json", **(headers or {})}

    last_status: int | None = None
    last_error: str | None = None
    attempt = 0
    max_attempts = max(1, retry_max_attempts)

    while attempt < max_attempts:
        attempt += 1
        request = urllib.request.Request(url, data=body, method=method, headers=req_headers)
        should_retry = False
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                status_code = int(response.status)
                if status_code < 400:
                    return True, status_code, None
                last_status = status_code
                last_error = f"HTTP {status_code}"
                should_retry = status_code in retry_status_codes
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            last_error = f"HTTP {exc.code}: {exc.reason}"
            should_retry = exc.code in retry_status_codes
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_status = None
            last_error = str(exc)
            should_retry = retry_on_network_error

        if not should_retry or attempt >= max_attempts:
            break

        delay = min(retry_backoff_seconds * (2 ** (attempt - 1)), retry_max_backoff_seconds)
        time.sleep(delay)

    return False, last_status, last_error


class WebhookDispatcherThread(threading.Thread):
    """
    Background daemon thread เดียว อายุเท่า process -- consume scan event จาก internal queue
    แล้วส่ง HTTP request ทีละตัวเรียงลำดับ (ไม่ parallel) โหลด config (`device_integrations`
    ประเภท "webhook") ใหม่ทุกครั้งก่อนส่ง เพื่อให้กด "บันทึก Webhook" แล้วมีผลทันทีโดยไม่ต้อง
    restart server (เหมือน mqtt/pipe ที่โหลด config สดทุกครั้งเช่นกัน)
    """

    def __init__(self) -> None:
        super().__init__(daemon=True, name="qr-webhook-dispatcher")
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_status: dict[str, Any] = {
            "enabled": False, "connected": False, "published": False, "error": None,
        }

    def publish(self, event: dict[str, Any]) -> None:
        """เรียกจาก ScanPublisherThread -- enqueue อย่างเดียว, return ทันทีเสมอ ไม่รอ HTTP"""
        self._queue.put(event)

    def stop(self) -> None:
        self._stop_event.set()

    def get_last_status(self) -> dict[str, Any]:
        """คืนสถานะการส่ง webhook ครั้งล่าสุด (thread-safe) -- รูปแบบเดียวกับ mqtt_status/
        pipe_status: {"enabled": bool, "connected": bool, "published": bool, "error": str|None}
        อาจ "ล้าหลัง" scan ปัจจุบันไป 1 รอบเพราะส่งแบบ async ผ่าน queue (เหมือน SSE status
        อื่นๆ ที่เป็น eventually-consistent ไม่ใช่ผูกกับ scan นี้เป๊ะๆ)"""
        with self._lock:
            return dict(self._last_status)

    def _set_status(self, status: dict[str, Any]) -> None:
        with self._lock:
            self._last_status = status

    def run(self) -> None:
        from features.qr.registry import load_integrations

        while not self._stop_event.is_set():
            try:
                event = self._queue.get(timeout=QUEUE_POLL_INTERVAL)
            except queue.Empty:
                continue

            try:
                integ = load_integrations(DEVICE_ID).get("webhook") or {}
            except Exception:
                integ = {}

            if not integ.get("enabled"):
                self._set_status({"enabled": False, "connected": False, "published": False, "error": None})
                continue

            url = str(integ.get("url") or "").strip()
            if not url:
                self._set_status({
                    "enabled": True, "connected": False, "published": False,
                    "error": "ยังไม่ได้ตั้งค่า Base URL",
                })
                continue

            method = str(integ.get("method") or "POST").upper()
            retry_max_attempts = int(integ.get("retry") or 5)
            timeout_seconds = float(integ.get("timeout_sec") or 5)

            from features.qr.payload import build_scan_body
            payload = build_scan_body(event)

            try:
                ok, status_code, error = send_webhook_request(
                    url, method, timeout_seconds, retry_max_attempts, payload,
                )
            except Exception as exc:  # กัน dispatcher thread ตายทิ้งถ้ามี edge case ที่ไม่คาดคิด
                ok, status_code, error = False, None, str(exc)

            self._set_status({
                "enabled": True,
                "connected": True,  # ส่ง request ออกไปแล้วจริง (ต่างจาก mqtt "connected" ที่หมายถึง
                                     # persistent connection -- webhook ไม่มีแนวคิดนี้ ใช้แทนว่า
                                     # "config ครบพอจะส่งได้" ให้ frontend ใช้ตัดสี chip แบบเดียวกัน)
                "published": ok,
                "error": None if ok else (error or f"HTTP {status_code}"),
            })


_dispatcher_lock = threading.Lock()
_dispatcher: WebhookDispatcherThread | None = None


def start_webhook_dispatcher() -> WebhookDispatcherThread:
    """เริ่ม background dispatcher (idempotent -- เรียกซ้ำได้ปลอดภัย คืน thread เดิมถ้ารันอยู่แล้ว)"""
    global _dispatcher
    with _dispatcher_lock:
        if _dispatcher is not None and _dispatcher.is_alive():
            return _dispatcher
        _dispatcher = WebhookDispatcherThread()
        _dispatcher.start()
        return _dispatcher


def get_webhook_dispatcher() -> WebhookDispatcherThread | None:
    with _dispatcher_lock:
        return _dispatcher


def stop_webhook_dispatcher() -> None:
    global _dispatcher
    with _dispatcher_lock:
        d = _dispatcher
        _dispatcher = None
    if d is not None:
        d.stop()
        d.join(timeout=2.0)
