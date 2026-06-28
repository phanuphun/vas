# Source Architecture — โครงสร้าง src/

## ภาพรวม

```
src/
├── cli.py                  ← Entry point: CLI commands ทั้งหมด
├── server.py               ← Flask app: routes + API endpoints
│
├── core/                   ← Infrastructure ที่ทุก layer ใช้ร่วมกัน
│   ├── auth.py             ← User auth, roles, session
│   ├── config.py           ← Config paths (vas.db, qr config ฯลฯ)
│   ├── database.py         ← SQLite layer: schema, CRUD, connection pool
│   └── runner.py           ← CommandRunner: รัน subprocess + dry-run support
│
├── features/               ← Business features แต่ละโดเมน
│   ├── display/
│   │   └── display.py      ← xrandr/xinput, rotation, Xorg config
│   ├── mqtt/
│   │   └── client.py       ← MQTT broker client, monitor session
│   ├── packages/
│   │   ├── installers.py   ← ติดตั้ง packages (apt, script)
│   │   └── settings.py     ← Package status, install queue (SSE)
│   ├── qr/
│   │   ├── reader.py       ← ZKTeco QR reader thread, SSE stream
│   │   └── registry.py     ← QR device catalog, integrations
│   └── wireguard/
│       └── manager.py      ← WireGuard config, sync, history
│
├── services/               ← Application-level orchestration
│   ├── reset.py            ← Reset/uninstall components
│   ├── server_service.py   ← systemd service lifecycle (start/stop/status)
│   └── updater.py          ← Self-update จาก GitHub
│
├── system/                 ← Linux system primitives
│   ├── audit.py            ← System log snapshot (journalctl ฯลฯ)
│   ├── clock.py            ← System time utilities
│   ├── info.py             ← OS info helpers
│   ├── monitor.py          ← Metrics: CPU/RAM/disk/network/temp
│   ├── status.py           ← Status collectors (VPN, SSH, display ฯลฯ)
│   └── utils.py            ← Shared utilities
│
├── mcp/                    ← MCP (Model Context Protocol) server
│   ├── server.py           ← MCP server entry point
│   ├── service.py          ← MCP service lifecycle
│   └── tools/              ← MCP tool definitions
│       ├── display.py
│       ├── docker.py
│       ├── logs.py
│       ├── network.py
│       └── system.py
│
└── web/                    ← Frontend assets (Jinja2 template engine)
    ├── static/
    │   ├── app.css
    │   ├── homeoffice.css
    │   └── js/app.js       ← Sidebar, toast, confirm modal
    └── templates/
        ├── base.html
        ├── base_partial.html
        ├── dashboard.html
        ├── display.html
        ├── logs.html
        ├── monitor.html
        ├── mqtt.html
        ├── mqtt_broker_detail.html
        ├── mqtt_broker_form.html
        ├── qr.html
        ├── qr_device_zkteco_qr500.html
        ├── qr_devices.html
        ├── settings.html
        ├── users.html
        ├── wireguard.html
        ├── commands.html
        ├── command_docs.html
        ├── database.html
        └── auth/
            ├── login.html
            └── setup.html
```

---

## Layer Diagram

```
┌─────────────────────────────────────────┐
│           CLI (cli.py)                  │  ← argparse, subcommands
│           Web (server.py)               │  ← Flask routes + API
└───────────────┬─────────────────────────┘
                │
┌───────────────▼─────────────────────────┐
│           services/                     │  ← Orchestration
│   updater · server_service · reset      │
└───────────────┬─────────────────────────┘
                │
┌───────────────▼─────────────────────────┐
│           features/                     │  ← Business logic
│  display · mqtt · qr · wireguard        │
│  packages                               │
└───────────────┬─────────────────────────┘
                │
┌───────────────▼─────────────────────────┐
│           system/                       │  ← Linux primitives
│  monitor · status · audit · clock       │
└───────────────┬─────────────────────────┘
                │
┌───────────────▼─────────────────────────┐
│           core/                         │  ← Infrastructure
│  database · auth · runner · config      │
└─────────────────────────────────────────┘
```

---

## Entry Points

| Entry Point | Module | คำอธิบาย |
|---|---|---|
| `vas` | `cli.py` | CLI commands ทั้งหมด |
| `vending-auto-setup` | `cli.py` | alias ของ `vas` |
| `vending-status` | `status.py` | แสดง system status แบบ quick |
| MCP server | `mcp/server.py` | MCP protocol สำหรับ AI tools |

---

## ไฟล์หลักแต่ละ Layer

### `core/`

| ไฟล์ | หน้าที่ |
|---|---|
| `database.py` | SQLite schema, CRUD, thread-local connection pool, WAL mode |
| `auth.py` | bcrypt password hash, user CRUD, role check, session management |
| `runner.py` | `CommandRunner` — wraps subprocess, รองรับ dry-run, capture stdout/stderr |
| `config.py` | paths สำหรับ config files (`~/.config/vas/`) |

### `features/`

| ไฟล์ | หน้าที่ |
|---|---|
| `display/display.py` | `DisplayConfigurator`: apply/persist rotation, Xorg config, Wayland toggle |
| `mqtt/client.py` | `MqttClient`: connect/publish/reconnect, `MonitorSession`: live message capture |
| `qr/reader.py` | `QrReader` thread: อ่าน `/dev/hidraw*` หรือ evdev, SSE stream |
| `qr/registry.py` | device catalog, integration config (webhook/mqtt/pipe) |
| `wireguard/manager.py` | generate config template, validate, save, sync (`wg-quick`) |
| `packages/installers.py` | รัน install scripts ผ่าน subprocess |
| `packages/settings.py` | package status check, install queue (SSE streaming) |

### `services/`

| ไฟล์ | หน้าที่ |
|---|---|
| `updater.py` | `SelfUpdater`: ดาวน์โหลด tarball จาก GitHub, replace install dir, rewrite wrappers |
| `server_service.py` | install/start/stop/status Flask server เป็น systemd service |
| `reset.py` | uninstall/reset components |

### `system/`

| ไฟล์ | หน้าที่ |
|---|---|
| `monitor.py` | `collect_metrics()`: CPU/RAM/disk/temp/network/block จาก `/proc` และ `/sys` |
| `status.py` | collect status ของ VPN, SSH, display session, web server, QR reader |
| `audit.py` | journalctl snapshot, อ่าน/บันทึก log files |
| `clock.py` | system time, NTP status |
| `info.py` | OS info helpers |

### `mcp/`

| ไฟล์ | หน้าที่ |
|---|---|
| `server.py` | MCP server (stdio transport) |
| `service.py` | lifecycle management |
| `tools/*.py` | MCP tools: display, docker, logs, network, system |

---

## Data Flow: QR Scan → MQTT

```
ZKTeco QR500 device
    ↓ /dev/hidraw0 หรือ evdev
QrReader thread (features/qr/reader.py)
    ↓ last_scan attribute
SSE stream /api/qr/stream (server.py)
    ↓ poll ทุก 0.2s
    ├─→ log_qr_scan()         → DB: qr_scans table
    └─→ publish_qr_scan()     → MQTT client
                                    ↓
                               log_mqtt_event()  → DB: mqtt_events table
```

## Data Flow: vas update

```
vas update
    ↓
cli.py parse args → SelfUpdater(runner, version="latest")
    ↓
archive_url() → https://github.com/.../main.tar.gz
    ↓
urllib.request.urlretrieve() → /tmp/vending-auto-setup-update-xxx/source.tar.gz
    ↓
extract_source_archive() → validate src/cli.py exists
    ↓
shutil.rmtree(/opt/vending-auto-setup)
shutil.copytree(source → /opt/vending-auto-setup)
    ↓
install_wrappers() → เขียน /usr/local/bin/vas ใหม่
```
