# MQTT Client — เอกสารระบบ

ไฟล์หลัก: `src/features/mqtt/client.py`

## ภาพรวม

MQTT client ของ VAS publish QR scan events ออกไปยัง MQTT broker แบบ real-time ทุกครั้งที่ QR reader อ่านได้ค่าใหม่ **รองรับ broker หลายตัว connect พร้อมกันจริง** — แต่ละ broker enable/disable อิสระต่อกัน broker หนึ่งตัว connect fail จะไม่กระทบ broker ตัวอื่น

**Dependencies:** `paho-mqtt >= 1.6` (`python3-paho-mqtt`)

**Config storage:** ตาราง `mqtt_brokers` ใน SQLite (`~/.config/vas/vas.db`) **เท่านั้น** — เดิมเก็บใน `config.json` ที่โฟลเดอร์ install แต่ไฟล์นั้นถูกลบไปแล้ว (ข้อมูลถูก migrate เข้า `mqtt_brokers` อัตโนมัติตอน migration version 2 แล้วจึงลบไฟล์ทิ้ง — ดู `docs/database.md`) เหตุผลที่ย้าย: `config.json` เดิมอยู่ในโฟลเดอร์ที่ `vas update` ลบทิ้งทุกครั้ง (`shutil.rmtree`) ทำให้การตั้งค่า MQTT หายทุกรอบอัปเดต ส่วน `vas.db` อยู่นอกโฟลเดอร์นั้นจึงปลอดภัย

---

## Configuration

### `MqttConfig` (dataclass)

Object ชั่วคราวสำหรับส่งค่าระหว่าง DB row กับ `VasMqttClient` เท่านั้น — **ไม่ผูกกับไฟล์ใดๆ อีกต่อไป**

| Field | Type | Default | คำอธิบาย |
|-------|------|---------|----------|
| `enabled` | `bool` | `False` | เปิด/ปิด MQTT publish |
| `broker_url` | `str` | `mqtts://mqtt-apps.hapysterile.xenex.io:8883` | URL ของ broker |
| `username` | `str` | `""` | Username สำหรับ auth |
| `password` | `str` | `""` | Password สำหรับ auth |
| `client_id` | `str` | `""` | Client ID (ว่าง = auto-generate) |
| `tls_insecure` | `bool` | `False` | Skip TLS verify (สำหรับ self-signed cert) |
| `topic` | `str` | `sterile/vending/qr/scan` | Topic default ของ broker (resolve จาก `mqtt_broker_topics` ตัวแรกที่ enabled) |
| `qos` | `int` | `1` | Quality of Service (0/1/2) |
| `retain` | `bool` | `False` | Retain flag |
| `payload_mode` | `str` | `"decoded"` | `"decoded"` \| `"raw_keycode"` \| `"raw_report"` |

### `broker_db_to_config(broker: dict) → MqttConfig`
แปลง row จาก `mqtt_brokers` (dict จาก `core.database.get_mqtt_broker()`) เป็น `MqttConfig` — resolve `topic` จาก `mqtt_broker_topics` ตัวแรกที่ `enabled=1` ของ broker นั้น (`mqtt_brokers` เองไม่มี column `topic` โดยตรง เพราะ broker หนึ่งตัวมีได้หลาย topic)

### Payload Modes

**Payload keys (ทุก mode):**

| Key | คำอธิบาย |
|-----|----------|
| `data` | ข้อมูลตาม `mode` ที่เลือก (string สำหรับ `decoded`, JSON array ของ int/hex string สำหรับ `raw_*`) — เดิมชื่อ `"scan"` |
| `device` | path ของ device เช่น `/dev/hidraw0`, `/dev/input/event7` |
| `mode` | payload mode ที่ใช้จริงตอน publish นี้ (`"decoded"` \| `"raw_keycode"` \| `"raw_report"`) — field ใหม่ |
| `read_mode` | วิธีที่ device อ่านค่า (`"hidraw"` \| `"evdev"` \| `null`) — ใช้ตีความ numbering space ของ `raw_keycode` |
| `timestamp` | เวลาที่ publish (ISO 8601 UTC) — เดิมชื่อ `"ts"` |

**`"decoded"` (default):**
```json
{"data": "3833401723", "device": "/dev/hidraw0", "mode": "decoded", "read_mode": "hidraw", "timestamp": "2026-07-02T10:30:00+00:00"}
```

**`"raw_keycode"`:**
```json
{"data": [39, 30, 30, 32, 30, 39, 31, 33], "device": "/dev/hidraw0", "mode": "raw_keycode", "read_mode": "hidraw", "timestamp": "2026-07-02T10:30:00+00:00"}
```
ค่าใน `"data"` เป็น JSON array ของ HID keycode (ถ้า `read_mode="hidraw"`) หรือ evdev scancode (ถ้า `read_mode="evdev"`) — คนละ numbering space กัน ต้องดู `read_mode` เพื่อตีความให้ถูก

**`"raw_report"`:**
```json
{"data": ["a1000000000000", "00000000000000"], "device": "/dev/hidraw0", "mode": "raw_report", "read_mode": "hidraw", "timestamp": "2026-07-02T10:30:00+00:00"}
```
ค่าใน `"data"` เป็น JSON array ของ hex string — 64-byte HID report ดิบทั้งก้อนต่อ frame (`report.hex()`) รวม key-up/all-zero frame ด้วย **มีเฉพาะ `read_mode="hidraw"` เท่านั้น** — evdev ไม่มี raw byte report ให้ดัก (kernel แปลงเป็น key event ให้ตั้งแต่ driver แล้ว)

**ทุก payload mode แนบ field `"mode"`, `"read_mode"`, `"timestamp"` เข้าไปเสมอ** เพื่อให้ third-party consumer รู้ว่ากำลังอ่านข้อมูลรูปแบบไหนและ numbering space ไหน

**การสแกนซ้ำ (ค่าเดิมซ้ำกับครั้งก่อน) ก็ publish ทุกครั้งเช่นกัน** — การตรวจจับ "scan ใหม่" ฝั่ง server ใช้ตัวนับ (`reader.last_scan_seq`) ไม่ใช่การเทียบค่า string ดังนั้นสแกน QR code เดิมซ้ำๆ ติดกันจะไม่ถูกข้าม (ต่างจากพฤติกรรมเดิมที่ dedupe ด้วยค่า)

**ไม่มี silent fallback:** ถ้า broker ตั้ง `payload_mode="raw_report"` แต่เครื่องอ่าน QR เป็น evdev (ไม่มี raw report ให้) ระบบ**จะไม่ publish** (`return False`) แทนที่จะ publish เป็น `decoded` แทนแบบเงียบๆ พร้อมบันทึก `mqtt_events` row ที่ `ok=0` และ payload อธิบายเหตุผล (`{"error": "raw_report not available for read_mode=evdev"}`)

---

## Multi-Broker Support

### `_clients: dict[int, VasMqttClient]`
Module-level registry แทนที่ singleton ตัวเดียวแบบเดิม — key คือ `broker_id`

### `start_mqtt_broker(broker_id: int) → VasMqttClient`
โหลด broker จาก DB, สร้าง/แทนที่ client ใน `_clients[broker_id]`, เรียก `.connect()` — ถ้ามี client เดิมของ broker นี้อยู่แล้วจะ disconnect ก่อน

### `stop_mqtt_broker(broker_id: int) → None`
Disconnect + ลบ broker นั้นออกจาก `_clients` — ไม่กระทบ broker ตัวอื่น

### `start_all_enabled_brokers() → None`
วน broker ทุกตัวที่ `enabled=1` แล้วเรียก `start_mqtt_broker()` ทีละตัว **แยก try/except ต่อ broker** — broker ตัวหนึ่ง connect fail ไม่ทำให้ตัวอื่นไม่ทำงาน เรียกตอน server boot อัตโนมัติแทน `start_mqtt()` เดิม

### `get_primary_broker_id() → int | None`
คืน `id` ของ broker ที่ `is_primary=1` — ใช้กับ path แบบ primary-only (ดูด้านล่าง)

### `get_mqtt_client(broker_id: int | None = None) → VasMqttClient | None`
คืน client ของ broker ที่ระบุ ถ้าไม่ระบุจะ resolve เป็น primary broker อัตโนมัติ

### Legacy (backward compat)
`start_mqtt()` / `stop_mqtt()` ยังอยู่ — `stop_mqtt()` ตอนนี้ disconnect + ล้าง client **ทุกตัว** ใน `_clients` (ไม่ใช่แค่ตัวเดียวเหมือนเดิม)

---

## Publish — สอง Code Path แยกกัน

### `publish_qr_scan(scan, device, ts, scan_raw_keycode=None, scan_raw_report=None, read_mode=None) → bool`
**Primary-broker-only** — publish ไปยัง broker ที่ `is_primary=1` เท่านั้น ไม่สนใจการตั้งค่าต่อ device ใดๆ
ใช้กับ: CLI `vas mqtt test`, `/api/mqtt/test` (legacy single-broker API) — **ไม่ใช่ path ที่ SSE stream ใช้จริง**

### `publish_qr_scan_for_device(device_id, scan, device, ts, scan_raw_keycode=None, scan_raw_report=None, read_mode=None) → dict`
**Device-aware** — เลือก broker/topic/payload_mode ตามตาราง `device_integrations` ของ `device_id` นั้นๆ (ดู `docs/database.md`)

**คืนค่าเป็น status dict เสมอ** (ไม่ใช่ `bool` เหมือนเดิม): `{"enabled": bool, "connected": bool, "published": bool, "error": str | None}` — เปลี่ยนจาก `bool` เป็น dict เพื่อให้ SSE stream ส่งสถานะจริงกลับไปให้ frontend แสดงสีของ integration chip (เทา/เหลือง/เขียว/แดง) ได้ตรงกับความเป็นจริง

Logic:
1. ดึง `device_integrations` ของ `device_id`, ดู entry ประเภท `"mqtt"`
2. ถ้าไม่มีหรือ `enabled=0` → `{"enabled": False, "connected": False, "published": False, "error": None}` (ไม่ error — แค่ยังไม่เปิดใช้งาน)
3. ถ้าไม่มี `broker_id` ผูกไว้ → `{"enabled": True, "connected": False, "published": False, "error": "..."}`
4. ถ้า broker นั้นยังไม่มี client connect อยู่ → `{"enabled": True, "connected": False, "published": False, "error": "..."}`
5. Publish ผ่าน `client.publish_qr_scan(..., topic_override=<topic ที่ตั้งไว้ที่ device หรือ None>, payload_mode_override=<payload_mode ที่ตั้งไว้ที่ device หรือ None>)` แล้วคืน `{"enabled": True, "connected": client.is_connected, "published": ok, "error": None|client.last_error}`

**นี่คือ path ที่ SSE stream (`/api/qr/stream` ใน `server.py`) เรียกใช้จริง** — ทุกครั้งที่มี scan ใหม่จะเรียก `publish_qr_scan_for_device("zkteco-qr500", ...)` แล้วแนบผลลัพธ์เข้าไปใน SSE `event: scan` payload ที่ key `"mqtt"` (ดู `docs/qr/qr-reader.md`)

> `topic_override` ใน `VasMqttClient.publish_qr_scan()`: ถ้าระบุจะใช้แทน `self.config.topic` (topic default ของ broker) — device แต่ละตัวตั้ง topic ของตัวเองแยกจาก topic default ของ broker ได้

> `payload_mode_override` ใน `VasMqttClient.publish_qr_scan()`: ถ้าระบุและอยู่ใน `PAYLOAD_MODES` จะใช้แทน `self.config.payload_mode` (payload mode default ของ broker) — เหตุผลที่เพิ่ม field นี้: ข้อมูลระดับ raw (`raw_keycode`/`raw_report`) มีต้นทางจริงจากฝั่ง **QR reader ต่อ device** ไม่ใช่จากฝั่ง broker การผูก payload mode ไว้ที่ broker เพียงอย่างเดียวทำให้ถ้ามี device หลายตัวใช้ broker เดียวกันแต่ต้องการ mode ต่างกัน (เช่น device หนึ่งเป็น hidraw อยากได้ `raw_report`, อีกตัวเป็น evdev ต้องใช้ `decoded`) จะทำไม่ได้ ตอนนี้ตั้งค่าได้ที่หน้า device (`/qr/devices/zkteco-qr500` → การ์ด MQTT Publish → dropdown "Payload Mode") ถ้าเลือก "ใช้ค่า default ของ Broker" (ค่าว่าง/`None`) จะ fallback ไปใช้ `broker.payload_mode` ตามเดิม

> ⚠️ `vas mqtt test`/`/api/mqtt/test` (primary-broker path) กับ SSE loop (device-aware path) เป็นคนละ code path กัน — ถ้า debug ปัญหา publish ไม่ออกต้องแยกให้ถูกว่ากำลังดู path ไหน primary-broker path **ไม่รองรับ** payload_mode override ต่อ device (ใช้ payload_mode ของ broker เสมอ)

---

## Device Integration Config (`device_integrations` table)

ตั้งค่าผ่านหน้า `/qr/devices/zkteco-qr500` (การ์ด "MQTT Publish") — บันทึกลง SQLite (`device_integrations`: `device_id`, `integration_type='mqtt'`, `enabled`, `broker_id`, `topic`, `qos`) ไม่ใช่ไฟล์ JSON อีกต่อไป (เดิมคือ `qr_integrations.json` ซึ่งถูก migrate เข้า DB แล้วลบทิ้ง)

รองรับ 3 ประเภท integration: `webhook`, `mqtt`, `pipe` — **ปัจจุบันมี backend logic จริงเฉพาะ `mqtt`** ส่วน `webhook`/`pipe` เก็บ config ได้แต่ยังไม่มีการ publish จริง (เตรียม schema ไว้สำหรับอนาคต)

**Payload ที่ publish ออกไปสำหรับ device นี้ ตั้งได้ที่หน้า device โดยตรง** ผ่าน dropdown "Payload Mode" ในการ์ด MQTT Publish (`decoded` / `raw_keycode` / `raw_report` / "ใช้ค่า default ของ Broker") — เก็บเป็น key `payload_mode` ใน `device_integrations.settings_json` (ไม่ต้อง migration schema เพิ่ม เพราะ `settings_json` เป็น JSON column ที่ flexible อยู่แล้ว, flatten กลับเป็น top-level field ตอนอ่านผ่าน `list_device_integrations()`) ถ้าไม่เลือก (ค่าว่าง/`None`) จะ fallback ไปใช้ `payload_mode` ของ broker ที่เลือกไว้ตามเดิม

---

## MQTT Broker Form (`/mqtt/broker/add`, `/mqtt/broker/<id>/edit`)

ฟอร์มสร้าง/แก้ broker มี field `payload_mode` เป็น dropdown เลือกได้จริง (`decoded` / `raw_keycode` / `raw_report`) — pre-select ค่าปัจจุบันถูกต้องตอนแก้ broker เดิม (ก่อนหน้านี้ JS hardcode ส่งค่า `"json"` เสมอ ซึ่งเป็นบั๊ก — แก้แล้วในรอบนี้)

---

## `VasMqttClient`

Wrapper รอบ `paho.mqtt.client.Client` พร้อม thread-safe state — หนึ่ง instance ต่อหนึ่ง broker (เก็บใน `_clients` registry ด้านบน)

### `connect() / disconnect()`
เชื่อมต่อ/ตัดการเชื่อมต่อแบบ non-blocking (background thread ของ paho, auto-reconnect ผ่าน `reconnect_delay_set`)

### `publish(topic, payload) → bool`
Publish message ดิบ — คืน `False` ถ้าไม่ connected

### `publish_qr_scan(scan, device, ts, scan_raw_keycode=None, scan_raw_report=None, read_mode=None, topic_override=None, payload_mode_override=None) → bool`
สร้าง payload ตาม `payload_mode_override` ถ้าระบุและถูกต้อง (ไม่งั้น fallback ไป `self.config.payload_mode`) แล้ว publish ไปที่ `topic_override` ถ้าระบุ ไม่งั้นใช้ `self.config.topic` — ดู "Payload Modes" ด้านบนสำหรับ logic แบบเต็ม (รวม no-silent-fallback)

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

`_parse_broker_url(url)` แปลง URL เป็น connection params — ไม่เปลี่ยนจากเดิม:

| Scheme | Transport | TLS | Default Port |
|--------|-----------|-----|-------------|
| `mqtt://` | TCP | ❌ | 1883 |
| `mqtts://` | TCP | ✅ | 8883 |
| `ws://` | WebSocket | ❌ | 8083 |
| `wss://` | WebSocket | ✅ | 8084 |

---

## Client ID Auto-generation

ถ้า `client_id` ว่าง จะ generate อัตโนมัติ: `vas-qr-reader-<6 random alphanumeric chars>`

---

## MQTT Monitor Session (`MqttMonitorSession`)

Client แยกต่างหากสำหรับ subscribe ทดสอบ (ดูข้อความสด) — ไม่ใช้ `_clients` registry หลัก เชื่อมต่อผ่าน `broker_db_to_config()` เหมือนกัน

---

## Config File Management

~~`load_mqtt_config()` / `save_mqtt_config()`~~ — **ถูกลบออกแล้ว** พร้อม `main_config_path()` ใน `core/config.py` การตั้งค่า MQTT อ่าน/เขียนผ่าน `core.database` (`get_mqtt_broker`, `create_mqtt_broker`, `update_mqtt_broker`, `get_primary_broker_id`) โดยตรงแทน `config.json` ไม่ถูกใช้งานแล้วสำหรับ MQTT

---

## Integration กับส่วนอื่น

### QR Reader SSE Stream (`/api/qr/stream`)
เมื่อ scan ใหม่ถูกตรวจพบ ระบบดึง `scan_raw_keycode`/`scan_raw_report`/`read_mode` จาก reader แล้วเรียก:
```python
from features.mqtt.client import publish_qr_scan_for_device
publish_qr_scan_for_device(
    "zkteco-qr500", scan, reader.device_path, ts,
    scan_raw_keycode=scan_raw_keycode, scan_raw_report=scan_raw_report, read_mode=read_mode,
)
```

### Server Boot
```python
start_all_enabled_brokers()   # เดิมคือ start_mqtt(load_mqtt_config())
```

### Server Shutdown (atexit)
```python
atexit.register(stop_mqtt)   # disconnect ทุก broker ใน _clients
```

### CLI `vas mqtt config`
หลังบันทึก config (เขียนลง `mqtt_brokers`/`mqtt_broker_topics`) จะ POST ไปยัง `http://localhost:8888/api/mqtt/config` เพื่อ reload primary broker ทันที (ถ้า server กำลัง run)

---

## CLI Commands

| Command | คำอธิบาย |
|---------|----------|
| `vas mqtt status` | แสดง config และสถานะการเชื่อมต่อของ primary broker |
| `vas mqtt config --broker-url ...` | ตั้งค่า broker URL ของ primary broker |
| `vas mqtt config --username ... --password ...` | ตั้งค่า credentials |
| `vas mqtt config --topic ...` | ตั้งค่า topic (sync เข้า `mqtt_broker_topics`) |
| `vas mqtt config --qos 1` | ตั้งค่า QoS |
| `vas mqtt config --payload-mode {decoded,raw_keycode,raw_report}` | ตั้งค่า payload mode |
| `vas mqtt config --enable` / `--disable` | เปิด/ปิดใช้งาน |
| `vas mqtt config --tls-insecure` | Skip TLS verify |
| `vas mqtt config --retain` | Enable retain |
| `vas mqtt test` | Test publish ไปยัง primary broker |

---

## Web API Endpoints

| Method | Path | คำอธิบาย |
|--------|------|----------|
| `GET` | `/api/mqtt/status` | สถานะ primary broker |
| `POST` | `/api/mqtt/brokers` | สร้าง broker ใหม่ |
| `PUT` | `/api/mqtt/brokers/<id>` | แก้ broker — reload connection ของ broker นั้นเท่านั้น |
| `DELETE` | `/api/mqtt/brokers/<id>` | ลบ broker — disconnect ก่อนลบ |
| `GET` | `/api/mqtt/brokers/<id>/status` | สถานะ connection ของ broker ที่ระบุ |
| `POST` | `/api/mqtt/brokers/<id>/connect` | เชื่อมต่อ broker ที่ระบุ |
| `POST` | `/api/mqtt/brokers/<id>/disconnect` | ตัดการเชื่อมต่อ broker ที่ระบุ (ไม่กระทบตัวอื่น) |
| `POST` | `/api/mqtt/brokers/<id>/test` | Test publish ไปยัง broker ที่ระบุ |
| `GET`/`POST`/`PUT`/`DELETE` | `/api/mqtt/brokers/<id>/topics...` | จัดการ topics ของ broker |
| `POST` | `/api/mqtt/config` | Legacy — อ่าน/เขียน primary broker |
| `POST` | `/api/mqtt/test` | Legacy — test publish ไปยัง primary broker |
| `POST` | `/api/mqtt/disconnect` | Legacy — ตัดการเชื่อมต่อ primary broker |
| `POST`/`GET` | `/api/mqtt/monitor/...` | MQTT monitor session (subscribe ทดสอบ) |

---

## ติดตั้ง paho-mqtt

```bash
sudo apt install -y python3-paho-mqtt
```

หรือ:

```bash
pip install paho-mqtt
```
