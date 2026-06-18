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

---

## Wayland Research Summary

Researched 2026-06-05. Full notes in `docs/research.md`.

**TL;DR:**
- `xrandr` / `xinput` do not exist on Wayland
- Display rotation on GNOME Wayland requires D-Bus calls (`gnome-randr`)
- Touchscreen mapping has no universal Wayland equivalent; best cross-compositor option is udev hwdb (kernel-level, works on X11 too)
- For kiosk use, forcing X11 via GDM is the lowest-friction short-term solution
- Full Wayland support requires a `DisplayBackend` abstraction with compositor-specific implementations
