# TODO

## Current State

**Phase 1** — Core tool installation is complete and working:
- Git, Node.js (v22), Docker Engine, AnyDesk installable via `vas install --component all`
- Bootstrap script works on a fresh Ubuntu 22.04 machine without Git
- Self-update via `vas update` from GitHub

**Phase 2** — Display/touchscreen configuration is working for X11:
- Session type detection (X11 / Wayland / unknown)
- List touchscreen devices with xinput ID via `vas display list-touch` (udevadm-based)
- Runtime display rotation via `xrandr`
- Runtime touchscreen coordinate mapping via `xinput`
- Persist touchscreen matrix via Xorg InputClass config
- Persist display rotation via `~/.xprofile` + retry script
- Web dashboard with real-time display status bar and config file viewer
- Virtual touchscreen POC for VirtualBox testing

**Phase 3** — WireGuard VPN is implemented:
- Install, validate, save, sync, history, unsync
- Secret masking in all output by default
- Backup before overwrite, `chmod 600` on active config

---

## Known Limitations

### Display / Wayland
- All display and touchscreen commands require an **X11 session**
- Wayland session shows `WARN` in `vas check` and `vas display status`
- `xrandr`, `xinput` do not work under Wayland
- See `docs/research.md` for full Wayland research and migration options
- **Short-term workaround:** force X11 session via GDM config (no code changes needed)

### PM2
- `vas check` shows `[PM2][ERROR] Permission denied` when run as sudo
- PM2 global install is user-scoped; sudo context cannot see user PM2

---

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
- Add `display configure` — interactive guided setup (asks output, touch, rotate step by step)
- Add auto-select touch device when only one is detected
- Add log viewer for `display-session.sh` in the web UI
- Wayland support: udev hwdb for touchscreen calibration (compositor-agnostic)
- Wayland support: `gnome-randr` (GNOME) / `wlr-randr` (wlroots) backend for display rotation
- Wayland support: systemd user service as persistence mechanism (replaces `~/.xprofile`)
- Real-time touchscreen test via SSE + `python3-evdev` (reads `/dev/input/eventX` directly)

### System Checks
- Check whether Docker daemon is active (`docker info`)
- Check whether the current user is in the `docker` group
- Check available disk space before installation

### Packaging
- Build `.deb` package once CLI is stable
- Set up apt repository (S3 / Cloudflare R2 / GitHub Pages) for `apt upgrade` support
- Consider Launchpad PPA for Ubuntu ecosystem distribution

### WireGuard
- Stricter base64 key format validation without leaking the value
- `wireguard restore` command to roll back to a previous history snapshot
- History rotation policy (max N snapshots)
- Option to use `wg-quick up` instead of `systemctl restart` for environments without systemd

### Web Dashboard
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
