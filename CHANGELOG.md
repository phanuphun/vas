# Changelog

## [2026-06-28]

### ย้าย paho-mqtt และ evdev เป็น core dependencies
- เพิ่ม `paho-mqtt>=1.6` และ `evdev>=1.6` ใน `pyproject.toml` dependencies หลัก
- ลบ package entries `paho-mqtt` และ `python-evdev` ออกจาก `settings.py` (ไม่ต้องติดตั้งแยกอีกต่อไป)
- `display_sim_status()` คืน `lib_ok: True` ถาวร เนื่องจาก evdev เป็น dep หลักแล้ว

### เพิ่ม get_broker_connection_status() ใน mqtt/client.py
- ฟังก์ชันใหม่สำหรับ broker detail page — ตรวจสอบว่า active client กำลังใช้ broker นั้นอยู่หรือไม่
- แก้ MqttMonitorSession cleanup: ลบ `c.disconnect()` ออกเพื่อป้องกัน disconnect client ที่ยังใช้งานอยู่

### อัปเดต QR device และ MQTT pages ให้ใช้ multi-broker API
- `qr_device_zkteco_qr500_page` เปลี่ยนจาก `load_mqtt_config()` เป็น `list_mqtt_brokers()`
- `mqtt_page` ลบ `paho_available` context variable ออก (ไม่จำเป็นแล้ว)

### เพิ่ม Confirm Modal Convention ใน INSTRUCTIONS.md
- บังคับใช้ `showConfirm()` แทน `window.confirm()` สำหรับ action ที่ย้อนกลับไม่ได้
- เพิ่มตัวอย่าง HTML modal และ JS usage ใน INSTRUCTIONS.md

### ปรับ UI หลายหน้า
- base.html, database.html, display.html, monitor.html — UI cleanup และ showConfirm integration
- mqtt.html, mqtt_broker_detail.html, mqtt_broker_form.html — อัปเดตให้รองรับ multi-broker
- qr_device_zkteco_qr500.html, qr_devices.html — ใช้ broker list แทน single config
- wireguard.html — ปรับ UI ครั้งใหญ่

## [2026-06-27]

### ปรับ mqtt.html — Section Menu 2 tabs + Message Monitor panel
- แทนที่ Toolbar "รายการ Broker" label ด้วย Section Menu แบบ 2 tabs: **Brokers** (lucide:server) และ **Message Monitor** (lucide:activity)
- ย้ายปุ่ม "เพิ่ม Broker" จาก toolbar เข้าไปใน card header ของ broker list (ขวาบน)
- เพิ่ม tab panel **Message Monitor**: control card (broker select + topic input + เริ่ม/หยุด), status strip (dot indicator + topic label + message count + ล้าง + auto-scroll), message log (dark terminal style, max-height 380px)
- Polling JS: `monStart/Stop/Clear/Poll` — polling ทุก 1.5s ผ่าน `GET /api/mqtt/monitor/messages?since=N`, แสดง timestamp/topic/payload ด้วย syntax highlight
- Tab switching: `mqttTab()` toggle class `bg-accent/8 text-accent font-semibold` / `text-muted` โดยไม่ใช้ Tailwind JIT
- SPA cleanup: `window.__vasCleanup.push(...)` หยุด interval และ stop session เมื่อ navigate ออก
- ใช้ bash heredoc แทน Write tool เพื่อป้องกัน truncation (ไฟล์ 465 บรรทัด)

### เพิ่ม paho-mqtt ใน Settings > Software
- เพิ่ม package entry `paho-mqtt` ในกลุ่ม Network ของ `features/packages/settings.py`
- check: `_python_import_check("paho")`, install: `apt-get install python3-paho-mqtt`
- logo: ใช้ `mqtt-logo.png` ที่มีอยู่แล้วใน `public/images/logo/`
- ปรากฏในหน้า Settings > Software ใต้กลุ่ม NETWORK พร้อมปุ่ม Install

### ปรับ UX หน้า MQTT Broker List (รอบ 2)
- Stats Cards: ปรับเป็น Monitor style — icon box (`w-9 h-9 bg-surface border rounded-lg`) + label + metric value ขนาด 1.25rem แทน big number เดิม
- Broker List: ปรับเป็น Settings pkg-row style — icon box (wifi, เปลี่ยนสีตามสถานะ) + ชื่อ/badge/URL/topic count + ปุ่ม action (เชื่อมต่อ/จัดการ/แก้ไข icon/ลบ icon)
- Empty state: ใช้ iconify-icon `lucide:wifi-off` แทน SVG inline

### ปรับ UX หน้า MQTT Broker List
- ย้ายปุ่ม "เพิ่ม Broker" ออกจาก header_actions เข้ามาใน Content area
- เพิ่ม Toolbar Section (nav bar เหมือน display.html) แสดง label "รายการ Broker" + ปุ่ม action ทางขวา
- แทนที่ paho-mqtt alert banner ด้วย Library card แบบเดียวกับ "Library ที่จำเป็น" ใน display.html: header+badge status + missing row (bg-caution/5, border-caution/20) + ปุ่ม "ไปติดตั้ง"
- ห่อ content ทั้งหมดด้วย `<div class="flex flex-col gap-4">` ตาม convention ของ INSTRUCTIONS.md

### MQTT Multi-Broker Management
- ปรับหน้า `/mqtt` ใหม่เป็น **Broker List** — ตาราง brokers พร้อม status badge, ปุ่มเชื่อมต่อ/จัดการ/แก้ไข/ลบ
- เพิ่มหน้า `/mqtt/broker/add` — ฟอร์มเพิ่ม broker ใหม่ (แยกหน้าตาม UX requirement)
- เพิ่มหน้า `/mqtt/broker/<id>/edit` — ฟอร์มแก้ไข broker (แยกหน้า)
- เพิ่มหน้า `/mqtt/broker/<id>` — Broker Detail: tab สถานะ, tab Topics (เพิ่ม/ลบ/toggle), tab ข้อมูล
- เพิ่ม `mqtt_brokers` table — เก็บ name, broker_url, username, password, client_id, qos, retain, payload_mode, tls_insecure, keep_alive, reconnect_min/max, notes, is_primary, enabled
- เพิ่ม `mqtt_broker_topics` table — เก็บ topics หลายรายการต่อ broker (topic, label, enabled)
- เพิ่ม CRUD functions ใน `core/database.py`: `list/get/create/update/delete_mqtt_broker`, `list/add/update/delete_mqtt_topic`
- เพิ่ม helper functions ใน `features/mqtt/client.py`: `broker_db_to_config`, `start_mqtt_broker`, `get_broker_connection_status`, `get_primary_broker_id`
- API endpoints ใหม่: `POST/PUT/DELETE /api/mqtt/brokers/<id>`, `POST /api/mqtt/brokers/<id>/connect`, `/disconnect`, `/test`, `/status`, `POST/PUT/DELETE /api/mqtt/topics/<id>`
- UI ตาม INSTRUCTIONS.md convention: Page Header + Section Menu (tabs) + Content Section, ui-minimal design system



### ระบบจัดการผู้ใช้งาน (Auth & User Management)
- เพิ่ม `src/core/auth.py` — auth module: สร้าง/แก้ไข/ลบผู้ใช้, hash password ด้วย werkzeug, roles: root/admin/user
- เพิ่ม `users` table ใน SQLite (เรียก `init_users()` จาก `init_db`)
- หน้า First-run Setup (`/setup`) — ครั้งแรกที่ไม่มี user ให้สร้าง Root ก่อน
- หน้า Login (`/login`) — form login พร้อม toggle show/hide password
- หน้า User Management (`/users`) — ตาราง users, เพิ่ม/แก้ไข/ลบ, reset password ผ่าน modal
- `before_request` guard — ป้องกัน route ที่ต้อง login, redirect first-run อัตโนมัติ
- Navbar: user dropdown แสดงชื่อ+role, แก้ไขโปรไฟล์, เปลี่ยนรหัสผ่าน, ออกจากระบบ
- Sidebar: เมนู "ผู้ใช้งาน" แสดงเฉพาะ root/admin
- API: `/api/users`, `/api/users/<id>`, `/api/users/<id>/reset-password`, `/api/profile`, `/api/profile/password`

### QR Device Catalog & Integration System
- เพิ่มหน้า **อุปกรณ์** (`/qr/devices`) — catalog ของ hardware ที่รองรับ, ปุ่มติดตั้ง/ถอน, แสดง device ที่ install แล้ว
- เพิ่มหน้า **ZKTeco QR500** (`/qr/device/zkteco/qr500`) — tab ตั้งค่า device (hidraw/evdev) + tab Integration (Webhook, MQTT Publish, Named Pipe I/O)
- Integration Webhook: กำหนด URL, HTTP Method, Retry (1/5/10 ครั้ง), Timeout, แสดง Payload ตัวอย่าง
- Integration MQTT: เลือก broker จากที่ตั้งไว้ในหน้า MQTT หรือกรอกใหม่, กำหนด topic และ QoS
- Integration Pipe I/O: สร้าง named pipe (`mkfifo`) ให้ process อื่นอ่านข้อมูลสแกนได้
- เพิ่ม `qr_device_registry.py` — จัดการ installed devices + integration config (JSON)
- ปรับ `qr.html` — เพิ่มปุ่ม Copy Clipboard ชัดเจน, ลบ scan animation, เพิ่ม Flow Diagram แบบ pipeline
- ปรับ `base.html` sidebar — เพิ่ม "อุปกรณ์" nav, conditional "QR500" sub-item เมื่อ install
- เพิ่ม API: `/api/qr/devices/<id>/install`, `/api/qr/devices/<id>/uninstall`, `/api/qr/integrations`, `/api/qr/integrations/<type>`, `/api/qr/integrations/pipe/create`

### แก้ SPA Router โหลดซ้ำหลายรอบ (base.html)
- **FIX 1**: เพิ่ม `e.isTrusted` check — ป้องกัน synthetic click events จาก web components (เช่น `<iconify-icon>`) trigger navigation ซ้ำ
- **FIX 2**: เพิ่ม `e.stopPropagation()` — ป้องกัน listener อื่นจับ event ซ้ำ
- **FIX 3**: เพิ่ม `AbortController` — cancel fetch ที่ค้างอยู่เมื่อ navigate ใหม่, ป้องกัน concurrent navigation ทำให้ content ถูกเขียนทับหลายรอบ
- **FIX 4**: เปลี่ยน `window.__vasCleanup = []` → `window.__vasCleanup = window.__vasCleanup || []` — ป้องกัน SPA init ลบ cleanup functions ที่ page scripts ลงทะเบียนไว้ก่อนหน้า (เพราะ `{% block extra_scripts %}` รันก่อน SPA init)

### ปรับ Monitor ตาม page convention
- ย้าย styles จาก `{% block extra_styles %}` (ไม่ได้ defined ใน base.html) มาเป็น `<style>` tag ใน content block
- เพิ่ม Page Header (eyebrow + h1 + subtitle) ตาม INSTRUCTIONS.md convention
- ปรับโครงสร้าง content block ให้ถูกต้อง: Page Header → Content Section

### Re-Design หน้า Monitor
- ออกแบบหน้า System Monitor ใหม่ด้วย UI-Minimal Design System
- เพิ่ม Summary Stat Row (4 cards: CPU%, RAM%, Load Avg, Temperature) ไว้ด้านบน
- เพิ่ม Loading skeleton แทน spinner เพื่อประสบการณ์ที่ดีขึ้น
- ปรับ CPU/RAM card: bar usage + grid metric ที่อ่านง่ายขึ้น
- ปรับ per-core bars เป็น micro-bar grid แบบ compact
- Disk section: เพิ่ม icon, fstype badge, และ layout ที่สะอาดขึ้น
- Network section: เพิ่ม interface icon และจัด layout ชัดเจน
- ใช้สี dynamic (safe/caution/danger) ตาม threshold บน stat cards

## [2026-06-23]

### OpenSSH Server
- เพิ่ม `vas install/reset --component openssh` ติดตั้งและรีเซ็ต openssh-server
- แสดงสถานะ OpenSSH ใน `vas check` และ dashboard

### HomeOffice Theme
- ย้าย web templates มาใช้ HomeOffice Design System (sidebar, cf-* components)
- เพิ่ม `homeoffice.css` และ `app.js` สำหรับ layout และ UI interactions

### QR Code Reader (ZKTeco QR500-BM)
- อ่าน QR ผ่าน hidraw HID keyboard mode พร้อม CLI (`vas qr`) และ web UI (`/qr`)
- SSE stream สำหรับ real-time scan, API start/stop/config
- ติดตั้ง udev rule ผ่าน `vas install --component qr-udev`
- เพิ่ม agent skill และเอกสารอ้างอิง ZKTeco QR500

## [2026-06-20]

### เพิ่ม MCP tool specs และปรับปรุง TODO
- เพิ่ม spec สำหรับ MCP tool `diagnose_touchscreen` — วิเคราะห์ปัญหา touchscreen แบบ step-by-step (kernel → xinput → xorg → session)
- เพิ่ม spec สำหรับ MCP tool `diagnose_remote_access` — วิเคราะห์ปัญหา AnyDesk เข้าไม่ได้ (service → network → logs)
- เพิ่ม spec สำหรับ MCP tool `diagnose_display` — วิเคราะห์ปัญหาหน้าจอไม่แสดงผลหรือ rotation ผิด
- เพิ่ม improvement notes สำหรับ production server (gunicorn), Basic Auth dashboard, และ pytest-cov
- เพิ่ม retrospective: MCP server startup และ mount() fix

## [2026-06-18]

### ปรับปรุง agentflow และโครงสร้างโปรเจกต์
- อัปเดต `.agents/README.md`, `.agents/workflows/` ให้ใช้ config.json แทน hardcode path
- ลบ `AGENTS.md` (ย้ายเนื้อหาไปใช้ผ่าน `@AGENTS.md` ใน CLAUDE.md)
- อัปเดต `AGENTS.md.bak` ให้ตรงกับเนื้อหาล่าสุด
- เพิ่ม `.agents/config.json` สำหรับ resolve `agentsPath` และ `wikiPath` แบบ dynamic
- เพิ่ม `.agents/skills/grill-me/` skill ใหม่
- เพิ่มโฟลเดอร์ `wiki/` สำหรับ project wiki
- เพิ่ม `.mcp.json` ใน `.gitignore` เพื่อป้องกัน machine-specific config รั่วไหล
- แก้ไข `CLAUDE.md` ให้ reference `@AGENTS.md` ตัวพิมพ์ถูกต้อง
