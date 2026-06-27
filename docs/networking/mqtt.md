# MQTT Client — เอกสารระบบ

ไฟล์หลัก: `src/mqtt_client.py`

## ภาพรวม

MQTT client ของ VAS publish QR scan events ออกไปยัง MQTT broker แบบ real-time ทุกครั้งที่ QR reader อ่านได้ค่าใหม่

**Dependencies:** `paho-mqtt >= 1.6` (`python3-paho-mqtt`)

**Config storage:** `config.json` ที่ project root — ส่วน `"mqtt": {...}`

---

## Configuration

### `MqttConfig` (dataclass)

| Field | Type | Default | คำอธิบาย |
|-------|------|---------|----------|
| `enabled` | `bool` | `False` | เปิด/ปิด MQTT publish |
| `broker_url` | `str` | `mqtts://mqtt-apps.hapysterile.xenex.io:8883` | URL ของ broker |
| `username` | `str` | `""` | Username สำหรับ auth |
| `password` | `str` | `""` | Password สำหรับ auth |
| `client_id` | `str` | `""` | Client ID (ว่าง = auto-generate) |
| `tls_insecure` | `bool` | `False` | Skip TLS verify (สำหรับ self-signed cert) |
| `topic` | `str` | `sterile/vending/qr/scan` | MQTT topic |
| `qos` | `int` | `1` | Quality of Service (0/1/2) |
| `retain` | `bool` | `False` | Retain flag |
| `payload_mode` | `str` | `"decoded"` | `"decoded"` หรือ `"raw"` |

### Payload Modes

**`"decoded"` (default):**
```json
{"scan": "3833401723", "device": "/dev/hidraw0", "ts": "2026-06-27T10:30:00+00:00"}
```

**`"raw"`:**
```json
{"scan": [39, 30, 30, 32, 30, 39, 31, 33], "device": "/dev/hidraw0", "ts": "2026-06-27T10:30:00+00:00"}
```
ค่าใน `"scan"` เป็น list ของ HID keycodes หรือ evdev scancodes ดิบ

---

## Config File Management

### `load_mqtt_config() → MqttConfig`
อ่าน `config.json` และดึงส่วน `"mqtt"` คืน `MqttConfig()` defaults ถ้าไม่มีหรือ parse ไม่ได้

### `save_mqtt_config(config: MqttConfig) → None`
Merge ส่วน `"mqtt"` เข้ากับ `config.json` ที่มีอยู่ (ไม่ทับ key อื่น) เขียน JSON indent=2

---

## `VasMqttClient`

Wrapper รอบ `paho.mqtt.client.Client` พร้อม thread-safe state

### Constructor
```python
VasMqttClient(config: MqttConfig)
```

### Properties
- `is_connected: bool` — สถานะการเชื่อมต่อ (thread-safe)
- `last_error: str | None` — error ล่าสุด

### `connect() → None`
เริ่ม connect ใน background thread (non-blocking):

1. **ถ้า connected อยู่แล้ว** → disconnect ก่อน
2. Parse `broker_url` ด้วย `_parse_broker_url()` → `(host, port, use_tls, use_websocket)`
3. สร้าง paho client (`MQTTv311`, `clean_session=True`)
4. ตั้ง auth (`username_pw_set`) ถ้ามี credentials
5. ตั้ง WebSocket path `/mqtt` ถ้า scheme เป็น `ws`/`wss`
6. ตั้ง TLS ถ้า scheme เป็น `mqtts`/`wss`:
   - `tls_insecure=True` → สร้าง SSL context ที่ข้าม verify
   - `tls_insecure=False` → `tls_set(PROTOCOL_TLS_CLIENT)`
7. ตั้ง callbacks: `on_connect`, `on_disconnect`, `on_log`
8. ตั้ง `reconnect_delay_set(min_delay=3, max_delay=30)` — auto-reconnect
9. `connect_async()` + `loop_start()` — non-blocking network loop

**Raises:** `ImportError` ถ้า paho-mqtt ไม่ได้ติดตั้ง

### `disconnect() → None`
`disconnect()` + `loop_stop()` บน paho client

### `publish(topic, payload) → bool`
Publish message ไปยัง topic ที่กำหนด:
- คืน `True` ถ้า `result.rc == 0`
- คืน `False` ถ้าไม่ connected หรือ error

### `publish_qr_scan(scan, device, ts, scan_raw=None) → bool`
Publish QR scan event:
- ถ้า `payload_mode == "raw"` และมี `scan_raw` → ใช้ raw keycodes
- ไม่ทำอะไรถ้า `config.enabled == False`

### `status_dict() → dict`
```python
{
    "enabled": bool,
    "connected": bool,
    "broker_url": str,
    "topic": str,
    "last_error": str | None,
    "paho_available": bool,
}
```

---

## URL Scheme Mapping

`_parse_broker_url(url)` แปลง URL เป็น connection params:

| Scheme | Transport | TLS | Default Port |
|--------|-----------|-----|-------------|
| `mqtt://` | TCP | ❌ | 1883 |
| `mqtts://` | TCP | ✅ | 8883 |
| `ws://` | WebSocket | ❌ | 8083 |
| `wss://` | WebSocket | ✅ | 8084 |

---

## Module-level Singleton

### `start_mqtt(config=None) → VasMqttClient`
เริ่ม global singleton — disconnect ตัวเก่าถ้ามี

### `stop_mqtt() → None`
Disconnect และล้าง global singleton

### `get_mqtt_client() → VasMqttClient | None`
คืน singleton ปัจจุบัน (thread-safe)

### `publish_qr_scan(scan, device, ts, scan_raw=None) → bool`
Convenience wrapper — publish ถ้า client เชื่อมต่ออยู่

### `get_mqtt_status() → dict`
คืน status dict สำหรับ API/template

---

## Client ID Auto-generation

ถ้า `client_id` ว่าง จะ generate อัตโนมัติ:
```python
vas-qr-reader-<6 random alphanumeric chars>
# เช่น: vas-qr-reader-k3m9xp
```

---

## Integration กับส่วนอื่น

### QR Reader SSE Stream
เมื่อ scan ใหม่ถูกตรวจพบใน `/api/qr/stream`:
```python
from mqtt_client import publish_qr_scan as _mqtt_publish
_mqtt_publish(scan, reader.device_path, ts, scan_raw=scan_raw)
```

### Server Boot
```python
cfg = load_mqtt_config()
if cfg.enabled:
    start_mqtt(cfg)
```

### Server Shutdown (atexit)
```python
atexit.register(stop_mqtt)
```

### CLI `vas mqtt config`
หลังบันทึก config จะ POST ไปยัง `http://localhost:8888/api/mqtt/config` เพื่อ reload MQTT ทันที (ถ้า server กำลัง run)

---

## CLI Commands

| Command | คำอธิบาย |
|---------|----------|
| `vas mqtt status` | แสดง config และสถานะการเชื่อมต่อ |
| `vas mqtt config --broker-url ...` | ตั้งค่า broker URL |
| `vas mqtt config --username ... --password ...` | ตั้งค่า credentials |
| `vas mqtt config --topic ...` | ตั้งค่า topic |
| `vas mqtt config --qos 1` | ตั้งค่า QoS |
| `vas mqtt config --enable` | เปิดใช้งาน |
| `vas mqtt config --disable` | ปิดใช้งาน |
| `vas mqtt config --tls-insecure` | Skip TLS verify |
| `vas mqtt config --retain` | Enable retain |
| `vas mqtt test` | Test publish ไปยัง broker |

---

## Web API Endpoints

| Method | Path | คำอธิบาย |
|--------|------|----------|
| `GET` | `/api/mqtt/status` | สถานะ MQTT client |
| `POST` | `/api/mqtt/config` | บันทึก config และ restart client |
| `POST` | `/api/mqtt/test` | Publish test message `{"scan":"TEST-VAS-QR",...}` |
| `POST` | `/api/mqtt/disconnect` | ตัดการเชื่อมต่อ |

---

## ติดตั้ง paho-mqtt

```bash
sudo apt install -y python3-paho-mqtt
```

หรือ:

```bash
pip install paho-mqtt
```
