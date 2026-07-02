# Changelog

## [2026-07-02]

### หน้า "โปรแกรมเพิ่มเติม" — เพิ่มปุ่มถอนการติดตั้ง (uninstall) พร้อม progress bar สำหรับทั้งติดตั้งและถอน
- `src/features/packages/settings.py`: เพิ่ม `uninstall_cmds` ให้ทุก package ใน manifest (git, node, pm2, docker, wireguard, openssh, anydesk, qr-udev) โดยอิงคำสั่งชุดเดียวกับ `LifecycleManager.uninstall_*` ใน `services/reset.py` เพิ่ม `start_uninstall()` / `get_uninstall_queue()` / `is_uninstalling()` คู่กับของเดิมฝั่ง install รวมทั้ง refactor runner เดิมเป็น `_run_commands(cmds, q, stop_on_error)` ใช้ร่วมกันทั้งสองฝั่ง — install หยุดทันทีถ้า command ไหน fail (`stop_on_error=True`), uninstall เป็น best-effort ข้ามไปคำสั่งถัดไปถ้า fail (`stop_on_error=False`) เพราะ `apt purge` ของที่ไม่ได้ติดตั้งอยู่แล้วไม่ควรทำให้ทั้ง flow พัง
- Queue item เปลี่ยนจาก string ล้วนเป็น dict มี `type: "progress"|"line"` — `"progress"` มี `step`/`total` ให้ฝั่งหน้าเว็บคำนวณ % ได้ นอกจากนี้ยังเพิ่ม dependency-guard: `start_uninstall()` เช็คว่ามี package อื่นที่ติดตั้งอยู่และ `depends` ตัวที่จะถอนหรือไม่ (เช่น ห้ามถอน Node.js ถ้า PM2 ยังติดตั้งอยู่) ถ้ามีจะ error กลับไปพร้อมชื่อ package ที่ต้องถอนก่อน — ผลลัพธ์นี้ expose ผ่าน `get_package_status()` เป็น field ใหม่ `can_uninstall` / `uninstall_blockers` / `uninstall_warning` (คำเตือนเฉพาะของแต่ละ package เช่น OpenSSH/AnyDesk ที่ถอนแล้วอาจเสียการเชื่อมต่อระยะไกล)
- `src/server.py`: เพิ่ม route `POST /api/settings/uninstall/<pkg_id>` และ `GET /api/settings/uninstall/<pkg_id>/stream` (SSE) คู่กับของเดิมฝั่ง install — ดึง logic SSE ที่ซ้ำกันออกมาเป็น `_stream_pkg_action_queue()` ตัวเดียวใช้ร่วมกันทั้ง install/uninstall stream แทนการก็อปโค้ดซ้ำ, parse queue item type ใหม่ (`progress` → ส่ง SSE event `progress`, อื่นๆ → event `line` เหมือนเดิม)
- `src/web/templates/apps.html`: เพิ่มปุ่ม "ถอน" (สีแดง, ใช้ `showConfirm()` ตาม convention ของโปรเจกต์ — ห้ามใช้ `window.confirm()`) ให้ package ที่ติดตั้งแล้วและไม่มีตัวอื่นพึ่งพาอยู่ (`can_uninstall`) ถ้ามีตัวอื่นพึ่งพาอยู่จะโชว์ปุ่ม disabled พร้อม tooltip บอกว่าต้องถอนอะไรก่อน — เพิ่ม progress bar (`.pkg-progress-track`/`.pkg-progress-fill`, สไตล์เดียวกับหน้า "อัปเดตระบบ") ในกล่อง modal เดิมที่ใช้ร่วมกันทั้งติดตั้ง/ถอน อัปเดตจาก SSE event `progress` แบบ real-time, เขียวเมื่อเสร็จ (`is-done`) แดงเมื่อ error (`is-error`) — รวม logic ปุ่ม install/uninstall/blocked ทั้งหมดเป็นฟังก์ชันเดียว `actionButtonHtml()` ใช้ร่วมกันทั้งแถว parent และ sub-row (children)

### SPA route-loading indicator — เปลี่ยนจาก progress bar เป็น icon หมุนข้าง info button
- เวอร์ชันแรกเพิ่มแถบสีฟ้า (`#vas-loading-bar`) fixed ขอบบนสุดของหน้าจอ ภายหลังปรับตามที่ผู้ใช้ขอ: เอาแถบออก เปลี่ยนเป็น icon `lucide:refresh-cw` ในกล่องเดียวกับปุ่ม header (ข้างปุ่ม info/circle-alert)
- Idle state: icon จาง (`text-faint opacity-40`), `pointer-events-none` — ไม่ใช่ปุ่ม ไม่ทำอะไร
- Loading state (SPA navigate กำลังทำงาน): เพิ่ม class `.is-loading` ที่ container ทำให้ icon หมุน (`@keyframes vas-icon-spin`, 0.7s linear infinite) พร้อมเปลี่ยนสีเป็นฟ้า (`--c-accent`) เหมือนสี active ของ sidebar icon
- ผูกเข้ากับ SPA router เดิมใน `base.html`: `showLoadingIcon()` ตอน `navigate()` เริ่ม fetch, `hideLoadingIcon()` เมื่อ content swap เสร็จ หรือ fetch error จริง (ไม่ hide ตอน `AbortError` เพราะเป็น request เก่าที่ถูกแทนที่ด้วย navigate ใหม่ที่กำลัง show ของตัวเองอยู่แล้ว)
- ขอบเขต: แก้เฉพาะ `src/web/templates/base.html` (CSS + 1 HTML element ใน header + 2 ฟังก์ชัน JS ผูกเข้า `navigate()` เดิม) ไม่กระทบ `base_partial.html`, route อื่น, หรือ SPA router logic ส่วนอื่น

### ZKTeco QR500 — ซ่อมปุ่ม Copy, สแกนวันนี้จาก DB, ประวัติการสแกน/publish MQTT query จาก DB พร้อม pagination
- แก้บั๊กปุ่ม Copy ที่ "ค่าล่าสุด" ไม่ทำงาน: root cause คือ `qr_device_zkteco_qr500.html` เรียก `copyValue()` ที่ไม่เคยถูก define ในไฟล์นี้ (มีอยู่แค่ใน `qr.html`) ทำให้เกิด `ReferenceError` ทุกครั้งที่กด — เพิ่ม `copyValue()`/`fallbackCopy()` ในไฟล์นี้ตรงๆ, เพิ่ม `cursor-pointer` (และ `disabled:cursor-not-allowed`) บนปุ่ม, เปลี่ยนข้อความหลัง copy สำเร็จเป็น "Copied !!" แล้วกลับเป็น "Copy" อัตโนมัติ, และ init `lastScanVal` จากค่า `qr_reader.last_scan` ที่ server render มาแทนที่จะรอ SSE event แรกก่อนถึงจะใช้ปุ่มได้
- Stat "สแกนแล้ว (session)" เปลี่ยนเป็น "สแกนวันนี้" — ดึงจำนวนจริงจาก DB (`count_qr_scans_today()`) แทน counter ฝั่ง browser ที่รีเซ็ตทุกครั้งที่ reload
- `src/core/database.py`: เพิ่ม `count_qr_scans_today(tz="Asia/Bangkok")`, `list_qr_scans(limit, offset)` (คืน raw_keycode/raw_report ที่ decode แล้ว), `list_mqtt_events(limit, offset)` — ทุกตัวรองรับ limit สูงสุด 500
- `src/server.py`: เพิ่ม route `GET /api/qr/scans` (pagination, limit จำกัดเฉพาะ 100/250/500), `GET /api/qr/scans/stats` (today_count), `GET /api/mqtt/events` (pagination เหมือนกัน)
- หน้า "ประวัติการสแกน" เปลี่ยนจาก in-memory array ของ browser session (หายเมื่อ reload, จำกัด 50 รายการ) เป็น query จาก DB จริงทั้งหมด แสดงเป็น card list (สไตล์เดียวกับ broker list ในหน้า MQTT) พร้อม page size selector [100, 250, 500] และปุ่มก่อนหน้า/ถัดไป — ปุ่ม "ล้าง" เรียก `/api/database/qr_scans/clear` จริงแทนที่จะล้างแค่ array ใน browser
- เพิ่ม section ใหม่ "ประวัติการ Publish MQTT" ในแท็บเดียวกัน — query จาก `mqtt_events` (บันทึกทุกครั้งที่ `publish_qr_scan_for_device` ยิงออกจาก QR reader นี้) พร้อม pagination แบบเดียวกัน และปุ่ม "ล้าง" เรียก `/api/database/mqtt_events/clear`
- SSE scan event ใหม่จะ debounce-refresh ทั้งสอง list อัตโนมัติถ้ากำลังดูหน้าแรกอยู่ (offset=0) เพื่อให้เห็นรายการใหม่แบบ real-time โดยไม่ต้อง manual refresh
- ใช้ ui-minimal design system เดิมของหน้านี้ทั้งหมด (bg-card/border-line/zone-*/font-display) ไม่ได้เพิ่ม framework ใหม่
- แก้ "Payload (ตัวอย่าง)" ในการ์ด MQTT Publish: ของเดิม hardcode ตัวอย่างเดียวและ field ไม่ตรงกับ payload จริงที่ `publish_qr_scan()` ส่งออก (`{"scan":...,"ts":...}` เก่า vs `{"data":...,"mode":...,"timestamp":...}` จริง) — เปลี่ยนเป็น readonly `<textarea>` สไตล์เดียวกับกล่องแก้ไข config ในหน้า WireGuard (`font-mono`, `bg-surface`, `border-line/15`) พร้อม button group (สไตล์เดียวกับ Decoded/Raw Keycode/Raw Report ใน Live Monitor) ให้สลับดูตัวอย่างทีละโหมดแทนการโชว์ทั้ง 3 พร้อมกัน — default เปิดตามค่า Payload Mode ที่ตั้งไว้
- แท็บ "ประวัติการสแกน" เดิมโชว์การ์ด "ประวัติการสแกน" และ "ประวัติการ Publish MQTT" พร้อมกันเรียงต่อกัน (ยาวเกินไป) — เปลี่ยนเป็น subview switcher ให้แสดงทีละการ์ดเท่านั้น สลับด้วยปุ่ม "ประวัติการสแกน" / "ประวัติการ Publish MQTT" — ปรับ style ปุ่มให้เป็น button group เดียวกับตัวเลือกโหมด Payload ตัวอย่าง (`.scan-mode-btn`) แทน nav-tab แบบเดิม เพื่อความสม่ำเสมอ
- แต่ละแถวในประวัติการสแกนเดิมแสดงแค่ค่า decoded — ทำให้ดูเหมือนระบบไม่ได้เก็บ raw_keycode/raw_report ทั้งที่จริง `qr_scans` เก็บไว้ครบ (`log_qr_scan()` บันทึกทุก field เสมอ, evdev มีแค่ raw_keycode ไม่มี raw_report เพราะ device ไม่ส่ง byte report มาให้) — แรกๆ เพิ่มเป็นปุ่ม "raw" ให้กดขยายดู แต่ปรับตามที่ผู้ใช้ขอเป็นแสดงทั้ง 3 version (Decoded/Raw Keycode/Raw Report) พร้อมกันเสมอในทุกแถว ไม่ต้องกด toggle — mode ไหนไม่มีข้อมูลจะโชว์ "ไม่มีข้อมูล" แทนการซ่อน
- ปรับ layout แถวประวัติการสแกนให้กระทัดรัดขึ้น (ของเดิมสูงเกินไปเวลามีหลายร้อยแถว): ลบ block "Decoded" ที่ซ้ำกับหัวแถวออก, เปลี่ยน Raw Keycode/Raw Report จากกล่อง `<code>` มีขอบ/พื้นหลัง เป็นบรรทัด label:value เรียบๆ ไม่มีกล่อง, ลดขนาด icon box/padding/font ของแต่ละแถวลง, Raw Report ต่อ frame เชื่อมด้วย " · " แทนการขึ้นบรรทัดใหม่ทีละ frame

### Database foundation — ย้าย config.json/qr_integrations.json เข้า SQLite + schema migration system + ซ่อม multi-broker
- `src/core/database.py`: แทนที่ `_SCHEMA` เดี่ยวด้วย `_MIGRATIONS: list[tuple[int, str]]` ใช้ `PRAGMA user_version` เก็บเวอร์ชัน schema — version 1 = schema เดิมทั้งหมด (รวม `users` table ที่ย้ายมาจาก `core/auth.py:init_users()`), version 2 = ตารางใหม่ `device_integrations` เพิ่ม `run_migrations()` (apply migration ทีละ version, wrap transaction, ห้าม DROP/DELETE ข้อมูลเดิม), `current_schema_version()`, `latest_schema_version()` — `init_db()` เปลี่ยนเป็น read-only version check (raise `SchemaOutOfDateError` ถ้า DB เก่ากว่าโค้ด) ไม่เขียน schema ตอน boot อีกต่อไป
- Data migration (ผูกกับ migration version 2, insert-then-read-back-verify ก่อนลบไฟล์เสมอ): `config.json` → `mqtt_brokers` (broker ใหม่ `is_primary=1`), `~/.config/vas/qr_integrations.json` → `device_integrations` (device_id="zkteco-qr500") — ถ้าไม่มีไฟล์ต้นทางจะข้ามไม่ error, ลบไฟล์จริงเฉพาะเมื่อ read-back ยืนยันสำเร็จ
- `src/features/mqtt/client.py`: เปลี่ยน singleton `_client` เดี่ยวเป็น `_clients: dict[int, VasMqttClient]` (key=broker_id) รองรับหลาย broker connect พร้อมกันจริง แต่ละตัว enable/disable อิสระต่อกัน เพิ่ม `broker_db_to_config()`, `start_mqtt_broker()`, `stop_mqtt_broker()`, `get_primary_broker_id()` (ใน database.py), `start_all_enabled_brokers()` (แยก try/except ต่อ broker — ตัวหนึ่ง fail ไม่กระทบตัวอื่น) `get_mqtt_client()` เปลี่ยน signature เป็นรับ `broker_id: int | None` (None = primary) `publish_qr_scan()` เปลี่ยนไป publish เข้า broker ที่ `is_primary=1` แทน legacy `_client` (device-aware routing เป็น scope รอบถัดไป) ลบ `load_mqtt_config()`/`save_mqtt_config()` (file-based)
- `src/core/config.py`: ลบ `main_config_path()` (ไม่ใช้ config.json อีกต่อไป)
- `src/features/qr/registry.py`: `load_integrations()`/`save_integrations()` เปลี่ยนไปอ่าน/เขียน `device_integrations` ผ่าน `core.database` แทน `qr_integrations.json` — คง signature เดิม (dict keyed by type) ไม่กระทบ caller ใน `server.py`
- `src/server.py`: `_init_db()` ตอน boot เปลี่ยนเป็น version check — ถ้า schema ไม่ทันสมัย log `[FATAL]` พร้อมบอกให้รัน `vas db migrate` แล้วปฏิเสธ start (fail loud) เปลี่ยน auto-start MQTT ตอน boot จาก single-config เป็น `start_all_enabled_brokers()` แก้ legacy `/api/mqtt/config`, `/api/mqtt/test`, `/api/mqtt/disconnect` และ broker CRUD API (`update`/`delete`/`disconnect`/`test`) ให้ทำงานกับ broker ที่ระบุเท่านั้น (ไม่ทำ global `stop_mqtt()` ตัดทุก broker เหมือนเดิมที่เป็นผลข้างเคียงจาก singleton) sync `MqttConfig.topic` เข้า `mqtt_broker_topics` เพราะ `mqtt_brokers` ไม่มี column `topic` โดยตรง
- `src/cli.py`: เพิ่มคำสั่ง `vas db migrate` (เรียก `run_migrations()` ตรงๆ, dry-run แสดง schema version ปัจจุบัน/ล่าสุดโดยไม่เขียนจริง) `vas install` เรียก migration ต่อท้ายหลัง component อื่นติดตั้งเสร็จ `vas mqtt status/config/test` เปลี่ยนไปอ่าน/เขียน primary broker ใน DB แทน `config.json`
- `src/services/updater.py`: ทั้ง `SelfUpdater.update()` (CLI `vas update`) และ `start_web_update()` (web update) เรียก `run_migrations()` หลัง `shutil.copytree` เสร็จ เพื่อให้ schema ทันสมัยหลังอัปเดตโดยไม่ลบข้อมูลเดิม
- Breaking/known gap ที่ยอมรับตามสโคป: `publish_qr_scan()` ยัง publish ที่ primary broker เท่านั้น (ไม่ device-aware) จนกว่าจะถึงรอบถัดไปตาม TODO `webhook`/`pipe` integration type เก็บ schema ได้แต่ยังไม่มี backend publish logic จริง (ของเดิม ไม่ใช่ regression) `mqtt_broker_form.html` ส่ง `payload_mode: "json"` (ไม่ตรงกับ `PAYLOAD_MODES`) เป็นบั๊กเดิมที่ปล่อยไว้แก้พร้อม UI wiring รอบถัดไปตามที่ระบุใน spec ไม่ใช่ regression จากงานนี้

### เพิ่ม dev-mode toggle `VAS_DEV_FAKE_INSTALLED` — ทดสอบ UI โดยไม่ต้องมี package/systemd จริง
- เพิ่ม `dev_fake_installed()` ใน `src/system/utils.py` — อ่าน env var `VAS_DEV_FAKE_INSTALLED=1` (ค่า `1`/`true`/`yes`)
- เมื่อเปิดใช้: `system/status.py` (`_check_tool`, `collect_remote_access_status`, `collect_openssh_status`, `collect_vpn_status`) และ `features/packages/settings.py` (`_which_check`, `_file_check`, `_python_import_check`) จะรายงานว่าทุก package/service "ติดตั้งแล้วและทำงานอยู่" โดยจำลองค่า version/id/service state แทนการเรียก `shutil.which`/`systemctl`/binary จริง
- `server.py` (`nav_status_api`) และ `features/remote/anydesk.py` (`service_action`, `set_unattended_password`) รองรับ flag เดียวกัน — ปุ่ม start/stop/restart และตั้งรหัสผ่าน Unattended Access ในหน้า AnyDesk จะจำลองผลสำเร็จโดยไม่รันคำสั่งจริง (ไม่บันทึก/ส่งรหัสผ่านที่ใดเลย)
- เปิดใช้ค่านี้อัตโนมัติใน `dev.bat` (`set VAS_DEV_FAKE_INSTALLED=1`) เพื่อให้ sidebar/หน้า AnyDesk, WireGuard, โปรแกรมเพิ่มเติม แสดงสถานะ "ติดตั้งแล้ว" ทันทีบนเครื่อง dev (เช่น Windows) ที่ไม่มี apt package หรือ systemd จริง — **ห้ามตั้งค่านี้บน production** (systemd service ที่รันจริงไม่ได้ set env var นี้)

### FIX apps.html (โปรแกรมเพิ่มเติม) — หน้าค้าง "กำลังตรวจสอบสถานะ..." เมื่อเข้าจาก SPA navigate
- สาเหตุ: `loadPackages()` และ `setTab("software")` ถูกเรียกใน `document.addEventListener("DOMContentLoaded", ...)` แต่ `DOMContentLoaded` fire แค่ครั้งเดียวตอนโหลดหน้าเว็บจริง — เมื่อ SPA router (`base.html`) swap `#spa-content-wrap` แล้ว `execScripts()` re-run สคริปต์ event นี้จะไม่ fire อีก ทำให้ `loadPackages()` ไม่ถูกเรียก และ spinner "กำลังตรวจสอบสถานะ..." ค้างตลอดไปจนกว่าจะ refresh (hard reload)
- แก้ไข: เปลี่ยนจาก `document.addEventListener("DOMContentLoaded", ...)` เป็นเรียก `setTab("software")` และ `loadPackages()` ทันที (immediate call) — รูปแบบเดียวกับที่เคยแก้ไว้แล้วใน `settings.html` (เทมเพลตเดิมก่อนเปลี่ยนชื่อเป็น "โปรแกรมเพิ่มเติม") แต่ตกหล่นตอนสร้าง `apps.html` ใหม่
- ขอบเขต: แก้เฉพาะ `src/web/templates/apps.html` (ส่วน `extra_scripts`) ไม่กระทบ SPA router ใน `base.html` หรือหน้าอื่น

### Re-design หน้า System Logs (`/logs`) + เพิ่มฟีเจอร์ที่ขาด
- ออกแบบใหม่ `src/web/templates/logs.html` ตาม design system เดิมของ VAS (page header + card pattern, `zone` badge, accordion/list convention จาก `INSTRUCTIONS.md`)
- รายการ snapshot: แสดงเวลาแบบ relative + absolute (แปลงจาก id `YYYYMMDDTHHMMSSZ`) และขนาดไฟล์แบบ human-readable (`fmtBytes`) แทนตัวเลข bytes ดิบ พร้อม badge จำนวน snapshot ทั้งหมด
- Log viewer: เพิ่มเลขบรรทัด, ไฮไลต์สีตามระดับ (error/critical แดง, warning เหลือง, `## header` เป็นหัวข้อ section), ช่องค้นหาในเนื้อหาพร้อมไฮไลต์คำที่ตรง, ปุ่ม Copy และ Download (.log) แบบ client-side
- เพิ่มฟีเจอร์ที่ขาด — **ลบ snapshot**: เพิ่ม `delete_system_snapshot()` ใน `src/system/audit.py` และ route `DELETE /api/logs/system/<snapshot_id>` ใน `src/server.py` (บันทึก audit event `snapshot_deleted`) พร้อม confirm modal ตาม convention ของโปรเจกต์ (`showConfirm`, ห้ามใช้ `window.confirm`)
- เพิ่มการ์ด "เหตุการณ์ล่าสุด" (Audit Trail) ต่อท้ายหน้า — ใช้ endpoint `/api/database/audit_log` ที่มีอยู่แล้ว เพื่อให้ตรงกับคำอธิบายเมนู sidebar ("Log และ audit เหตุการณ์") ที่เดิมหน้านี้ยังไม่มีส่วนนี้ พร้อมลิงก์ "ดูทั้งหมด" ไปหน้า Database
- Empty/loading state ใหม่ตาม convention (`lucide:inbox`, `.spin`) และปุ่ม header เพิ่มไอคอนให้ตรงกับหน้าอื่น
- ตรวจสอบด้วย `ruff` + `mypy --strict` (เทียบ error ก่อน/หลัง — ไม่มี error ใหม่นอกจาก pattern เดิมที่มีอยู่แล้วในทุก route ของไฟล์) เนื่องจาก mount ของ sandbox sync ไฟล์จริงไม่ตรงกับต้นทาง จึงตรวจสอบผ่านสำเนาที่ patch จาก git HEAD แทน
- พบว่า test suite เดิม (`tests/test_audit_log.py` และอีก 7 ไฟล์) collection fail อยู่ก่อนแล้วจาก import path ที่ไม่ตรงกับโครงสร้าง `src/` ปัจจุบัน (เช่น `import audit_log` ควรเป็น `system.audit`) — ไม่เกี่ยวกับการแก้ไขครั้งนี้ แนะนำให้ทำ ticket แยกเพื่ออัปเดต import path ของ test suite

### ลบหน้า Dashboard — ให้ Monitor เป็นหน้าแรกแทน
- ลบ `src/web/templates/dashboard.html` และ nav link "แดชบอร์ด" ใน `base.html` ออกทั้งหมด
- route `/` (เดิมชื่อฟังก์ชัน `dashboard`) เปลี่ยนไปเรนเดอร์ `monitor.html` แทน (rename เป็น `monitor_page`) — Monitor กลายเป็นหน้าแรกของระบบ
- route เดิม `/monitor` เปลี่ยนเป็น redirect ไปที่ `/` เพื่อไม่ให้ลิงก์/bookmark เดิมพัง
- อัปเดตทุกจุดที่ `url_for("dashboard")` (setup/login/login_post) ให้ชี้ไปที่ `url_for("monitor_page")` แทน
- ลบ import ที่ไม่ได้ใช้แล้วใน `src/server.py` (`collect_status`, `collect_remote_access_status`, `collect_openssh_status`, `collect_web_server_status`) เนื่องจากถูกใช้เฉพาะใน route dashboard เดิม
- อัปเดต `tests/test_server.py`: แทนที่ `test_dashboard_route_renders_status_without_command_preview` ด้วย `test_home_route_renders_monitor_page` และเพิ่ม `test_monitor_route_redirects_to_home`, ลบ helper `_patched_status_collectors` และ import ที่ไม่ใช้แล้ว
- เนื่องจาก sandbox mount sync ไฟล์จริงไม่ตรงกับต้นทาง (ปัญหาเดิมที่บันทึกไว้ด้านบน) จึงตรวจสอบผ่านสำเนาที่ patch จาก git HEAD แทน: `ruff check` และ `mypy --strict` เทียบ error ก่อน/หลัง — ไม่มี error ใหม่ (54 errors เท่าเดิมทั้งคู่ เป็น debt เดิมของไฟล์ ไม่เกี่ยวกับการแก้ไขนี้)
- รัน `pytest tests/test_server.py` พบว่า 5 tests fail ด้วย 302 redirect ไป `/setup` หรือ `/login` — ยืนยันแล้วว่าเป็นปัญหาเดิมของ sandbox (ไม่มี test DB/session fixture ให้ผ่าน auth gate) เกิดขึ้นเหมือนกันทั้งก่อนและหลังแก้ไข (รวมถึง test เดิมที่ถูกแทนที่) ไม่ใช่จากการเปลี่ยนแปลงนี้ — ตรวจ logic จริงด้วยการ patch `is_first_run`/`get_user_by_id` และตั้ง session ปลอมแทน ยืนยันว่า `test_home_route_renders_monitor_page` และ `test_monitor_route_redirects_to_home` ผ่านตามที่คาดไว้

### เพิ่มหน้าใหม่ + เมนู Sidebar สำหรับจัดการ AnyDesk
- เพิ่ม route `GET /anydesk` (`anydesk_page`) ใน `src/server.py` — เรนเดอร์ `anydesk.html` ด้วยข้อมูลจาก `collect_remote_access_status()` (มีอยู่แล้วใน `system/status.py`)
- สร้าง `src/features/remote/anydesk.py` (ใหม่) — `service_action()` สำหรับ `systemctl start/stop/restart/enable/disable anydesk` และ `set_unattended_password()` สำหรับตั้งรหัสผ่าน Unattended Access ผ่าน `anydesk --set-password` ทาง stdin โดยตั้งใจไม่ใช้ `CommandRunner` เพื่อไม่ให้รหัสผ่านหลุดไปอยู่ใน log
- เพิ่ม API 3 endpoint ใน `src/server.py`: `GET /api/anydesk/status`, `POST /api/anydesk/action`, `POST /api/anydesk/password` (log audit event แต่ไม่บันทึกค่ารหัสผ่าน)
- สร้าง template ใหม่ `src/web/templates/anydesk.html` ตาม page-structure convention ของ VAS (page header + tab nav "สถานะ" / "Unattended Access") พร้อม banner แจ้งเตือนและลิงก์ไปหน้า "โปรแกรมเพิ่มเติม" เมื่อยังไม่ได้ติดตั้ง AnyDesk
- เพิ่ม `nav_link('anydesk_page', ...)` ในหมวด "เครือข่าย" ของ sidebar (`base.html`) ใช้ `data-nav-pkg="anydesk"` — ซ่อน/แสดงอัตโนมัติผ่าน `/api/nav/status` ที่ return field `anydesk` อยู่แล้ว ไม่ต้องแก้ JS เพิ่ม
- ตรวจสอบ `features/remote/anydesk.py` ด้วย `py_compile` + `ruff` + `mypy --strict` ผ่านทั้งหมด (ไม่มี error ของโค้ดตัวเอง) และตรวจ syntax template ทั้งหมดผ่าน Jinja2 parser ผ่าน — ส่วน `server.py` เจอปัญหา sandbox mount sync ช้า/ค้าง (ปัญหาเดียวกับที่บันทึกไว้ในหัวข้อ "Re-design หน้า System Logs" ข้างต้น) จึงตรวจ syntax ด้วยการอ่านไฟล์เต็มแทน และยืนยันตำแหน่ง route/endpoint ใหม่ด้วย grep บนไฟล์จริง

## [2026-07-01]

### ย้ายเมนู "คำสั่ง CLI" จาก Sidebar ไปเป็นไอคอนใน Navigation bar
- ลบ `nav_link('commands', ...)` ออกจากหมวด "ระบบ" ใน sidebar (`base.html`)
- เพิ่มปุ่มไอคอน `lucide:circle-alert` (ตกใจ/แจ้งเตือน) ไว้ใน header ข้างๆ ปุ่ม account (user dropdown) ลิงก์ไปที่ `url_for('commands')`
- ปุ่มใช้ class `nav-link` เพื่อให้ SPA router intercept และสลับหน้าแบบ partial ได้เหมือนลิงก์อื่นในระบบ

### เปลี่ยนชื่อ Settings → โปรแกรมเพิ่มเติม + Download Source tab
- เปลี่ยนชื่อเมนู "ตั้งค่า" → "โปรแกรมเพิ่มเติม" พร้อม icon `package-plus`
- เปลี่ยน route `/settings` → `/apps` (endpoint `apps_page`); `/settings` redirect 301 → `/apps`
- สร้าง template ใหม่ `apps.html` (ลบ `settings.html` ออกจาก route หลัก)
- ลบ tab Hardware, General, Network, Security ออก — เหลือเฉพาะ Software
- เพิ่ม tab "แหล่งดาวน์โหลด" (mock-up): เลือกระหว่าง VAS Default กับ On-Premise Server พร้อม URL input / API token / test connection
- เพิ่ม per-package override table (mock-up, disabled)
- ลบ `renderHardware` และ `hwRowHtml` ออกจาก JS ของ apps.html
- เพิ่ม `docs/download-source.md` — spec สำหรับ On-Premise Package API, data model, และแผนการ implement



### เพิ่มหน้าอัปเดตระบบ (`/update`) พร้อม Download Progress Bar
- เพิ่มหน้า `/update` — ตรวจสอบ GitHub releases และแสดงเวอร์ชั่นปัจจุบัน vs ล่าสุด
- เพิ่ม API `GET /api/update/check` — เรียก GitHub API (`releases/latest`) เปรียบเทียบกับ `APP_VERSION`
- เพิ่ม API `GET /api/update/stream` — SSE stream ส่ง progress events ระหว่าง download + extract + install wrappers (รองรับ `Content-Length` → คำนวณ % จริง)
- เพิ่ม API `POST /api/server/restart` — restart via PM2 หรือ systemd (ใช้ thread delay 1.5s)
- `base.html` — footer (`VAS v0.1 · online`) เปลี่ยนเป็น `<a class="nav-link">` ชี้ไป `/update`; SPA router intercept ได้ปกติ
- UI: progress bar 6px + step indicators (ตรวจสอบ / ดาวน์โหลด / แตกไฟล์ / ติดตั้ง / เสร็จสิ้น), terminal log box, done bar พร้อมปุ่ม restart



### เพิ่ม --branch parameter ใน install.sh และ vas update
- `scripts/install.sh` รับ `--branch <name>` (default: `main`) และใช้ `${BRANCH}` แทน hardcode `/refs/heads/main`
- `src/services/updater.py` — `SelfUpdater.__init__()` รับ `branch: str = "main"` และ `archive_url()` ใช้ `self.branch` เมื่อ version เป็น `latest`
- `src/cli.py` — `update` subparser เพิ่ม `--branch` argument และ pass ไปยัง `SelfUpdater`
- พฤติกรรมเดิมไม่เปลี่ยน: ไม่ระบุ `--branch` → ดึงจาก `main` เหมือนเดิม; ระบุ `--version <tag>` → ใช้ Git tag (branch ถูก ignore)
- แก้ไข pre-existing bug: `src/services/updater.py` ถูก truncate ที่ `_can_import_flask()` — append บรรทัดที่หายไป

### FIX display.html — Config Files tab เปิดดูไฟล์ไม่ได้
- ลบ `.config-pre` dark theme CSS (ไม่ตรง design system)
- เปลี่ยน `<pre>` เป็น `<textarea readonly>` + `div.p-4` wrapper ตาม INSTRUCTIONS.md (Accordion Card Convention)
- แก้ JS: เพิ่ม `window.toggleConfig()` ที่ตรงกับ `onclick` ใน HTML, และ `window.loadConfig()` ที่ใช้ `.value =` แทน `.textContent =`
- แก้ padding toolbar จาก `py-4` → `py-3` ให้ตรง standard

### FIX SPA — หน้าค้าง skeleton หลัง navigate (DOMContentLoaded ไม่ fire ซ้ำ)
- **Root cause**: `monitor.html`, `settings.html`, `display.html`, `database.html`, `qr.html` ใช้ `document.addEventListener("DOMContentLoaded", ...)` เพื่อ init — event นี้ fire เพียงครั้งเดียวตอน full page load; หลัง SPA swap `execScripts()` re-run script แต่ callback ไม่ถูกเรียก → หน้าค้าง skeleton / loading ตลอด ต้อง refresh
- แก้: เปลี่ยนทุกไฟล์เป็น immediate call ตรงๆ ท้าย IIFE (DOM พร้อมแล้วตอน `execScripts()` รัน)

### FIX SPA Router — extra_scripts ไม่ถูก execute หลัง navigate
- **Root cause**: `{% block extra_scripts %}` อยู่นอก `<div id="spa-content">` ใน `base_partial.html` → SPA router swap เฉพาะ content block, scripts ของแต่ละหน้าไม่รัน → ไม่มี event listeners → คลิก element ไม่ได้ ต้อง reload เอง
- แก้: ย้าย `{% block extra_scripts %}` เข้าไปใน `#spa-content` ใน `base_partial.html` → `execScripts()` จับ scripts ได้และ execute หลัง swap
- เพิ่ม hard fallback ใน `navigate()`: ถ้า `#spa-content` ไม่พบใน partial response → `location.href = url` แทน silent fail



### Settings Software — Sub-item: PM2 ฝังใต้ Node.js
- PM2 ไม่แสดงเป็น row แยกอีกต่อไป — render เป็น sub-row อยู่ภายใต้ Node.js พร้อม connector line สีม่วงอ่อน
- เมื่อ Node.js ยังไม่ได้ติดตั้ง → ปุ่ม "ติดตั้ง" เปิด sub-select modal ให้เลือกว่าจะลง Node.js อย่างเดียวหรือพร้อม PM2
- เมื่อ Node.js ติดตั้งแล้ว → PM2 sub-row แสดงปุ่ม Install ของตัวเอง (ถ้ายังไม่ได้ลง)
- `renderPackages` ข้ามการ render child IDs เป็น top-level row
- `filterPackages` อัปเดตให้ sub-row ค้นหาได้ — ถ้า sub-row match แต่ parent ไม่ match ก็ยังแสดง parent
- `streamInstall` รับ optional `onComplete` callback เพื่อรองรับ sequential install
- เพิ่ม `installSequential(pkgIds)` — ติดตั้งทีละ package ใน modal เดียวกัน แสดง separator label แต่ละ package



### คืน SPA Router ใน base.html (sidebar ไม่ Re-Render)
- เพิ่ม `id="spa-content-wrap"` ใน wrapper div ภายใน `#spa-main` เพื่อเป็น swap target
- เพิ่ม SPA router script ใน `base.html` — intercept `.nav-link` clicks, fetch partial ด้วย `X-VAS-Partial: 1`, swap เฉพาะ `#spa-content-wrap` (sidebar/header ไม่ถูก re-render)
- FIX 1: `e.isTrusted` check — ปฏิเสธ synthetic events จาก iconify-icon
- FIX 2: `e.stopPropagation()` — ป้องกัน listener อื่น trigger ซ้ำ
- FIX 3: `AbortController` — cancel fetch ที่ค้างเมื่อ navigate ใหม่
- FIX 4: `window.__vasCleanup = window.__vasCleanup || []` — ป้องกัน SPA init ลบ cleanup functions ที่ page scripts ลงทะเบียนไว้ก่อน
- `runCleanup()` เรียกก่อน navigate ทุกครั้ง, `execScripts()` re-execute scripts ใน content ใหม่
- `updateNavActive()` toggle Tailwind classes บน `.nav-link` ตาม current pathname
- Handle browser back/forward ด้วย `popstate`

### แก้ evdev ติดตั้งบน Windows ไม่ได้
- เพิ่ม `; sys_platform == 'linux'` marker ใน `pyproject.toml` — evdev ถูกติดตั้งเฉพาะ Linux

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
