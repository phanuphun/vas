# Flask Web Server — เอกสารระบบ

ไฟล์หลัก: `src/server.py`, `src/server_service.py`

## ภาพรวม

VAS Web Dashboard คือ Flask HTTP server ที่ให้ UI และ REST API สำหรับจัดการ vending machine ทั้งหมด รองรับการรัน 2 วิธี:

1. **Foreground** (`vas server run`) — รันใน process ปัจจุบัน
2. **Background service** (`sudo vas server start`) — รันเป็น systemd unit

Default: `http://127.0.0.1:8080`

---

## สร้าง Flask App

### `create_app() → Flask`

ฟังก์ชันหลักที่สร้างและ configure Flask application:
- `template_folder` = `src/web/templates/`
- `static_folder` = `src/web/static/`
- เพิ่ม Jinja global `vpn_connection_label`
- ลงทะเบียน `atexit` hook สำหรับ `stop_reader()` และ `stop_mqtt()`
- Auto-start QR reader และ MQTT client เมื่อ boot

### `run_server(host, port, debug) → None`
เรียก `create_app().run(...)` โดยตรง

---

## Routes ทั้งหมด

### หน้า UI

| Method | Path | Template | คำอธิบาย |
|--------|------|----------|----------|
| `GET` | `/` | `dashboard.html` | หน้าหลัก — สถานะระบบทั้งหมด |
| `GET` | `/install` | `commands.html` | รายการ install commands |
| `GET` | `/reset` | `commands.html` | รายการ reset/uninstall commands |
| `GET` | `/wireguard` | `wireguard.html` | จัดการ WireGuard VPN |
| `GET` | `/logs` | `logs.html` | รายการ system log snapshots |
| `GET` | `/commands` | `command_docs.html` | คู่มือ commands ทั้งหมด |
| `GET` | `/display` | `display.html` | จัดการ display และ touchscreen |
| `GET` | `/qr` | `qr.html` | จัดการ QR reader |
| `GET` | `/mqtt` | `mqtt.html` | จัดการ MQTT client |
| `GET` | `/health` | — | Health check (JSON `{"status":"ok"}`) |

---

### Dashboard (`GET /`)

ส่ง context ต่อไปนี้ไปยัง template:
- `tools` — ToolStatus ของ Git, Node, npm, PM2, Docker, AnyDesk
- `session` — DisplaySessionStatus (X11/Wayland)
- `display_config` — DisplaySessionConfigStatus (`~/.xprofile`)
- `display_script` — DisplaySessionScriptStatus
- `touchscreen` — XorgTouchscreenConfigStatus
- `remote` — RemoteAccessStatus (AnyDesk)
- `openssh` — OpenSshStatus
- `vpn` — VpnStatus (WireGuard wg0)
- `web_server` — WebServerStatus
- `qr_reader` — QrReaderStatus

---

### QR Reader API

| Method | Path | คำอธิบาย |
|--------|------|----------|
| `GET` | `/api/qr/last-scan` | ค่า scan ล่าสุด |
| `POST` | `/api/qr/start` | Start reader (body: `{"device":"..."}`) |
| `POST` | `/api/qr/stop` | Stop reader |
| `GET` | `/api/qr/config` | QR config ปัจจุบัน |
| `POST` | `/api/qr/config` | บันทึก config (body: `{"device_path":"..."}`) |
| `GET` | `/api/qr/stream` | SSE stream (real-time scan events) |

**SSE Stream** (`/api/qr/stream`):
- poll `reader.last_scan` ทุก `0.2` วินาที
- ส่ง `event: scan` เมื่อค่าเปลี่ยน
- ส่ง `event: status` เมื่อ reader state เปลี่ยน
- ส่ง `event: heartbeat` ทุก `5` วินาที
- Auto-restart reader ทุก `8` วินาที ถ้า reader ตาย
- Publish ออก MQTT ทันทีเมื่อ scan ใหม่

---

### MQTT API

| Method | Path | คำอธิบาย |
|--------|------|----------|
| `GET` | `/api/mqtt/status` | สถานะ MQTT client |
| `POST` | `/api/mqtt/config` | บันทึก config และ restart client |
| `POST` | `/api/mqtt/test` | Publish test message |
| `POST` | `/api/mqtt/disconnect` | ตัดการเชื่อมต่อ |

---

### WireGuard API

| Method | Path | คำอธิบาย |
|--------|------|----------|
| `GET` | `/api/wireguard/config` | อ่าน saved config (query: `?name=wg0`) |
| `POST` | `/api/wireguard/config` | บันทึก config |
| `DELETE` | `/api/wireguard/config` | ลบ saved config |
| `POST` | `/api/wireguard/template` | สร้าง config template |
| `POST` | `/api/wireguard/validate` | Validate config content |
| `POST` | `/api/wireguard/action` | Execute action: `sync` หรือ `unsync` |
| `GET` | `/api/wireguard/history` | รายการ history snapshots |
| `GET` | `/api/wireguard/history/<id>` | อ่าน history snapshot |
| `DELETE` | `/api/wireguard/history/<id>` | ลบ history snapshot |

---

### Display API

| Method | Path | คำอธิบาย |
|--------|------|----------|
| `GET` | `/api/display/devices` | รายการ xrandr outputs และ touchscreens |
| `GET` | `/api/display/config-content` | อ่าน config file (query: `?key=xprofile`) |
| `POST` | `/api/display/apply` | Apply display rotation + touchscreen mapping |
| `POST` | `/api/display/wayland` | Enable/disable GDM Wayland |

**`/api/display/apply` Payload:**
```json
{
  "output": "Virtual1",
  "touch": "Vending Virtual Touchscreen",
  "rotate": "normal",
  "display": ":0",
  "persistSession": true,
  "persistXorg": false
}
```

**Config keys ที่ `/api/display/config-content` รองรับ:**
- `gdm_custom` — `/etc/gdm3/custom.conf`
- `xprofile` — `~/.xprofile`
- `display_script` — `~/.config/vending-auto-setup/display-session.sh`
- `xorg_touchscreen` — `/etc/X11/xorg.conf.d/99-vending-touchscreen.conf`

---

### Logs API

| Method | Path | คำอธิบาย |
|--------|------|----------|
| `GET` | `/api/logs/system` | รายการ system log snapshots |
| `POST` | `/api/logs/system/snapshot` | สร้าง snapshot ใหม่ |
| `GET` | `/api/logs/system/<snapshot_id>` | อ่าน snapshot |

---

## Auto-Start Behaviors

ใน `create_app()` มีการ auto-start:

```python
# 1. QR Reader — start ทันทีถ้ามี device ต่ออยู่
try:
    if get_reader() is None:
        start_reader()
except Exception:
    pass  # ยังไม่มี device — ข้ามไป

# 2. MQTT — start ถ้า enabled ใน config
cfg = load_mqtt_config()
if cfg.enabled:
    start_mqtt(cfg)
```

---

## Helper Functions

### `collect_display_devices(x_display) → DisplayDevices`
รวม outputs จาก `xrandr --query` และ touchscreen devices จาก `udevadm + xinput`

โดยถ้า xrandr ไม่ได้รับข้อมูล (เช่น รัน sudo) จะลอง `runuser -u <desktop_user>` แทน

### `DisplayCommandRunner`
Subclass ของ `CommandRunner` ที่ wrap `xrandr`/`xinput` ด้วย `runuser` โดยอัตโนมัติเมื่อ process เป็น root

### `_desktop_user() → str | None`
หา desktop user ที่ควรรัน X commands:
1. ตรวจ `SUDO_USER` environment variable
2. Fallback: `Path.home().name`

### `vpn_connection_label(vpn: VpnStatus) → str`
สร้าง label แสดงสถานะ VPN:
- `"Connected with N peer(s)"` — มี handshake
- `"Active, waiting for peer handshake"` — active แต่ยังไม่ได้ handshake
- `"Service <status>"` — service ไม่ active

---

## Server Service (`server_service.py`)

### ค่า Constants

```python
SERVICE_NAME = "vending-auto-setup-server"
SERVICE_UNIT = "vending-auto-setup-server.service"
SERVICE_PATH = Path("/etc/systemd/system/vending-auto-setup-server.service")
ENV_PATH     = Path("/etc/default/vending-auto-setup-server")
```

### `ServerConfig`
```python
@dataclass(frozen=True)
class ServerConfig:
    host: str   # default: "127.0.0.1"
    port: int   # default: 8080
    url: str    # property: f"http://{host}:{port}"
```

### `ServerServiceManager`

| Method | คำอธิบาย |
|--------|----------|
| `install(config)` | ติดตั้ง systemd unit และ env file |
| `start(config)` | install + `systemctl restart` |
| `stop()` | `systemctl disable --now` |
| `status()` | แสดงผล `systemctl status` |

### `render_service_file() → str`
สร้าง systemd unit content:
```ini
[Unit]
Description=Vending Auto Setup dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/vas server run --host ${VAS_SERVER_HOST} --port ${VAS_SERVER_PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### `render_env_file(config) → str`
สร้าง `/etc/default/vending-auto-setup-server`:
```bash
VAS_SERVER_HOST=127.0.0.1
VAS_SERVER_PORT=8080
```

---

## Command Previews

Server สร้าง `CommandPreview` objects สำหรับแสดงใน `/commands` และ `/install`:

### `build_install_commands()`
Components: `all`, `git`, `node`, `docker`, `wireguard`, `anydesk`, `openssh`, `qr-udev`
→ Command: `sudo vas install --component <component>`

### `build_reset_commands()`
Actions: `uninstall`, `reset` × components
→ Commands: `sudo vas uninstall --component <c>`, `sudo vas reset --component <c>`

### `build_wireguard_commands()`
ดู `WIREGUARD_ACTIONS` constant ใน `server.py`

### `build_display_commands()`
ดู `DISPLAY_ACTIONS` constant ใน `server.py`

### `build_server_commands()`
Start/stop/status ของ dashboard service

---

## Security Notes

- API `/api/display/config-content` มี allowlist (`_allowed_config_paths()`) กำหนดไฟล์ที่อ่านได้
- WireGuard interface name ผ่าน `sanitize_interface_name()` — รับเฉพาะ `[A-Za-z0-9_.-]+`
- WireGuard history ID ผ่าน `sanitize_history_id()` — รับเฉพาะ `[A-Za-z0-9_.-]+`
- Private key content ผ่าน `mask_secrets()` ก่อนส่งไปยัง client
