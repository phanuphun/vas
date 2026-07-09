# Changelog

## [2026-07-09]

### หน้า "คีออส" แท็บ "เปิดแอปอัตโนมัติ" — เพิ่ม toggle bar ปิดฟีเจอร์เบราว์เซอร์ที่ไม่ต้องการให้ user แตะได้ใน kiosk mode
- **ที่มา**: ผู้ใช้แจ้งว่าเข้าหน้าเว็บใน kiosk mode แล้วฟังก์ชันแปลภาษาอัตโนมัติของ Chromium ยังเด้งขึ้นมาอยู่ ทั้งที่ script เดิม hardcode แค่ `--noerrdialogs --disable-infobars` เท่านั้น ไม่มีทางปิดฟีเจอร์อื่น (แปลภาษา, เสนอบันทึกรหัสผ่าน, suggestion service ฯลฯ) จากหน้าเว็บได้เลย ต้องแก้ script เองเท่านั้น
- เพิ่ม `CHROME_KIOSK_FLAG_DEFS` (`src/features/kiosk/manager.py`) — รายการ chromium flag 7 ตัวที่ toggle ได้ (`--no-first-run`, `--disable-translate`, `--disable-infobars`, `--noerrdialogs`, `--disable-suggestions-service`, `--disable-save-password-bubble`, `--start-maximized`) แต่ละตัวมี label/desc ภาษาไทยกำกับ ค่า default ทุกตัว = เปิด (True) เพราะ kiosk mode ควรกัน browser action ทุกชนิดโดยปริยาย — เพิ่ม `normalize_chrome_flags()` รวม payload จาก JSON กับ default, เพิ่มฟิลด์ `chrome_flags` เข้า `KioskAutostartStatus`
- `build_kiosk_launch_script()` รับพารามิเตอร์ `chrome_flags` เพิ่ม ประกอบ flag ที่เปิดอยู่เข้ากับ `--kiosk` ต่อท้ายด้วย URL — `_parse_kiosk_flags()` (ใหม่) อ่านบรรทัด `chromium ...` ของ script ที่มีอยู่จริงบนดิสก์กลับมาเป็น dict ให้หน้าเว็บ sync สถานะ toggle ตรงกับที่เคยตั้งไว้จริง ไม่ใช่ default เสมอ
- `server.py`: `/api/kiosk/autostart` (POST) รับ `chrome_flags` จาก payload ผ่าน `normalize_chrome_flags()` ก่อนส่งต่อ `KioskManager.write_autostart()`, บันทึกลง audit/config log ด้วย — `_kiosk_page_context()` ส่ง `chrome_flag_defs`, `autostart.chrome_flags`, และ `autostart_script_preview` (เรียก `build_kiosk_launch_script()` จริงแทนการต่อ string มือ) เข้า template
- `kiosk.html`: เพิ่มการ์ด toggle switch 7 อันในแท็บ "เปิดแอปอัตโนมัติ" พร้อม label/desc ต่อรายการ, ผูก `updateScriptPreview()` เข้ากับทุก toggle + URL/restart input ให้กล่อง "ตัวอย่าง script ที่จะสร้าง" อัปเดตสด ไม่ต้อง save ก่อนถึงจะเห็น — Config Files tab (`openbox_autostart_card`, `kiosk_launch_script_card`) เปลี่ยนจาก mock string ที่เขียนมือมาใช้ `autostart_script_preview` ตัวเดียวกัน กันเนื้อหาสองที่ไม่ตรงกัน
- **ตรวจสอบ**: เจอ mount-truncation bug ซ้ำแบบเดียวกับ entry `[2026-07-05]` — ไฟล์ที่แก้ผ่าน Edit tool (`src/features/kiosk/manager.py`, `src/server.py`) ถูกตัดท้ายไฟล์ขาดหายหลัง sync ไป bash mount (ยืนยันด้วย `git diff -b` เทียบกับ `git show HEAD:<path>` เจอ `\ No newline at end of file` กลางฟังก์ชัน คนละจุดกับที่แก้เลย) — `src/web/templates/kiosk.html` ไม่โดน (diff สะอาด) — แก้โดย reconstruct เนื้อหาที่ถูกต้องจาก `git show HEAD:<path>` แล้ว apply edit เดิมซ้ำ (สำหรับ `server.py`) หรือพิมพ์เนื้อหาที่ยืนยันถูกต้องจาก Read tool ใหม่ทั้งไฟล์ (สำหรับ `manager.py`) เขียนลง path ใหม่ผ่าน Write tool (ยืนยันว่าไฟล์ใหม่ที่ไม่เคยมีมาก่อนจะ sync ครบเสมอ ต่างจากการ edit ไฟล์เดิมซ้ำ) แล้ว `mv` ทับ path จริงผ่าน bash — ตรวจสอบสุดท้าย: `python3 -m py_compile` sweep ทุกไฟล์ `.py` ใน `src/` ผ่านหมด, `jinja2.Environment().parse()` ผ่านสำหรับ `kiosk.html`, `node --check` ผ่านสำหรับ JS block ใน `kiosk.html` (แทนที่ Jinja placeholder ด้วยค่า dummy), `git diff -b` ของทั้ง 3 ไฟล์จบแบบสมบูรณ์ไม่มี truncation marker แล้ว — ยังไม่ได้ทดสอบ end-to-end บนเครื่อง kiosk จริง (ต้อง deploy แล้วเปิดหน้าเว็บเช็คว่า toggle ทำงาน + เปิด chromium จริงแล้วแปลภาษา/popup หายไปตามที่ตั้งค่า)

## [2026-07-08]

### `vas update` (ทั้งโหมดปกติและโหมด Dev) ดึงโค้ดจาก repo ผิด — แก้ `DEFAULT_REPO` ให้ตรงกับ repo จริงที่ push งาน
- **ที่มา**: `src/services/updater.py` hardcode `DEFAULT_REPO = "phanuphun/vending-auto-setup"` มาตั้งแต่แรก แต่ repo ที่ผู้ใช้พัฒนา/push โค้ดจริงคือ `phanuphun/vas` (คนละชื่อ) — ผลคือกด "อัปเดตระบบ" หรือโหมด Dev "ดึง Source ล่าสุด & ติดตั้ง" ไปเรื่อยๆ ก็ไม่มีวันเห็นโค้ดที่เพิ่งแก้/push ขึ้นไปเลย เพราะ `archive_url()` ไปดึง tarball จาก `github.com/phanuphun/vending-auto-setup/archive/refs/heads/<branch>.tar.gz` ซึ่งเป็นคนละ repo กับที่มีการ commit จริง (ยืนยันจาก `git remote -v` ของโปรเจกต์ = `github.com/phanuphun/vas.git` และหน้า GitHub repo `phanuphun/vas` ไม่มี Releases เลยด้วย ทำให้โหมดปกติที่เช็คผ่าน `check_latest_release()` ก็ใช้งานไม่ได้ตั้งแต่ต้นเช่นกัน)
- แก้ `DEFAULT_REPO` เป็น `"phanuphun/vas"` ใน `updater.py` — ทุกจุดที่ใช้ (`SelfUpdater`, `check_latest_release()`, `start_web_update()`, `cli.py --repo` default) อ้างอิงค่าคงที่นี้ที่เดียว แก้จุดเดียวจบ
- `update.html` เดิม hardcode ลิงก์ `https://github.com/phanuphun/vending-auto-setup` และชื่อ repo ในการ์ด "ข้อมูลระบบ" แยกจาก `DEFAULT_REPO` อีกที่หนึ่ง (จุดเดิมที่เคยเพี้ยนมาแล้วในอดีต — ดู entry ก่อนหน้าเรื่องไฟล์ถูกตัดท้าย) — เปลี่ยนให้ route `/update` (`server.py`) ส่ง `update_repo`/`update_install_dir` จาก `DEFAULT_REPO`/`DEFAULT_INSTALL_DIR` เข้า template แทน ป้องกัน repo name เพี้ยนซ้ำแบบนี้อีกในอนาคต (ไม่มีทาง hardcode สองที่ไม่ตรงกันได้อีกเพราะอ่านจาก source เดียวกัน)
- ตรวจสอบ: grep หา `"phanuphun"` ทั้ง `src/` ยืนยันไม่มี hardcode ชื่อ repo เหลือที่อื่นนอกจาก `DEFAULT_REPO` — อ่านไฟล์ที่แก้ทั้ง 3 (`updater.py`, `server.py`, `update.html`) กลับผ่าน Read tool เทียบทีละบรรทัดแล้ว ยังไม่ได้ลอง `vas update` จริงบนเครื่อง vending หลัง deploy รอบนี้ (ต้อง push + ให้ผู้ใช้กดทดสอบอีกครั้ง)

### จอ "Monitor Setting" — Touch rotation toggle ไม่เคย hydrate จากค่าจริงบนเครื่อง ทำให้กด Apply ซ้ำทับค่าที่ถูกต้องอยู่แล้วแบบเงียบๆ
- **ที่มา**: `display.html` เดิม initialize `selectedTouchRotation`/`decoupleTouchRotation` เป็นค่า default เสมอทุกครั้งที่โหลดหน้า ไม่เคยอ่านค่า touch rotation จริงจากเครื่อง (ต่างจาก screen rotation ที่มี `current_rotation`/`device_rotations` hydrate อยู่แล้ว) — เวลาเปิดหน้าใหม่/refresh แล้วกด Apply โดยไม่ได้ตั้งใจแก้ touch เลย จะทับค่า touch rotation ที่ตั้งไว้ถูกต้องอยู่แล้ว (เช่น "left") ด้วยค่า default "normal" ไปเงียบๆ (เคสจริง: เครื่อง `hapymed-sterile-00` จอหมุน Left touch ตั้งไว้ Left ตรงกันอยู่แล้ว พอกด Apply ซ้ำหลัง deploy โค้ด log เพิ่ม กลับเปลี่ยน touch เป็น Normal ทำให้แตะจอไม่ตรงจุด)
- เพิ่ม `parse_touch_rotation()` (`server.py`) อ่านค่า "Coordinate Transformation Matrix" จริงจาก `xinput list-props <device>` แล้วเทียบย้อนกลับกับ `ROTATION_MATRICES` เพื่อรู้ชื่อ rotation ปัจจุบัน — เพิ่ม `touch_rotations` เข้า `DisplayDevices`, คำนวณใน `collect_display_devices()` ต่อ touch device ที่ detect เจอ (รองรับทั้ง path ปกติและ path ที่ fallback ผ่าน `runuser`) — ส่ง `current_touch_rotation`/`device_touch_rotations` เข้า route `/display` และ `/api/display/devices`
- `display.html`: hydrate `selectedTouchRotation` จาก `current_touch_rotation` ที่ server render มาให้ (แทนที่จะ mirror ตาม screen rotation เสมอ), เพิ่ม `applyTouchRotationForSelectedDevice()` เปิด toggle "แยกทิศทาง Touch จากจอ" อัตโนมัติเฉพาะกรณีที่ touch จริงต่างจากจอเท่านั้น ผูกกับ event `touchSelect.change` และหลังกด Refresh — cache `deviceTouchRotations` หลัง Apply/Reset สำเร็จเพื่อไม่ให้ค่าเพี้ยนถ้ากด Apply ซ้ำในหน้าเดิมโดยไม่ reload
- เพิ่ม log เข้า `display-session.sh` (`display.py`: `build_display_session_script`) เขียนไปที่ `display-session.log` ข้างสคริปต์ — เดิมสคริปต์นี้รันแบบ background จาก `.xprofile` ตอน login แล้ว fail แบบเงียบๆ ไม่มีร่องรอย debug เลย
- ตรวจสอบ: ทดสอบ `parse_touch_rotation()` แยกด้วย matrix ตัวอย่างจริงที่ดึงมาจากเครื่อง (`normal`/`left`/`right`) ได้ผลตรงหมด — ทดสอบ syntax `display.py`/`server.py` ผ่านสำเนาใน sandbox (`py_compile`) เพราะ bash mount ของไฟล์ที่เพิ่งแก้ในเซสชันนี้ค้าง/ไม่ sync ทันที (ปัญหาเดิมของ session นี้) — ทดสอบ JS ที่แก้ใน `display.html` ผ่าน `node --check` บนสำเนาที่ประกอบขึ้นใหม่ (แทนที่ Jinja placeholder ด้วยค่าตัวอย่าง) ผ่านหมด — ยังไม่ได้ทดสอบ end-to-end บนเครื่องจริงหลังแก้ repo mismatch (ต้องรอ deploy รอบใหม่)

### ตามด้วย: toggle "แยกทิศทาง Touch จากจอ" ยังปิดเองทุกครั้งที่ refresh แม้ตั้งค่าถูกต้องอยู่แล้ว
- **ที่มา**: เงื่อนไขเดิม (`applyTouchRotationForSelectedDevice()` ใน `display.html`) เปิด toggle ก็ต่อเมื่อค่า touch จริงที่ detect ได้ **ต่างจาก** ค่า rotate ของจอเท่านั้น (`shouldDecouple = !!known && known !== selectedRotation`) — เคสที่ touch ตั้งไว้ตรงกับจอพอดี (เช่นทั้งคู่เป็น "left") จะโดนตีความว่า "ไม่ได้ decouple" แล้วปิด toggle ให้เองทุกครั้ง ทั้งที่ผู้ใช้ตั้งใจเปิด toggle + เลือกทิศทาง + Apply ไปแล้วจริง ดูเหมือนการตั้งค่าหายไปทุกครั้งที่ refresh
- เปลี่ยนเงื่อนไขเป็น `shouldDecouple = !!known` — เปิด toggle ทุกครั้งที่ detect ค่า touch จริงได้สำเร็จ ไม่สนว่าค่านั้นจะตรงกับจอหรือไม่ ให้ toggle สะท้อนสถานะจริงของเครื่องเสมอ ไม่ขึ้นอยู่กับว่าค่าบังเอิญตรงกับจอหรือไม่
- หมายเหตุ: toggle "Persist touch in Xorg" (คนละอันกับ "แยกทิศทาง") ยังคงเป็น action flag ล้วนๆ ไม่ hydrate จากสถานะจริง (เจตนา — ใช้บอกว่า "จะเขียน Xorg config รอบนี้ไหม" ไม่ใช่ "เคยเขียนไว้หรือยัง" ซึ่งมีสถานะแยกแสดงอยู่แล้วในส่วน config file ของหน้าเดียวกัน) — ถ้าผู้ใช้อยากให้ toggle นี้ hydrate ด้วยต้องแก้เพิ่มเป็นคนละงาน

## [2026-07-05]

### หน้า "ซอฟต์แวร์ระบบ" — ปิดแท็บ "แหล่งดาวน์โหลด" เป็น "เร็วๆ นี้", หน้า "คีออส" — ปรับกล่อง caution ให้ตรง convention ของ Named Pipe
- **แท็บ "แหล่งดาวน์โหลด" (`apps.html`)**: ยังไม่พร้อมใช้งานจริง (เนื้อหาเป็น mock-up) แต่ก่อนหน้านี้กดเข้าไปได้ปกติ — ปิดตาม convention เดียวกับ MQTT "Message Monitor" (ดู INSTRUCTIONS.md § "Disabled (coming soon) tab-btn"): เพิ่ม `disabled aria-disabled="true" title="เร็วๆ นี้"`, เปลี่ยน class เป็น `text-faint cursor-not-allowed opacity-60`, เพิ่ม badge `<span class="zone zone-mute">เร็วๆ นี้</span>` — แก้ `setTab()` ให้ query ด้วย `.tab-btn:not([disabled])` กันไม่ให้ full-class-rewrite ไปทับ style ของปุ่มที่ disabled แล้ว (บั๊กที่จะเกิดถ้าใช้ selector เดิม เพราะปุ่มนี้ไม่เคยเป็น active เลยจะโดน rewrite เป็น "inactive" ทุกครั้งที่สลับแท็บ ทำให้ hover state โผล่มาทับ opacity-60)
- **กล่อง caution สีเหลืองหน้า "คีออส" (`kiosk.html`)**: กล่อง "ยังไม่มี Broker" (ในการ์ด MQTT Heartbeat) และ "ยังตั้งค่าไม่ครบ" (autostart banner) ใช้ opacity/padding/มุมโค้งไม่ตรงกัน (`bg-caution/5` กับ `bg-caution/8`, `rounded-lg` กับ `rounded-xl`, `px-3 py-2` กับ `px-4 py-3`) และใช้ `iconify-icon` แทนที่จะเป็น raw SVG แบบหน้า Named Pipe — แก้ทั้ง 2 กล่องให้ตรงกับ convention ของหน้า Named Pipe (`pipe_tester.html` แท็บ "คำแนะนำ") เป๊ะ: `bg-caution/10 border border-caution/25 rounded-lg px-4 py-4`, ไอคอนเป็น raw `<svg style="color:#92660b;">`, ข้อความหลักใช้ `text-ink` (เอาสี caution ออกจากตัวอักษรทั้งกล่อง ให้เหลือแค่ที่ไอคอน)
- เพิ่ม section ใหม่ "Alert / Caution Box Convention" ใน `INSTRUCTIONS.md` (ก่อน "Accordion Card Convention") บันทึก convention นี้เป็นมาตรฐานบังคับสำหรับทุกหน้าที่มี caution/warning banner ต่อไป

### พบและแก้ไฟล์หลายไฟล์ที่ถูกตัดท้ายไฟล์ขาดหาย (truncated) อยู่ก่อนแล้วทั่วทั้ง repo — บล็อก syntax check และทำให้ `vas` server รันไม่ได้จริง
- **ที่มา**: ระหว่างตรวจ syntax หลังแก้งานข้างบน พบว่าไฟล์ที่แก้ (`apps.html`, `kiosk.html`, `INSTRUCTIONS.md`) ถูกเขียนกลับมาขาดท้ายไฟล์หลังผ่าน Edit tool (เนื้อหาคัตกลางบรรทัด/กลาง multi-byte UTF-8 character พอดี ไม่มี `{% endblock %}`/`</script>` ปิดท้าย) — ตรวจสอบเพิ่มเจอว่าไฟล์อื่นที่ไม่เกี่ยวกับงานนี้เลยก็ถูกตัดท้ายแบบเดียวกันมาก่อนหน้านี้แล้ว (เทียบ working tree กับ git index/`git show :<path>`): `src/server.py` (ขาด 2 บรรทัดสุดท้าย ทำให้ `python3 -m py_compile` ทั้งไฟล์ fail ตั้งแต่ module level — **แปลว่า service ตัวจริงสตาร์ทไม่ได้เลยก่อนหน้านี้**), `src/core/config.py`, `src/features/wireguard/manager.py`, `src/services/updater.py`, `src/web/templates/mqtt.html`, `mqtt_broker_detail.html`, `mqtt_broker_form.html`, `update.html`, และ `CHANGELOG.md` เอง (เขียน entry นี้ผ่าน Edit tool ครั้งแรกก็โดนตัดท้ายเช่นกัน ต้องเขียนซ้ำผ่าน bash โดยตรง)
- **วิธีแก้**: สำหรับทุกไฟล์ที่เจอ ตรวจก่อนว่า working tree เป็น byte-prefix ของ `git show :<path>` เป๊ะ (ไม่มีเนื้อหาอื่นเพี้ยนไปนอกจากส่วนที่ถูกตัด) แล้ว reconstruct เนื้อหาที่ถูกต้องจาก index snapshot (แปลง LF→CRLF ให้ตรงกับที่ working tree ทั้ง repo ใช้อยู่) เขียนทับกลับผ่าน bash โดยตรง (ไม่ผ่าน Edit/Write tool ซ้ำ เพราะสงสัยว่าเป็นจุดที่ทำให้ตัดท้ายไฟล์) — สำหรับไฟล์ที่กำลังแก้เนื้อหาจริงอยู่ (`apps.html`/`kiosk.html`/`INSTRUCTIONS.md`/`CHANGELOG.md` นี้) ใช้วิธี apply diff ที่ตั้งใจแก้ทับบน index snapshot ก่อน แล้วค่อยเขียนกลับ เพื่อไม่ให้เสียงานที่เพิ่งแก้ไป
- **ตรวจสอบ**: `python3 -m py_compile` sweep ทุกไฟล์ `.py` ใน repo (`src/`, `tests/`, `scripts/`) ผ่านหมดหลังแก้ — `jinja2.Environment().parse()` sweep ทุกไฟล์ `.html` ใน `src/web/templates/` ผ่านหมด (0 broken จากเดิมที่เจอ 4 ไฟล์ในรอบแรก) — `diff` เทียบทุกไฟล์ที่ restore กับ `git show :<path>` ตรงกัน 100% (ไม่มีการเสียเนื้อหาอื่นนอกจากส่วนที่ถูกตัดไปคืนมา) — **ยังไม่ทราบสาเหตุต้นตอ**ว่าอะไรทำให้การเขียนไฟล์ผ่าน mount นี้ถูกตัดท้าย (จุดตัดไม่ตรง byte length เดิมทุกครั้ง ไม่ใช่ตัดที่ boundary คงที่) แนะนำให้ผู้ใช้เช็ค sync/antivirus/OneDrive ที่อาจ intercept การเขียนไฟล์บน path นี้ และสุ่มตรวจไฟล์อื่นที่ไม่ได้อยู่ใน sweep นี้ (เช่นไฟล์นอก `src/`) ว่าไม่โดนตัดท้ายเช่นกัน

### Sidebar footer — เปลี่ยน "Version 0.1" hardcode ให้อิงตาม `APP_VERSION` เดียวกับหน้าอัปเดต
- **ที่มา**: footer แถบล่าง sidebar (`base.html`) เขียน "Version 0.1" เป็นข้อความคงที่ ไม่ตรงกับเวอร์ชั่นจริงที่หน้า "อัปเดตระบบ" แสดง (อ่านจาก `APP_VERSION`/`pyproject.toml` ตาม entry ก่อนหน้า) — พอ bump version ใน `pyproject.toml` แล้ว footer ไม่ตามไปด้วย
- เพิ่ม `app_version` เข้า `inject_spa_context()` (`context_processor` ใน `server.py`) — inject `APP_VERSION` (import จาก `core.config`) เข้าไปเป็น global ให้ทุกเทมเพลตใช้ได้ (context processor ทำงานกับทุก route อยู่แล้ว ไม่ต้องแก้ทีละหน้า) — เปลี่ยน `base.html` บรรทัด footer จาก `Version 0.1` เป็น `Version {{ app_version }}` — `base_partial.html` (ใช้ตอน SPA fetch) ไม่มี sidebar/footer อยู่แล้วจึงไม่ต้องแก้
- ตรวจสอบ: ยืนยันเนื้อหาไฟล์จริงผ่าน Read tool ทั้ง 2 ไฟล์ที่แก้ — ทดสอบ block ที่แก้ใน `server.py` แยกด้วย `py_compile` ผ่าน — ทดสอบ Jinja snippet ของ footer ด้วย `jinja2.Environment().from_string()` render ได้ค่า `Version 0.1.5` ตรงตามคาด — ยังไม่ได้เปิดหน้าเว็บจริงเช็คว่า sidebar แสดงตรงกับหน้าอัปเดตครบทุกหน้า (SPA navigation ทุกเส้นทาง) ควร verify อีกครั้งหลัง deploy

### รวม `APP_VERSION` ให้อ่านจาก `pyproject.toml` ที่เดียว (single source of truth)
- **ที่มา**: `APP_VERSION` (`src/core/config.py`) hardcode แยกจาก `version` ใน `pyproject.toml` เป็นคนละค่ากันมาตลอด (บังเอิญเท่ากันคือ `"0.1.0"`) ทำให้ต้องแก้ 2 ที่เวลาจะ bump version ไม่งั้นค่าที่แสดงในหน้า "อัปเดตระบบ"/`vas --version`/version compare ตอนเช็ค release จะไม่ตรงกับที่ประกาศใน package metadata
- เปลี่ยน `APP_VERSION` ให้เรียก `_read_pyproject_version()` ตอน import — อ่านค่า `version = "..."` จากใต้ `[project]` section ของ `pyproject.toml` ด้วย regex ล้วนๆ (ไม่ใช้ `tomllib` เพราะเป็นของ Python 3.11+ แต่เครื่องเป้าหมาย Ubuntu 22.04 jammy มากับ Python 3.10 เป็นค่าเริ่มต้น) — resolve path แบบ `Path(__file__).resolve().parents[2] / "pyproject.toml"` (ใช้ได้ทั้งตอน dev ในนี้ และตอนติดตั้งจริงที่ `/opt/vending-auto-setup` เพราะ `shutil.copytree(source_dir, install_dir)` ใน `services/updater.py` ก็อปปี้ทั้ง repo root รวม `pyproject.toml` ไปด้วยอยู่แล้ว ไม่ใช่แค่ `src/`) — ถ้าอ่านไม่ได้ (path ไม่มี/ไฟล์เพี้ยน) fallback กลับไปที่ `_FALLBACK_VERSION = "0.1.0"` ไม่ crash
- **ผลลัพธ์กับผู้ใช้**: ต่อไปนี้แก้ version ที่เดียวพอ — เปลี่ยน `version = "x.y.z"` ใน `pyproject.toml` แล้วหน้า "อัปเดตระบบ", `vas --version`/`vas version`, และ logic เทียบเวอร์ชั่นตอนเช็ค release จะอ่านค่าใหม่ตรงกันทันที (แค่ต้อง restart service ให้ Python re-import module)
- ตรวจสอบ: คัดลอกเนื้อหาไฟล์จริงจาก Read tool ไปรัน `python3 -m py_compile`/`ast.parse` แยกใน sandbox ผ่านทั้งคู่ (bash mount ของไฟล์นี้ในเซสชันนี้ยังไม่ทันเช็คว่าค้างหรือไม่ ใช้แนวทางเดิมเพื่อความชัวร์) — ทดสอบ logic การ parse แยกด้วยไฟล์ `pyproject.toml` จริงในโปรเจกต์ ได้ค่า `"0.1.0"` ตรงตามที่ประกาศไว้ — ยังไม่ได้รัน `pytest`/`mypy --strict` เต็มโปรเจกต์ (ต้องมี env ครบ), ยังไม่ได้ทดสอบ path resolution บนเครื่อง Ubuntu จริงหลัง self-update จริง (เคสที่ก็อปปี้ไปที่ `/opt/vending-auto-setup`) ควร verify อีกครั้งหลัง deploy

### หน้า "อัปเดตระบบ" — เพิ่มโหมด Dev สำหรับดึง source ล่าสุดจาก branch มาติดตั้งทันที (ไม่ผ่าน GitHub release)
- **ที่มา**: หน้า Update เดิมใช้ GitHub Releases เป็นเกณฑ์เดียวในการเช็ค/แสดงปุ่มอัปเดต (`check_latest_release()` เรียก `/releases/latest`) แต่ repo ของผู้ใช้ยังไม่เคยสร้าง release เลย ("ไม่พบ release บน GitHub repository นี้") ทำให้กดอัปเดตจริงไม่ได้แม้ push code ใหม่ขึ้น branch ไปแล้ว ทั้งที่กลไก `SelfUpdater`/`start_web_update()` (`src/services/updater.py`) ที่ใช้ติดตั้งจริงรองรับการดึง tarball จาก branch HEAD อยู่แล้ว (`archive_url()` เมื่อ `version="latest"` จะดึงจาก `refs/heads/{branch}.tar.gz` ตรงๆ ไม่ต้องมี release/tag) เพียงแต่ยังไม่มีทางเลือกใน UI ให้เลือก branch หรือข้ามการเช็ค release
- เพิ่ม query param `?branch=<name>` ให้ `/api/update/stream` (`src/server.py`) — ส่งต่อเป็น `start_web_update(branch=branch)` โดยไม่ผ่าน `check_latest_release()` เลย (endpoint เดิมเริ่มอัปเดตทันทีอยู่แล้วโดยไม่รอผลเช็ค แค่ไม่เคยรับ branch จาก client) — เพิ่ม `is_valid_branch_name()`/`BRANCH_NAME_RE` ใน `updater.py` เช็คชื่อ branch (`^[A-Za-z0-9._\-/]+$`, ไม่ขึ้นต้นด้วย `/`/`-`, ไม่มี `..`) ก่อนนำไปประกอบ URL ป้องกัน path/URL injection จาก input ที่ผู้ใช้กรอกเอง — ถ้าไม่ผ่าน validation คืน error ทันทีไม่เริ่ม thread
- เพิ่มการ์ด "โหมด Dev — ดึงจาก Source โดยตรง" ใน `update.html` ระหว่างการ์ดเวอร์ชั่นกับ progress card — ช่อง input ให้กรอกชื่อ branch เอง (default `main` ถ้าเว้นว่าง) + ปุ่ม "ดึง Source ล่าสุด & ติดตั้ง" ที่เรียก flow เดิมทันทีไม่เช็คเวอร์ชั่นก่อน (ตามที่ผู้ใช้ยืนยัน — ใช้สำหรับทดสอบระหว่าง develop เท่านั้น) — refactor JS: แยก `startUpdate()` เดิมออกเป็น `beginUpdateFlow(branch, disableBtn)` ใช้ร่วมกัน แล้วเพิ่ม `window.startDevUpdate()` อ่านค่าจาก `#dev-branch-input` ต่อเป็น query string ของ `EventSource` — ปุ่ม/state/terminal log ใช้ progress card เดิมร่วมกันทั้ง 2 โหมด ไม่ต้องสร้างซ้ำ
- **พบและแก้ไฟล์ `src/server.py` ที่เสียหายอยู่ก่อนแล้ว (ไม่เกี่ยวกับงานนี้โดยตรง แต่บล็อก syntax check)**: ท้ายไฟล์มี fragment ของ `def vpn_connection_label(...)` ซ้ำอยู่ 2 ชุดที่เขียนไม่จบ (ชุดแรกขาดหายกลางชื่อพารามิเตอร์ ชุดที่สองเป็นโค้ด logic คนละแบบกับตัวจริงที่ใช้งานอยู่จริงที่บรรทัด 249 ซึ่ง register เป็น jinja global ไปแล้ว) — ลบ fragment ที่ค้างทั้ง 2 ชุดออก ยืนยันด้วย `python3 -m py_compile` ผ่าน ไม่กระทบฟังก์ชัน `vpn_connection_label` ตัวจริงที่ใช้อยู่ในหน้า WireGuard
- **เพิ่ม auto-restart หลังอัปเดตเสร็จ**: เดิม `done-bar` โชว์ปุ่ม "รีสตาร์ท" ให้ผู้ใช้กดเองหลังอัปเดตสำเร็จ (ทั้ง release mode และ dev mode) — เปลี่ยนให้ SSE event `done` เรียก `restartServer()` เอง (ยิง `POST /api/server/restart` ที่มีอยู่แล้ว → `systemctl restart vending-auto-setup-server.service` หลัง delay 0.5 วิ) ทันทีที่อัปเดตเสร็จโดยไม่ต้องรอผู้ใช้กด — host/port ยังคงเดิมเสมออยู่แล้วเพราะ systemd unit อ่านจาก `EnvironmentFile=/etc/default/vending-auto-setup-server` (`VAS_SERVER_HOST`/`VAS_SERVER_PORT`) ที่ตั้งไว้ตอน install ไม่เกี่ยวกับ process ที่ restart เลย — เพิ่ม guard `_restartTriggered` กัน fetch ซ้ำถ้าผู้ใช้ยังกดปุ่ม "รีสตาร์ทตอนนี้" (คงไว้เป็น fallback) หลัง auto-fire ไปแล้ว — เปลี่ยนข้อความ/ไอคอนใน done-bar จาก static เป็น dynamic (spinner → check) สะท้อนสถานะ "กำลังรีสตาร์ท" / "รีสตาร์ทแล้ว รอเซิร์ฟเวอร์กลับมา"
- ตรวจสอบ: bash sandbox mount ของทั้ง `server.py`/`updater.py` ค้างเหมือนที่เจอซ้ำๆ ในหลาย entry ก่อนหน้า (แสดงเนื้อหาเก่า/มี null byte padding ท้ายไฟล์หลัง edit) — คัดลอกเนื้อหาไฟล์จริงจาก Read tool ไปสร้างสำเนาแยกใน sandbox ก่อนรัน `python3 -m py_compile` และ `ast.parse` จนผ่านทั้งคู่ — แยก JS block ของ `update.html` (รวมส่วน auto-restart ที่เพิ่มรอบหลัง) ไปรัน `node --check` ผ่านทุกครั้งที่แก้ — mypy แบบ standalone (ไม่มี project context) ขึ้น internal error ของตัวเครื่องมือเอง ไม่ใช่จาก code จึงข้าม ใช้ py_compile + ตรวจ type hint ด้วยตาแทน — ยังไม่ได้ทดสอบ end-to-end บนเครื่อง Ubuntu จริง (ยิงอัปเดตจริงจาก branch ทดสอบ แล้วเช็คว่า `/opt/vending-auto-setup` อัปเดตตรงตาม commit ล่าสุด, service restart แล้ว listen พอร์ตเดิมจริง, และ SSE connection ไม่หลุดก่อน restart request ยิงออกไปสำเร็จ) ควร verify อีกครั้งหลัง deploy

### หน้า "จอแสดงผล" — Reactive protocol switch, แก้บั๊ก WaylandEnable comment สะสม, hover state ของ Tab menu
- **Reactive protocol switch**: กด "เปลี่ยนมาใช้ X11/Wayland" ในแท็บ "Display Protocol" เดิม `setTimeout(() => location.reload(), 1200)` reload หน้าทั้งหน้าเสมอหลัง API สำเร็จ ทำให้กะพริบ/เสีย scroll position — แก้โดยเพิ่ม id ให้ badge "Active"/กล่อง "กำลังใช้งาน"/ปุ่มสลับของทั้ง 2 การ์ด (`x11ActiveBadge`/`x11ActiveBox`/`x11SwitchBtn`, `waylandActiveBadge`/`waylandActiveBox`/`waylandSwitchBtn`) แล้วเขียน `renderProtocolState(disabled)` ใน `display.html` อัปเดต class `active`/`hidden` ของทั้ง 2 การ์ดตรงๆ จาก `gdmWayland.disabled` ที่ endpoint `/api/display/wayland` คืนมาอยู่แล้ว โดยไม่ reload หน้า — บรรทัด "ใช้งานได้หลัง re-login" ของ session banner ด้านบนยังคงเดิม (สะท้อน session จริงที่ต้อง re-login ถึงจะเปลี่ยน ไม่ใช่ config ที่อัปเดตทันที)
- **บั๊ก `WaylandEnable=false` สะสมหลายบรรทัดใน `/etc/gdm3/custom.conf`**: `build_gdm_wayland_config()` (`src/features/display/display.py`) เดิมมองหาเฉพาะบรรทัด active (ไม่ comment) ด้วย `_is_active_ini_key()` เวลา toggle กลับไป X11 ถ้าบรรทัดเดิมถูก comment ไว้จากรอบก่อน (ไม่ match เพราะขึ้นต้นด้วย `#`) โค้ดจะ `insert` บรรทัดใหม่เพิ่มเข้าไปโดยไม่ลบของเก่าทิ้ง สลับไปมาหลายรอบจึงเห็น `#WaylandEnable=false` ซ้ำกันหลายบรรทัดใน Config Files tab — แก้โดยเพิ่ม param `allow_commented` ให้ `_is_active_ini_key()` (strip `#`/`;` ออกก่อนเช็ค key) แล้วเปลี่ยน `build_gdm_wayland_config()` ให้หาทุกบรรทัดที่ match key (comment หรือไม่ก็ตาม), แทนที่บรรทัดแรกด้วยค่าใหม่ แล้วลบบรรทัดซ้ำที่เหลือทั้งหมด — self-heal ไฟล์ config เดิมที่พังจาก bug นี้อยู่แล้วได้ทันทีที่ toggle ครั้งถัดไป
- **Hover state ของ Tab menu หน้า Display ไม่ทำงาน**: ปุ่ม tab (`.disp-tab-btn`) ที่ active ตอน initial render (`loop.first`) ไม่มี class `hover:*` ติดมาด้วยเลยตั้งแต่แรก (template ใส่ class คนละชุดให้ active/inactive) แล้ว `switchTab()` เดิมใช้ `classList.toggle()` แค่บาง class (`bg-accent/8`/`text-accent`/`font-semibold`/`text-muted`) ไม่เคยจัดการ hover class — พอสลับปุ่มนั้นออกจาก active จึงไม่มี hover state ตลอดไป — แก้โดยเปลี่ยน hover class ให้ตรงกับ convention (`hover:bg-surface` แทน `hover:bg-line/6`) และ rewrite `switchTab()` ให้ strip + append class ทั้งชุดทุกครั้งเหมือนหน้า "คีออส" (`setTab()`) แทนการ toggle ทีละ class — เพิ่ม section "JS Tab Switch Pattern" ใน `INSTRUCTIONS.md` ให้เป็น convention บังคับสำหรับหน้าที่มี tab menu ทุกหน้า
- ตรวจสอบ: เพิ่ม unit test 2 เคสใน `tests/test_display.py` (`test_gdm_wayland_collapses_duplicate_commented_lines`, `test_gdm_wayland_toggle_twice_does_not_accumulate_lines`) ครอบคลุมทั้งเคส config ที่พังอยู่แล้ว (มีบรรทัดซ้ำ 5 บรรทัด) และเคส toggle สลับไปมา 5 รอบ — รัน `pytest tests/test_display.py` ผ่านทั้งหมด 11 เคส (รวมเทสต์เดิม), `ruff check` ผ่าน, `mypy --config-file pyproject.toml` ไม่มี error ใหม่จากจุดที่แก้ (2 warning ที่เจอเป็นของเดิมใน `_chown_to_effective_user` ไม่เกี่ยวกับรอบนี้ ยืนยันด้วยการรัน mypy กับไฟล์ต้นฉบับก่อนแก้เทียบกัน) — bash sandbox mount ของไฟล์ที่แก้ผ่าน Edit tool ค้างเหมือนที่เคยพบมาก่อน (ดู entry ก่อนหน้า) จึงคัดลอกเนื้อหาไฟล์จริงจาก Read tool ไป sync ใน sandbox แยกก่อนรันเทสต์ — ยังไม่ได้ทดสอบบนเครื่อง Ubuntu จริงกับ GDM/`/etc/gdm3/custom.conf` จริง ควร verify อีกครั้งหลัง deploy

### WireGuard — แก้กับดัก sudo/non-sudo ที่ทำให้ store dir ค้างเป็นของ root (auto-chown คืน user)
- **ปัญหาที่รายงาน**: ผู้ใช้สับสนลำดับการใช้ `sudo` กับ `vas wireguard` ตอนติดตั้งเครื่องครั้งแรก แล้วเจอ Permission denied ตอนรันคำสั่งที่ไม่ได้ใส่ sudo
- **สาเหตุจริง (ไม่ใช่แค่ความเข้าใจผิดของผู้ใช้)**: มีแค่ 3 คำสั่งที่บังคับ root ผ่าน `require_root()` (`cli.py`) คือ `install`/`sync`/`unsync` ส่วน `init-config`/`validate`/`save`/`status`/`history`/`show` ไม่บังคับ แต่ก็ไม่ได้ป้องกันไม่ให้รันด้วย sudo — `default_store_dir()` (`src/features/wireguard/manager.py`) resolve path ผ่าน `SUDO_USER`/`HOME` ไปยังโฮมของ user จริงเสมอ แต่ไฟล์ที่เขียนจะเป็นเจ้าของโดย root ถ้า process รันเป็น root ซ้ำร้ายกว่านั้น web dashboard (`src/services/server_service.py` — systemd unit ไม่มี `User=` จึงรันเป็น root เสมอ) เรียก `WireGuardManager` ตรงๆ ผ่าน `server.py` โดยไม่ผ่าน `require_root()` เลย ทำให้ทุกครั้งที่ใช้หน้าเว็บ WireGuard (Save/Template ฯลฯ) ไฟล์ใน `~/.config/vending-auto-setup/wireguard/` กลายเป็นของ root โดยอัตโนมัติอยู่แล้ว แล้วครั้งถัดไปที่รัน `vas wireguard save`/`show`/`history` แบบไม่ sudo จะเจอ Permission denied ทันทีเพราะ `chmod_private()` ล็อกไฟล์เป็น `600`
- แก้โดยเพิ่ม `reclaim_ownership()`/`_resolve_home()` ใน `manager.py` — เมื่อ `os.geteuid() == 0` จะ chown ไฟล์/โฟลเดอร์ที่เพิ่งเขียนกลับเป็นเจ้าของของโฮมจริง (ดู owner จาก `os.stat(home)` แทนที่จะพึ่ง `SUDO_USER` อย่างเดียว เพราะ systemd service ไม่มี `SUDO_USER` มีแค่ `HOME`) เรียกใช้ท้าย `init_config()`/`save()`/`sync()`/`unsync()` — เจาะจงเฉพาะไฟล์ใน store dir (`~/.config/...`) เท่านั้น ไม่แตะ active config ใต้ `/etc/wireguard` ซึ่งต้องเป็นของ root ตามปกติ — ไม่ต้องบังคับ sudo เพิ่มในคำสั่งที่ไม่จำเป็น (`validate`/`history`/`show`/`status` ยังใช้แบบไม่ sudo ได้ตามเดิม)
- ตรวจสอบ: `mypy --strict`/`ruff check` ผ่านทั้งคู่ (แยกทดสอบผ่านสำเนาไฟล์ sync เองใน sandbox เพราะ bash mount ของ `manager.py` ในเซสชันนี้ค้างเหมือนเคยพบมาก่อน — ยืนยันเนื้อหาไฟล์จริงผ่าน Read tool ก่อน) — เขียน smoke script แยก (`unittest.mock` ปลอม `os.geteuid`/`os.chown`) แทนการรัน `tests/test_wireguard.py` เพราะพบว่าทั้ง `tests/` ในโปรเจกต์ผูก import เป็น `from wireguard import ...`/`from status import ...` แบบ flat module เดิม ซึ่งพังไปแล้วตั้งแต่ก่อนรอบนี้จากการ refactor เข้า `features/`/`system/`/`services/` (ไม่เกี่ยวกับการแก้ครั้งนี้ ควรแก้แยกต่างหาก) — สแกม 4 เคสผ่านหมด: ไม่ใช่ root ไม่มีการ chown เลย, `save()` เป็น root chown ไฟล์ configs, `sync()` เป็น root chown เฉพาะ history snapshot ไม่แตะ `/etc/wireguard`, `unsync()` เป็น root chown backup snapshot — ยังไม่ได้ทดสอบบนเครื่อง Ubuntu จริงกับ systemd service ตัวจริง ควร verify อีกครั้งหลัง deploy

## [2026-07-04]

### หน้า "Kiosk" — แก้บั๊ก session type รีเซ็ตกลับ gnome เสมอ, ปรับ UI ส่วนผู้ใช้/สร้าง user
- **บั๊กที่เจอ**: "ประเภท Session" (GNOME/Openbox) รีเซ็ตกลับไปที่ GNOME ทุกครั้งที่กลับมาเปิดหน้าใหม่ ทั้งที่เพิ่งเลือก Openbox ไป — สาเหตุคือ `_kiosk_page_context()`/`_allowed_kiosk_config_paths()` (`src/server.py`) หา "user เป้าหมาย" ของหน้าโดยดูจาก `is_autologin` ตรงๆ เท่านั้น (`autologin_user = next(u for u in users if u.is_autologin)`) ถ้า auto-login ปิดอยู่ (หรือยังไม่เคยเปิดเลย) โค้ดจะมองว่า "ไม่มี user" แล้ว fallback ไปอ่านค่า default ปลอมๆ (`session_type="gnome"`, `home="/home/kiosk-user"`) ทั้งที่จริงมี kiosk-user ที่ VAS สร้างให้อยู่แล้วพร้อมค่า session type ที่เคยตั้งไว้จริงบนดิสก์ (`/var/lib/AccountsService/users/<user>`) — ฝั่ง frontend เองก็ซ้ำเติมปัญหานี้ เพราะ radio เลือก user (`{{ 'checked' if u.is_autologin else '' }}`) จะไม่มีอันไหนถูกเลือกไว้เลยถ้า auto-login ปิดอยู่ ทำให้ `getSelectedKioskUsername()` คืนค่า `null` และปุ่มเปลี่ยน session type ขึ้น error "ยังไม่มี user ที่เลือกไว้" แทนที่จะบันทึกจริง
- เพิ่ม `resolve_kiosk_target_user()` ใน `src/features/kiosk/manager.py` — หา "user เป้าหมาย" ตามลำดับ: user ที่ auto-login อยู่ปัจจุบัน → user ที่ VAS สร้างให้ (`managed_by_vas`) → user แรกสุดในลิสต์ → ไม่มี user เลย แทนที่การเช็ค `is_autologin` ตรงๆ ทั้ง 2 จุดใน `server.py` (`_kiosk_page_context()` ใช้กำหนด `session_type`/`home`, `_allowed_kiosk_config_paths()` ใช้กำหนด path ของ Config Files tab) — เพิ่ม field ใหม่ `default_kiosk_username` ใน context แล้วเปลี่ยน radio ในแท็บ "ผู้ใช้ Kiosk" ให้ pre-select ตาม field นี้แทน `is_autologin` ตรงๆ เพื่อให้ `getSelectedKioskUsername()` มีค่าเสมอตราบใดที่มี user อยู่ ไม่ว่า auto-login จะเปิดอยู่หรือไม่ก็ตาม
- ปรับ checkbox "เพิ่มเข้ากลุ่ม video, input, plugdev" ในฟอร์ม "สร้าง user ใหม่" เป็น toggle switch ให้ตรงกับ pattern ของ toggle อื่นในหน้าเดียวกัน (id เดิม `#newKioskGroups` ไม่เปลี่ยน — JS ที่อ่านค่าไม่ต้องแก้)
- เพิ่ม logo GNOME/Openbox (`gnome-logo.jpg`/`openbox-logo.png` จาก `public/images/logo/`) ในการ์ดเลือก "ประเภท Session" ตาม pattern เดียวกับที่หน้า "จอแสดงผล" ใช้กับ X11/Wayland (`<img src="/public/images/logo/...">` ขนาด `w-9 h-9` ให้เข้ากับ scale ของหน้า kiosk)
- ย้าย "ลบ user นี้" ออกจากกล่อง "Danger zone" แยกต่างหาก (แดงทั้งกล่อง ดูหนักเกินไป) มารวมเป็น footer bar บางๆ ท้ายการ์ด "เลือก user สำหรับ Kiosk" แทน — คำเตือนเดิมยังอยู่ (ข้อความ + ปุ่มสีแดง) แค่ลดความเป็น "กล่องเตือนขนาดใหญ่" ลงเป็นแถบ utility ธรรมดา
- ตรวจสอบ: เพิ่ม unit test เฉพาะจุดให้ `resolve_kiosk_target_user()` ครอบคลุม 4 เคส (ไม่มี user, มี user ธรรมดาไม่มี autologin, มี user ที่ VAS สร้างแต่ autologin ปิด — เคสตรงกับบั๊กที่รายงาน, autologin user มาก่อนเสมอแม้ user นั้นไม่ใช่ managed_by_vas) ผ่านทั้งหมด; render เทมเพลตจริงผ่าน Flask (`test_request_context`) 3 เคส รวมเคสจำลองบั๊ก (มี kiosk-user แต่ autologin ปิด, session_type=openbox) ยืนยันว่า radio/row ของทั้ง user และ session type ยัง pre-select ถูกต้องตาม `default_kiosk_username` ไม่ reset — `python3 -m py_compile` ผ่านทั้ง `server.py` และ `manager.py` — ยังไม่ได้ทดสอบบนเครื่อง Ubuntu จริงกับ AccountsService ไฟล์จริง ควร verify อีกครั้งหลัง deploy

### หน้า "Kiosk" — ปุ่ม "หยุด kiosk mode" กดไม่ทำงาน (error `Cannot set properties of null`)
- **สาเหตุ**: `kiosk.html` มี modal HTML (`#confirm-modal`) และ CSS ครบตาม convention แต่ไม่เคย define `window.showConfirm` เองในหน้า (ต่างจากทุกหน้าอื่นที่มีปุ่มลบ/ปุ่มอันตราย เช่น `mqtt.html`, `docker.html`, `wireguard.html` ที่ define ไว้ในหน้าตัวเอง) เพราะแอปเป็น SPA ไม่ reload หน้าเวลาเปลี่ยนแท็บ ถ้าก่อนหน้านี้เคยเข้าหน้าอื่นที่ define `window.showConfirm` ไว้มาก่อน ฟังก์ชันนั้นจะค้างอยู่ใน `window` และถูกเรียกแทนตอนกดปุ่มในหน้า Kiosk ซึ่งไปอ้างอิง DOM element (`#confirm-title` ฯลฯ) ของหน้าเก่าที่ไม่มีอยู่แล้ว ทำให้ throw `TypeError: Cannot set properties of null (setting 'textContent')` ที่ `window.showConfirm` แล้วปุ่มไม่ทำงาน
- แก้โดยเพิ่ม `window.showConfirm` ตาม convention ใน `INSTRUCTIONS.md` เข้าไปใน script block ของ `kiosk.html` ตรงๆ (`src/web/templates/kiosk.html:506-527`) — ใช้ `#confirm-modal`/`#confirm-title`/`#confirm-body`/`#confirm-ok`/`#confirm-cancel` ที่มีอยู่แล้วในไฟล์เดียวกัน แก้จุดเดียวจบ ไม่ต้องแตะ `confirmStopKiosk()`/`confirmDeleteKioskUser()` ที่เรียกอยู่แล้ว
- ตรวจสอบ: syntax check ผ่าน `node --check` (แยก script block ออกมาทดสอบเพราะ bash sandbox mount ของ `kiosk.html` ในเซสชันนี้ค้าง — ยืนยันเนื้อหาไฟล์จริงผ่าน Read tool แทน) ยังไม่ได้ทดสอบ end-to-end บนเครื่องจริง (คลิกปุ่มแล้วเช็คว่า auto-login/autostart ถูกลบจริง) ควร verify อีกครั้งบนเครื่อง Ubuntu จริง

### หน้า "Kiosk" — ทำให้แต่ละ section reactive ไม่ reload หน้าทั้งหน้าหลัง action สำเร็จ
- **ก่อนหน้านี้**: สร้าง user, ลบ user, บันทึก autostart, และหยุด kiosk mode ทั้ง 4 action เรียก `window.location.reload()` หลัง API สำเร็จเสมอ (auto-login toggle กับ session-type เดิมอัปเดตแบบ reactive อยู่แล้ว) ทำให้หน้ากะพริบ/เสีย scroll position ทุกครั้งที่กดปุ่ม ทั้งที่ backend คืนค่าล่าสุดมาให้ใน response อยู่แล้ว
- เพิ่ม state กลาง `readinessState` (`software_ok`/`user_ok`/`autologin_ok`/`autostart_ok`, init จาก `readiness | tojson` ตอน render) พร้อม helper 3 ตัวใน `kiosk.html`: `updateReadinessRow()` อัปเดต icon/badge/คำอธิบายของแต่ละแถวในการ์ด "ความพร้อมของ Kiosk Mode", `updateReadinessSummary()` อัปเดตตัวนับ "X จาก 4 ขั้นตอน" + ซ่อน/โชว์ banner เตือนกับการ์ด "หยุด Kiosk Mode" ตาม state ปัจจุบัน, `updateCfgCardStatus()` อัปเดต badge OK/WARN ของการ์ดในแท็บ Config Files — ต้องเพิ่ม `id`/`data-*` hook ในหลายจุดของ template (`data-readiness="{key}"`, `#readiness-count-text`, `#autostart-caution-banner`, `#stop-kiosk-card`, `#kiosk-user-list`, `#kuser-row-{username}`, `#kioskAutologinToggle`, `#cfg-zone-{key}`, `#cfg-status-icon-{key}`, `#cfg-status-text-{key}`) เพื่อให้ query ได้ตรงจุดโดยไม่ต้อง re-render ทั้งหน้า — banner เตือนกับการ์ด "หยุด Kiosk Mode" เปลี่ยนจาก `{% if %}...{% endif %}` (render หรือไม่ render เลย) เป็น render เสมอ + toggle class `hidden` แทน เพื่อให้ JS ซ่อน/โชว์ได้โดยไม่ต้อง reload
- แก้ 4 action ให้ใช้ response ที่ backend คืนมาตรงๆ แทนการ reload: **สร้าง user** — เพิ่ม field `user` (`uid`/`home`/`managed_by_vas`) ใน response ของ `POST /api/kiosk/users` (`src/server.py`) แล้ว insert แถวใหม่เข้า `#kiosk-user-list` ด้วย `insertAdjacentHTML` ฝั่ง client; **ลบ user** — ลบ DOM row ที่ตรงกับ username ออกตรงๆ; **บันทึก autostart** — ใช้ `configured`/`url` ที่ endpoint เดิมคืนอยู่แล้วอัปเดต readiness row + เรียก `reloadConfigContent()` ซ้ำเฉพาะ config key ที่เกี่ยวข้อง (`autostart_desktop`/`kiosk_launch_script` หรือ `openbox_autostart` ตาม session type) เพื่อดึงเนื้อหาไฟล์จริงจาก server โดยไม่ reload; **หยุด kiosk mode** — เพิ่ม field `autologin_enabled`/`autostart_configured` (hardcode `false` เพราะ `stop_kiosk_mode()` รับประกันผลลัพธ์นี้เสมอ) ใน response ของ `POST /api/kiosk/stop` แล้วรีเซ็ต toggle + readiness + cfg cards ที่เกี่ยวข้องทั้งหมดฝั่ง client
- ข้อจำกัดที่รู้อยู่ (ไม่ได้แก้ในรอบนี้): ถ้าเปิด auto-login ให้ user คนละคนกับที่เคย autologin อยู่ (เปลี่ยน user แล้วเปิด toggle ทันที) พาธไฟล์ใน Config Files tab (`home` ที่ใช้สร้าง path ของ autostart/openbox cards) จะไม่อัปเดตจนกว่าจะ reload หน้าเอง เพราะ `kioskHome` เป็นค่าคงที่ตอน render — เคสนี้เกิดยากในทางปฏิบัติ (ปกติสร้าง user เดียวแล้วเปิด autologin ค้างไว้เลย)
- ตรวจสอบ: จำลอง DOM ด้วย `jsdom` (mock `fetch`/`showToast`) รัน flow จริงทั้ง 5 ขั้น (สร้าง user → เปิด autologin → บันทึก autostart → ลบ user อื่น → หยุด kiosk mode) ผ่านทุก assertion (21 ข้อ) ว่า DOM/badge/toggle อัปเดตถูกต้องโดยไม่มีการ reload; เทมเพลตตรวจด้วย `jinja2.Environment.parse()` และ render จริงผ่าน Flask (`test_request_context`) ทั้ง 2 เคส (ครบทุกขั้นตอน / ไม่มีอะไรพร้อมเลย) ผ่านหมด — ฝั่ง Python endpoint ที่แก้ (`server.py`) ตรวจด้วย Read tool แบบ authoritative เพราะ bash sandbox mount ของไฟล์นี้ค้าง (คัด syntax ของ block ที่แก้แล้วยืนยันด้วยตา ไม่พบปัญหา) — ยังไม่ได้ทดสอบบนเครื่อง Ubuntu จริงกับ backend จริง (list_kiosk_linux_users/GDM/AccountsService)

### หน้า "จอแสดงผล" — เพิ่มส่วนตั้งค่า Screen Blank (ปิดหน้าจออัตโนมัติ) เทียบเท่า Ubuntu Settings > Power
- เพิ่มการ์ด "การปิดหน้าจออัตโนมัติ (Screen Blank)" ต่อจากการ์ด "Monitor Setting" ในแท็บ "จอแสดงผล" (`display.html`) — dropdown ตัวเลือกเวลา (3/4/5/8/10/12/15 นาที, ไม่ปิดหน้าจอ/Never) มี badge แสดงค่าปัจจุบัน, checkbox "จำค่านี้ไว้หลัง reboot", ปุ่ม Apply — ใช้ pattern การ์ด/ปุ่ม/badge เดียวกับการ์ด Monitor Setting ที่มีอยู่แล้วในหน้าเดียวกันตาม convention ของ `INSTRUCTIONS.md`
- Backend ควบคุมผ่าน `xset` (ไม่มี GNOME Settings บนเครื่อง vending kiosk ที่ปกติรัน bare X11/openbox ไม่ใช่ full desktop): เพิ่ม `SCREEN_BLANK_OPTIONS`, `build_screen_blank_commands()` (seconds<=0 -> `xset s off`/`xset s noblank`/`xset -dpms` = Never, seconds>0 -> `xset s <sec> <sec>` + `xset dpms <sec> <sec> <sec>`), `parse_xset_screen_blank_seconds()`/`get_screen_blank_seconds()` (parse `xset q`), `DisplayConfigurator.apply_screen_blank()`/`persist_screen_blank()`/`remove_screen_blank_persist()` ใน `src/features/display/display.py` — persist ใช้กลไก managed-block เดิมใน `.xprofile` (เหมือน rotation/touch) แต่แยก signature เป็น `SCREEN_BLANK_SIGNATURE`/`SCREEN_BLANK_BEGIN`/`END` ของตัวเอง จึงต้อง generalize `upsert_managed_block()`/`remove_managed_block()` ให้รับ `begin`/`end` เป็น parameter (default เดิมคือ `DISPLAY_SESSION_BEGIN`/`END` เพื่อไม่กระทบ call site เดิมที่ไม่ส่ง parameter นี้)
- เพิ่ม `ScreenBlankConfigStatus`/`collect_screen_blank_config_status()` ใน `src/system/status.py`, route ใหม่ `POST /api/display/screen-blank` และ context (`screen_blank_options`/`screen_blank_config`/`current_screen_blank`/`current_screen_blank_label`) ใน `GET /display` (`src/server.py`) — เพิ่ม `"xset"` เข้า allowlist ของ `_is_display_command()` ให้รันผ่าน `runuser -u <desktop_user>` เหมือน `xrandr`/`xinput` (ไม่งั้น `xset` จะรันเป็น root แล้วไม่มีผลกับ X session ของ user จริงบนจอ)
- ตรวจสอบ: `python3 -m py_compile`/`ruff check`/`mypy` (แยกทดสอบเพราะ bash sandbox mount ของ `server.py`/`display.py` ในเซสชันนี้ค้างเหมือนที่เคยพบมาก่อน — คัดลอกเนื้อหาไฟล์จริงจาก Read tool ไปตรวจใน sandbox แทน) ผ่านทั้งหมด ไม่มี type error; ทดสอบ syntax ของ route ใหม่ + helper functions ที่แทรกใน `server.py` แยกเป็น harness ต่างหากเพราะไฟล์ใหญ่เกินจะ reconstruct ทั้งไฟล์ — เทมเพลต `display.html` ตรวจด้วย `jinja2.Environment` ทั้ง parse และ render จริง 2 เคส (มีค่า/ไม่มีค่า current_screen_blank) ผ่านหมด — ยังไม่ได้ทดสอบบนเครื่อง Ubuntu จริงว่า `xset` มีผลกับจอจริงหรือไม่ (โดยเฉพาะกรณีไม่มี X session ทำงานอยู่ตอน apply) ควร verify อีกครั้งหลัง deploy

### หน้า "Kiosk" — เพิ่ม Audit Log + แท็บ "ประวัติ", MQTT Heartbeat แบบเปิด-ปิดได้, ตรวจสอบ URL จริง/ไม่จริง
- **Audit log**: เพิ่ม `list_kiosk_audit_log(limit, offset)` ใน `src/core/database.py` — query ตาราง `audit_log` เดิม (ไม่มี migration ใหม่) กรองเฉพาะ `action LIKE 'kiosk_%'` คืน shape เดียวกับ `list_qr_scans()` (`{rows, total, limit, offset}`) เพื่อรองรับ pagination แบบเดียวกัน — เพิ่ม `log_audit(...)` เข้า 6 จุดในทุก route ที่แก้ไข kiosk (`kiosk_create_user_api`, `kiosk_delete_user_api`, `kiosk_autologin_api`, `kiosk_session_type_api`, `kiosk_autostart_api`, `kiosk_stop_api`) พร้อม `log_config_change("kiosk", ...)` เพิ่มเติมใน 3 จุดที่มีค่า config เปลี่ยนจริง (autologin, session_type, autostart) เพื่อให้ตาราง `config_history` ที่ฟีเจอร์อื่นใช้อยู่แล้วมีข้อมูลของ kiosk ด้วย (ก่อนหน้านี้ kiosk ไม่เคยเขียนเข้า `config_history` เลย) — เพิ่ม route `GET /api/kiosk/audit` และแท็บ "ประวัติ" ใหม่ใน `kiosk.html` (list + reload button + pagination ก่อนหน้า/ถัดไป) ก็อปปี้ pattern การแสดงผล/formatTs (พ.ศ. + ซ่อนวันที่ถ้าเป็นวันนี้)/escHtml ตรงจากหน้าประวัติการสแกน QR500 ตามที่ขอ
- **MQTT Heartbeat**: เพิ่ม `src/features/kiosk/heartbeat.py` — background thread (`KioskHeartbeatThread`, pattern เดียวกับ `features/qr/reader.py`: module-level singleton + lock + start/stop function) publish สถานะ kiosk ปัจจุบัน (hostname, kiosk_user, session_type, autologin, autostart_url, readiness) เป็น JSON ไปยัง MQTT broker ทุก N วินาที — เก็บ config (enabled/broker_id/topic/interval) ใน `device_integrations` ตาราง/pattern เดียวกับที่หน้า QR500 ใช้อยู่แล้ว (`device_id="kiosk"`) ไม่ต้องสร้างตารางใหม่ — เพิ่มการ์ด "MQTT Heartbeat" แบบ expand/collapse ในแท็บภาพรวมของ `kiosk.html` (เลือก broker/topic/interval + ปุ่มเปิด-ปิด) ตาม UX pattern เดียวกับการ์ด integration ของหน้า QR500 ตามที่ขอ — เพิ่ม route `GET/POST /api/kiosk/heartbeat` และ boot-time auto-resume ใน `create_app()` (รันหลัง auto-start MQTT broker เดิมเสมอ กัน publish รอบแรกก่อน broker connect เสร็จ)
- **ตรวจสอบ URL**: เพิ่ม `check_url_reachable(url, timeout=10)` ใน `manager.py` — ใช้ `urllib.request`/`urllib.error` ล้วน (ตาม convention เดิมของ `system/clock.py`/`services/updater.py` ไม่เพิ่ม dependency ใหม่) HTTP GET สั้นๆ ไปที่ URL, ถือว่า "เข้าถึงได้" ถ้า status < 500 (401/403/404 = server ตอบจริงแค่ route/auth ไม่ตรง ไม่ใช่เข้าไม่ถึง) — เพิ่มปุ่ม "ทดสอบ URL" ข้างช่องกรอก autostart URL ในแท็บ "เปิดแอปอัตโนมัติ" กันเคสพิมพ์ URL ผิดแล้วจอ kiosk ขึ้นขาวตอน boot โดยไม่มีทางรู้จนกว่าจะเดินไปดูจอจริง
- **ข้ามตามที่ขอ**: ไม่ได้กรองรายชื่อ kiosk user ให้เหลือเฉพาะ `managed_by_vas` ตามที่เคยแนะนำไว้ (ความเห็นเชิง security รอบก่อน) — ผู้ใช้ยืนยันว่า use case จริงอาจต้องใช้ Linux user อื่นที่ไม่ได้สร้างผ่าน VAS เป็น kiosk user ด้วย จึงคงพฤติกรรมเดิมไว้ (แสดง/เลือกได้ทุก user ที่ UID อยู่ในช่วงปกติ) — ส่วน guide wizard สำหรับตั้งค่า kiosk แบบทีละขั้น เลื่อนไปทำทีหลังตามที่ขอเช่นกัน ยังไม่ได้เริ่ม
- ตรวจสอบ: `node --check` ผ่านสำหรับ JS ที่เพิ่ม (`checkKioskUrl`/`toggleHeartbeatCard`/`saveHeartbeat`/`disableHeartbeat`/`loadKioskAudit`/`renderKioskAudit` ฯลฯ — แยกไฟล์ทดสอบต่างหากเพราะ bash sandbox mount ของ `kiosk.html` ในเซสชันนี้ค้างอีกครั้ง เจอปัญหาเดิมที่เคยพบมาก่อนหลาย session ตรวจเนื้อหาไฟล์จริงผ่าน Read/Grep tool แทนแล้วยืนยันว่า edit ลงจริง); ตรวจโค้ด Python ที่แก้ทั้งหมด (`database.py`, `server.py`, `features/kiosk/manager.py`, `features/kiosk/heartbeat.py`) ด้วย Read tool แบบ authoritative ทีละจุด (import block, route handlers, `_kiosk_page_context()`, boot auto-resume block) ยืนยันไม่มี syntax/indentation ผิดพลาด เพราะ `py_compile` ตรงบน bash mount รายงาน error ปลอม (ไฟล์ขาดตอนกลาง multi-byte UTF-8 — ปัญหาเดิมที่เคยเจอและบันทึกไว้ก่อนหน้านี้) — ยังไม่ได้ทดสอบบนเครื่อง Ubuntu จริงกับ MQTT broker จริงและ URL จริงบนเครือข่ายจริง ควร verify อีกครั้งหลัง deploy โดยเฉพาะ heartbeat thread lifecycle ตอน restart server บ่อยๆ

### หน้า "จอแสดงผล" — แก้บั๊ก "Config Files" tab อ่านไฟล์ไม่ได้ (`SyntaxError: Unexpected token '<'`)
- **สาเหตุ**: `_allowed_config_paths()` ใน `src/server.py` ที่ endpoint `GET /api/display/config-content` เรียกใช้ ยัง import แบบเก่าจากยุคก่อน refactor เป็น `features/`/`system/` packages อยู่ (`from display import _effective_home_config_path, _effective_home_script_path`, `from status import GDM_CUSTOM_CONFIG_PATH, XORG_TOUCHSCREEN_CONFIG_PATH`) ซึ่งไม่มี module ชื่อ `display`/`status` อยู่จริงที่ top level ของ `src/` (ของจริงอยู่ที่ `features/display/display.py`/`system/status.py`) ทำให้ทุกครั้งที่เปิดการ์ดไฟล์ config (`.xprofile`, `display-session.sh`, GDM Configuration, `99-vending-touchscreen.conf`) endpoint จะ throw `ModuleNotFoundError` แล้ว Flask ส่ง HTML error page (500) กลับมาแทน JSON — ฝั่ง frontend เอา response ไป `.json()` ตรงๆ จึงเจอ `SyntaxError: Unexpected token '<', "<!DOCTYPE "... is not valid JSON` ทุกการ์ด
- แก้เป็น `from system.status import (GDM_CUSTOM_CONFIG_PATH, XORG_TOUCHSCREEN_CONFIG_PATH, _effective_home_config_path, _effective_home_script_path)` ตรงตาม package path จริง (ทั้ง 4 ชื่อ define/re-export อยู่ใน `system/status.py` อยู่แล้ว)
- ตรวจสอบ: import จริงผ่าน `PYTHONPATH=src python3 -c "from system.status import ..."` สำเร็จ คืนค่า path ถูกต้องครบทั้ง 4 ตัว — ยังไม่ได้เปิดหน้าเว็บจริงทดสอบว่าการ์ดโหลดเนื้อหาไฟล์ขึ้นมาแสดงจริงหลัง fix (ผู้ใช้แจ้งบั๊กมาจาก screenshot บนเครื่อง dev Windows ของผู้ใช้เอง) ควร refresh หน้า `/display` แล้วกดเปิดการ์ด config อีกครั้งเพื่อยืนยัน

### Header (ทุกหน้า) — เพิ่มเมนู "สั่งงานระบบปฏิบัติการ" (รีสตาร์ท/ปิดเครื่อง)
- ผู้ใช้ขอเพิ่มปุ่มสั่งปิด/รีสตาร์ทเครื่องจากหน้า System Monitor (จุดว่างมุมขวาบน header) — เพิ่มเป็นปุ่ม global ใน `base.html` แทนที่จะผูกกับหน้า Monitor เพียงหน้าเดียว เพราะเป็นคำสั่งระดับ OS ที่ควรเรียกได้จากทุกหน้า (วางไว้ระหว่างปุ่ม "คำสั่ง CLI" กับ user dropdown เดิม) — จำกัดให้เห็นเฉพาะ `current_user.role in ('root', 'admin')` ตาม pattern เดียวกับเมนู "ระบบ" ใน sidebar
- Backend: เพิ่ม `src/system/power.py` (`reboot_system()`/`shutdown_system()` เรียก `systemctl reboot`/`systemctl poweroff` ผ่าน `CommandRunner` ที่มีอยู่แล้ว) และ route ใหม่ `POST /api/system/reboot`, `POST /api/system/shutdown` ใน `src/server.py` (วางต่อจาก `/api/monitor/metrics` ในหมวด "System Monitor routes") — ทั้งสอง route เช็คสิทธิ์ผ่าน `_require_admin_user()` เดิม (คืน 403 ถ้าไม่ใช่ root/admin) และเขียน `audit_log` (`system_reboot`/`system_shutdown` พร้อม username) ก่อนคืนผลสำเร็จ
- Frontend: เพิ่ม dropdown 2 ตัวเลือก (รีสตาร์ทเครื่อง/ปิดเครื่อง) ใน `base.html` ที่เปิด modal ยืนยันแยกต่างหาก (`#modal-power`) แทนการยิง action ทันที — ใช้ pattern `modal-backdrop`/`modal-dialog` เดิมที่มีอยู่แล้วสำหรับ modal โปรไฟล์/เปลี่ยนรหัสผ่าน (ไม่ใช้ `window.confirm()` ตาม convention ของ `INSTRUCTIONS.md`) ปุ่มยืนยันเป็นสีแดง (`bg-danger`) เพราะเป็น action ที่ย้อนกลับไม่ได้
- ตรวจสอบ: `python3 -m py_compile` ผ่านสำหรับ `src/system/power.py`; ส่วน `src/server.py`/`src/web/templates/base.html` ตรวจผ่าน harness แยก (bash sandbox mount ของทั้ง 2 ไฟล์นี้ค้าง/แสดงเนื้อหาเก่ากว่าที่แก้จริงอีกครั้ง — ปัญหาเดิมที่เคยพบและบันทึกไว้หลายรอบก่อนหน้า) คัดลอกเนื้อหาไฟล์จริงจาก Read tool ไปสร้าง harness ต่างหาก: ส่วนของ `server.py` (route handlers ใหม่ 2 ตัว) ยืนยัน syntax ถูกต้องด้วย `py_compile`; ส่วนของ `base.html` ยืนยัน JS ด้วย `node --check` และยืนยัน Jinja template (parse + render จริงผ่าน `render_template_string` 2 เคส คือ role=admin เห็นปุ่ม/role=user ไม่เห็นปุ่ม) ผ่านหมดทั้งคู่ — ยังไม่ได้ทดสอบบนเครื่อง Ubuntu จริงว่า `systemctl reboot`/`systemctl poweroff` ทำงานได้จริงกับสิทธิ์ที่ VAS server รันอยู่ (ควรรันเป็น root หรือมี polkit rule ที่อนุญาต) ควร verify อีกครั้งหลัง deploy

## [2026-07-02]

### หน้า "Docker" — ต่อ backend จริงเข้ากับ frontend ครบทุก action (แทนที่ mock ทั้งหมด)
- เพิ่ม `src/features/docker/manager.py` (~730 บรรทัด) เป็น module หลักคุยกับ `docker` CLI ตรงๆ ตาม pattern ของ `features/wireguard/manager.py`/`features/remote/anydesk.py`: query ที่วิ่งตอนโหลดหน้า (`collect_docker_status`, `_collect_containers/_images/_networks/_volumes/_compose_projects/_swarm`) ใช้ `subprocess` ตรงพร้อม timeout 10s (ไม่ผ่าน `CommandRunner` เพราะ `.run()` ไม่รองรับ timeout — สำคัญกับ query หน้าเว็บที่ห้ามค้าง) ส่วน action (start/stop/remove/prune/swarm ฯลฯ) ใช้ `CommandRunner` ตาม convention เดิม (dry_run/print_operation) และเช็ค `dev_fake_installed()` ก่อนเพื่อจำลองผลสำเร็จบนเครื่อง dev ที่ไม่มี docker daemon จริง
- แก้บั๊ก 2 จุดตอนออกแบบ (พบจากการ review เอง เพราะไม่มี docker daemon จริงให้ทดสอบใน sandbox นี้): (1) `docker compose ls --format json` (Compose v2 plugin) คืนค่าเป็น JSON array ก้อนเดียว ไม่ใช่ newline-delimited JSON เหมือนคำสั่ง `docker` หลักตัวอื่น (`ps`/`image ls`/ฯลฯ) ถ้าพลาดจะ parse ผิดจนหน้า Compose พังทั้งหน้า (2) การหา role/address ของ node ใน `docker node ls` เดิม logic งงและไม่ถูกต้อง แก้เป็นเช็ค `ManagerStatus` ตรงๆ และดึง address จริงผ่าน `docker node inspect --format '{{.Status.Addr}}'` ต่อ node
- แก้ `docker_page()` ใน `src/server.py` ให้เรียก `docker_manager.collect_docker_status()` แทน `_collect_docker_status_mock()` แล้วลบฟังก์ชัน mock (~160 บรรทัด) ทิ้ง — shape ของ context ตรงกับที่ `docker.html` ใช้อยู่แล้ว ไม่ต้องแก้ template ส่วนแสดงผล
- เพิ่ม API routes ใหม่ 26 endpoints ใน `src/server.py` (`/api/docker/...`) ครอบคลุมทุกปุ่มใน mockup เดิม: container start/stop/restart/pause/unpause/remove/logs, image pull/remove/prune, network create, volume create/prune, compose save/up/down/restart, swarm init/join/leave/rotate-tokens/promote-node/set-availability/remove-node/scale-service/remove-stack/redeploy-stack, daemon.json save (+restart daemon), restart daemon, system prune, uninstall (เรียก `LifecycleManager.uninstall_docker()` เดิมใน `services/reset.py` ตรงๆ) — action ทำลายล้างระดับ cluster/daemon (swarm init/join/leave/rotate/node ops, daemon.json, system prune, uninstall) ผ่าน `_require_admin_user()` gate ตาม pattern ของ openssh, ส่วน container/image/network/volume/compose เปิดให้ผู้ใช้ที่ login แล้วทุกคนใช้ได้ ตาม pattern ของ wireguard/anydesk เดิม
- แก้ `docker.html`: เพิ่ม log viewer panel (`#containerLogsPanel`) ในแท็บ Containers สำหรับแสดงผล `docker logs`, แทนที่ `runMockAction()` ทั้งก้อนด้วย `postJson()`/`deleteJson()` เรียก endpoint จริงตาม pattern ของ `wireguard.html` — action ที่เปลี่ยน state (container/image/network/volume/compose/swarm/settings) จะ reload หน้าอัตโนมัติหลังสำเร็จเพื่อดึงสถานะล่าสุด ส่วน "Exec Shell" และ "Update Service" ตัดสินใจไม่ทำผ่านเว็บ (ต้องมี interactive PTY / ยังไม่มี manager function รองรับ) แสดง error message ตรงไปตรงมาแทนที่จะ fake ว่าใช้ได้ เช่นเดียวกับ "Create Service" ที่ซับซ้อน (ต้องระบุ image/replicas/ports) ใช้ error message ชี้ไปใช้ `docker service create` ผ่าน terminal แทนแทนที่จะสร้าง form เต็มรูปแบบ; "Create Network"/"Create Volume"/"Scale Service"/"Init Swarm"/"Join Swarm" ใช้ `window.prompt()` รับ input ง่ายๆ แทนการสร้าง modal form ใหม่ (ยังไม่มี input UI ใน mockup เดิม)
- ตรวจสอบ: `python3 -m py_compile`/`ast.parse` และ `ruff check` (ค่า default โปรเจกต์) ผ่านทั้ง `server.py` และ `manager.py` ไม่มี error ใหม่จากโค้ดที่เพิ่ม (76 errors ที่ ruff เจอใน `server.py` เป็นของเดิมทั้งหมด ไม่เกี่ยวกับ docker) เทียบ function signature ทุกจุดที่ route เรียก `docker_manager.*` กับ definition จริงครบ 26 ฟังก์ชัน ตรงกันหมด — **ยังไม่ได้ test รันจริงกับ docker daemon** เพราะ sandbox นี้ไม่มี Docker ติดตั้ง ควร verify อีกครั้งบนเครื่อง Ubuntu จริงของผู้ใช้ก่อนใช้งานจริง โดยเฉพาะ flow ที่พึ่งพา output format ของ `docker` CLI ตรงๆ (compose ls, node inspect, swarm token parsing)
- หมายเหตุสภาพแวดล้อม: bash sandbox mount ของ `docker.html` ในเซสชันนี้ค้าง (stale) หลัง edit ก้อนใหญ่ — `wc -c`/`decode utf-8` ผ่าน mount รายงานไฟล์ขาดตอนกลาง multi-byte UTF-8 (ปัญหาเดิมที่เจอกับ `server.py` ตอนทำ mock) ตรวจสอบไฟล์จริงผ่าน Read tool (authoritative) แทน ยืนยันโครงสร้างไฟล์ครบถ้วนถูกต้อง (script ปิดถูกต้อง, `{% endblock %}` ครบ)

### เพิ่มหน้า "Docker" — mock UI พร้อม route จริง เตรียมต่อ backend
- เพิ่ม `src/web/templates/docker.html` ตาม page-structure convention เดียวกับ `wireguard.html` (page header / tab nav / tab-panel) มี 8 แท็บ: สถานะ, Containers, Images, Networks, Volumes, Compose, Swarm (รองรับ Docker Swarm — join tokens, cluster nodes, services, stacks, leave swarm), ตั้งค่า (daemon.json editor, danger zone)
- เพิ่ม route `GET /docker` (`docker_page`) ใน `src/server.py` เรียก `_collect_docker_status_mock()` — ฟังก์ชัน mock data ที่คง shape เดียวกับที่ `docker.html` ใช้ไว้แล้ว เพื่อให้แทนที่ด้วยการอ่านค่าจริงผ่าน `docker` CLI ทีหลัง (ดู pattern ใน `src/mcp/tools/docker.py`) โดยไม่ต้องแก้ template — มี TODO comment กำกับจุดที่ต้องแก้ไว้ทั้งสองจุด
- เพิ่ม nav link "Docker" ใน `base.html` (section เครือข่าย, `data-nav-pkg="docker"`) และเพิ่ม `"docker": _shutil.which("docker") is not None` ใน `/api/nav/status` ให้เมนูโผล่เฉพาะเมื่อติดตั้ง Docker แล้ว ตาม pattern เดียวกับ Wireguard/AnyDesk/OpenSSH
- ปุ่ม action ทั้งหมด (start/stop/remove container, remove image, leave swarm, uninstall ฯลฯ) ต่อ `showConfirm()` ตาม convention ของโปรเจกต์แล้ว (ห้าม `window.confirm()`) แต่ยังยิง mock handler ไม่ใช่ fetch จริง — พร้อมสลับเป็น `postJson()` ตอนต่อ backend
- ตรวจสอบ: `py_compile` fragment ของ `_collect_docker_status_mock()`, `ruff check` (ค่า default โปรเจกต์ ไม่มี error), และ Jinja2 render test ของ `docker.html` ผ่านทั้ง 3 เคส (mock เต็ม, swarm inactive, list ว่าง) ผ่านหมด — bash sandbox mount ของ `src/server.py`/`.git` ในเซสชันนี้ค้าง (stale) ทำให้ `py_compile`/`git status` ตรงบน mount รายงานผิด จึงตรวจผ่านการอ่านไฟล์แบบ authoritative (Read tool) และ fragment test แทน

### เพิ่มหน้า "PM2" — mock UI พร้อม route จริง เตรียมต่อ backend
- เพิ่ม `src/web/templates/pm2.html` ตาม page-structure/tab-panel/accordion/confirm-modal convention เดียวกับ `docker.html` มี 7 แท็บ: สถานะ (daemon info, process summary, quick actions), Processes (list พร้อม start/stop/restart/reload/delete, scale instances สำหรับ cluster mode, toggle watch), Logs (เลือก process/stream stdout-stderr/tail lines), Monitoring (CPU/Memory ต่อ process แบบ mock jitter ทุก 3 วิ เพื่อจำลองอัปเดตแบบ realtime), Ecosystem (แก้ไข `ecosystem.config.js` + validate/save), Modules (pm2-logrotate/pm2-server-monit/pm2-auto-pull — enable/disable/configure/uninstall), ตั้งค่า (startup script, save/resurrect, update PM2, danger zone: reset counters/delete all/kill daemon)
- เพิ่ม route `GET /pm2` (`pm2_page`) ใน `src/server.py` เรียก `_collect_pm2_status_mock()` — ฟังก์ชัน mock data (processes/logs/ecosystem/modules/startup) คง shape เดียวกับที่ `pm2.html` ใช้ เพื่อให้แทนที่ด้วยการอ่านค่าจริงผ่าน `pm2` CLI ทีหลัง (แนะนำสร้าง `src/mcp/tools/pm2.py` ตาม pattern ของ `docker.py` — ใช้ `pm2 jlist` สำหรับ process list, `pm2 describe <id>` สำหรับ detail, `pm2 logs <name> --lines N --nostream` สำหรับ logs) — มี TODO comment กำกับจุดที่ต้องแก้
- เพิ่ม nav link "PM2" ใน `base.html` (section เครือข่าย ต่อจาก Docker, `data-nav-pkg="pm2"`, icon `simple-icons:pm2`) และเพิ่ม `"pm2": _shutil.which("pm2") is not None` ใน `/api/nav/status` ให้เมนูโผล่เฉพาะเมื่อติดตั้ง PM2 แล้ว (PM2 เป็น child package ของ Node.js อยู่แล้วใน `features/packages/settings.py`)
- ปุ่ม action ทั้งหมดต่อ `showConfirm()` ตาม convention (ห้าม `window.confirm()`) ยิง mock handler ไม่ใช่ fetch จริง พร้อมสลับเป็น `postJson()` ตอนต่อ backend
- ตรวจสอบ: bash sandbox mount ของ `src/server.py`/`base.html` ในเซสชันนี้ค้าง (stale — เจอปัญหาเดิมกับตอนทำ Docker) ทำให้ `py_compile` ตรงบน mount รายงาน false error จึงตรวจแบบ authoritative แทน — (1) แยก `_collect_pm2_status_mock()` เป็นไฟล์เดี่ยวใน `/tmp` แล้ว `python3 -m py_compile` + รันจริงผ่าน assertion (6 processes, 6 log groups, 3 modules, 6 apps ใน ecosystem) ผ่านหมด (2) `jinja2.Environment.parse()` บน `pm2.html` ผ่าน (3) render test เต็มรูปแบบด้วย context จริงจาก `_collect_pm2_status_mock()` ผ่าน `base_partial.html` ได้ HTML ~92KB ครบทั้ง 7 tab-panel ไม่มี Jinja error

### หน้า "โปรแกรมเพิ่มเติม" — เพิ่ม confirm modal ก่อนติดตั้ง/ถอน, แสดง state กำลังดำเนินการที่ปุ่ม, ขยาย modal
- **บั๊กที่เจอ**: กด Install ซ้ำสองครั้งติดกัน เกิดคำสั่ง 2 ครั้ง — ครั้งที่สอง backend ปฏิเสธถูกต้อง ("มีการติดตั้ง/ถอนการติดตั้งรายการนี้อยู่แล้ว") แต่ปุ่มในหน้ารายการไม่มี state บอกว่ากำลังทำงานอยู่ (โดยเฉพาะถ้าปิด modal ไปแล้วกลับมาเห็นปุ่มปกติ เข้าใจผิดว่ากดซ้ำได้)
- เพิ่ม `activeAction` (JS local state, pkgId → "install"/"uninstall") — set ทันทีแบบ synchronous ตอนผู้ใช้กดยืนยันใน confirm modal ก่อนยิง fetch เสมอ ปิด race window ที่ทำให้กดซ้ำได้จริงๆ ปุ่มจะเปลี่ยนเป็น disabled + spinner + "กำลังติดตั้ง.../กำลังถอน..." ทันที ไม่ต้องรอ network, และคง state นี้ไว้แม้ปิด install modal ไปแล้ว จนกว่า SSE จะส่ง `done`/`error` หรือ request ล้มเหลว
- Backend (`get_package_status()` ใน `settings.py`) เพิ่ม field `busy` (`"install"` / `"uninstall"` / `null`) จาก `is_installing()`/`is_uninstalling()` ที่มีอยู่แล้ว — ใช้ sync state ตอนโหลดหน้าใหม่ระหว่างที่มีงานค้างอยู่ (เช่น refresh หน้าระหว่างติดตั้ง) ให้ปุ่มยังโชว์ busy ถูกต้อง ไม่ใช่แค่ local state ฝั่ง browser ที่หายไปตอน refresh
- เพิ่ม confirm modal ก่อนกด **Install** ด้วย (เดิมมีแค่ก่อนถอน) — ใช้ `showConfirm()` เดียวกัน เพิ่ม `variant: "accent"` (ไอคอน/สีฟ้าแทนแดง) ให้แยกจาก uninstall ที่เป็น `variant: "danger"` (ค่า default) — ปุ่ม "ติดตั้งเดี๋ยวนี้" ใน dependency modal (ที่ถามอยู่แล้วว่าจะติดตั้ง dependency เลยไหม) ข้าม confirm ซ้ำซ้อน เรียก `runInstall()` ตรงๆ แทน `installPkg()`
- ขยาย install/uninstall modal: เดิม inline style ตั้งแค่ `max-width` แต่ class `.modal-dialog` set `width: min(420px, ...)` ไว้แล้ว ทำให้ `max-width` ไม่มีผลจริง (ยังกว้างแค่ ~420px) แก้โดย set ทั้ง `width` และ `max-width` เป็น `min(760px, calc(100vw - 2rem))` และเพิ่มความสูงกล่อง terminal log จาก `max-height:320px` เป็น `min(480px, 60vh)` พร้อม `min-height:220px`

### หน้า "โปรแกรมเพิ่มเติม" — ติดตั้ง/ถอนเสร็จแล้ว sidebar ไม่อัปเดตเอง ต้อง refresh หน้าเอง
- `base.html` มี `window.refreshNavStatus()` ให้เรียกอยู่แล้ว (เขียนไว้เผื่อหน้าอื่นเรียกหลัง install/uninstall ตาม comment เดิม) แต่ `apps.html` ไม่เคยเรียกใช้ — sidebar (เช่นเมนู Wireguard/OpenSSH/AnyDesk ที่โผล่เฉพาะตอนติดตั้งแล้ว) เลยไม่รู้ว่ามีการเปลี่ยนแปลงจนกว่าจะ refresh หน้าเอง
- เพิ่มการเรียก `window.refreshNavStatus()` ใน `apps.html` สองจุด: ใน `streamAction()` ตอน SSE ส่ง event `done` (ครอบคลุมทั้ง install เดี่ยวและ uninstall) และใน `installSequential()` ตอนคิวติดตั้งครบทุกรายการ (flow parent+children) — ไม่ต้องแก้ backend เพราะ `/api/nav/status` เดิมอ่านสถานะสดจากเครื่องอยู่แล้ว

### ติดตั้ง Node.js/AnyDesk ผ่านหน้าเว็บล้มเหลว — gpg คุย /dev/tty ไม่ได้
- Test บนเครื่องจริงพบว่าติดตั้ง Node.js และ AnyDesk ผ่านหน้า "โปรแกรมเพิ่มเติม" ค้างที่ขั้น `curl ... | gpg --dearmor -o ...` เสมอ ด้วย error `gpg: cannot open '/dev/tty': No such device or address` ตามด้วย `curl: (23) Failed writing body` (curl เขียนเข้า pipe ที่ gpg ปิดไปแล้วไม่ได้) — สาเหตุคือคำสั่งรันผ่าน `subprocess.Popen` จาก Flask backend (ไม่มี controlling terminal) แต่ `gpg --dearmor` พยายามเปิด `/dev/tty` เพื่อโต้ตอบ (เช่น ถามยืนยันถ้าไฟล์ปลายทางมีอยู่แล้ว) ตามค่าเริ่มต้นเมื่อไม่ได้สั่ง batch mode
- แก้โดยเพิ่ม `--batch --yes --no-tty` ให้ `gpg --dearmor` ทุกจุดที่เรียกผ่าน `bash -lc` (`src/features/packages/settings.py`: node, anydesk — ทั้งฝั่ง web install ที่เจอบั๊ก และ `src/features/packages/installers.py`: node, anydesk ที่เป็น CLI equivalent เดิม ก็มีบั๊กเดียวกันแฝงอยู่ แก้ไปพร้อมกันเพื่อความสอดคล้อง) — `--batch --no-tty` ปิดการโต้ตอบผ่าน terminal ทั้งหมด `--yes` ให้เขียนทับไฟล์ keyring เดิมได้โดยไม่ถาม
- Docker ไม่กระทบ เพราะขั้นตอนดาวน์โหลด key ของ Docker ใช้ `curl -o` เขียนไฟล์ `.asc` ตรงๆ ไม่ได้ผ่าน `gpg --dearmor`

### หน้า "โปรแกรมเพิ่มเติม" — แก้บั๊ก onclick พัง (JSON.stringify ใน double-quoted attribute)
- ปุ่ม `installPkg`/`uninstallPkg`/`openSubSelectModal` เดิมสร้าง `onclick="fn(' + JSON.stringify(p.id) + ')"` — `JSON.stringify` คืน string ที่ครอบด้วย double quote (`"node"`) ไปฝังอยู่ใน HTML attribute ที่ครอบด้วย double quote เหมือนกัน ทำให้ quote ปิด attribute ก่อนเวลา (`onclick="installPkg("` เท่านั้น) กดปุ่มแล้วได้ `Uncaught SyntaxError: expected expression, got '}'` ทันที — บั๊กนี้มีอยู่เดิมตั้งแต่ก่อนเพิ่มปุ่มถอน แต่ไม่เคยโผล่ให้เห็นเพราะ dev-mode (`VAS_DEV_FAKE_INSTALLED=1`) ทำให้ทุก package โชว์ "Installed" (ปุ่ม disabled ไม่มี onclick) จนกว่าจะรันบนเครื่องจริงที่มี package ยังไม่ติดตั้งแล้วกดปุ่มจริงๆ ครั้งแรก
- แก้เป็น `onclick="fn(\'' + esc(p.id) + '\')"` — ใช้ single quote ครอบค่าที่ฝังใน attribute แทน ไม่ชนกับ double quote ของ attribute เอง

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
