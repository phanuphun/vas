---
tags: [spec, plan]
date: 2026-07-13
project: vas
status: draft
---

# Spec: ปิด Touch Gesture ของ GNOME Shell (ปัดขวา/ปัดขึ้น) ด้วย "Disable Gestures 2021"

## Goal

ปิดช่องทางหลุดออกจาก kiosk mode ที่เหลืออยู่ 2 ทาง (พบจากคลิปวิดีโอที่วิเคราะห์ไว้): ปัดขวาบนจอสัมผัส (สลับ workspace) และปัดขึ้น 4 นิ้ว (ยุบแอปเข้า Activities Overview) — เป็น touch gesture ที่ mutter/GNOME Shell ฝังมาในตัว ไม่มี gsettings key ให้ปิดตรงๆ ต่างจาก Hot Corner/Terminal shortcut/Super key/Ubuntu Dock ที่ปิดไปแล้วก่อนหน้า (`disable_ubuntu_dock`, commit `605ff3e`)

**ทดสอบมือบนเครื่อง production แล้วสำเร็จ** (2026-07-13, เครื่อง `hapymed-sterile-00`, user จริงที่ auto-login คือ `kios2-user` ไม่ใช่ `kiosk-user` ที่เป็นบัญชีค้างเก่า — ดูหัวข้อ Risks):
- GNOME Shell เวอร์ชันบนเครื่องจริง: 42.9 (Ubuntu 22.04) → ต้องใช้ extension **version 5** (รองรับ Shell 3.36–44) ไม่ใช่ version 9 (รองรับ 45–47 เท่านั้น)
- ติดตั้งผ่าน `gnome-extensions install --force` ลง `~/.local/share/gnome-shell/extensions/` ของ `kios2-user`, reboot 1 ครั้งให้ gnome-shell rescan extension directory ใหม่ (จำเป็น — extension directory ที่เพิ่งสร้างครั้งแรกจะไม่ถูก gnome-shell รู้จักจนกว่าจะ restart session), แล้ว `gnome-extensions enable disable-gestures-2021@verycrazydog.gmail.com` สำเร็จ ยืนยันด้วย `gnome-extensions list --enabled`
- Extension license: MIT (VeryCrazyDog/gnome-disable-gestures) — vendor เข้า repo ได้ถูกต้องตามกฎหมายแค่ต้องเก็บ copyright notice ไว้

## Data model changes

ไม่มี —ใช้แพทเทิร์นเดิม 2 จุดที่มีอยู่แล้วในโปรเจกต์ทั้งคู่ ไม่มี schema/DB เปลี่ยน:
- `PACKAGES` list (`src/features/packages/settings.py`) — เพิ่ม entry ใหม่
- `GNOME_LOCKDOWN_FLAG_DEFS` tuple (`src/features/kiosk/manager.py`) — เพิ่ม entry ใหม่ (แพทเทิร์นเดียวกับ `disable_ubuntu_dock`)

## Process flow

### 1. Vendor ไฟล์ extension เข้า repo (ไฟล์ใหม่)

สร้างโฟลเดอร์ `src/features/packages/vendor/gnome-disable-gestures/` แยก 2 เวอร์ชันตาม GNOME Shell ที่รองรับ (ต้องมีทั้งคู่เพราะเครื่อง vending อาจเป็น Ubuntu 22.04 หรือ 24.04+ ก็ได้):
- `v5/extension.js`, `v5/metadata.json`, `v5/LICENSE` — รองรับ Shell 3.36–44 (Ubuntu ≤22.04)
- `v9/extension.js`, `v9/metadata.json`, `v9/LICENSE` — รองรับ Shell 45–47 (Ubuntu 24.04+)

ดึงไฟล์จาก `https://extensions.gnome.org/review/download/44034.shell-extension.zip` (v5) และ `https://extensions.gnome.org/review/download/59618.shell-extension.zip` (v9) เก็บ `LICENSE` (MIT, VeryCrazyDog) ไว้ในทั้ง 2 โฟลเดอร์ตาม license requirement

UUID ของ extension (เหมือนกันทั้ง 2 เวอร์ชัน): `disable-gestures-2021@verycrazydog.gmail.com`

### 2. `src/features/packages/settings.py` — เพิ่ม package entry ใหม่

เพิ่มใน `PACKAGES` list ต่อจาก entry `chromium` (หมวด `kiosk` เดิม, ก่อนหมวด Hardware ที่มี `qr-udev`):

```python
{
    "id":          "gnome-gesture-lockdown",
    "name":        "Disable Gestures 2021",
    "description": "GNOME Shell extension — ปิด touch gesture ในตัว (ปัดขวาสลับ workspace, ปัดขึ้นยุบแอปเข้า Activities) กันหลุดออกจาก kiosk",
    "logo":        None,
    "category":    "kiosk",
    "depends":     [],
    "children":    [],
    "check":       _file_check("/usr/share/gnome-shell/extensions/disable-gestures-2021@verycrazydog.gmail.com/metadata.json"),
    "install_cmds": [
        # เลือกโฟลเดอร์ vendor (v5/v9) ให้ตรงกับ GNOME Shell เวอร์ชันจริงของเครื่องนั้น ณ เวลาติดตั้ง
        ["bash", "-lc",
         "SHELL_VER=$(gnome-shell --version | grep -oE '[0-9]+' | head -1); "
         "SRC_DIR=$(dirname $(readlink -f $0))/vendor/gnome-disable-gestures; "  # ปรับ path จริงตอน implement — ดู note ด้านล่าง
         "if [ \"$SHELL_VER\" -ge 45 ]; then SRC=\"$SRC_DIR/v9\"; else SRC=\"$SRC_DIR/v5\"; fi; "
         "mkdir -p /usr/share/gnome-shell/extensions/disable-gestures-2021@verycrazydog.gmail.com; "
         "cp \"$SRC\"/extension.js \"$SRC\"/metadata.json /usr/share/gnome-shell/extensions/disable-gestures-2021@verycrazydog.gmail.com/"],
    ],
    "uninstall_cmds": [
        ["rm", "-rf", "/usr/share/gnome-shell/extensions/disable-gestures-2021@verycrazydog.gmail.com"],
    ],
    "uninstall_warning": "การถอนจะเปิดทางให้ปัดขวา/ปัดขึ้นหลุดออกจาก kiosk ได้อีกครั้ง",
},
```

**หมายเหตุสำคัญที่ต้องแก้ตอน implement จริง**: คำสั่ง bash ด้านบนอ้าง path แบบ `$(dirname $(readlink -f $0))` ซึ่งใช้ไม่ได้จริงเพราะรันผ่าน `bash -lc` ไม่มี `$0` ที่ชี้ไปไฟล์ต้นทาง — ต้อง resolve absolute path ของ `vendor/gnome-disable-gestures/` จากฝั่ง Python ก่อน (เช่นผ่าน `Path(__file__).parent / "vendor" / "gnome-disable-gestures"`) แล้ว inject เป็น string literal เข้าไปใน command list ตอนสร้าง `PACKAGES` แทนที่จะ hardcode เป็น shell path-finding — ต้อง design ให้ถูกต้องตอนเขียนโค้ดจริง ไม่ใช่ copy ตัวอย่างนี้ตรงๆ

### 3. `src/features/kiosk/manager.py` — เพิ่ม lockdown flag (แพทเทิร์นเดียวกับ `disable_ubuntu_dock`)

เพิ่มใน `GNOME_LOCKDOWN_FLAG_DEFS` ต่อจาก `disable_ubuntu_dock`:

```python
{
    "key": "disable_touch_gestures",
    "command": "gnome-extensions enable disable-gestures-2021@verycrazydog.gmail.com",
    "label": "ปิด touch gesture ของ GNOME Shell (ปัดขวา/ปัดขึ้น)",
    "desc": (
        "เปิดใช้ extension \"Disable Gestures 2021\" กันปัดขวาสลับ workspace และปัดขึ้น 4 นิ้ว "
        "ยุบแอปเข้า Activities Overview — ต้องติดตั้ง extension นี้ก่อนที่หน้า \"ซอฟต์แวร์ระบบ\" "
        "(package id: gnome-gesture-lockdown) ไม่งั้น toggle นี้จะไม่มีผลอะไรเลย"
    ),
},
```

ใช้กลไก `build_gnome_lockdown_preamble()` / `_parse_gnome_lockdown_flags()` / `normalize_gnome_lockdown_flags()` เดิมทั้งหมดแบบ generic ไม่ต้องแก้ logic เพิ่ม (เหมือน `disable_ubuntu_dock`)

### 4. Readiness check ใหม่ — `KioskSoftwareStatus`

เพิ่ม field `gesture_lockdown_installed: bool` ใน `KioskSoftwareStatus` (`manager.py`) และเติมค่าใน `collect_kiosk_software_status()` โดยเช็ค path เดียวกับ `check` ของ package ในข้อ 2 (`/usr/share/gnome-shell/extensions/disable-gestures-2021@verycrazydog.gmail.com/metadata.json`) — ให้หน้า Kiosk แสดงเตือนได้ถ้า toggle เปิดอยู่แต่ extension ยังไม่ถูกติดตั้งจริง (สถานการณ์เดียวกับที่เจอตอนทดสอบมือ: enable แล้วแต่ไฟล์ไม่มี → error เงียบ)

### 5. Auto-install ตอนสร้าง kiosk user ครั้งแรก (`src/server.py`)

จุดที่เรียก `manager.create_user(...)` ใน endpoint `POST /api/kiosk/users` (`kiosk_create_user_api()`, บรรทัด ~1505-1516 ปัจจุบัน) — เพิ่มการเรียก install_cmds ของ package `gnome-gesture-lockdown` (ผ่าน mechanism ที่มีอยู่แล้วใน `features/packages/settings.py`, เช่น `run_install("gnome-gesture-lockdown")` หรือฟังก์ชันเทียบเท่าที่ใช้เรียก install จาก endpoint อื่นอยู่แล้ว) ต่อท้ายหลัง `create_user()` สำเร็จ — **ไม่ implement logic install ซ้ำใน `KioskManager.create_user()` เอง** เพราะ `manager.py` ไม่ควร import จาก `features/packages/settings.py` (คนละ concern: user/session management vs software installation) — ให้ server.py เป็นชั้น orchestrate ที่เรียกทั้งสองแทน

## API changes

ไม่มี endpoint ใหม่ — `POST /api/kiosk/users` เดิมเพิ่ม side-effect (auto-install) เท่านั้น, `/api/kiosk/os-notifications`-style endpoint เดิมของ GNOME lockdown flags ใช้ generic mechanism ที่มีอยู่แล้วรองรับ flag ใหม่โดยอัตโนมัติ (เหมือน `disable_ubuntu_dock`)

## Frontend changes

- หน้า **Kiosk mode**: toggle ใหม่โผล่อัตโนมัติจาก loop `gnome_lockdown_flag_defs` เดิม — **ไม่ต้องแก้ template**
- หน้า **ซอฟต์แวร์ระบบ** (`apps.html` หรือ template ที่ render `PACKAGES`): entry ใหม่โผล่อัตโนมัติจาก loop เดิมเช่นกัน — **ไม่ต้องแก้ template** (สมมติฐานนี้ต้องยืนยันจริงตอน implement ว่า template render `PACKAGES` แบบ dynamic ทั้งหมดจริง เหมือนที่ `kiosk.html` render `gnome_lockdown_flag_defs`)

## Implementation routing

- backend-builder: required (`settings.py`, `manager.py`, `server.py`, vendor asset files)
- frontend-builder: ไม่จำเป็นถ้ายืนยันแล้วว่า template เดิม render แบบ generic ทั้ง 2 หน้า
- test-verifier: required
- pr-reviewer: required
- build order: (1) vendor asset → (2) `settings.py` package entry → (3) `manager.py` lockdown flag + readiness field → (4) `server.py` auto-install wiring → (5) tests + CHANGELOG

## Tests required

- Unit (`tests/test_kiosk_manager.py`): `test_touch_gestures_lockdown_present_by_default_and_omitted_when_disabled()` — โครงเดียวกับ `test_ubuntu_dock_lockdown_present_by_default_and_omitted_when_disabled()`
- Unit (`tests/test_packages_settings.py` หรือไฟล์ทดสอบที่มีอยู่ของ packages): เช็คว่า `gnome-gesture-lockdown` อยู่ใน `PACKAGES`, `check()` คืน `False` ถ้าไฟล์ไม่มีอยู่จริง
- Manual (บนเครื่องจริงเท่านั้น เพราะเป็น GUI/gesture ทดสอบอัตโนมัติไม่ได้): หลัง implement แล้ว กด "ติดตั้ง" ที่หน้าซอฟต์แวร์ระบบ + เปิด toggle ที่หน้า Kiosk → reboot → ทดสอบปัดขวา/ปัดขึ้นบนจอจริงอีกรอบว่ายังหยุดเหมือนตอนทดสอบมือ

## Risks and open questions

- **บัญชี kiosk ซ้ำซ้อนบนเครื่องจริง**: พบว่ามี `kiosk-user` (uid 1001, ไม่ได้ใช้งาน) กับ `kios2-user` (uid 1002, auto-login จริง) พร้อมกันบนเครื่อง `hapymed-sterile-00` — ยังไม่รู้ที่มาว่า `kios2-user` เกิดจากอะไร (สร้างซ้ำโดยไม่ตั้งใจ?) ต้องตัดสินใจแยกว่าจะลบ `kiosk-user` ทิ้งหรือไม่ ก่อน/หลัง implement รอบนี้ก็ได้ ไม่ผูกกับงานนี้โดยตรงแต่ควรเคลียร์ไว้กันสับสนต่อ
- **shell-version detection ตอน install อาจไม่ตรง 100%** — ถ้าเครื่องในอนาคตใช้ GNOME Shell เวอร์ชันที่ไม่ใช่ 42.x หรือ 45-47.x เป๊ะ (เช่น Ubuntu รุ่นกลางๆ ที่แพตช์เวอร์ชันเอง) logic เลือก v5/v9 ต้องมี fallback/error message ที่ชัดเจน ไม่ใช่ install ผิดเวอร์ชันแล้ว fail เงียบ
- **การ enable ครั้งแรกต้อง reboot เสมอ** (ยืนยันจากการทดสอบมือ) — เพราะ gnome-shell ไม่ rescan extension directory ใหม่ที่เพิ่งสร้างจนกว่าจะ restart session — ต้องสื่อสารใน UI ว่า toggle นี้ต้อง reboot ถึงจะเห็นผล ถ้าเป็นการติดตั้งครั้งแรกของเครื่องนั้น (ต่างจาก `disable_ubuntu_dock` ที่ extension มีอยู่แล้วในเครื่องตั้งแต่ต้น ไม่ต้องรอ rescan)
- **ยังไม่ proof การ auto-install ผ่าน UI จริง** — ทดสอบมือผ่าน SSH เท่านั้น ยังไม่เคยลองผ่าน flow "กดปุ่มติดตั้งที่หน้าเว็บ" จริง ต้อง proof รอบใหม่หลัง implement

## Files that will change

- `src/features/packages/vendor/gnome-disable-gestures/{v5,v9}/{extension.js,metadata.json,LICENSE}` — ไฟล์ใหม่ (vendor asset)
- `src/features/packages/settings.py` — เพิ่ม package entry `gnome-gesture-lockdown`
- `src/features/kiosk/manager.py` — เพิ่ม flag `disable_touch_gestures` ใน `GNOME_LOCKDOWN_FLAG_DEFS`, เพิ่ม field `gesture_lockdown_installed` ใน `KioskSoftwareStatus`
- `src/server.py` — auto-install wiring ใน `kiosk_create_user_api()`
- `tests/test_kiosk_manager.py` — เทสต์ใหม่
- `tests/test_packages_settings.py` (หรือไฟล์เทียบเท่าที่มีอยู่) — เทสต์ package entry ใหม่
- `CHANGELOG.md` — ต่อท้าย entry วันที่ implement จริง
