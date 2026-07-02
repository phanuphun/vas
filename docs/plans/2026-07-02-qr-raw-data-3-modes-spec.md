---
tags: [spec, plan]
date: 2026-07-02
project: vas
status: draft
---

# Spec: QR Raw Data — 3 โหมด (decoded / raw_keycode / raw_report)

## Goal
เพิ่มการอ่าน/เก็บ/publish ข้อมูล QR scan ระดับ raw HID byte report (hidraw only) พร้อม field `read_mode` กำกับทุก record, ขยาย DB และ MQTT payload_mode ให้รองรับ 3 โหมดครบ

## Data model changes

### Migration version 3 (`src/core/database.py`)
เพิ่มเข้า `_MIGRATIONS` ต่อจาก version 2 (ห้าม DROP/DELETE ตามกติกาเดิม):
```sql
ALTER TABLE qr_scans ADD COLUMN raw_keycode TEXT;      -- JSON-encoded list[int], NULL ได้สำหรับ row เก่า
ALTER TABLE qr_scans ADD COLUMN raw_report  TEXT;      -- JSON-encoded list[str] (hex ต่อ report frame), NULL เสมอถ้า read_mode='evdev'
ALTER TABLE qr_scans ADD COLUMN read_mode   TEXT;      -- 'hidraw' | 'evdev' | NULL (row เก่าก่อน migration นี้)
```
`log_qr_scan()` (`database.py`) เพิ่ม parameter: `raw_keycode: list[int] | None = None`, `raw_report: list[str] | None = None`, `read_mode: str | None = None` — เก็บเป็น `json.dumps(...)` ถ้าไม่ None

## Process flow

### 1. Capture raw byte report (`src/features/qr/reader.py`, hidraw only)
- `QrReaderThread.run()` (บรรทัด 369-399 ปัจจุบัน): เพิ่ม `raw_report_buf: list[str] = []` เก็บ `report.hex()` ของ**ทุก** `os.read()` ที่อ่านได้ในรอบ scan (รวม key-up/all-zero frame ด้วย เพื่อความ "ดิบ" ตรงตามที่ผู้ใช้ต้องการเห็นตั้งแต่ต้น ไม่ใช่แค่ frame ที่มี keycode) — flush พร้อมกับ `_last_scan`/`_last_scan_raw` ตอนเจอ Enter
- เพิ่ม property ใหม่: `last_scan_raw_report: list[str] | None` (thread-safe เหมือน property อื่น)
- เพิ่ม attribute คงที่: `read_mode: str = "hidraw"` (class-level หรือ instance attribute ที่ set ใน `__init__`)
- `EvdevQrReaderThread`: เพิ่ม `read_mode: str = "evdev"` เท่านั้น — **ไม่เพิ่ม** `last_scan_raw_report` (หรือให้เป็น property คงที่ที่ return `None` เสมอ เพื่อให้ caller เขียน code เดียวกันได้ทั้งสอง class โดยไม่ต้อง `isinstance` check)

### 2. Rename/ขยาย `PAYLOAD_MODES` (`src/features/mqtt/client.py`)
- `PAYLOAD_MODES = ("decoded", "raw")` → `("decoded", "raw_keycode", "raw_report")` (บรรทัด 30 ปัจจุบัน)
- `MqttConfig.payload_mode` default ยังเป็น `"decoded"` เหมือนเดิม, validation ใน `_migrate_config_json_to_mqtt_brokers()` (จาก round 1, `database.py`) ต้องอัปเดตชุดค่าที่ยอมรับให้ตรงกับ `PAYLOAD_MODES` ใหม่ด้วย
- `VasMqttClient.publish_qr_scan()` (บรรทัด 320-350 ปัจจุบัน) เปลี่ยน signature เป็นรับ `scan_raw_keycode`, `scan_raw_report`, `read_mode` แทน `scan_raw` เดิม — logic:
  - `payload_mode == "decoded"` → `scan` field = decoded string
  - `payload_mode == "raw_keycode"` → `scan` field = `scan_raw_keycode` (list[int])
  - `payload_mode == "raw_report"` → `scan` field = `scan_raw_report` (list[str] hex)
  - **ทุก mode แนบ `"read_mode"` เข้า payload เสมอ**
  - **ถ้าข้อมูลของ mode ที่เลือกเป็น `None`** (เช่นขอ `raw_report` แต่ `read_mode="evdev"`) → **ไม่ publish, return `False`** พร้อม log ผ่าน `log_mqtt_event(..., ok=False)` ระบุเหตุผลใน payload/field เช่น `{"error": "raw_report not available for read_mode=evdev"}` — ตามที่ตกลงว่าห้าม silent fallback
- `publish_qr_scan()` module-level convenience wrapper (บรรทัด 483-500 ปัจจุบัน) และ `server.py` SSE loop ต้องส่งค่าใหม่ทั้ง 3 ผ่านมาด้วย

### 3. เชื่อมเข้า SSE loop (`src/server.py:804-891`)
- บรรทัด 876 (`scan = reader.last_scan`) → เพิ่มดึง `scan_raw_keycode = getattr(reader, "last_scan_raw", None)`, `scan_raw_report = getattr(reader, "last_scan_raw_report", None)`, `read_mode = getattr(reader, "read_mode", None)`
- บรรทัด 883-884 (`_db_log_qr`) → ส่ง 3 ค่าใหม่เข้า `log_qr_scan()`
- บรรทัด 889-891 (`_mqtt_publish`) → ส่ง 3 ค่าใหม่เข้า `publish_qr_scan()` แทน `scan_raw` เดิม

### 4. Dev convenience fix (`dev.bat`)
เพิ่มบรรทัด `uv run python -m cli db migrate` ก่อนบรรทัด `flask run` เพื่อไม่ให้เจอ `SchemaOutOfDateError` ซ้ำทุกครั้งที่มี migration ใหม่ระหว่าง dev

## API changes
ไม่มี endpoint ใหม่ — `/api/qr/stream` (SSE) ส่ง field เพิ่มใน `event: scan` payload: `raw_keycode`, `raw_report`, `read_mode` (เสริมจาก `scan`/`device`/`ts` เดิม ไม่ลบของเดิม)

## Frontend changes
ไม่มีในรอบนี้ (การเพิ่ม UI เลือก payload mode ในหน้า device เป็น scope ของรอบที่ 3 ตาม TODO.md เดิม)

## Implementation routing
- frontend-builder: not required
- backend-builder: required (`reader.py`, `database.py` migration v3 + `log_qr_scan`, `features/mqtt/client.py`, `server.py`, `dev.bat`)
- test-verifier: required
- pr-reviewer: required
- build order: backend only

## Tests required
- Unit: `QrReaderThread` จำลอง report bytes หลายเฟรม → `last_scan_raw_report` มี hex string ครบทุก frame รวม key-up
- Unit: `EvdevQrReaderThread.last_scan_raw_report` เป็น `None` เสมอ, `read_mode == "evdev"`
- Unit: migration v3 บน DB ที่มี row เก่าจาก round 1 → column ใหม่เป็น NULL ไม่ error, query เดิมยังทำงาน
- Integration: `publish_qr_scan(payload_mode="raw_report")` เมื่อ `scan_raw_report=None` → return False, ไม่ publish, มี log
- Integration: SSE loop end-to-end (mock reader) → DB row มีครบ 3 คอลัมน์ตรงกับ reader state

## Risks and open questions
- Raw report เก็บทุก frame (รวม key-up all-zero) ทำให้ payload/DB ใหญ่ขึ้นกว่าที่คิดในตอนแรกที่คุยกันแบบคร่าวๆ — ยอมรับได้เพราะเป็นความต้องการเดิมของผู้ใช้ที่อยากเห็น byte ดิบจริงๆ ("00 23 06 05...")
- `read_mode=None` กรณี reader ยังไม่เคย scan เลย (เพิ่ง start) — handle เป็น NULL ปกติ ไม่ error

## Files that will change
- `src/features/qr/reader.py` — raw report capture, `read_mode` attribute
- `src/core/database.py` — migration v3, `log_qr_scan()` signature
- `src/features/mqtt/client.py` — `PAYLOAD_MODES`, `publish_qr_scan()` (class method + module wrapper)
- `src/server.py` — SSE loop wiring
- `dev.bat` — auto-migrate บรรทัดใหม่
