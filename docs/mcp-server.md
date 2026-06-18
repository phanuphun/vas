# VAS MCP Server

MCP (Model Context Protocol) server สำหรับให้ AI agent เข้ามาตรวจสอบเครื่อง Mini PC (Ubuntu 22.04) ที่ใช้เป็นตู้จำหน่ายสินค้า

**หลักการ: Read-only เท่านั้น** — AI อ่านสถานะและ log ได้ แต่ไม่มี tool ใดที่เปลี่ยนแปลงระบบ

---

## Architecture

```
Mini PC (Ubuntu 22.04)
├── vas-server.service    → Flask Web Dashboard  (port 8888)  สำหรับคน
├── vas-mcp.service       → MCP Server           (port 8899)  สำหรับ AI
└── wg-quick@wg0.service  → WireGuard VPN        (wg0)        เป็น security layer
```

MCP Server bind บน `0.0.0.0:8899` แต่ถูกป้องกันโดย WireGuard — AI agent ต้อง connect ผ่าน VPN tunnel ก่อนเสมอ ไม่ต้องทำ auth เพิ่ม

### Transport

HTTP/SSE (Server-Sent Events) — รองรับ client หลายประเภท:

| Client | วิธีเชื่อมต่อ |
|---|---|
| Claude Code CLI (local) | `mcp add http://localhost:8899` |
| Claude Code CLI (remote) | `mcp add http://<wg-ip>:8899` |
| Claude.ai web | MCP remote server via WireGuard IP |
| Custom agent / n8n | HTTP POST to tool endpoints |

### Code Structure

```
src/
├── mcp_server.py      ← entry point (FastMCP app)
├── mcp_tools/
│   ├── system.py      ← get_system_status, get_os_info, get_hardware_info
│   ├── docker.py      ← get_docker_status
│   ├── network.py     ← get_network_status, get_vpn_status
│   ├── display.py     ← get_display_status, get_usb_devices
│   ├── logs.py        ← get_logs, get_journal_logs, get_logged_in_users
│   └── process.py     ← get_process_list, get_disk_usage
└── ... (existing modules)
```

MCP tools import module เดิมทั้งหมดโดยตรง (`status.py`, `audit_log.py`, `wireguard.py`, `display.py`, `os_info.py`) — ไม่เขียนซ้ำ

---

## MCP Tools Reference

### `get_system_status`

ตรวจสอบสถานะ tools หลักที่ติดตั้งในระบบ

**Input:** ไม่มี

**Output:**
```json
{
  "tools": [
    { "name": "Git", "installed": true, "version": "git version 2.34.1", "path": "/usr/bin/git" },
    { "name": "Docker", "installed": true, "version": "Docker version 24.0.5", "path": "/usr/bin/docker" },
    { "name": "Node.js", "installed": true, "version": "v22.0.0", "path": "/usr/bin/node" },
    { "name": "PM2", "installed": false, "version": null, "path": null },
    { "name": "AnyDesk", "installed": true, "version": "anydesk 6.3.0", "path": "/usr/bin/anydesk" }
  ]
}
```

**Source:** `status.collect_status()`

---

### `get_os_info`

ข้อมูล OS และ kernel

**Input:** ไม่มี

**Output:**
```json
{
  "name": "Ubuntu 22.04.3 LTS",
  "id": "ubuntu",
  "version_id": "22.04",
  "codename": "jammy",
  "kernel": "5.15.0-91-generic",
  "machine": "x86_64",
  "python": "3.12.0"
}
```

**Source:** `os_info.collect_os_info()`

---

### `get_vpn_status`

สถานะ WireGuard VPN

**Input:**
- `interface_name` (string, optional, default: `"wg0"`) — ชื่อ WireGuard interface

**Output:**
```json
{
  "interface_name": "wg0",
  "wg_installed": true,
  "wg_version": "wireguard-tools v1.0.20210914",
  "app_config_exists": true,
  "active_config_exists": true,
  "service_enabled": "enabled",
  "service_active": "active",
  "interface_exists": true,
  "handshake_peers": 1
}
```

**Source:** `status.collect_vpn_status()`

---

### `get_display_status`

สถานะ display session, touchscreen และ Wayland/X11

**Input:** ไม่มี

**Output:**
```json
{
  "session": { "session_type": "x11", "is_x11": true, "source": "XDG_SESSION_TYPE" },
  "gdm_wayland": { "disabled": true, "value": "false" },
  "touchscreen_config": { "exists": true, "has_signature": true, "path": "/etc/X11/xorg.conf.d/99-vending-touchscreen.conf" },
  "display_config": { "exists": true, "has_signature": true },
  "display_script": { "exists": true, "executable": true, "has_signature": true }
}
```

**Source:** `status.collect_display_session_status()`, `status.collect_gdm_wayland_status()` ฯลฯ

---

### `get_usb_devices`

รายการ USB device ที่เชื่อมต่ออยู่ (รวมถึง touchscreen)

**Input:** ไม่มี

**Output:**
```json
{
  "devices": [
    { "bus": "001", "device": "003", "id": "0eef:0001", "description": "D-WAV Scientific Co., Ltd eGalax TouchScreen" },
    { "bus": "001", "device": "002", "id": "8087:0032", "description": "Intel Corp. AX210 Bluetooth" }
  ],
  "touchscreen_names": ["eGalax TouchScreen"]
}
```

**Source:** `lsusb` + `get_udevadm_touchscreen_names()`

---

### `get_docker_status`

สถานะ Docker daemon และ containers ทั้งหมด

**Input:**
- `include_logs` (bool, optional, default: `false`) — ดึง log ล่าสุดของแต่ละ container
- `log_lines` (int, optional, default: `50`) — จำนวนบรรทัด log (ถ้า include_logs=true)

**Output:**
```json
{
  "daemon_running": true,
  "containers": [
    {
      "id": "a1b2c3d4e5f6",
      "name": "vending-app",
      "image": "vending:latest",
      "status": "Up 3 hours",
      "running": true,
      "restart_count": 0,
      "ports": ["0.0.0.0:3000->3000/tcp"],
      "logs": "2026-06-18T12:00:00Z app started\n..."
    }
  ]
}
```

**Source:** `docker ps --format json`, `docker inspect`, `docker logs`

---

### `get_network_status`

สถานะ network interfaces และ connectivity

**Input:** ไม่มี

**Output:**
```json
{
  "interfaces": [
    { "name": "eth0", "state": "UP", "addresses": ["192.168.1.100/24"] },
    { "name": "wg0",  "state": "UP", "addresses": ["10.8.0.13/24"] },
    { "name": "lo",   "state": "UNKNOWN", "addresses": ["127.0.0.1/8"] }
  ],
  "default_gateway": "192.168.1.1",
  "gateway_reachable": true,
  "dns_resolving": true
}
```

**Source:** `ip -j addr`, `ip route`, `ping -c 1`

---

### `get_logs`

รายการ log snapshot ที่บันทึกไว้ และอ่าน snapshot ย้อนหลัง

**Input:**
- `snapshot_id` (string, optional) — ถ้าไม่ระบุ จะคืน list ของ snapshots ทั้งหมด

**Output (list mode):**
```json
{
  "snapshots": [
    { "id": "20260618T120000Z", "path": "...", "size": 45231 },
    { "id": "20260615T000000Z", "path": "...", "size": 43100 }
  ]
}
```

**Output (read mode):**
```json
{
  "id": "20260615T000000Z",
  "content": "# vending-auto-setup system log snapshot\n..."
}
```

**Source:** `audit_log.list_system_snapshots()`, `audit_log.read_system_snapshot()`

---

### `get_journal_logs`

ดู systemd journal โดยกรองตามเวลา หรือ service

**Input:**
- `since` (string, optional) — เช่น `"2026-06-15 12:00:00"` หรือ `"3 days ago"`
- `until` (string, optional) — เช่น `"2026-06-15 13:00:00"`
- `unit` (string, optional) — เช่น `"docker"`, `"wg-quick@wg0"`, `"vas-server"`
- `lines` (int, optional, default: `200`) — จำนวนบรรทัดสูงสุด

**Output:**
```json
{
  "query": { "since": "2026-06-15 12:00:00", "until": "2026-06-15 13:00:00", "unit": null },
  "content": "Jun 15 12:00:01 minipc systemd[1]: Started Docker Application Container Engine.\n..."
}
```

**Source:** `journalctl --since --until --unit --no-pager`

---

### `get_logged_in_users`

ดูว่าใครใช้งานเครื่องตอนไหน (ย้อนหลังได้)

**Input:**
- `history` (bool, optional, default: `false`) — ถ้า true จะดึง login history ด้วย `last`

**Output:**
```json
{
  "current_users": [
    { "user": "operator", "tty": "tty1", "from": "", "login_time": "Jun 18 08:30" }
  ],
  "login_history": [
    { "user": "operator", "tty": "tty1", "from": "", "login": "Jun 15 12:00", "logout": "Jun 15 13:45", "duration": "01:45" }
  ]
}
```

**Source:** `who`, `last -n 50`

---

### `get_web_server_status`

สถานะ VAS web dashboard service

**Input:** ไม่มี

**Output:**
```json
{
  "host": "0.0.0.0",
  "port": 8888,
  "url": "http://0.0.0.0:8888",
  "service_enabled": "enabled",
  "service_active": "active"
}
```

**Source:** `status.collect_web_server_status()`

---

### `get_remote_access_status`

สถานะ AnyDesk remote access

**Input:** ไม่มี

**Output:**
```json
{
  "anydesk_installed": true,
  "anydesk_version": "AnyDesk 6.3.0",
  "anydesk_id": "123456789",
  "anydesk_status": "online",
  "service_enabled": "enabled",
  "service_active": "active"
}
```

**Source:** `status.collect_remote_access_status()`

---

### `get_disk_usage` _(nice to have)_

พื้นที่ดิสก์

**Input:** ไม่มี

**Output:**
```json
{
  "filesystems": [
    { "filesystem": "/dev/sda1", "size": "237G", "used": "45G", "available": "180G", "use_pct": "20%", "mount": "/" }
  ]
}
```

**Source:** `df -h --output=source,size,used,avail,pcent,target`

---

### `get_process_list` _(nice to have)_

Top processes เรียงตาม CPU หรือ RAM

**Input:**
- `sort_by` (string, optional, default: `"cpu"`) — `"cpu"` หรือ `"memory"`
- `limit` (int, optional, default: `10`)

**Output:**
```json
{
  "processes": [
    { "pid": 1234, "user": "root", "cpu": 12.5, "memory": 3.2, "command": "python3 mcp_server.py" }
  ]
}
```

**Source:** `ps aux --sort=-%cpu`

---

## Deploy

### Dependencies

```toml
# pyproject.toml
[project.optional-dependencies]
mcp = ["fastmcp>=2.0", "uvicorn>=0.29"]
```

### Run

```bash
# foreground (dev)
uv run python -m src.mcp_server

# background service
sudo vas mcp start
sudo vas mcp stop
sudo vas mcp status
```

### systemd Unit

ไฟล์: `/etc/systemd/system/vas-mcp.service`

```ini
[Unit]
Description=VAS MCP Server
After=network.target vas-server.service

[Service]
Type=simple
User=<operator-user>
WorkingDirectory=/opt/vas
ExecStart=uv run python -m src.mcp_server
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Add to Claude Code

```bash
# local (บนเครื่อง Mini PC)
claude mcp add vas-local http://localhost:8899

# remote (ผ่าน WireGuard)
claude mcp add vas-remote http://10.8.0.13:8899
```

---

## Security Notes

- MCP server เป็น **read-only** — ไม่มี tool ใดที่แก้ไขระบบ
- ป้องกันโดย WireGuard VPN — ต้อง connect VPN ก่อนถึงจะเข้าถึง port 8899 ได้
- ไม่มี API key / token เพิ่มเติม (trust model: VPN = auth)
- ถ้าต้องการ expose สาธารณะในอนาคต ต้องเพิ่ม Bearer token auth ก่อน

---

## Related Files

| ไฟล์ | บทบาท |
|---|---|
| `src/mcp_server.py` | MCP entry point |
| `src/mcp_tools/` | MCP tool implementations |
| `src/status.py` | system status collectors (reused) |
| `src/audit_log.py` | log snapshot system (reused) |
| `src/wireguard.py` | WireGuard manager (reused) |
| `src/display.py` | display/touchscreen (reused) |
| `src/os_info.py` | OS info (reused) |
| `docs/mcp-server.md` | this file |
| `TODO.md` | Phase 4 checklist |
