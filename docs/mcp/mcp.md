# MCP Server — เอกสารระบบ

ไฟล์หลัก: `src/mcp_server.py`, `src/mcp_service.py`, `src/mcp_tools/`

## ภาพรวม

VAS MCP Server คือ **read-only AI diagnostic interface** ที่ expose ข้อมูลสถานะเครื่องผ่าน [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) โดยใช้ [FastMCP](https://github.com/jlowin/fastmcp) framework

ออกแบบมาสำหรับให้ Claude/AI agents สามารถตรวจสอบสถานะ vending machine ได้โดยตรง

**Default:** `http://0.0.0.0:8899` (SSE transport)

**Dependencies:** `fastmcp`, `uvicorn`

---

## Architecture

```
mcp_server.py  — entry point, mounts all sub-MCPs
    │
    ├── mcp_tools/system.py   — tools: get_system_status, get_os_info, get_web_server_status, get_remote_access_status
    ├── mcp_tools/network.py  — tools: get_vpn_status, get_network_status
    ├── mcp_tools/display.py  — tools: get_display_status, get_usb_devices
    ├── mcp_tools/docker.py   — tools: get_docker_status
    └── mcp_tools/logs.py     — tools: get_logs, get_journal_logs, get_logged_in_users
```

---

## `mcp_server.py`

### Setup
```python
from fastmcp import FastMCP
mcp = FastMCP("vas-mcp")

mcp.mount(system.mcp)
mcp.mount(network.mcp)
mcp.mount(display.mcp)
mcp.mount(docker.mcp)
mcp.mount(logs.mcp)
```

### `run_server(host, port) → None`
รัน FastMCP ด้วย SSE transport:
```python
mcp.run(transport="sse", host=host, port=port)
```

---

## MCP Tools ทั้งหมด

### System Tools (`mcp_tools/system.py`)

#### `get_system_status() → dict`
ตรวจสอบ tools หลักที่ติดตั้ง:
```json
{
  "tools": [
    {"name": "Git", "installed": true, "version": "git version 2.43.0", "path": "/usr/bin/git"},
    {"name": "Node.js", "installed": true, "version": "v22.0.0", "path": "/usr/bin/node"},
    {"name": "npm", "installed": true, "version": "10.0.0", "path": "/usr/bin/npm"},
    {"name": "PM2", "installed": false, "version": null, "path": null},
    {"name": "Docker", "installed": true, "version": "Docker version 24.0.0", "path": "/usr/bin/docker"},
    {"name": "AnyDesk", "installed": false, "version": null, "path": null}
  ]
}
```

#### `get_os_info() → dict`
ข้อมูล OS จาก `/etc/os-release` และ `uname`:
```json
{
  "os_name": "Ubuntu 22.04.3 LTS",
  "kernel": "5.15.0-91-generic",
  "architecture": "x86_64",
  "hostname": "vending-001"
}
```

#### `get_web_server_status() → dict`
สถานะ VAS web dashboard:
```json
{
  "host": "127.0.0.1",
  "port": 8080,
  "url": "http://127.0.0.1:8080",
  "service_enabled": "enabled",
  "service_active": "active"
}
```

#### `get_remote_access_status() → dict`
สถานะ AnyDesk:
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

---

### Network Tools (`mcp_tools/network.py`)

#### `get_vpn_status(interface_name="wg0") → dict`
สถานะ WireGuard VPN:
```json
{
  "interface_name": "wg0",
  "wg_installed": true,
  "wg_version": "wireguard-tools v1.0.20210914",
  "app_config_path": "~/.config/vending-auto-setup/wireguard/configs/wg0.conf",
  "app_config_exists": true,
  "active_config_path": "/etc/wireguard/wg0.conf",
  "active_config_exists": true,
  "service_enabled": "enabled",
  "service_active": "active",
  "interface_exists": true,
  "handshake_peers": 1
}
```

#### `get_network_status() → dict`
สถานะ network:
```json
{
  "interfaces": [
    {"name": "eth0", "state": "UP", "addresses": ["192.168.1.100/24"]},
    {"name": "wg0",  "state": "UP", "addresses": ["10.8.0.13/24"]}
  ],
  "default_gateway": "192.168.1.1",
  "gateway_reachable": true,
  "dns_resolving": true
}
```

**Implementation:**
- `interfaces`: `ip -j addr show` → JSON
- `default_gateway`: `ip route show default` → parse `via <ip>`
- `gateway_reachable`: `ping -c 1 -W 2 <gateway>`
- `dns_resolving`: `socket.getaddrinfo("google.com", 80)`

---

### Display Tools (`mcp_tools/display.py`)

#### `get_display_status() → dict`
สถานะ display และ touchscreen config:
```json
{
  "session": {"session_type": "x11", "is_x11": true, "source": "XDG_SESSION_TYPE"},
  "gdm_wayland": {"exists": true, "readable": true, "disabled": true, "value": "false"},
  "touchscreen_config": {"exists": true, "has_signature": true},
  "display_config": {"exists": true, "has_signature": true},
  "display_script": {"exists": true, "has_signature": true, "executable": true}
}
```

#### `get_usb_devices() → dict`
USB devices ที่เชื่อมต่อ:
```json
{
  "devices": [
    {"bus": "001", "device": "003", "id": "0416:5020", "description": "ZKTeco QR500-BM"}
  ],
  "touchscreen_names": ["Vending Virtual Touchscreen"]
}
```

**Implementation:**
- `devices`: parse `lsusb` output
- `touchscreen_names`: parse `udevadm info --export-db` หา blocks ที่มี `ID_INPUT_TOUCHSCREEN=1`

---

### Docker Tools (`mcp_tools/docker.py`)

#### `get_docker_status(include_logs=False, log_lines=50) → dict`
สถานะ Docker daemon และ containers:
```json
{
  "daemon_running": true,
  "containers": [
    {
      "id": "abc123",
      "name": "vending-app",
      "image": "node:22-alpine",
      "status": "Up 3 hours",
      "running": true,
      "restart_count": 0,
      "ports": ["0.0.0.0:3000->3000/tcp"],
      "logs": "..."  // เฉพาะถ้า include_logs=true
    }
  ]
}
```

**Implementation:**
- `docker info` → ตรวจ daemon
- `docker ps -a --format "{{json .}}"` → container list
- `docker inspect --format "{{.RestartCount}}"` → restart count
- `docker logs --tail N` → container logs (optional)

---

### Logs Tools (`mcp_tools/logs.py`)

#### `get_logs(snapshot_id=None) → dict`
- `snapshot_id=None` → รายการ snapshots: `{"snapshots": [{"id":...,"path":...,"size":...}]}`
- `snapshot_id="20260627T103000Z"` → เนื้อหา snapshot: `{"id":...,"path":...,"content":"..."}`

#### `get_journal_logs(since=None, until=None, unit=None, lines=200) → dict`
ดู systemd journal:
```json
{
  "query": {"since": "3 days ago", "until": null, "unit": "docker", "lines": 200},
  "content": "Jun 27 10:30:00 machine docker[1234]: ..."
}
```

**Parameters:**
- `since`, `until`: เช่น `"2026-06-15 12:00:00"` หรือ `"3 days ago"`
- `unit`: เช่น `"docker"`, `"wg-quick@wg0"`, `"vending-auto-setup-server"`
- `lines`: max 2000

#### `get_logged_in_users(history=False) → dict`
```json
{
  "current_users": [
    {"user": "ubuntu", "tty": "pts/0", "from": "192.168.1.50", "login_time": "Jun 27 10:00"}
  ],
  "login_history": [...]  // เฉพาะถ้า history=true
}
```

**Implementation:**
- `current_users`: parse `who` output
- `login_history`: parse `last -n 50` output (ถ้า `history=True`)

---

## MCP Service Manager (`mcp_service.py`)

### Constants
```python
MCP_PORT         = 8899
MCP_SERVICE_NAME = "vending-auto-setup-mcp"
MCP_SERVICE_UNIT = "vending-auto-setup-mcp.service"
MCP_SERVICE_PATH = Path("/etc/systemd/system/vending-auto-setup-mcp.service")
MCP_BIN          = "/usr/local/bin/vas"
```

### `McpConfig`
```python
@dataclass(frozen=True)
class McpConfig:
    host: str   # default: "0.0.0.0"
    port: int   # default: 8899
```

### `McpServiceManager`

| Method | คำอธิบาย |
|--------|----------|
| `install(config)` | ติดตั้ง runtime packages + systemd unit |
| `start(config)` | install + `systemctl restart` |
| `stop()` | `systemctl disable --now` |
| `status()` | แสดง `systemctl status` |

### `render_mcp_service_file(config) → str`
```ini
[Unit]
Description=Vending Auto Setup MCP server
After=network.target vending-auto-setup-server.service

[Service]
Type=simple
ExecStart=/usr/local/bin/vas mcp run --host 0.0.0.0 --port 8899
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### `_ensure_pip(runner)`
Bootstrap pip ถ้าไม่มี:
1. ลอง `python3 -m ensurepip --upgrade`
2. Fallback: `apt-get install python3-pip`

---

## ติดตั้งและรัน

```bash
# ติดตั้ง dependencies
uv pip install -e '.[mcp]'
# หรือ
pip install fastmcp uvicorn

# รัน foreground
vas mcp run --host 0.0.0.0 --port 8899

# รัน background service
sudo vas mcp start --host 0.0.0.0 --port 8899

# ดูสถานะ
vas mcp status

# หยุด
sudo vas mcp stop
```

---

## Error Handling

ทุก tool wrap body ด้วย try/except:
```python
@mcp.tool()
def get_system_status() -> dict:
    try:
        ...
        return {...}
    except Exception as e:
        return {"error": str(e)}
```

ทำให้ไม่มี tool ไหน crash MCP server แม้ระบบปัญหา
