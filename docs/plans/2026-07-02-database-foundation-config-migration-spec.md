---
tags: [spec, plan]
date: 2026-07-02
project: vas
status: draft
---

# Spec: Database Foundation — Config Migration to SQLite + Schema Migration System

## Goal
ย้าย MQTT config (`config.json`) และ QR device integration config (`qr_integrations.json`) เข้า SQLite ทั้งหมด, สร้างระบบ schema migration ที่ไม่ลบข้อมูลเดิม, ซ่อมระบบ multi-broker ให้ connect ได้พร้อมกันหลายตัวจริง, และแยก DB provisioning ออกจาก server boot ไปไว้ที่ install/update

## Data model changes

### Migration mechanism (`src/core/database.py`)
- ใช้ `PRAGMA user_version` เก็บเลขเวอร์ชัน schema ปัจจุบันของ `vas.db`
- แทนที่ `_SCHEMA` string เดี่ยว ด้วย `_MIGRATIONS: list[tuple[int, str]]` เรียงเวอร์ชัน:
  - **version 1** = schema ปัจจุบันทั้งหมด (`qr_scans`, `mqtt_events`, `audit_log`, `config_history`, `mqtt_brokers`, `mqtt_broker_topics`) — ใช้ `CREATE TABLE IF NOT EXISTS` เดิมได้เลย ปลอดภัยสำหรับ DB ที่มีอยู่แล้ว
  - **version 2** = เพิ่มตาราง `device_integrations` (ดูด้านล่าง)
- `init_db()` เปลี่ยนพฤติกรรม: อ่าน `PRAGMA user_version` ปัจจุบัน → รันเฉพาะ migration ที่ version สูงกว่า → อัปเดต `user_version` ทีละขั้นหลัง apply สำเร็จแต่ละ step (ไม่ jump ข้าม)
- **ห้ามมี `DROP TABLE`/`DELETE` ใน migration script ใดๆ**
- เพิ่มฟังก์ชันใหม่แยกจาก `init_db()`: `run_migrations() -> None` (เขียน logic จริง), `current_schema_version() -> int`, `latest_schema_version() -> int` (สำหรับ boot-time version check ด้านล่าง)

### ตารางใหม่: `device_integrations` (migration version 2)
```sql
CREATE TABLE IF NOT EXISTS device_integrations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT    NOT NULL,                 -- เช่น "zkteco-qr500"
    integration_type TEXT   NOT NULL CHECK(integration_type IN ('webhook','mqtt','pipe')),
    enabled         INTEGER NOT NULL DEFAULT 0,
    broker_id       INTEGER REFERENCES mqtt_brokers(id) ON DELETE SET NULL,  -- ใช้เฉพาะ type='mqtt'
    topic           TEXT    NOT NULL DEFAULT '',
    qos             INTEGER NOT NULL DEFAULT 1,
    settings_json   TEXT    NOT NULL DEFAULT '{}',    -- field เฉพาะประเภท (webhook: url/method/headers, pipe: path) — ยังไม่ implement ฝั่ง publish จริงสำหรับ webhook/pipe ในรอบนี้ แค่เตรียม schema ไว้
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    UNIQUE(device_id, integration_type)
);
CREATE INDEX IF NOT EXISTS idx_device_integrations_device ON device_integrations(device_id);
```
หมายเหตุ: ตอนนี้มีข้อมูลจริงใช้งานแค่ type `mqtt` เท่านั้น (`webhook`/`pipe` เป็นแค่ placeholder tab ใน UI ปัจจุบัน ไม่มี backend logic) — migration data จาก `qr_integrations.json` จะย้ายเฉพาะ key ที่มีอยู่จริงในไฟล์ (ปกติคือแค่ `mqtt`)

### `mqtt_brokers` (มีอยู่แล้ว — ไม่ต้องแก้ schema)
Column ครบสำหรับเก็บสิ่งที่เคยอยู่ใน `config.json`/`MqttConfig` อยู่แล้ว (`broker_url, username, password, client_id, tls_insecure, topic, qos, retain, payload_mode, enabled, is_primary, keep_alive, reconnect_min, reconnect_max, notes`) — งานนี้คือ **data migration** (ย้ายค่า) + **แก้ application code** ไม่ใช่ schema migration

## Process flow

### 1. Schema migration runner
1. `run_migrations()` เช็ค `current_schema_version()` เทียบ `latest_schema_version()`
2. Apply migration ทีละ version ที่ยังไม่ถึง เรียง 1 → 2 → ...
3. แต่ละ migration wrap ใน transaction เดียว (commit ต่อเมื่อสำเร็จทั้ง statement + version bump)

### 2. Migrate `config.json` → `mqtt_brokers` (data migration, ผูกกับ migration version 2)
1. Hardcode path `{install_dir}/config.json` ตรงในโค้ด migration นี้ (ไม่พึ่ง `main_config_path()` เพราะฟังก์ชันนี้จะถูกลบ) — resolve `install_dir` แบบเดียวกับที่ `core/config.py:44` ทำอยู่เดิม (`Path(__file__).parent.parent`)
2. ถ้าไฟล์ไม่มี → ข้าม ไม่ error
3. ถ้ามี → parse JSON, ดึง key `"mqtt"`, map field ตรงเข้า `mqtt_brokers` columns, insert แถวใหม่ (`is_primary=1`, `name='Migrated from config.json'`, `created_at`/`updated_at`=UTC now)
4. อ่านค่ากลับมา (read-back) เพื่อยืนยัน insert สำเร็จก่อนขั้นตอนถัดไป
5. บันทึก event ผ่าน `log_config_change()` (pattern เดิมที่มีอยู่แล้วใน `database.py`) เพื่อ traceability
6. **ลบไฟล์ `config.json` จริง** (`Path.unlink()`) เฉพาะเมื่อ read-back ยืนยันสำเร็จเท่านั้น
7. ก่อนลบ: audit ทุกจุดอ้างอิง `config.json`/`main_config_path` ในโค้ด (รายการอยู่ใน "Files that will change" ด้านล่าง — ตรวจแล้วจากรอบ research มีแค่ 3 ไฟล์ ปิด reference ให้ครบก่อน merge)

### 3. Migrate `qr_integrations.json` → `device_integrations` (ผูกกับ migration version 2)
1. อ่าน `~/.config/vas/qr_integrations.json` ถ้ามี (path เดิมจาก `registry.py`)
2. วน key ที่มีจริงในไฟล์ (`webhook`/`mqtt`/`pipe`) → insert แถวใน `device_integrations` ต่อ `device_id="zkteco-qr500"` (ตอนนี้มี device เดียวใน `DEVICE_CATALOG`)
3. สำหรับ `mqtt`: map `broker_id`/`topic`/`qos`/`enabled` ตรงเข้า column, ที่เหลือ (ถ้ามี) ลง `settings_json`
4. สำหรับ `webhook`/`pipe`: ทุก field ที่มี (ถ้ามี) ลง `settings_json` ทั้งหมด (schema ไม่ constraint รูปแบบ เพราะยังไม่มี backend logic ใช้งานจริง)
5. ลบไฟล์ `qr_integrations.json` หลัง read-back ยืนยันสำเร็จ (เหมือนขั้นตอน config.json)

### 4. Multi-broker connection support (`src/features/mqtt/client.py`)
- เปลี่ยนจาก module-level singleton `_client: VasMqttClient | None` เป็น `_clients: dict[int, VasMqttClient]` (key = broker_id)
- ฟังก์ชันใหม่ที่ต้องเขียน (ที่หายไปตามที่ research เจอ):
  - `broker_db_to_config(broker: dict) -> MqttConfig` — แปลง row จาก `mqtt_brokers` (dict จาก `get_mqtt_broker()`) เป็น `MqttConfig` object (ใช้ class เดิม เป็น in-memory transfer object เท่านั้น ไม่ผูกกับไฟล์อีกต่อไป)
  - `start_mqtt_broker(broker_id: int) -> VasMqttClient` — โหลด broker จาก DB, แปลงด้วย `broker_db_to_config`, สร้าง/เก็บใน `_clients[broker_id]`, เรียก `.connect()`
  - `stop_mqtt_broker(broker_id: int) -> None` — disconnect + ลบออกจาก `_clients`
  - `get_primary_broker_id() -> int | None` — คืน `id` ของ broker ที่ `is_primary=1` (query ใหม่ใน `database.py`)
  - `start_all_enabled_brokers() -> None` — วน broker ทุกตัวที่ `enabled=1` ใน DB แล้วเรียก `start_mqtt_broker` ทีละตัว, **แยก try/except ต่อ broker** — broker ตัวหนึ่ง connect fail ต้องไม่ทำให้ตัวอื่นไม่ทำงาน
- `get_mqtt_client()` เปลี่ยน signature เป็น `get_mqtt_client(broker_id: int | None = None)` — ถ้าไม่ระบุ ใช้ primary broker
- `publish_qr_scan()` (ฟังก์ชัน convenience เดิม) **คงไว้ชั่วคราวเพื่อไม่ให้ SSE loop ใน `server.py:873-891` พังระหว่างรอรอบที่ 3** — แก้ให้ publish ไปยัง broker ที่ `is_primary=1` (ใช้ `get_primary_broker_id()` + `get_mqtt_client()`) แทนการใช้ legacy `_client` — พฤติกรรม device-aware routing (เลือก broker ตาม `device_integrations`) เป็น scope ของรอบที่ 3 ตาม TODO.md ไม่ทำในรอบนี้
- ลบ: `MqttConfig` file-based `load_mqtt_config()`/`save_mqtt_config()`, ลบ `main_config_path()` ใน `core/config.py`

### 5. แยก DB provisioning ออกจาก server boot
- `server.py:684` (`_init_db()`) → เปลี่ยนจากเรียก schema-writing เต็มรูปแบบ เป็น **read-only version check**: เทียบ `current_schema_version()` กับ `latest_schema_version()` — ถ้าไม่ตรง ให้ log error ชัดเจน (`"Database schema out of date — run: vas db migrate"`) แล้ว **หยุด start server** (fail loud แทน silent-write) — ไม่เขียน schema ที่ boot อีกต่อไป
- เพิ่มคำสั่ง CLI ใหม่ `vas db migrate` (หรือ `vas db init` — ชื่อเดียวกันใช้ได้ทั้ง first-install และ update) → เรียก `run_migrations()` ตรงๆ
- `cli.py` — คำสั่ง `install` (บรรทัด ~402-428) เรียก `vas db migrate` logic ต่อท้ายหลัง component อื่นติดตั้งเสร็จ
- `services/updater.py` — ทั้ง `SelfUpdater.update()` และ `start_web_update()` หลัง `shutil.copytree(source_dir, self.install_dir)` เสร็จ → เพิ่มขั้นตอนเรียก migration runner (import ตรงจาก `core.database` แล้วเรียก `run_migrations()`, ไม่ต้อง subprocess เพราะ python เดียวกัน) — นี่คือจุดที่ตอบโจทย์ "vas update ให้ update database โดยไม่ลบข้อมูลเก่า"

## API changes
ไม่มี endpoint ใหม่ในรอบนี้ — endpoint เดิมที่ยังใช้ path เดิม (request/response contract ไม่เปลี่ยน) แต่เปลี่ยน storage layer ด้านหลัง:
- `POST /api/mqtt/config`, `vas mqtt status/config` (CLI) — เขียนใหม่ให้อ่าน/เขียน `mqtt_brokers` (primary broker) แทน `config.json`
- `GET/POST /api/qr/integrations/<type>` (`server.py:969-988`) — เขียนใหม่ให้อ่าน/เขียน `device_integrations` แทน `qr_integrations.json`

## Frontend changes
ไม่มีในรอบนี้ — `qr_device_zkteco_qr500.html` ยังโพสต์ไปที่ endpoint เดิม, `mqtt_broker_form.html` (payload_mode bug) ปล่อยไว้แก้ในรอบที่ 3 พร้อมกับงาน UI wiring อื่นๆ เพื่อไม่ให้ scope ปนกัน — **ยกเว้น**: ถ้า pr-reviewer เจอว่า multi-connection ทำให้ mqtt_broker_form.html พังจริง (เช่น toggle enabled หลายตัวพร้อมกันแล้ว UI ไม่รองรับ) ให้ patch เท่าที่จำเป็นเพื่อไม่ให้ regression เท่านั้น

## Implementation routing
- frontend-builder: **not required** (เหตุผล: ไม่มีการเปลี่ยน UI/template ในรอบนี้ตามที่ระบุด้านบน)
- backend-builder: **required** (DB migration system, data migration script, `features/mqtt/client.py` rewrite, `core/config.py`/`core/database.py`/`cli.py`/`server.py`/`services/updater.py`/`services/server_service.py` แก้)
- test-verifier: **required**
- pr-reviewer: **required**
- build order: backend only

## Tests required
- Unit: `run_migrations()` บน DB ว่าง → ได้ schema ครบ version ล่าสุด
- Unit: `run_migrations()` บน DB ที่มี version 1 อยู่แล้ว (มีข้อมูลใน `qr_scans` ฯลฯ) → ได้ version ล่าสุด, ข้อมูลเดิมไม่หาย, รันซ้ำได้ไม่ error
- Unit: `broker_db_to_config()` แปลง dict ครบทุก field ถูกต้อง
- Integration: มี `config.json` ตัวอย่าง → รัน migration → `mqtt_brokers` มีแถวถูกต้อง, `config.json` ถูกลบจริง
- Integration: ไม่มี `config.json` เลย → migration ไม่ error, ไม่พยายามลบไฟล์ที่ไม่มี
- Integration: มี `qr_integrations.json` ตัวอย่าง (มีแค่ key `mqtt`) → `device_integrations` มีแถว type='mqtt' ถูกต้อง
- Integration: `start_all_enabled_brokers()` — broker 2 ตัว enabled, ตัวหนึ่ง connect fail (mock) → อีกตัวยัง connect สำเร็จ ไม่ throw
- Integration: server boot ด้วย DB schema เก่ากว่า latest → server ปฏิเสธ start พร้อม error message ที่บอกให้รัน `vas db migrate`
- CLI: `vas db migrate` รันสำเร็จบน DB ทั้งสองสภาพ (ว่าง/มีข้อมูลเดิม)

## Risks and open questions
- **Breaking change ระหว่าง round 1 กับ round 3**: SSE publish loop (`server.py:873-891`) ยังใช้ `publish_qr_scan()` แบบ publish ไปที่ primary broker เท่านั้น (ไม่ device-aware) จนกว่าจะถึงรอบที่ 3 — เป็นพฤติกรรมชั่วคราวที่ยอมรับได้ตามสโคปที่ระบุ ไม่ใช่บั๊ก
- Multi-connection เพิ่ม resource ต่อ broker ที่ enabled พร้อมกัน (ยอมรับความเสี่ยงนี้แล้วตามการตัดสินใจ)
- `webhook`/`pipe` integration type ยังไม่มี backend logic จริง — เก็บได้แต่ publish ไม่ได้ ต้องแจ้งให้ชัดใน commit/PR ว่าไม่ใช่ของใหม่ที่ implement เต็ม แค่เตรียม schema
- **การลบไฟล์เป็น one-way action** — ต้อง insert + read-back สำเร็จก่อนเท่านั้นถึงจะลบ (ระบุใน process flow แล้ว) ไม่มี rollback mechanism ถ้าลบไปแล้วพบปัญหาทีหลัง (ยอมรับความเสี่ยงนี้เพราะเครื่อง production ที่มีจะลงใหม่อยู่แล้ว)
- Timezone: ทุก timestamp ใหม่ต้องใช้ `datetime.now(timezone.utc).isoformat()` ตาม pattern เดิมใน `database.py`

## Files that will change
- `src/core/database.py` — migration system, `device_integrations` schema, `run_migrations()`, `current_schema_version()`, `latest_schema_version()`, query helpers สำหรับ `device_integrations`
- `src/core/config.py` — ลบ `main_config_path()`
- `src/features/mqtt/client.py` — ลบ `MqttConfig` file load/save, เพิ่ม `broker_db_to_config`/`start_mqtt_broker`/`stop_mqtt_broker`/`get_primary_broker_id`/`start_all_enabled_brokers`, เปลี่ยน singleton เป็น multi-client dict
- `src/features/qr/registry.py` — เปลี่ยน `load_integrations`/`save_integrations` ให้อ่าน/เขียน `device_integrations` แทน JSON (คง function signature เดิมถ้าเป็นไปได้เพื่อลด diff ที่ `server.py`)
- `src/cli.py` — คำสั่ง `vas mqtt status/config` (บรรทัด ~705-786) อ่าน/เขียน DB แทนไฟล์, เพิ่มคำสั่ง `vas db migrate`, แก้ `install` command เรียก migration
- `src/server.py` — จุด auto-start MQTT ตอน boot (~700-707), legacy MQTT API (~1201-1226) เขียนใหม่, `init_db()` call (~684) เปลี่ยนเป็น version check
- `src/services/updater.py` — เพิ่มเรียก `run_migrations()` หลัง copytree ทั้งสอง path (CLI + web update)
- `src/services/server_service.py` — เอกสาร/hook เพิ่มเติมถ้าจำเป็นสำหรับ install-time provisioning
