"""
MQTT client สำหรับ VAS — publish QR scan events ออกไปยัง broker.

Dependencies:
    paho-mqtt >= 1.6  (sudo apt install -y python3-paho-mqtt)

Config storage:
    ตาราง mqtt_brokers ใน SQLite (~/.config/vas/vas.db) — ไม่ใช้ config.json อีกต่อไป

Multi-broker:
    รองรับ broker หลายตัว connect พร้อมกันจริง — เก็บใน `_clients: dict[int, VasMqttClient]`
    (key = broker_id) แทน singleton ตัวเดียวแบบเดิม แต่ละ broker enable/disable อิสระต่อกัน
"""
from __future__ import annotations

import json
import random
import string
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PAYLOAD_MODES = ("decoded", "raw_keycode", "raw_report")
"""
payload_mode:
    "decoded"     → publish ข้อมูลหลัง decode แล้ว     {"scan":"3833401723","device":"...","ts":"...","read_mode":"..."}
    "raw_keycode" → publish raw keycodes ก่อน decode  {"scan":[39,30,30,...],"device":"...","ts":"...","read_mode":"..."}
    "raw_report"  → publish raw HID byte report (hex) {"scan":["a1000000...","00000000..."],"device":"...","ts":"...","read_mode":"..."}
                    (มีเฉพาะ read_mode="hidraw" เท่านั้น -- evdev ไม่มี raw byte report)

ทุก mode แนบ field "read_mode" เข้า payload เสมอ (ค่า 'hidraw' | 'evdev' | None)
ถ้าข้อมูลของ mode ที่เลือกเป็น None (เช่นขอ raw_report แต่ read_mode="evdev") จะไม่ publish
และ return False -- ห้าม silent fallback ไปโหมดอื่น
"""


@dataclass
class MqttConfig:
    enabled: bool = False
    broker_url: str = "mqtts://mqtt-apps.hapysterile.xenex.io:8883"
    username: str = ""
    password: str = ""
    client_id: str = ""          # ว่าง = auto-generate
    tls_insecure: bool = False   # True = rejectUnauthorized=false (self-signed cert)
    topic: str = "sterile/vending/qr/scan"
    qos: int = 1
    retain: bool = False
    payload_mode: str = "decoded"   # "decoded" | "raw_keycode" | "raw_report"

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "broker_url": self.broker_url,
            "username": self.username,
            "password": self.password,
            "client_id": self.client_id,
            "tls_insecure": self.tls_insecure,
            "topic": self.topic,
            "qos": self.qos,
            "retain": self.retain,
            "payload_mode": self.payload_mode,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> "MqttConfig":
        def _str(key: str, default: str = "") -> str:
            return str(d.get(key) or default)
        def _bool(key: str, default: bool = False) -> bool:
            v = d.get(key)
            if isinstance(v, bool):
                return v
            return default
        def _int(key: str, default: int = 1) -> int:
            try:
                return int(d.get(key, default))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return default
        mode = _str("payload_mode", "decoded")
        if mode not in PAYLOAD_MODES:
            mode = "decoded"
        return cls(
            enabled=_bool("enabled"),
            broker_url=_str("broker_url", cls.__dataclass_fields__["broker_url"].default),  # type: ignore[attr-defined]
            username=_str("username"),
            password=_str("password"),
            client_id=_str("client_id"),
            tls_insecure=_bool("tls_insecure"),
            topic=_str("topic", cls.__dataclass_fields__["topic"].default),  # type: ignore[attr-defined]
            qos=_int("qos", 1),
            retain=_bool("retain"),
            payload_mode=mode,
        )


def broker_db_to_config(broker: dict[str, object]) -> MqttConfig:
    """
    แปลง row จาก mqtt_brokers (dict จาก core.database.get_mqtt_broker()) เป็น MqttConfig
    ใช้เป็น in-memory transfer object เท่านั้น — ไม่ผูกกับไฟล์อีกต่อไป

    หมายเหตุ: mqtt_brokers ไม่มี column "topic" โดยตรง (topics เก็บแยกใน mqtt_broker_topics
    เพราะ broker หนึ่งตัวมีได้หลาย topic) — publish_qr_scan ใช้ topic แรกที่ enabled ของ
    broker นั้น (pattern เดียวกับ mqtt_broker_test_api ใน server.py) ถ้าไม่มี topic ที่ enabled เลย
    จะ fallback เป็นค่า default เดิม
    """
    topic = str(broker.get("topic") or "")
    if not topic:
        try:
            from core.database import list_mqtt_topics
            broker_id = broker.get("id")
            if broker_id is not None:
                topics = list_mqtt_topics(int(broker_id))  # type: ignore[arg-type]
                topic = next((str(t["topic"]) for t in topics if t.get("enabled")), "")
        except Exception:
            topic = ""
    if not topic:
        topic = "sterile/vending/qr/scan"

    return MqttConfig(
        enabled=bool(broker.get("enabled", False)),
        broker_url=str(broker.get("broker_url") or "mqtts://localhost:8883"),
        username=str(broker.get("username") or ""),
        password=str(broker.get("password") or ""),
        client_id=str(broker.get("client_id") or ""),
        tls_insecure=bool(broker.get("tls_insecure", False)),
        topic=topic,
        qos=int(broker.get("qos", 1)),  # type: ignore[arg-type]
        retain=bool(broker.get("retain", False)),
        payload_mode=str(broker.get("payload_mode") or "decoded"),
    )


# ---------------------------------------------------------------------------
# MQTT client singleton
# ---------------------------------------------------------------------------

def _gen_client_id() -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"vas-qr-reader-{suffix}"


def _parse_broker_url(url: str) -> tuple[str, int, bool, bool]:
    """
    Return (host, port, use_tls, use_websocket)

    Scheme mapping:
        mqtt://   → TCP plain,       port 1883
        mqtts://  → TCP + TLS,       port 8883
        ws://     → WebSocket plain, port 8083
        wss://    → WebSocket + TLS, port 8084
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "mqtt").lower()
    use_tls       = scheme in ("mqtts", "ssl", "wss")
    use_websocket = scheme in ("ws", "wss")
    host = parsed.hostname or "localhost"
    if parsed.port:
        port = parsed.port
    elif scheme == "wss":
        port = 8084
    elif scheme == "ws":
        port = 8083
    elif use_tls:
        port = 8883
    else:
        port = 1883
    return host, port, use_tls, use_websocket


class VasMqttClient:
    """
    Singleton MQTT client wrapper รอบ paho-mqtt.

    สร้างด้วย config → connect → publish_qr_scan()
    """

    def __init__(self, config: MqttConfig) -> None:
        self.config = config
        self._paho: object | None = None          # paho.mqtt.client.Client
        self._connected = False
        self._last_error: str | None = None
        self._lock = threading.Lock()
        self._on_connect_callbacks: list[Callable[[], None]] = []

    # ── public ────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def connect(self) -> None:
        """
        เริ่ม connect ใน background thread (non-blocking).
        เรียก connect() ซ้ำได้ — ถ้า connected อยู่แล้วจะ disconnect ก่อน
        Raises:
            ImportError: ถ้า paho-mqtt ไม่ได้ติดตั้ง
        """
        try:
            import paho.mqtt.client as _paho  # type: ignore[import]
        except ImportError:
            raise ImportError(
                "paho-mqtt ไม่ได้ติดตั้ง — รัน: sudo apt install -y python3-paho-mqtt"
            )

        with self._lock:
            if self._paho is not None:
                try:
                    self._paho.disconnect()  # type: ignore[union-attr]
                    self._paho.loop_stop()   # type: ignore[union-attr]
                except Exception:
                    pass
                self._paho = None
                self._connected = False

        cfg = self.config
        client_id = cfg.client_id.strip() or _gen_client_id()
        host, port, use_tls, use_websocket = _parse_broker_url(cfg.broker_url)

        client = _paho.Client(
            client_id=client_id,
            protocol=_paho.MQTTv311,
            clean_session=True,
            transport="websockets" if use_websocket else "tcp",
        )

        # Auth
        if cfg.username:
            client.username_pw_set(cfg.username, cfg.password or None)

        # WebSocket path — EMQX ใช้ /mqtt (paho default คือ /)
        if use_websocket:
            client.ws_set_options(path="/mqtt")

        # TLS (mqtts:// หรือ wss://)
        if use_tls:
            import ssl as _ssl
            if cfg.tls_insecure:
                # self-signed cert — ข้าม verify
                ctx = _ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = _ssl.CERT_NONE
                client.tls_set_context(ctx)
            else:
                client.tls_set(tls_version=_ssl.PROTOCOL_TLS_CLIENT)

        # Callbacks
        def on_connect(c, userdata, flags, rc):
            ok = rc == 0
            with self._lock:
                self._connected = ok
                self._last_error = None if ok else f"connect failed rc={rc}"

        def on_disconnect(c, userdata, rc):
            with self._lock:
                self._connected = False
                if rc != 0:
                    self._last_error = f"disconnected unexpectedly rc={rc}"

        def on_log(c, userdata, level, buf):
            pass  # suppress paho verbose logging

        client.on_connect    = on_connect
        client.on_disconnect = on_disconnect
        client.on_log        = on_log
        client.reconnect_delay_set(min_delay=3, max_delay=30)

        try:
            client.connect_async(host, port, keepalive=60)
            client.loop_start()  # background network thread
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            raise

        with self._lock:
            self._paho = client

    def disconnect(self) -> None:
        with self._lock:
            if self._paho is None:
                return
            client = self._paho
            self._paho = None
            self._connected = False
        try:
            client.disconnect()  # type: ignore[union-attr]
            client.loop_stop()   # type: ignore[union-attr]
        except Exception:
            pass

    def publish(self, topic: str, payload: str) -> bool:
        """
        Publish message — ถ้าไม่ connected จะ return False
        Returns:
            True ถ้า publish สำเร็จ (mid ได้รับ), False ถ้าไม่ connected หรือ error
        """
        with self._lock:
            client = self._paho
            connected = self._connected
        if not connected or client is None:
            return False
        try:
            result = client.publish(  # type: ignore[union-attr]
                topic, payload,
                qos=self.config.qos,
                retain=self.config.retain,
            )
            return result.rc == 0
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            return False

    def publish_qr_scan(
        self,
        scan: str,
        device: str,
        ts: str,
        scan_raw_keycode: "list[int] | None" = None,
        scan_raw_report: "list[str] | None" = None,
        read_mode: "str | None" = None,
        topic_override: "str | None" = None,
        payload_mode_override: "str | None" = None,
    ) -> bool:
        """
        Publish QR scan ไปยัง topic ที่ config ไว้ (หรือ topic_override ถ้าระบุ)

        payload_mode == "decoded"     → {"scan": "<decoded_text>",  "device":"...", "ts":"...", "read_mode":"..."}
        payload_mode == "raw_keycode" → {"scan": [39,30,30,...],    "device":"...", "ts":"...", "read_mode":"..."}
        payload_mode == "raw_report"  → {"scan": ["a1000000...",..],"device":"...", "ts":"...", "read_mode":"..."}

        ทุก mode แนบ "read_mode" เข้า payload เสมอ

        ถ้าข้อมูลของ payload_mode ที่เลือกเป็น None (เช่นขอ raw_report แต่ read_mode="evdev"
        ทำให้ scan_raw_report=None) → **ไม่ publish**, return False, log ผ่าน log_mqtt_event(ok=False)
        พร้อมเหตุผล -- ห้าม silent fallback ไปโหมดอื่น

        topic_override: ถ้าไม่ใช่ None ใช้แทน self.config.topic ทั้งใน publish() และใน
        payload/error-log construction — ใช้สำหรับ device-aware publish
        (ดู publish_qr_scan_for_device()) ที่ topic มาจาก device_integrations แทน broker เอง

        payload_mode_override: ถ้าไม่ใช่ None และอยู่ใน PAYLOAD_MODES ใช้แทน
        self.config.payload_mode — ให้ device_integrations (ต้นทางข้อมูลจริงคือฝั่ง QR
        reader) กำหนดรูปแบบ payload ต่อ device ได้ แทนที่จะผูกตายตัวกับ broker เพียงอย่างเดียว
        (broker.payload_mode ยังเป็นค่า default เผื่อ device ไม่ได้ override)
        """
        if not self.config.enabled:
            return False

        topic = topic_override if topic_override is not None else self.config.topic

        mode = self.config.payload_mode
        if payload_mode_override is not None and payload_mode_override in PAYLOAD_MODES:
            mode = payload_mode_override
        if mode == "raw_keycode":
            scan_value: object = scan_raw_keycode
        elif mode == "raw_report":
            scan_value = scan_raw_report
        else:
            scan_value = scan

        if scan_value is None:
            error_payload = json.dumps(
                {"error": f"{mode} not available for read_mode={read_mode}"},
                ensure_ascii=False,
            )
            try:
                from core.database import log_mqtt_event as _db_mqtt
                _db_mqtt(scan=scan, topic=topic, payload=error_payload, ok=False, ts=ts)
            except Exception:
                pass
            return False

        payload = json.dumps(
            {"scan": scan_value, "device": device, "ts": ts, "read_mode": read_mode},
            ensure_ascii=False,
        )
        ok = self.publish(topic, payload)
        try:
            from core.database import log_mqtt_event as _db_mqtt
            _db_mqtt(scan=scan, topic=topic, payload=payload, ok=ok, ts=ts)
        except Exception:
            pass
        return ok

    def status_dict(self) -> dict[str, object]:
        with self._lock:
            return {
                "enabled": self.config.enabled,
                "connected": self._connected,
                "broker_url": self.config.broker_url,
                "topic": self.config.topic,
                "last_error": self._last_error,
                "paho_available": _paho_available(),
            }


# ---------------------------------------------------------------------------
# Module-level multi-client registry
# ---------------------------------------------------------------------------
#
# แทนที่ singleton ตัวเดียว (_client) ด้วย dict เก็บ client ต่อ broker_id — รองรับหลาย broker
# connect พร้อมกันจริง แต่ละ broker enable/disable อิสระต่อกัน (broker หนึ่งตัว connect fail
# ต้องไม่กระทบ broker ตัวอื่น — ดู start_all_enabled_brokers())

_clients: dict[int, VasMqttClient] = {}
_client_lock = threading.Lock()


def get_mqtt_client(broker_id: int | None = None) -> VasMqttClient | None:
    """
    คืน client ตาม broker_id ที่ระบุ — ถ้าไม่ระบุ (None) ใช้ primary broker
    คืน None ถ้าไม่มี client สำหรับ broker นั้น (ยังไม่ได้ connect หรือไม่มี broker)
    """
    with _client_lock:
        if broker_id is not None:
            return _clients.get(broker_id)
        primary_clients = dict(_clients)
    if broker_id is None:
        from core.database import get_primary_broker_id
        primary_id = get_primary_broker_id()
        if primary_id is None:
            return None
        return primary_clients.get(primary_id)
    return None


def start_mqtt_broker(broker_id: int) -> VasMqttClient:
    """
    โหลด broker จาก DB ตาม broker_id, แปลงด้วย broker_db_to_config, สร้าง/เก็บใน
    _clients[broker_id] แล้ว connect() — ถ้ามี client เดิมของ broker นี้อยู่แล้วจะ disconnect ก่อน

    Raises:
        ImportError: ถ้า paho-mqtt ไม่ได้ติดตั้ง
        ValueError: ถ้าไม่พบ broker ตาม broker_id
    """
    from core.database import get_mqtt_broker
    broker = get_mqtt_broker(broker_id)
    if broker is None:
        raise ValueError(f"MQTT broker not found: id={broker_id}")

    cfg = broker_db_to_config(broker)
    with _client_lock:
        existing = _clients.get(broker_id)
        if existing is not None:
            existing.disconnect()
        c = VasMqttClient(cfg)
        c.connect()
        _clients[broker_id] = c
    return c


def stop_mqtt_broker(broker_id: int) -> None:
    """Disconnect broker ตาม broker_id แล้วลบออกจาก _clients"""
    with _client_lock:
        c = _clients.pop(broker_id, None)
    if c is not None:
        c.disconnect()


def start_all_enabled_brokers() -> None:
    """
    วน broker ทุกตัวที่ enabled=1 ใน DB แล้วเรียก start_mqtt_broker ทีละตัว
    แยก try/except ต่อ broker — broker ตัวหนึ่ง connect fail ต้องไม่ทำให้ตัวอื่นไม่ทำงาน
    """
    from core.database import list_mqtt_brokers
    for broker in list_mqtt_brokers():
        if not broker.get("enabled"):
            continue
        broker_id = broker.get("id")
        if broker_id is None:
            continue
        try:
            start_mqtt_broker(int(broker_id))  # type: ignore[arg-type]
        except Exception:
            pass  # broker ตัวนี้ connect ไม่สำเร็จ — ไม่กระทบ broker ตัวอื่น


def start_mqtt(config: MqttConfig | None = None) -> VasMqttClient:
    """
    (Legacy compat) เริ่ม MQTT client โดยใช้ config ที่ให้มาตรงๆ โดยไม่ผูกกับ broker_id ใน DB
    ใช้ broker_id=0 เป็น key ภายใน — สำหรับ caller เดิม (เช่น `vas mqtt test`) ที่ยังไม่ได้ผ่าน DB
    ถ้า config=None จะใช้ primary broker จาก DB แทน

    Raises:
        ImportError: ถ้า paho-mqtt ไม่ได้ติดตั้ง
    """
    if config is None:
        from core.database import get_primary_broker_id, get_mqtt_broker
        primary_id = get_primary_broker_id()
        if primary_id is not None:
            return start_mqtt_broker(primary_id)
        config = MqttConfig()

    with _client_lock:
        existing = _clients.get(0)
        if existing is not None:
            existing.disconnect()
        c = VasMqttClient(config)
        c.connect()
        _clients[0] = c
    return c


def stop_mqtt() -> None:
    """
    Disconnect + ลบ client ทั้งหมดใน registry (ทุก broker) — ใช้สำหรับ shutdown/legacy
    single-connection call sites ที่คาดหวังพฤติกรรม "ตัด MQTT ทั้งหมด"
    """
    with _client_lock:
        clients = list(_clients.values())
        _clients.clear()
    for c in clients:
        c.disconnect()


def publish_qr_scan(
    scan: str,
    device: str,
    ts: str,
    scan_raw_keycode: "list[int] | None" = None,
    scan_raw_report: "list[str] | None" = None,
    read_mode: "str | None" = None,
) -> bool:
    """
    Convenience wrapper — publish ไปยัง broker ที่ is_primary=1 เท่านั้น (ไม่ device-aware
    routing — เลือก broker ตาม device_integrations เป็น scope ของรอบถัดไป)
    """
    from core.database import get_primary_broker_id
    primary_id = get_primary_broker_id()
    if primary_id is None:
        return False
    c = get_mqtt_client(primary_id)
    if c is None:
        return False
    return c.publish_qr_scan(
        scan, device, ts,
        scan_raw_keycode=scan_raw_keycode,
        scan_raw_report=scan_raw_report,
        read_mode=read_mode,
    )


def publish_qr_scan_for_device(
    device_id: str,
    scan: str,
    device: str,
    ts: str,
    scan_raw_keycode: "list[int] | None" = None,
    scan_raw_report: "list[str] | None" = None,
    read_mode: "str | None" = None,
) -> bool:
    """
    Device-aware publish — เลือก broker ตาม device_integrations ของ device_id นั้นๆ แทน
    primary broker ตรงๆ (ต่างจาก publish_qr_scan() ด้านบนที่เป็น primary-broker-only)

    Return False (ไม่ error) ถ้า:
        - device ไม่มี integration แบบ "mqtt" หรือไม่ enabled
        - integration ไม่มี broker_id ผูกไว้
        - broker ที่ผูกไว้ยังไม่มี client connect อยู่ (get_mqtt_client คืน None)

    payload_mode: อ่านจาก device_integrations (mqtt_integ["payload_mode"]) ถ้าตั้งไว้ — เก็บใน
    settings_json ผ่าน upsert_device_integration() แบบเดียวกับ field เสริมอื่นๆ (ไม่ต้อง
    migration schema เพิ่ม) ถือเป็น override เหนือ broker.payload_mode เพราะข้อมูล raw
    ต้นทางจริงๆ มาจากฝั่ง QR reader ต่อ device ไม่ใช่จากฝั่ง broker — ถ้า device ไม่ได้ตั้งไว้
    (None/ค่าว่าง) จะ fallback ไปใช้ payload_mode ของ broker เอง (ดู publish_qr_scan())

    หมายเหตุ: นี่คือ code path ที่ SSE loop (server.py qr_stream_api) ใช้จริง — แยกจาก
    publish_qr_scan() ที่ยังใช้กับ `vas mqtt test` / `/api/mqtt/test` เหมือนเดิม
    """
    from core.database import list_device_integrations, get_mqtt_broker  # noqa: F401

    integrations = list_device_integrations(device_id)
    mqtt_integ = integrations.get("mqtt")
    if not mqtt_integ or not mqtt_integ.get("enabled"):
        return False

    broker_id = mqtt_integ.get("broker_id")
    if broker_id is None:
        return False

    c = get_mqtt_client(broker_id)  # type: ignore[arg-type]
    if c is None:
        return False

    topic = mqtt_integ.get("topic") or None
    payload_mode = mqtt_integ.get("payload_mode") or None
    return c.publish_qr_scan(
        scan, device, ts,
        scan_raw_keycode=scan_raw_keycode,
        scan_raw_report=scan_raw_report,
        read_mode=read_mode,
        topic_override=topic,  # type: ignore[arg-type]
        payload_mode_override=payload_mode,  # type: ignore[arg-type]
    )


def get_mqtt_status() -> dict[str, object]:
    """Return status dict ของ primary broker — ใช้ใน API/template (legacy single-status view)"""
    c = get_mqtt_client(None)
    if c is None:
        return {
            "enabled": False,
            "connected": False,
            "broker_url": None,
            "topic": None,
            "last_error": None,
            "paho_available": _paho_available(),
        }
    return c.status_dict()


def _paho_available() -> bool:
    try:
        import paho.mqtt.client  # noqa: F401
        return True
    except ImportError:
        return False


def get_broker_connection_status(broker_id: int) -> dict[str, object]:
    """คืน connection status ของ broker ตาม id — ใช้ใน detail page"""
    with _client_lock:
        c = _clients.get(broker_id)
    is_active = c is not None
    if c is None:
        return {"connected": False, "is_active": False, "broker_url": None, "last_error": None}
    status = c.status_dict()
    return {
        "connected": status.get("connected", False),
        "is_active": is_active,
        "broker_url": status.get("broker_url"),
        "last_error": status.get("last_error"),
    }


# ---------------------------------------------------------------------------
# MQTT Monitor Session — background subscriber for live message testing
# ---------------------------------------------------------------------------

import collections as _collections
import ssl as _ssl
import time as _time
import urllib.parse as _urlparse


class MqttMonitorSession:
    """Dedicated paho client สำหรับ subscribe ทดสอบ — แยกจาก VAS main client"""

    MAX_MESSAGES = 200

    def __init__(self) -> None:
        self._client = None
        self._lock = threading.Lock()
        self._messages: _collections.deque = _collections.deque(maxlen=self.MAX_MESSAGES)
        self._counter: int = 0
        self._running: bool = False
        self._broker_id: int | None = None
        self._broker_name: str = ""
        self._topic: str = ""
        self._error: str | None = None

    # ── Public API ────────────────────────────────────────────────

    def start(self, broker_id: int, topic: str) -> dict[str, object]:
        """Connect + subscribe. คืน {"ok": bool, "error": str|None}"""
        self.stop()

        from core.database import get_mqtt_broker
        broker = get_mqtt_broker(broker_id)
        if not broker:
            return {"ok": False, "error": "Broker not found"}

        if not _paho_available():
            return {"ok": False, "error": "paho-mqtt ยังไม่ได้ติดตั้ง"}

        import paho.mqtt.client as _mqtt  # type: ignore

        cfg = broker_db_to_config(broker)
        parsed = _urlparse.urlparse(cfg.broker_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (8883 if parsed.scheme in ("mqtts", "ssl") else 1883)
        use_tls = parsed.scheme in ("mqtts", "ssl")

        c = _mqtt.Client(client_id=(cfg.client_id or "vas-mon") + "-monitor")
        if cfg.username:
            c.username_pw_set(cfg.username, cfg.password or "")
        if use_tls:
            c.tls_set(cert_reqs=_ssl.CERT_NONE if cfg.tls_insecure else _ssl.CERT_REQUIRED)
            if cfg.tls_insecure:
                c.tls_insecure_set(True)

        session_topic = topic or "#"

        def _on_connect(cl, ud, flags, rc):
            if rc == 0:
                cl.subscribe(session_topic, qos=cfg.qos)
                with self._lock:
                    self._error = None
            else:
                with self._lock:
                    self._error = f"เชื่อมต่อไม่ได้ (rc={rc})"

        def _on_message(cl, ud, msg):
            with self._lock:
                self._counter += 1
                try:
                    payload = msg.payload.decode("utf-8", errors="replace")
                except Exception:
                    payload = repr(msg.payload)
                self._messages.append({
                    "id":      self._counter,
                    "ts":      _time.strftime("%H:%M:%S"),
                    "topic":   msg.topic,
                    "payload": payload,
                    "qos":     msg.qos,
                    "retain":  bool(msg.retain),
                })

        def _on_disconnect(cl, ud, rc):
            with self._lock:
                if rc != 0:
                    self._error = f"ถูกตัดการเชื่อมต่อ (rc={rc})"
                self._running = False

        c.on_connect    = _on_connect
        c.on_message    = _on_message
        c.on_disconnect = _on_disconnect

        try:
            c.connect_async(host, port, keepalive=30)
            c.loop_start()
            with self._lock:
                self._client      = c
                self._running     = True
                self._broker_id   = broker_id
                self._broker_name = broker.get("name", "")
                self._topic       = session_topic
                self._error       = None
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def stop(self) -> None:
        with self._lock:
            c = self._client
            self._client  = None
            self._running = False
        if c:
            try:
                c.loop_stop()
            except Exception:
                pass

    def status(self) -> dict[str, object]:
        with self._lock:
            connected = bool(self._client and getattr(self._client, "is_connected", lambda: False)())
            return {
                "running":      self._running,
                "connected":    connected,
                "broker_id":    self._broker_id,
                "broker_name":  self._broker_name,
                "topic":        self._topic,
                "error":        self._error,
                "msg_count":    self._counter,
            }

    def get_messages(self, since_id: int = 0) -> list[dict[str, object]]:
        with self._lock:
            msgs = list(self._messages)
        return [m for m in msgs if m["id"] > since_id]

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()
            self._counter = 0


_monitor_session = MqttMonitorSession()


def get_monitor_session() -> MqttMonitorSession:
    return _monitor_session
