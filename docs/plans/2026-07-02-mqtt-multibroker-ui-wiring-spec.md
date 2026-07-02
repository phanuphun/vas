---
tags: [spec, plan]
date: 2026-07-02
project: vas
status: draft
---

# Spec: MQTT Multi-Broker UI Wiring (Round 3)

## Goal
ปิด gap ที่เลื่อนมาจาก round 1: ทำให้ SSE publish loop publish ตาม `device_integrations` จริง (device-aware routing) แทนการ hardcode primary broker, และแก้ `mqtt_broker_form.html` ให้เลือก `payload_mode` ได้จริงแทนค่า hardcode `"json"`

## Data model changes
ไม่มี schema เปลี่ยน — ใช้ตาราง `mqtt_brokers`, `device_integrations` ที่มีอยู่แล้วจาก round 1 ครบทุก column ที่ต้องการ (`device_integrations.broker_id`, `.topic`, `.enabled`; `mqtt_brokers.payload_mode`)

## Process flow

### 1. Device-aware publish (`src/features/mqtt/client.py`)
- เพิ่ม `topic_override: str | None = None` parameter ใน `VasMqttClient.publish_qr_scan()` (ปัจจุบันบรรทัด 326-375) — ใช้ `topic_override` แทน `self.config.topic` เมื่อไม่ใช่ `None`, logic ที่เหลือ (no-silent-fallback, read_mode ฯลฯ จาก round 2) เหมือนเดิมทุกอย่าง
- เพิ่มฟังก์ชันใหม่ `publish_qr_scan_for_device(device_id, scan, device, ts, scan_raw_keycode=None, scan_raw_report=None, read_mode=None) -> bool`:
  1. `from core.database import list_device_integrations, get_mqtt_broker` → ดึง `integrations = list_device_integrations(device_id)`
  2. `mqtt_integ = integrations.get("mqtt")` — ถ้าไม่มีหรือ `not mqtt_integ.get("enabled")` → `return False` (ไม่ error — แปลว่ายังไม่เปิดใช้งาน)
  3. `broker_id = mqtt_integ.get("broker_id")` — ถ้า `None` → `return False`
  4. `c = get_mqtt_client(broker_id)` — ถ้า `None` (ยังไม่ connect) → `return False`
  5. `topic = mqtt_integ.get("topic") or None` (ว่าง = ใช้ default ของ broker เอง)
  6. `return c.publish_qr_scan(scan, device, ts, scan_raw_keycode=scan_raw_keycode, scan_raw_report=scan_raw_report, read_mode=read_mode, topic_override=topic)`
- **ฟังก์ชันเดิม `publish_qr_scan()` (module-level, primary-broker-only) ต้องคงไว้ไม่แตะ** — ยังใช้กับ `vas mqtt test` และ `/api/mqtt/test` เหมือนเดิม

### 2. เปลี่ยน SSE loop มาใช้ device-aware publish (`src/server.py`)
- จุดที่เรียก `_mqtt_publish` (ปัจจุบันบรรทัด ~899-905): เปลี่ยน import จาก `publish_qr_scan` เป็น `publish_qr_scan_for_device`, เรียกด้วย `device_id="zkteco-qr500"` (hardcode ตรงตาม `DEVICE_CATALOG` ที่มี device เดียวตอนนี้) ตามด้วย argument เดิมทั้งหมด

### 3. แก้ payload_mode selector (`src/web/templates/mqtt_broker_form.html`)
- เพิ่ม `<select id="f-payload-mode">` ในฟอร์ม (วางใกล้ QoS select, บรรทัด ~99-107 ปัจจุบัน) ตัวเลือก: `decoded` / `raw_keycode` / `raw_report` พร้อม pre-select จาก `broker.payload_mode` ตอนแก้ broker เดิม (pattern เดียวกับ QoS select ที่มีอยู่แล้ว)
- แก้ JS `readForm()` (บรรทัด 220-238 ปัจจุบัน) เปลี่ยน `payload_mode: "json"` เป็น `payload_mode: document.getElementById("f-payload-mode").value`

### 4. อัปเดตตัวอย่าง payload preview (`src/web/templates/qr_device_zkteco_qr500.html`)
- MQTT card payload preview (บรรทัด ~461 ปัจจุบัน) เปลี่ยนข้อความให้สะท้อนว่า payload mode มาจากการตั้งค่าของ broker ที่เลือก ไม่ใช่ mode คงที่ — ใส่หมายเหตุสั้นๆ ใต้ preview ว่า "รูปแบบ payload ขึ้นกับ payload mode ที่ตั้งไว้ที่ broker" แทนการแก้ preview แบบ dynamic (ไม่ต้อง JS เพิ่ม เพราะ mode ไม่ได้เลือกที่หน้านี้)

## API changes
ไม่มี endpoint ใหม่ — plumbing เปลี่ยนเฉพาะฝั่ง publish logic

## Frontend changes
- `mqtt_broker_form.html` — เพิ่ม payload_mode select + แก้ JS (ตามข้อ 3)
- `qr_device_zkteco_qr500.html` — ปรับข้อความ preview (ตามข้อ 4, เปลี่ยนน้อยมาก)

## Implementation routing
- frontend-builder: required (ทั้งสอง template ข้างต้น เป็นงาน HTML/JS ล้วน)
- backend-builder: required (`features/mqtt/client.py`, `server.py`)
- test-verifier: required
- pr-reviewer: required
- build order: backend first (เพราะ frontend แค่แก้ select/JS ไม่ผูก dependency จริงกับ backend ใหม่ แต่ทำ backend ก่อนตามธรรมเนียมเดิม)

## Tests required
- Unit: `publish_qr_scan_for_device()` เมื่อ integration ปิดอยู่ → False ไม่เรียก publish จริง
- Unit: `publish_qr_scan_for_device()` เมื่อ broker_id ไม่มี client (ยังไม่ connect) → False
- Unit: `VasMqttClient.publish_qr_scan(topic_override=...)` ใช้ topic ที่ override แทน `self.config.topic` จริง
- Integration: mock 2 broker, device integration ผูก broker B topic เฉพาะ → publish ไปที่ broker B เท่านั้น ไม่ไป broker A (primary)
- Manual/UI: สร้าง broker ใหม่เลือก `raw_report` → เช็คใน DB ว่าเก็บ `raw_report` ไม่ใช่ `json`

## Risks and open questions
- `vas mqtt test`/`/api/mqtt/test` (primary-broker path) กับ SSE loop (device-aware path) เป็นคนละ code path กันตั้งแต่รอบนี้ไป — ถ้า debug ปัญหา publish ต้องแยกให้ถูกว่าใช้ path ไหน (มีคอมเมนต์กำกับในโค้ดแล้ว)
- ไม่มี UI แจ้งเตือนถ้า device integration ผูก broker ที่ถูกลบไปแล้ว (`broker_id=NULL` จาก FK) — ยอมรับได้ในรอบนี้ (แค่ไม่ publish ไม่ crash ตาม acceptance criteria)

## Files that will change
- `src/features/mqtt/client.py` — `publish_qr_scan_for_device()` ใหม่, `topic_override` param
- `src/server.py` — SSE loop เปลี่ยนไปเรียก `publish_qr_scan_for_device`
- `src/web/templates/mqtt_broker_form.html` — payload_mode select + JS fix
- `src/web/templates/qr_device_zkteco_qr500.html` — ข้อความ preview
