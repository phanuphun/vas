# TODO — QR Raw Data (3 โหมด) + MQTT Multi-Broker + Database Migration

> Draft จาก session วิเคราะห์/grilling วันที่ 2026-07-02 (branch `refactor`, commit `805cffa`)
> สถานะ: **แผนงาน ยังไม่ implement** — ทุกข้อผ่านการตัดสินใจ (grilled) แล้ว พร้อมเริ่มเขียนโค้ดได้ทันที
> เครื่อง production ที่มีอยู่ตอนนี้ (1 เครื่อง, branch `main`) จะลงใหม่ทับ — ไม่ต้องกังวลเรื่อง backward-compat ของข้อมูลเก่าในรอบนี้

---

## บริบท (Context)

ต้องการให้ vas อ่าน/เก็บ/ส่งข้อมูล QR scan ได้ 3 ระดับความดิบ ไม่ใช่แค่ decoded text อย่างเดียว เพื่อให้ third-party ที่ subscribe MQTT เอาไปตรวจสอบ/decode เองได้ พร้อมกับแก้ปัญหาที่เจอระหว่างวิเคราะห์:

- `config.json` (เก็บ MQTT settings) อยู่ใน `/opt/vending-auto-setup` ซึ่งโดน `rm -rf` ทุกครั้งที่ `vas update` → ตั้งค่า MQTT หายทุกรอบ อัปเดต
- ระบบ multi-broker (ตาราง `mqtt_brokers`) มีฟังก์ชันหาย (`broker_db_to_config`, `start_mqtt_broker`, `get_primary_broker_id`) — ใช้งานไม่ได้จริง
- หน้า UI `/qr/devices/zkteco-qr500` (การ์ด MQTT Publish) เซฟลง `qr_integrations.json` แต่ไม่มีผลต่อการ publish จริง — เป็น UI ตกแต่ง
- `qr_scans` table ไม่มีคอลัมน์เก็บ raw data เลย มีแค่ decoded `value`
- ไม่มีระบบ migration schema — เพิ่ม column ใหม่จะไม่มีผลกับ DB ที่มีอยู่แล้ว (`CREATE TABLE IF NOT EXISTS` เท่านั้น)
- เครื่องอ่าน QR ตอนนี้ต้องเปิด `HID Keyboard = Open` (evdev mode) ถึงจะอ่านได้ แต่ raw byte report แบบดิบทั้งก้อนทำได้เฉพาะโหมด hidraw (`HID Keyboard = Close`) เท่านั้น

---

## Decision Log (สรุปคำตอบจากรอบ grilling)

| # | คำถาม | คำตอบ | ผลกระทบ |
|---|---|---|---|
| 1 | Device mode strategy สำหรับ raw_report | **Hybrid** — รองรับทั้ง hidraw และ evdev ต่อเครื่อง | `raw_report` มีค่าเฉพาะเครื่องที่เป็น hidraw, เป็น `null` บนเครื่อง evdev — ต้องมี capability flag บอกทุก scan |
| 2 | MQTT payload composition | **เลือกโหมดเดียวต่อ message** (ของเดิม) | แค่เพิ่ม `raw_report` เป็น enum ตัวที่ 3 ใน `payload_mode`, ไม่ต้องยิง 3 field พร้อมกัน |
| 3 | ชื่อ 3 โหมดข้อมูล | **`decoded` / `raw_keycode` / `raw_report`** | ใช้ชื่อชุดนี้ทั้ง enum, DB column, docs |
| 4 | หน้า device UI (MQTT card) | **ซ่อมให้ต่อจริงรอบนี้** | ต้องพึ่ง multi-broker ที่สมบูรณ์ก่อน |
| 5 | Multi-broker vs legacy single-config | **ซ่อม multi-broker ให้สมบูรณ์**, ใช้เป็นระบบเดียว | เขียน `broker_db_to_config`, `start_mqtt_broker`, `get_primary_broker_id` |
| 6 | Config storage (legacy `config.json` vs `mqtt_brokers`) | **เก็บที่ SQLite (`mqtt_brokers`) อย่างเดียว** | Migrate ข้อมูลเดิมจาก `config.json` เข้าเป็น row แรก (`is_primary=1`) แล้วเลิกใช้ `config.json`/`MqttConfig`/`main_config_path` ทิ้งทั้งหมด |
| 7 | Rollout / production state | เครื่อง production มี 1 เครื่อง แต่จะลงใหม่ | ไม่ต้องเขียน migration แบบระวังสุดขีดตอนนี้ แต่ยังต้องมีกลไก migration เพราะจะใช้จริงกับ column ใหม่ |
| 8 | `qr_integrations.json` | **ย้ายเข้า SQLite ด้วย** | รวมเป็นระบบเดียวกับ `mqtt_brokers` ไม่เหลือ JSON file loop |

---

## Phase 1 — Database Foundation

### [ ] 1.1 สร้างระบบ schema migration
- ไฟล์: `src/core/database.py`
- ใช้ `PRAGMA user_version` เก็บเลขเวอร์ชัน schema ปัจจุบัน
- เขียน list ของ migration steps เรียงเวอร์ชัน (`ALTER TABLE ...`) แทนการพึ่ง `CREATE TABLE IF NOT EXISTS` เพียงอย่างเดียว
- ต้อง idempotent — รันซ้ำได้โดยไม่พัง, apply เฉพาะ migration ที่ยังไม่เคย apply
- เก็บ baseline schema ปัจจุบัน (qr_scans, mqtt_events, audit_log, config_history, mqtt_brokers, mqtt_broker_topics) เป็น version 1
- **ห้าม** มี `DROP TABLE` หรือการลบข้อมูลใน migration script ใดๆ

### [ ] 1.2 แยก DB provisioning ออกจาก server boot
- ปัจจุบัน: `init_db()` (`database.py:155-166`) ถูกเรียกจาก `server.py:684` ทุกครั้งที่ process start
- เพิ่ม hook แยกใน `vas install` (`cli.py:402-428`) หรือ `vas server install-service` (`services/server_service.py:45-59`) ให้เรียก DB provisioning ครั้งแรกตอน install ชัดเจน
- server boot ยังคงเรียก migration-check ได้ (ปลอดภัยเพราะ idempotent) แต่ควรแยก concept "first install" กับ "routine boot check" ให้ชัดในโค้ด/log

### [ ] 1.3 Migrate MQTT config: `config.json` → `mqtt_brokers` เท่านั้น
- ไฟล์ที่เกี่ยวข้อง (จุดใช้งาน `config.json` ทั้งหมดที่ตรวจพบ):
  - `src/core/config.py:42-44` — `main_config_path()` (จุด define path, จะลบทิ้ง)
  - `src/features/mqtt/client.py:92-121` — `load_mqtt_config()` / `save_mqtt_config()` (จุดอ่าน/เขียนจริง จุดเดียว)
  - `src/cli.py:705-786` — คำสั่ง `vas mqtt config/status` (ต้องแก้ให้อ่าน/เขียน DB แทน)
- Migration step: ตอน DB migration รอบแรกที่เจอ `config.json` เดิม (ถ้ามี) → อ่านค่า `mqtt` section แล้ว insert เป็น row แรกใน `mqtt_brokers` (`is_primary=1`)
- ลบ `MqttConfig` dataclass, `load_mqtt_config()`, `save_mqtt_config()`, `main_config_path()` ออกทั้งหมดหลังย้ายเสร็จ — ไม่เหลือ dual-write
- แก้ทุกจุดที่ import จาก `features.mqtt.client` แบบ legacy (`server.py:702,1205-1226`, `cli.py:705-788`) ให้ใช้ multi-broker API แทน

### [ ] 1.4 Migrate `qr_integrations.json` → SQLite
- ไฟล์: `src/features/qr/registry.py` (`load_integrations`/`save_integrations`, บรรทัด 86-108)
- ออกแบบตาราง `device_integrations` ใหม่ (หรือเพิ่ม column `device_id` ใน `mqtt_brokers`/ตารางเชื่อม) เก็บ enable/topic/qos ต่อ device_id
- แก้ `server.py:930-988` (routes ที่ใช้ `load_integrations`/`save_integrations`) ให้อ่าน/เขียน DB แทน JSON
- ผลลัพธ์: หน้า `/qr/devices/zkteco-qr500` อ่าน/เขียนแหล่งข้อมูลเดียวกับที่ publish loop ใช้จริง (แก้ปัญหา UI ตกแต่งใน 3.2)

---

## Phase 2 — QR Raw Data (3 โหมด)

### [ ] 2.1 เพิ่ม raw byte report capture (hidraw only)
- ไฟล์: `src/features/qr/reader.py`, class `QrReaderThread.run()` (บรรทัด 369-399)
- ตอนนี้ตัวแปร `report` (64 bytes ดิบจาก `os.read()`, บรรทัด 380) ถูกส่งเข้า `decode_hid_report()` แล้วทิ้งทันที — ไม่มีการเก็บ
- เพิ่ม buffer ใหม่เก็บ raw byte reports ต่อรอบ scan (เช่น list ของ `bytes` หรือ hex string ต่อกัน), flush พร้อมกับ `_last_scan`/`_last_scan_raw` ตอนเจอ Enter
- เพิ่ม property ใหม่ `last_scan_raw_report: str | None` (hex-encoded เช่น `"00001e0000000000..."`) เพราะ JSON/MQTT เป็น text ใส่ binary ตรงๆไม่ได้
- `EvdevQrReaderThread` (บรรทัด 406-480): **ไม่ต้องทำ** — evdev ไม่มี byte report ให้ดัก ปล่อย property นี้เป็น `None` เสมอสำหรับโหมดนี้ (ตาม decision hybrid)

### [ ] 2.2 เพิ่ม field `read_mode` + capability flag
- แก้ทั้ง `QrReaderThread` และ `EvdevQrReaderThread` ให้ expose `read_mode: "hidraw" | "evdev"` (constant ต่อ instance อยู่แล้วโดยนัยจาก class แต่ยังไม่ expose เป็น field ชัดเจน)
- ป้องกันปัญหาที่เจอ: `last_scan_raw` เป็น HID keycode (hidraw) กับ evdev scancode (evdev) คนละ numbering space แต่ field เดิมชื่อเหมือนกัน — ต้องมี `read_mode` กำกับทุก payload/row เพื่อให้ third-party decode ถูก

### [ ] 2.3 Rename/เพิ่ม payload mode: `decoded` / `raw_keycode` / `raw_report`
- ไฟล์: `src/features/mqtt/client.py`
  - `PAYLOAD_MODES` (บรรทัด 26) → เปลี่ยนจาก `("decoded", "raw")` เป็น `("decoded", "raw_keycode", "raw_report")`
  - `publish_qr_scan()` (บรรทัด 311-341) → เพิ่ม branch สำหรับ `raw_report` ที่ใช้ `last_scan_raw_report` (จาก 2.1), ยัง fallback เป็น `decoded` ถ้าค่าที่ต้องการเป็น `None` (เช่น ขอ `raw_report` แต่เครื่องเป็น evdev)
- ไฟล์: `src/core/database.py` — คอลัมน์ `mqtt_brokers.payload_mode` (บรรทัด 89) ไม่ต้องแก้ type แต่ validation logic ที่ไหนก็ตามอ้าง `PAYLOAD_MODES` ต้องอัปเดตตาม
- payload ทุกโหมดควรมี `"read_mode"` แนบไปด้วยเสมอ (ดู 2.2) และถ้า mode ที่เลือกไม่มีข้อมูล (เช่น `raw_report` บนเครื่อง evdev) ให้ยิง error/skip พร้อม log ชัดเจน แทนการยิง payload เพี้ยนแบบเงียบๆ — ต้องตกลงพฤติกรรม fallback ให้ชัดตอน implement

### [ ] 2.4 เพิ่มคอลัมน์ใน `qr_scans` (ผ่าน migration, ห้ามใช้ `CREATE TABLE IF NOT EXISTS` เปล่าๆ)
- Schema ปัจจุบัน (`database.py:42-47`): `id, ts, value, device`
- เพิ่ม: `raw_keycode TEXT` (JSON-encoded list[int]), `raw_report TEXT` (hex string, nullable), `read_mode TEXT` (`hidraw`/`evdev`)
- ทำผ่าน migration step ใหม่ใน 1.1 (เช่น version 2): `ALTER TABLE qr_scans ADD COLUMN raw_keycode TEXT; ALTER TABLE qr_scans ADD COLUMN raw_report TEXT; ALTER TABLE qr_scans ADD COLUMN read_mode TEXT;`

### [ ] 2.5 ต่อข้อมูลเข้า `log_qr_scan()` + SSE publish loop
- ไฟล์: `src/core/database.py` — แก้ signature `log_qr_scan()` (บรรทัด 177-185) ให้รับ `raw_keycode`, `raw_report`, `read_mode` เพิ่ม
- ไฟล์: `src/server.py` — SSE loop `/api/qr/stream` (บรรทัด 855-891)
  - ดึง `reader.last_scan_raw`, `reader.last_scan_raw_report` (ใหม่จาก 2.1), `reader.read_mode` (ใหม่จาก 2.2) มาพร้อมกับ `reader.last_scan`
  - ส่งต่อให้ทั้ง `_db_log_qr()` (บันทึกครบ 3 โหมด) และ `_mqtt_publish()` (ใช้ตาม `payload_mode` ที่ config ไว้ต่อ broker)

---

## Phase 3 — MQTT Multi-Broker

### [ ] 3.1 ซ่อมฟังก์ชันที่หายไปใน `features/mqtt/client.py`
- `broker_db_to_config(broker: dict) -> MqttConfig-like` — แปลง row จาก `mqtt_brokers` เป็น object ที่ใช้ connect ได้ (อ้างอิงจาก `MqttMonitorSession.start()` บรรทัด 493 ที่เรียกอยู่แล้วแต่ฟังก์ชันไม่มีจริง)
- `start_mqtt_broker(broker_id: int)` — เริ่ม client instance ต่อ broker_id (อ้างอิงจาก `server.py:1066,1084,1125`)
- `get_primary_broker_id()` — คืน id ของ broker ที่ `is_primary=1`
- ตรวจสอบว่าต้องรองรับหลาย client พร้อมกัน (หลาย broker enabled พร้อมกัน) หรือ primary เดียวที่ active — ต้องดูการใช้งานจริงใน `server.py` ทุกจุดที่เรียกฟังก์ชันเหล่านี้ก่อนออกแบบ

### [ ] 3.2 ต่อหน้า `/qr/devices/zkteco-qr500` เข้าระบบจริง
- ไฟล์: `src/web/templates/qr_device_zkteco_qr500.html` (การ์ด MQTT บรรทัด 407-470)
- เปลี่ยนจากเซฟลง `qr_integrations.json` เป็นเซฟลง SQLite (ดู 1.4)
- เพิ่ม UI เลือก payload mode (`decoded`/`raw_keycode`/`raw_report`) ที่การ์ดนี้ — ตอนนี้ preview payload (บรรทัด 461) โชว์แค่ตัวอย่าง decoded เท่านั้น ไม่มีให้เลือกเลย
- แก้ SSE publish loop (`server.py:873-891`) ให้ resolve broker/topic/mode จาก DB ตาม device แทนการใช้ legacy singleton `_client` ตัวเดียวแบบ global

### [ ] 3.3 อัปเดต `mqtt_broker_form.html`
- บรรทัด 228 hardcode `payload_mode: "json"` ซึ่งไม่ valid — แก้เป็น dropdown จริงที่ส่งค่า `decoded`/`raw_keycode`/`raw_report`

---

## Phase 4 — Docs & Verification

### [ ] 4.1 อัปเดตเอกสาร
- `docs/qr/qr-reader.md` — เพิ่มส่วน raw_report, read_mode, hybrid mode behavior
- `docs/networking/mqtt.md` — อัปเดต payload mode ตัวที่ 3, ตัวอย่าง payload ใหม่, ลบส่วนอ้างอิง `config.json`
- `docs/database.md` — เพิ่ม schema ใหม่ + อธิบายระบบ migration

### [ ] 4.2 Verification
- ทดสอบบนฮาร์ดแวร์จริงทั้ง 2 โหมด (hidraw และ evdev) — ยืนยัน `raw_report` เป็น `null` ถูกต้องบน evdev, มีค่าถูกต้องบน hidraw
- ยืนยันว่า `vas update` ไม่ทำให้ MQTT settings หายอีกต่อไป (เพราะย้ายไป SQLite แล้ว)
- ยืนยันว่า migration รันบน DB เปล่าได้ (fresh install) และบน DB ที่มี schema เก่าอยู่แล้วได้ (เครื่อง production ปัจจุบันก่อนลงใหม่ ถ้าอยากทดสอบ)
- ทดสอบ multi-broker: publish ไปหลาย broker พร้อมกัน (ถ้าออกแบบให้รองรับ) หรือ broker เดียวที่ primary (ตามที่ตกลงใน 3.1)
- เช็คว่าหน้า `/qr/devices/zkteco-qr500` กด save แล้ว scan จริงส่งออก MQTT ตาม topic/mode ที่ตั้งในหน้านั้นจริง (ปิด gap ที่เจอว่า UI ตกแต่ง)

---

## หมายเหตุ — งานที่ตัดขอบเขตออกไปแล้ว (Out of scope รอบนี้)

- ไม่ต้องเขียน migration แบบ backup/rollback เข้มงวดระดับ production (เครื่องเดียวที่มีจะลงใหม่)
- ไม่ต้องรองรับ MQTT payload ส่ง 3 โหมดพร้อมกันในข้อความเดียว (ตกลงใช้ selectable mode แบบเดิม)
- ไม่แตะ `qr_config.json` / `qr_devices.json` (ปลอดภัยจาก `vas update` อยู่แล้ว ไม่ได้อยู่ใน scope ที่คุยกัน)
