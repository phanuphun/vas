# VAS (Vending Auto Setup) — ภาพรวมระบบ

## คืออะไร

**VAS** (Vending Auto Setup) คือ toolkit สำหรับเตรียมและจัดการ **Ubuntu 22.04 LTS vending machines** ประกอบด้วย:

- **CLI** — ติดตั้ง/จัดการ software บนเครื่อง
- **Web Dashboard** — UI สำหรับดูสถานะและ configure ระบบ
- **QR Reader** — อ่าน QR code จาก ZKTeco QR500-BM และ publish ผ่าน MQTT
- **WireGuard** — จัดการ VPN configuration lifecycle
- **MCP Server** — AI diagnostic interface สำหรับ Claude/AI agents

---

## โครงสร้าง Codebase

```
vas/
├── src/                        # Source code หลัก
│   ├── cli.py                  # CLI entry point (argparse)
│   ├── server.py               # Flask web server + routes
│   ├── server_service.py       # systemd service management
│   ├── mcp_server.py           # FastMCP server
│   ├── mcp_service.py          # MCP systemd service management
│   ├── mcp_tools/              # MCP tool implementations
│   │   ├── system.py           # OS/tool status tools
│   │   ├── network.py          # VPN/network tools
│   │   ├── display.py          # Display/USB tools
│   │   ├── docker.py           # Docker tools
│   │   └── logs.py             # Log/journal tools
│   ├── qr_reader.py            # QR reader (HID raw + evdev)
│   ├── mqtt_client.py          # MQTT publish client
│   ├── wireguard.py            # WireGuard config management
│   ├── display.py              # Display/touchscreen configurator
│   ├── status.py               # Status collection + data classes
│   ├── audit_log.py            # System log snapshots
│   ├── clock.py                # Clock drift detection + fix
│   ├── runner.py               # Command runner (dry-run + progress)
│   ├── config.py               # App constants + path helpers
│   ├── installers.py           # Phase-1 installation logic
│   ├── reset.py                # Uninstall/reset logic
│   ├── updater.py              # Self-update from GitHub
│   ├── os_info.py              # OS information collector
│   └── system.py               # require_linux/require_root guards
│   └── web/
│       ├── templates/          # Jinja2 HTML templates
│       └── static/             # CSS + JS assets
├── tests/                      # Pytest test suite
├── docs/                       # Documentation (ไฟล์นี้และไฟล์อื่นๆ)
└── pyproject.toml              # Project metadata + dependencies
```

---

## Subsystem Map

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACES                          │
│                                                                 │
│  CLI (vas)              Web Dashboard            MCP Server     │
│  src/cli.py             src/server.py            src/mcp_server │
│  port: n/a              port: 8080               port: 8899     │
└────────┬────────────────────────┬────────────────────┬──────────┘
         │                        │                    │
         ▼                        ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                         CORE MODULES                            │
│                                                                 │
│  qr_reader.py      wireguard.py      mqtt_client.py            │
│  ZKTeco QR500-BM   WG config mgmt    paho-mqtt publish         │
│                                                                 │
│  display.py        status.py         audit_log.py              │
│  X11 config        status collect    log snapshots             │
│                                                                 │
│  runner.py         clock.py          updater.py                │
│  cmd execution     clock drift fix   self-update               │
└─────────────────────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
┌──────────────────┐    ┌──────────────────────────────────────┐
│   SYSTEM         │    │            CONFIG FILES              │
│                  │    │                                      │
│ /etc/wireguard/  │    │ ~/.config/vas/qr_config.json         │
│ /etc/systemd/    │    │ <root>/config.json (MQTT)            │
│ /etc/udev/       │    │ ~/.config/vending-auto-setup/wireguard/│
│ /etc/gdm3/       │    │ ~/.config/vending-auto-setup/logs/    │
│ /etc/X11/        │    │ ~/.xprofile                          │
└──────────────────┘    └──────────────────────────────────────┘
```

---

## Data Flow: QR Scan → MQTT

```
1. USB plug-in  →  ZKTeco QR500-BM
2. auto-detect  →  evdev (/dev/input/event*) หรือ hidraw (/dev/hidraw*)
3. QrReaderThread / EvdevQrReaderThread  →  last_scan (str)
4. SSE Stream (/api/qr/stream)  →  poll ทุก 0.2 วิ
5. new scan detected  →  SSE event: scan
6. publish_qr_scan()  →  MQTT broker
   payload: {"scan": "...", "device": "...", "ts": "..."}
```

---

## Service Architecture

VAS รัน 2 systemd services:

| Service | Unit | Port | Command |
|---------|------|------|---------|
| Web Dashboard | `vending-auto-setup-server.service` | 8080 | `vas server run` |
| MCP Server | `vending-auto-setup-mcp.service` | 8899 | `vas mcp run` |

---

## Installation

### Binary Wrappers
หลัง install มี 3 wrappers ใน `/usr/local/bin/`:
- `vending-auto-setup` → `python3 -m cli`
- `vas` → `python3 -m cli` (shorthand)
- `vending-status` → `python3 -m status`

ทั้งหมดใช้ `PYTHONPATH=/opt/vending-auto-setup/src`

### Install Directory
Default: `/opt/vending-auto-setup/`

---

## เอกสารแยกตาม Subsystem

| หัวข้อ | ไฟล์ |
|--------|------|
| QR Reader | [docs/qr/qr-reader.md](qr/qr-reader.md) |
| Web Server & API | [docs/server/server.md](server/server.md) |
| WireGuard VPN | [docs/networking/wireguard.md](networking/wireguard.md) |
| MQTT Client | [docs/networking/mqtt.md](networking/mqtt.md) |
| CLI Commands | [docs/cli/cli.md](cli/cli.md) |
| System Services | [docs/system/system-services.md](system/system-services.md) |
| MCP Server | [docs/mcp/mcp.md](mcp/mcp.md) |

---

## ข้อกำหนดระบบ

| ข้อกำหนด | รายละเอียด |
|----------|-----------|
| OS | Ubuntu 22.04 LTS (Jammy) |
| Python | 3.10+ |
| Hardware | ZKTeco QR500-BM (USB HID) |
| Optional | `python3-evdev` (evdev mode), `python3-paho-mqtt` (MQTT), `fastmcp` + `uvicorn` (MCP) |

---

## Quick Start

```bash
# ติดตั้ง tools หลัก
sudo vas install --component all

# ตรวจสถานะ
vas check

# เริ่ม web dashboard
sudo vas server start --host 0.0.0.0 --port 8080

# เปิดใน browser
# http://<machine-ip>:8080

# เริ่ม QR reader (auto-detect device)
vas qr start

# ตั้งค่า MQTT
vas mqtt config --broker-url mqtts://broker.example.com:8883 --enable

# ตั้งค่า WireGuard
vas wireguard init-config --name wg0 --output ./wg0.conf
# (แก้ไข wg0.conf)
vas wireguard save --name wg0 --config ./wg0.conf
sudo vas wireguard sync --name wg0
```
