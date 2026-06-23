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
## Phase 4 — MCP Server (AI Diagnostic Interface)

Goal: expose read-only system inspection tools as an MCP server so AI agents (Claude Code, Claude.ai, custom agents) can diagnose the vending machine remotely.

Full spec: `docs/mcp-server.md`

### Must Have
- [ ] `src/mcp_server.py` — FastMCP app entry point (HTTP/SSE, port 8899)
- [ ] Tool: `get_system_status` — wrap `status.collect_status()`
- [ ] Tool: `get_vpn_status` — wrap `status.collect_vpn_status()`
- [ ] Tool: `get_display_status` — wrap display + touchscreen status
- [ ] Tool: `get_web_server_status` — wrap `status.collect_web_server_status()`
- [ ] Tool: `get_remote_access_status` — wrap `status.collect_remote_access_status()`
- [ ] Tool: `get_os_info` — wrap `os_info.collect_os_info()`
- [ ] Tool: `get_logs` — wrap `audit_log` (list snapshots + read snapshot)
- [ ] Tool: `get_journal_logs` — journalctl with `--since` / `--until` filter
- [ ] Tool: `get_docker_status` — `docker ps`, container logs, restart count
- [ ] Tool: `get_usb_devices` — `lsusb` + udevadm (detect touchscreen USB)
- [ ] Tool: `get_logged_in_users` — `who`, `last`, `loginctl` (ใครใช้งานเมื่อเที่ยงคืน)
- [ ] Tool: `get_network_status` — `ip addr`, `ip route`, ping gateway
- [ ] systemd unit: `vas-mcp.service` (รันคู่กับ `vas-server.service`)
- [ ] บันทึก port ใน `server_service.py` หรือ `config.py`

### Nice to Have
- [ ] Tool: `get_disk_usage` — `df -h`, inode usage
- [ ] Tool: `get_process_list` — top CPU/RAM consumers (`ps aux`)
- [ ] Tool: `get_hardware_info` — CPU temp (`sensors`), RAM (`free -h`)
- [ ] MCP resource: expose `vas://status` as MCP Resource (ไม่ใช่แค่ tool)
- [ ] stdio transport mode สำหรับ Claude Code local (dual transport)

### Tool: `diagnose_touchscreen`

MCP tool สำหรับ AI agent วิเคราะห์ปัญหา touchscreen ไม่ติดแบบ step-by-step คืน structured result ต่อ step เพื่อให้ agent pinpoint สาเหตุได้โดยไม่ต้องรัน command เอง

**Input:** ไม่มี (หรือ optional `display: str = ":0"`)

**Output:** dict ของแต่ละ step พร้อม `status: ok | warn | fail` และ `detail`

**Steps ที่ต้องรัน:**

1. **kernel_usb** — `lsusb` ดูว่า OS เห็น USB device ที่มี "touch" ใน description ไหม
2. **kernel_input** — `/proc/bus/input/devices` ดูว่ามี input device ที่เป็น touchscreen (EV=b หรือ ABS flags)
3. **udevadm_detect** — `udevadm info --export-db` กรอง `ID_INPUT_TOUCHSCREEN=1` ดูว่า kernel classify เป็น touchscreen จริงไหม และได้ชื่อ device อะไร
4. **xinput_list** — `DISPLAY=:0 xinput list` ดูว่า X session เห็น device ไหม และ cross-ref กับชื่อจาก udevadm
5. **xinput_matrix** — `xinput list-props <ID>` ดู `Coordinate Transformation Matrix` ว่าถูก set ไหม (ไม่ใช่ identity matrix = มีการ apply แล้ว)
6. **xorg_config** — อ่าน `/etc/X11/xorg.conf.d/99-vending-touchscreen.conf` ดูว่า VAS เขียน config ไว้ถูกต้องไหม
7. **session_script** — ตรวจ `~/.config/vending-auto-setup/display-session.sh` ว่ามี, executable, และมี signature ของ VAS
8. **xprofile** — ตรวจ `~/.xprofile` ว่า script ถูก hook ไว้ใน session start
9. **session_type** — `loginctl show-session` ดูว่าเป็น X11 หรือ Wayland (Wayland = xinput ใช้ไม่ได้)

**Diagnosis logic:**
- ถ้า step 1–3 fail → แจ้ง "hardware/driver issue — kernel ไม่เห็น device"
- ถ้า step 4 fail แต่ 1–3 pass → แจ้ง "X session ไม่เห็น device — ตรวจ DISPLAY env หรือ Xorg permission"
- ถ้า step 5 fail (identity matrix) → แจ้ง "touch ยังไม่ถูก map — ให้รัน `vas display apply`"
- ถ้า step 9 เป็น Wayland → แจ้ง "session เป็น Wayland ซึ่ง xinput ไม่รองรับ — ให้รัน `sudo vas display disable-wayland` แล้ว reboot"

**ไฟล์ที่ควร implement:** `src/mcp_tools/display.py` เพิ่ม function `diagnose_touchscreen()` แล้ว register ใน `src/mcp_server.py`

### Tool: `diagnose_remote_access`

MCP tool สำหรับ AI agent วิเคราะห์ปัญหา AnyDesk เข้าไม่ได้ คืน structured result ต่อ step

**Input:** ไม่มี

**Output:** dict ของแต่ละ step พร้อม `status: ok | warn | fail` และ `detail`

**Steps:**

1. **service_active** — `systemctl is-active anydesk` — service ขึ้นไหม
2. **anydesk_id** — `anydesk --get-id` — อ่าน AnyDesk ID ได้ไหม
3. **socket_active** — `ss -tnp | grep anydesk` — port/socket active ไหม
4. **internet_reachable** — `ping -c 3 -W 2 8.8.8.8` — internet ออกได้ไหม
5. **default_route** — `ip route show default` — default route มีไหม
6. **recent_logs** — `journalctl -u anydesk -n 30 --no-pager` — log ล่าสุดมี error ไหม

**Diagnosis logic:**
- step 1 fail → แจ้ง "AnyDesk service ไม่ทำงาน — ให้รัน `sudo systemctl restart anydesk`"
- step 2 fail → แจ้ง "อ่าน ID ไม่ได้ — service อาจยังไม่พร้อม หรือ license มีปัญหา"
- step 4–5 fail → แจ้ง "internet ออกไม่ได้ — ตรวจ network/VPN ก่อน AnyDesk จะเชื่อมต่อไม่ได้"

**ไฟล์ที่ควร implement:** `src/mcp_tools/system.py` เพิ่ม function `diagnose_remote_access()` แล้ว register ใน `src/mcp_server.py`

### Tool: `diagnose_display`

MCP tool สำหรับ AI agent วิเคราะห์ปัญหาหน้าจอไม่แสดงผลหรือ rotation ผิด (แยกจาก `diagnose_touchscreen` ที่เน้น input mapping)

**Input:** ไม่มี (หรือ optional `display: str = ":0"`)

**Output:** dict ของแต่ละ step พร้อม `status: ok | warn | fail` และ `detail`

**Steps:**

1. **session_type** — `loginctl show-session ... -p Type --value` — X11 หรือ Wayland
2. **gdm_active** — `systemctl is-active gdm` — GDM ขึ้นไหม
3. **wayland_disabled** — `cat /etc/gdm3/custom.conf` — Wayland ถูก disable ไหม
4. **xrandr_outputs** — `DISPLAY=:0 xrandr --query` — output connected ไหม และ resolution ถูกต้องไหม
5. **xprofile_hook** — `cat ~/.xprofile` — session script ถูก hook ไหม
6. **session_script** — ตรวจ `~/.config/vending-auto-setup/display-session.sh` ว่ามี, executable, และมี VAS signature
7. **xorg_config** — `cat /etc/X11/xorg.conf.d/99-vending-touchscreen.conf` — Xorg config ของ VAS ถูกต้องไหม
8. **gdm_boot_logs** — `journalctl -b -u gdm --no-pager -n 30` — GDM boot errors

**Diagnosis logic:**
- step 1 เป็น Wayland → แจ้ง "session เป็น Wayland — ให้รัน `sudo vas display disable-wayland` แล้ว reboot"
- step 2 fail → แจ้ง "GDM ไม่ทำงาน — display manager ไม่ขึ้น ให้ตรวจ `journalctl -u gdm`"
- step 4 ไม่มี connected output → แจ้ง "xrandr ไม่เห็น display — ตรวจสาย HDMI/DisplayPort หรือ driver"
- step 5–6 fail → แจ้ง "session script ไม่ถูก hook — ให้รัน `vas display persist-session` ใหม่"

**ไฟล์ที่ควร implement:** `src/mcp_tools/display.py` เพิ่ม function `diagnose_display()` แล้ว register ใน `src/mcp_server.py`

---

## Improvements to Consider

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
- Real-time touchscreen event stream (SSE + evdev) in the display test panel
- Dark mode support

### Server & Testing
- ใช้ `gunicorn` แทน Flask dev server สำหรับ production (`gunicorn "server:create_app()" --bind 0.0.0.0:8888`) — Flask dev server เป็น single-threaded และไม่ graceful บน crash
- เพิ่ม Basic Auth ให้ web dashboard (port 8888) — ปัจจุบันไม่มี auth ใดๆ เลย ใครใน network เดียวกันเข้าได้ทันที
- เพิ่ม `pytest-cov` ใน dev deps เพื่อดู test coverage (`pytest --cov=src --cov-report=term-missing`)

---

## Wayland Research Summary

Researched 2026-06-05. Full notes in `docs/research.md`.

**TL;DR:**
- `xrandr` / `xinput` do not exist on Wayland
- Display rotation on GNOME Wayland requires D-Bus calls (`gnome-randr`)
- Touchscreen mapping has no universal Wayland equivalent; best cross-compositor option is udev hwdb (kernel-level, works on X11 too)
- For kiosk use, forcing X11 via GDM is the lowest-friction short-term solution
- Full Wayland support requires a `DisplayBackend` abstraction with compositor-specific implementations
