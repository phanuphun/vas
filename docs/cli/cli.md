# CLI — เอกสารคำสั่ง

ไฟล์หลัก: `src/cli.py`  
Entry point: `python3 -m cli` หรือผ่าน wrapper `/usr/local/bin/vas`

## ภาพรวม

CLI (`vas`) เป็น command-line interface หลักของระบบ VAS ใช้ `argparse` และมีโครงสร้างเป็น subcommands

```
vas [--dry-run] [--version] <command> [subcommand] [options]
```

**Global flags:**
- `--dry-run` — แสดงคำสั่งที่จะรันโดยไม่ execute จริง
- `--version` — แสดง version (`0.1.0`)

---

## Commands ทั้งหมด

### `vas check`
แสดงสถานะ tools ทั้งหมด (Git, Node, npm, PM2, Docker, AnyDesk, WireGuard, etc.)

```bash
vas check
```

เรียก `print_status()` จาก `status.py`

---

### `vas about-os`
แสดงข้อมูล OS และ kernel

```bash
vas about-os
```

เรียก `print_os_info()` จาก `os_info.py`

---

### `vas version`
แสดง version string

```bash
vas version
```

---

### `vas update`
อัปเดต CLI source จาก GitHub

```bash
sudo vas update [--repo <owner/repo>] [--version <tag|latest>]
```

| Flag | Default | คำอธิบาย |
|------|---------|----------|
| `--repo` | `phanuphun/vending-auto-setup` | GitHub repo |
| `--version` | `latest` | Git tag หรือ `latest` (= main branch) |

**ต้องรัน root** ขั้นตอน:
1. Download `.tar.gz` จาก GitHub
2. Extract ใน temp directory
3. Replace `/opt/vending-auto-setup/`
4. เขียน wrapper scripts ใน `/usr/local/bin/`

---

### `vas install`
ติดตั้ง components บน Ubuntu 22.04

```bash
sudo vas install [--component <component>] [--node-major 22] [--docker-version ...] [--git-version ...]
```

| Component | คำอธิบาย |
|-----------|----------|
| `git` | Git version control |
| `node` | Node.js (default major 22) |
| `docker` | Docker Engine + CLI + plugins |
| `wireguard` | WireGuard VPN |
| `anydesk` | AnyDesk remote desktop |
| `openssh` | OpenSSH server |
| `qr-udev` | udev rule สำหรับ QR reader |
| `all` | ทุก component |

- `--component` สามารถระบุซ้ำได้ (append)
- ถ้าไม่ระบุ → default: `node`, `docker`, `git`
- แสดง progress percentage ขณะติดตั้ง

---

### `vas uninstall`
ถอนการติดตั้ง components

```bash
sudo vas uninstall --component <component> [--wireguard-name wg0]
```

---

### `vas reset`
ถอนการติดตั้งและลบ config files ที่ VAS จัดการ

```bash
sudo vas reset --component <component> [--wireguard-name wg0]
```

---

### `vas server`
จัดการ Flask web dashboard

#### `vas server run`
รัน dashboard ใน foreground

```bash
vas server run [--host 127.0.0.1] [--port 8080] [--debug]
```

#### `vas server start`
ติดตั้งและรัน dashboard เป็น background service

```bash
sudo vas server start [--host 0.0.0.0] [--port 8080] [--foreground]
```

`--foreground` = เหมือน `run` แต่ผ่าน start command

#### `vas server install-service`
ติดตั้ง systemd unit โดยไม่ start

```bash
sudo vas server install-service [--host ...] [--port ...]
```

#### `vas server stop`
หยุด service

```bash
sudo vas server stop
```

#### `vas server status`
แสดงสถานะ service

```bash
vas server status
```

---

### `vas mcp`
จัดการ MCP server (AI diagnostic interface)

#### `vas mcp run`
รัน MCP server ใน foreground

```bash
vas mcp run [--host 0.0.0.0] [--port 8899]
```

#### `vas mcp start`
ติดตั้งและรัน MCP server เป็น background service

```bash
sudo vas mcp start [--host 0.0.0.0] [--port 8899] [--foreground]
```

#### `vas mcp install-service`
ติดตั้ง systemd unit โดยไม่ start

#### `vas mcp stop`
หยุด service

#### `vas mcp status`
แสดงสถานะ service

---

### `vas display`
จัดการ display และ touchscreen

#### `vas display status`
แสดง xrandr output และ xinput device list

```bash
vas display status [--display :0] [--xauthority /path/to/.Xauthority]
```

#### `vas display list-touch`
แสดง touchscreen devices พร้อม xinput ID

```bash
vas display list-touch [--display :0]
```

#### `vas display apply`
Apply rotation และ touchscreen mapping ทันที (runtime)

```bash
vas display apply \
  --output Virtual1 \
  --touch "Vending Virtual Touchscreen" \
  --rotate normal \
  [--display :0]
```

Rotation ที่รองรับ: `normal`, `left`, `right`, `inverted`

#### `vas display persist-session`
บันทึก display config เข้า `~/.xprofile` (โหลดอัตโนมัติเมื่อ login)

```bash
vas display persist-session \
  --output Virtual1 \
  --touch "Vending Virtual Touchscreen" \
  --rotate normal \
  [--delay-seconds 5] \
  [--retries 30]
```

สร้าง 2 ไฟล์:
1. `~/.config/vending-auto-setup/display-session.sh` — bash script ที่รอ display พร้อม
2. `~/.xprofile` — เพิ่ม managed block เรียก script ด้านบน

#### `vas display persist-xorg`
บันทึก touchscreen calibration เข้า Xorg config (persistent ข้ามกาน login)

```bash
sudo vas display persist-xorg \
  --touch "Vending Virtual Touchscreen" \
  --rotate normal
```

เขียน `/etc/X11/xorg.conf.d/99-vending-touchscreen.conf`

#### `vas display disable-wayland`
ปิด Wayland ใน GDM (บังคับใช้ X11)

```bash
sudo vas display disable-wayland
```

เพิ่ม `WaylandEnable=false` ใน `/etc/gdm3/custom.conf`

#### `vas display enable-wayland`
เปิด Wayland ใน GDM

```bash
sudo vas display enable-wayland
```

---

### `vas wireguard`
จัดการ WireGuard VPN

#### `vas wireguard status`
```bash
vas wireguard status [--name wg0]
```

#### `vas wireguard install`
```bash
sudo vas wireguard install
```

#### `vas wireguard init-config`
สร้าง config template
```bash
vas wireguard init-config [--name wg0] [--output ./wg0.conf] [--force]
```

#### `vas wireguard validate`
```bash
vas wireguard validate --config ./wg0.conf
```
Exit code 0 = valid, 1 = invalid

#### `vas wireguard save`
```bash
vas wireguard save --name wg0 --config ./wg0.conf
```

#### `vas wireguard sync`
Deploy และ restart service (ต้อง root)
```bash
sudo vas wireguard sync --name wg0 [--config ./wg0.conf] [--no-restart]
```

#### `vas wireguard history`
```bash
vas wireguard history --name wg0
```

#### `vas wireguard show`
```bash
vas wireguard show --name wg0 --id <snapshot_id> [--reveal-secrets]
```

#### `vas wireguard unsync`
```bash
sudo vas wireguard unsync --name wg0
```

---

### `vas qr`
จัดการ QR code reader (ZKTeco QR500-BM)

#### `vas qr status`
แสดงสถานะ udev rule, detected devices, reader thread
```bash
vas qr status
```

#### `vas qr start`
Start QR reader thread (blocking จนกว่าจะกด Ctrl+C)
```bash
vas qr start [--device /dev/input/event6]
```

#### `vas qr stop`
Stop global QR reader thread
```bash
vas qr stop
```

#### `vas qr last-scan`
แสดงค่า scan ล่าสุดใน memory
```bash
vas qr last-scan
```

#### `vas qr test`
Interactive test mode — scan QR แล้วพิมพ์ผลลัพธ์
```bash
vas qr test [--device /dev/input/event6] [--no-grab]
```
- `--no-grab` — ไม่ grab device (keystrokes ถึง OS — debug เท่านั้น)
- ต้องการ `python3-evdev`

#### `vas qr install-udev`
ติดตั้ง udev rule (ต้อง root)
```bash
sudo vas qr install-udev
```

#### `vas qr config`
ตั้งค่า device path
```bash
vas qr config --device /dev/hidraw0
vas qr config --clear-device   # กลับไป auto-detect
```

---

### `vas mqtt`
จัดการ MQTT publish settings

#### `vas mqtt status`
แสดง config ปัจจุบันและสถานะการเชื่อมต่อ
```bash
vas mqtt status
```

#### `vas mqtt config`
ตั้งค่า MQTT
```bash
vas mqtt config \
  [--broker-url mqtts://broker.example.com:8883] \
  [--username user] \
  [--password pass] \
  [--client-id my-device] \
  [--topic sterile/vending/qr/scan] \
  [--qos 1] \
  [--retain | --no-retain] \
  [--tls-insecure | --no-tls-insecure] \
  [--enable | --disable]
```

หลังบันทึก config จะ POST ไปยัง `http://localhost:8888/api/mqtt/config` เพื่อ reload ทันที (ถ้า server รันอยู่)

#### `vas mqtt test`
Test publish ไปยัง broker
```bash
vas mqtt test
```

รอ connect max 4 วินาที จากนั้น publish `{"scan":"TEST-VAS-QR","device":"test","ts":"..."}`

---

## Entry Point

```python
# src/cli.py
if __name__ == "__main__":
    raise SystemExit(main())
```

`main()` parse args และเรียก `_run_parsed_command()` คืน exit code:
- `0` = success
- `1` = error/failure
- `2` = unknown command
