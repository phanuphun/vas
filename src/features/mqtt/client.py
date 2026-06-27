"""
MQTT client สำหรับ VAS — publish QR scan events ออกไปยัง broker.

Dependencies:
    paho-mqtt >= 1.6  (sudo apt install -y python3-paho-mqtt)

Config file:
    {project_root}/config.json  ส่วน "mqtt": { ... }
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

PAYLOAD_MODES = ("decoded", "raw")
"""
payload_mode:
    "decoded"  → publish ข้อมูลหลัง decode แล้ว  {"scan":"3833401723","device":"...","ts":"..."}
    "raw"      → publish raw keycodes ก่อน decode  {"scan":[39,30,30,...],"device":"...","ts":"..."}
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
    payload_mode: str = "decoded"   # "decoded" | "raw"

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


def load_mqtt_config() -> MqttConfig:
    """โหลด config จาก config.json → ส่วน "mqtt" """
    from core.config import main_config_path
    path = main_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return MqttConfig()
    if not isinstance(raw, dict):
        return MqttConfig()
    mqtt_section = raw.get("mqtt")
    if not isinstance(mqtt_section, dict):
        return MqttConfig()
    return MqttConfig.from_dict(mqtt_section)


def save_mqtt_config(config: MqttConfig) -> None:
    """บันทึก config ลง config.json (merge กับ section อื่นที่มีอยู่)"""
    from core.config import main_config_path
    path = main_config_path()
    # โหลด existing content ก่อน (อาจมี key อื่น)
    try:
        raw: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raw = {}
    except (OSError, json.JSONDecodeError):
        raw = {}
    raw["mqtt"] = config.to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
        scan_raw: "list[int] | None" = None,
    ) -> bool:
        """
        Publish QR scan ไปยัง topic ที่ config ไว้

        payload_mode == "decoded"  → {"scan": "<decoded_text>", "device":"...", "ts":"..."}
        payload_mode == "raw"      → {"scan": [39,30,30,...],   "device":"...", "ts":"..."}
                                     scan_raw คือ list ของ HID keycodes / evdev scancodes
                                     ถ้า scan_raw เป็น None จะ fallback เป็น decoded mode
        """
        if not self.config.enabled:
            return False

        if self.config.payload_mode == "raw" and scan_raw is not None:
            scan_value: object = scan_raw
        else:
            scan_value = scan

        payload = json.dumps({"scan": scan_value, "device": device, "ts": ts}, ensure_ascii=False)
        ok = self.publish(self.config.topic, payload)
        try:
            from core.database import log_mqtt_event as _db_mqtt
            _db_mqtt(scan=scan, topic=self.config.topic, payload=payload, ok=ok, ts=ts)
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
# Module-level singleton
# ---------------------------------------------------------------------------

_client: VasMqttClient | None = None
_client_lock = threading.Lock()


def get_mqtt_client() -> VasMqttClient | None:
    with _client_lock:
        return _client


def start_mqtt(config: MqttConfig | None = None) -> VasMqttClient:
    """
    เริ่ม MQTT client global singleton.
    ถ้า config=None จะโหลดจาก config.json
    Raises:
        ImportError: ถ้า paho-mqtt ไม่ได้ติดตั้ง
    """
    global _client
    cfg = config or load_mqtt_config()
    with _client_lock:
        if _client is not None:
            _client.disconnect()
        c = VasMqttClient(cfg)
        c.connect()
        _client = c
    return c


def stop_mqtt() -> None:
    global _client
    with _client_lock:
        if _client is not None:
            _client.disconnect()
            _client = None


def publish_qr_scan(
    scan: str,
    device: str,
    ts: str,
    scan_raw: "list[int] | None" = None,
) -> bool:
    """Convenience wrapper — ส่งออก MQTT ถ้า client เชื่อมต่ออยู่"""
    with _client_lock:
        c = _client
    if c is None:
        return False
    return c.publish_qr_scan(scan, device, ts, scan_raw=scan_raw)


def get_mqtt_status() -> dict[str, object]:
    """Return status dict ที่ใช้ใน API/template"""
    with _client_lock:
        c = _client
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
                c.disconnect()
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
