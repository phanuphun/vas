"""
VAS — Kiosk MQTT Heartbeat

Background thread ที่ publish สถานะ kiosk (readiness/session/autostart) ไปยัง MQTT broker
เป็นระยะๆ ตาม interval ที่ตั้งไว้ — เปิด-ปิดได้ต่อเครื่อง เก็บ config ไว้ใน device_integrations
(device_id="kiosk", integration_type="mqtt") ตาราง/pattern เดียวกับที่หน้า QR500 ใช้อยู่แล้ว
(ดู features/qr/registry.py) เพียงแต่ device_id คงที่เป็น "kiosk" เพราะ VAS instance หนึ่งตัว
ดูแล kiosk เครื่องเดียวเสมอ (ต่าง user แต่ device_id เดียวกัน ไม่ต้องผูกกับ username)

ปิดช่องว่างที่ระบบเดิมไม่มีทางรู้ว่า kiosk "ทำงานอยู่จริง" ไหมถ้าไม่เดินไปดูหน้าจอ — heartbeat
"alive" ยังไม่เท่ากับ "chromium ไม่ crash loop" ตรงๆ (ต้องมี agent ฝั่ง kiosk เองถึงจะรู้แบบนั้น)
แต่เป็นก้าวแรกที่ทำได้จากฝั่ง VAS server โดยไม่ต้องแตะ kiosk-launch.sh บนเครื่อง kiosk เอง

Thread lifecycle pattern เลียนแบบ features/qr/reader.py (module-level singleton + lock +
start/stop function) เพื่อให้สอดคล้องกับ convention เดิมของโปรเจกต์
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from features.kiosk.manager import collect_kiosk_heartbeat_payload

__all__ = [
    "DEFAULT_HEARTBEAT_INTERVAL",
    "KIOSK_DEVICE_ID",
    "MAX_HEARTBEAT_INTERVAL",
    "MIN_HEARTBEAT_INTERVAL",
    "KioskHeartbeatThread",
    "get_heartbeat_thread",
    "publish_kiosk_heartbeat",
    "start_heartbeat",
    "stop_heartbeat",
]

KIOSK_DEVICE_ID = "kiosk"
DEFAULT_HEARTBEAT_INTERVAL = 30
MIN_HEARTBEAT_INTERVAL = 5
MAX_HEARTBEAT_INTERVAL = 3600


def publish_kiosk_heartbeat() -> dict[str, object]:
    """
    Publish heartbeat หนึ่งครั้ง — คืน status dict เสมอ ไม่ raise (เรียกจาก background thread
    ที่ต้องไม่ตายเพราะ broker unreachable ชั่วคราว) รูปแบบเดียวกับ
    features.mqtt.client.publish_qr_scan_for_device():

        {"enabled": bool, "connected": bool, "published": bool, "error": str | None}
    """
    from core.database import list_device_integrations
    from features.mqtt.client import get_mqtt_client

    integrations = list_device_integrations(KIOSK_DEVICE_ID)
    mqtt_integ = integrations.get("mqtt")
    if not mqtt_integ or not mqtt_integ.get("enabled"):
        return {"enabled": False, "connected": False, "published": False, "error": None}

    broker_id = mqtt_integ.get("broker_id")
    if broker_id is None:
        return {"enabled": True, "connected": False, "published": False, "error": "ยังไม่ได้เลือก broker"}

    client = get_mqtt_client(broker_id)  # type: ignore[arg-type]
    if client is None:
        return {"enabled": True, "connected": False, "published": False, "error": "broker ยังไม่ได้เชื่อมต่อ"}

    topic = str(mqtt_integ.get("topic") or "vas/kiosk/heartbeat")
    try:
        payload = json.dumps(collect_kiosk_heartbeat_payload(), ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 — thread ต้องไม่ตายเพราะ payload สร้างพัง
        return {"enabled": True, "connected": client.is_connected, "published": False, "error": str(exc)}

    ok = client.publish(topic, payload)
    error = None if ok else (client.last_error or "publish ไม่สำเร็จ")
    return {"enabled": True, "connected": client.is_connected, "published": ok, "error": error}


class KioskHeartbeatThread(threading.Thread):
    """
    Background thread — publish heartbeat ทุก `interval` วินาที จนกว่าจะเรียก stop()

    Usage:
        thread = KioskHeartbeatThread(interval=30)
        thread.start()
        thread.last_result   -> dict | None   ผลลัพธ์ publish ล่าสุด
        thread.stop()
        thread.join(timeout=2.0)
    """

    def __init__(self, interval: int = DEFAULT_HEARTBEAT_INTERVAL) -> None:
        super().__init__(daemon=True, name="kiosk-heartbeat")
        self.interval = max(MIN_HEARTBEAT_INTERVAL, min(int(interval), MAX_HEARTBEAT_INTERVAL))
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_result: dict[str, object] | None = None
        self._last_published_at: str | None = None

    @property
    def last_result(self) -> "dict[str, object] | None":
        with self._lock:
            return self._last_result

    @property
    def last_published_at(self) -> "str | None":
        with self._lock:
            return self._last_published_at

    def run(self) -> None:
        # publish รอบแรกทันที ไม่ต้องรอ interval เต็ม — เปิด toggle แล้วเห็นผลเร็ว
        while not self._stop_event.is_set():
            result = publish_kiosk_heartbeat()
            with self._lock:
                self._last_result = result
                if result.get("published"):
                    self._last_published_at = datetime.now(timezone.utc).isoformat()
            self._stop_event.wait(self.interval)

    def stop(self) -> None:
        self._stop_event.set()


_heartbeat_thread: "KioskHeartbeatThread | None" = None
_heartbeat_lock = threading.Lock()


def get_heartbeat_thread() -> "KioskHeartbeatThread | None":
    """Return running heartbeat thread หรือ None"""
    with _heartbeat_lock:
        return _heartbeat_thread


def start_heartbeat(interval: int = DEFAULT_HEARTBEAT_INTERVAL) -> KioskHeartbeatThread:
    """เริ่ม heartbeat thread global singleton — ถ้ากำลังรันด้วย interval เดิมอยู่แล้วคืนตัวเดิม
    ถ้า interval เปลี่ยนจะหยุดตัวเก่าแล้วเริ่มใหม่ (Event.wait() กำลังหลับอยู่ เปลี่ยนค่าตรงๆ
    ไม่ได้ระหว่างทาง restart ง่ายกว่าและชัดเจนกว่า)"""
    global _heartbeat_thread
    with _heartbeat_lock:
        if _heartbeat_thread is not None and _heartbeat_thread.is_alive():
            if _heartbeat_thread.interval == interval:
                return _heartbeat_thread
            _heartbeat_thread.stop()
            _heartbeat_thread = None

        thread = KioskHeartbeatThread(interval=interval)
        thread.start()
        _heartbeat_thread = thread
        return thread


def stop_heartbeat() -> None:
    """หยุด global heartbeat thread ถ้ากำลัง run"""
    global _heartbeat_thread
    with _heartbeat_lock:
        thread = _heartbeat_thread
        _heartbeat_thread = None
    # join นอก lock เพื่อไม่ให้ deadlock กับ thread ที่กำลัง run
    if thread is not None:
        thread.stop()
        thread.join(timeout=2.0)
