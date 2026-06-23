# TODO

## สิ่งที่ทำเสร็จแล้ว ✅

- **Phase 1** — ติดตั้ง tools หลัก: Git, Node.js v22, Docker Engine, AnyDesk, bootstrap script, self-update
- **Phase 2** — ตั้งค่า Display/Touchscreen: detect session, xrandr rotation, xinput mapping, persist via xprofile + Xorg, web dashboard, virtual touchscreen POC
- **Phase 3** — WireGuard VPN: install, validate, save, sync, history, unsync, secret masking
- **Phase 4 ขั้นที่ 1** — OpenSSH Server: `vas install/reset --component openssh`, `--component all`, status ใน `vas check` + dashboard (OpenSshStatus dataclass), ไม่แตะ UFW
- **Phase 4 ขั้นที่ 2** — HomeOffice Theme Migration: sidebar layout, cf-* components, mobile responsive, JS-frozen identifiers preserved, CSS legacy aliases
- **Phase 4 ขั้นที่ 3** — QR Code Reader (ZKTeco QR500-BM): hidraw HID reading, SSE stream, qr.html HomeOffice UI, udev rule install/reset, `vas qr` subcommand

---

## งานที่ต้องทำ (เรียงตามลำดับก่อน-หลัง)

---

### ✅ ขั้นที่ 1 — OpenSSH Server (เสร็จแล้ว)

> Implemented via code-factory pipeline (2026-06-23)
> spec บันทึกที่ `claude-vault/wiki/projects/vas/plans/2026-06-23-openssh-install-spec.md`

- [x] `src/installers.py` — `install_openssh()`: apt install openssh-server + systemctl enable --now ssh
- [x] `src/reset.py` — `reset_openssh()` + `uninstall_openssh()`: disable only ไม่ purge
- [x] `src/cli.py` — เพิ่ม openssh ใน core_components filter + INSTALL_COMPONENTS
- [x] `src/status.py` — `OpenSshStatus` dataclass + `collect_openssh_status()` (ตรวจ sshd ไม่ใช่ ssh)
- [x] `src/server.py` — dashboard route ส่ง openssh status + อัปเดต tuples
- [x] `src/web/templates/dashboard.html` — OpenSSH + SSH Service rows ใน Remote panel
- [x] `tests/test_cli.py` — install/reset/uninstall dry-run tests (64 passed)
- [x] `tests/test_status.py` — installed/not-installed paths

---

### ✅ ขั้นที่ 2 — ย้าย UI มาใช้ HomeOffice Theme (เสร็จแล้ว)

> Implemented via code-factory pipeline (2026-06-23)
> spec บันทึกที่ `claude-vault/wiki/projects/vas/plans/2026-06-23-homeoffice-theme-migration-spec.md`

- [x] **`src/web/static/homeoffice.css`** — copy จาก `mockups/css/homeoffice.css` + legacy badge aliases + danger-action alias
- [x] **`src/web/static/js/app.js`** — copy จาก `mockups/js/app.js` (sidebar toggle, toast, confirm modal)
- [x] **`src/web/templates/base.html`** — sidebar layout ใหม่, Google Fonts, hamburger mobile, active nav state
- [x] **`src/web/templates/dashboard.html`** — cf-card panels, cf-zone badges, status-dl pattern
- [x] **`src/web/templates/display.html`** — migrate HTML (JS-frozen identifiers คงไว้ครบ 18 IDs)
- [x] **`src/web/templates/wireguard.html`** — migrate HTML (wireguard-page class + frozen IDs คงไว้ครบ)
- [x] **`src/web/templates/logs.html`** — log-split pane layout
- [x] **`src/web/templates/command_docs.html`** — commands-grid layout
- [x] **`src/web/templates/_command_list.html`** — badge warn → cf-zone-caution

---

### ✅ ขั้นที่ 3 — QR Code Reader (ZKTeco QR500-BM) (เสร็จแล้ว)

> **ทำหลัง theme migration** — UI ของ QR page ให้ใช้ `homeoffice-theme` skill สร้างตั้งแต่แรก
> อ่าน QR ผ่าน `/dev/hidraw*` — ไม่เพิ่ม dependency ใหม่ (pure Python)
> ดู research ที่ `docs/zk500/zkteco-qr500-bm-usb-hid-setup-report.md`

#### 3.1 Backend ก่อน

- [ ] **`src/config.py`** — เพิ่ม `QR_CONFIG_DIR` และ `QR_CONFIG_FILE` path constants
- [ ] **`src/qr_reader.py`** — module หลัก (สร้างใหม่)
  - `HidrawDevice` dataclass: path, name, vendor_id, product_id, exists
  - `QrReaderConfig` dataclass: device_path, vendor_id, product_id, product_name, saved_at
  - `QrLastScan` dataclass: value, scanned_at (ISO 8601)
  - `list_hidraw_devices()` — parse `/sys/class/hidraw/*/device/uevent`
  - `decode_hid_keycode(keycode, shift)` — HID keycode → ASCII
  - `load_qr_config()` / `save_qr_config()` — อ่าน/เขียน JSON
  - `QrReaderThread(threading.Thread)` — open() + read(64) loop, threading.Event สำหรับ stop, เก็บ last scan
- [ ] **`src/status.py`** — เพิ่ม `QrReaderStatus` dataclass + `collect_qr_reader_status()`
- [ ] **`src/cli.py`** — เพิ่ม `vas qr status` และ `vas qr install-udev`
- [ ] **`src/installers.py`** — เพิ่ม `install_qr_udev_rule()` เขียน `/etc/udev/rules.d/99-qr500.rules`
- [ ] **`src/reset.py`** — เพิ่ม `reset_qr_config()` ลบ config file + udev rule
- [ ] **`src/server.py`** — เพิ่ม routes ทั้งหมด
  - `GET  /qr` — render หน้า QR
  - `GET  /api/qr/devices` — list hidraw devices
  - `GET  /api/qr/config` — config ปัจจุบัน
  - `POST /api/qr/config` — บันทึก device ที่เลือก
  - `GET  /api/qr/test/stream` — SSE stream real-time (Content-Type: text/event-stream)
  - `POST /api/qr/test/stop` — หยุด stream
  - `GET  /api/qr/last` — ค่าล่าสุด + timestamp

#### 3.2 Frontend (ใช้ homeoffice-theme skill)

- [ ] **`src/web/templates/base.html`** — เพิ่ม nav link "QR Reader" ระหว่าง Display กับ VPN
- [ ] **`src/web/templates/dashboard.html`** — เพิ่ม QR status widget (badge OK/WARN + last scan)
- [ ] **`src/web/templates/qr.html`** — สร้างใหม่ด้วย homeoffice-theme skill
  - Status panel: device path ปัจจุบัน, saved_at, badge OK/WARN
  - ตาราง device list: path, vendor_id, product_id, name, สถานะ exists
  - Radio/dropdown เลือก device
  - Test panel: ปุ่ม Start/Stop + แสดง SSE stream real-time
  - Last scan: value + timestamp
  - ปุ่ม Save → POST /api/qr/config

#### 3.3 Tests + Script

- [ ] **`tests/test_qr_reader.py`** — unit tests ครอบคลุม: list_hidraw_devices, decode_hid_keycode, QrReaderThread, load/save config
- [ ] **`scripts/install.sh`** — เพิ่ม optional `--qr-udev` flag

> `pyproject.toml` — **ไม่ต้องแก้ไข** (zero new dependencies)

---

## ปัญหาที่รู้อยู่แล้ว

- [ ] **Display / Wayland** — คำสั่ง display ทั้งหมดต้องใช้ X11 เท่านั้น, Wayland แสดง WARN — ดูรายละเอียดใน `docs/research.md`
- [ ] **PM2** — `vas check` แสดง `[PM2][ERROR] Permission denied` ตอน run ด้วย sudo

---

## ปรับปรุงที่คิดไว้ในอนาคต

### Display / Touchscreen
- [ ] `display configure` — guided setup แบบ interactive ถามทีละขั้นตอน
- [ ] auto-select touch device เมื่อมีอุปกรณ์เดียว
- [ ] log viewer สำหรับ `display-session.sh` ใน web UI
- [ ] รองรับ Wayland: udev hwdb, `gnome-randr`, systemd user service

### System Checks
- [ ] ตรวจสอบ Docker daemon active (`docker info`)
- [ ] ตรวจสอบว่า user อยู่ใน `docker` group
- [ ] ตรวจสอบ disk space ก่อน install

### Packaging
- [ ] build `.deb` package เมื่อ CLI stable
- [ ] ตั้ง apt repository สำหรับ `apt upgrade`

### WireGuard
- [ ] `wireguard restore` — roll back ไปยัง history snapshot ก่อนหน้า
- [ ] นโยบาย history rotation (เก็บสูงสุด N snapshots)

### Web Dashboard
- [ ] Dark mode
