# WireGuard VPN — เอกสารระบบ

ไฟล์หลัก: `src/wireguard.py`

## ภาพรวม

VAS จัดการ WireGuard VPN ผ่านคลาส `WireGuardManager` ซึ่ง wrap คำสั่ง `wg`, `wg-quick`, และ `systemctl` และรองรับ workflow:

```
init-config → validate → save → sync → (ใช้งาน) → unsync
```

Config ถูกจัดเก็บแยกจาก `/etc/wireguard/`:
- **Saved config** (staging): `~/.config/vending-auto-setup/wireguard/configs/<name>.conf`
- **Active config** (deployed): `/etc/wireguard/<name>.conf`
- **History snapshots**: `~/.config/vending-auto-setup/wireguard/history/<name>/<timestamp>-<action>.conf`

---

## Constants

```python
REQUIRED_INTERFACE_KEYS = ("PrivateKey", "Address")
REQUIRED_PEER_KEYS      = ("PublicKey", "AllowedIPs", "Endpoint")
SECRET_KEYS             = {"PrivateKey", "PresharedKey"}
WIREGUARD_CONFIG_DIR    = Path("/etc/wireguard")
```

---

## `WireGuardValidationResult` (dataclass)

```python
@dataclass(frozen=True)
class WireGuardValidationResult:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
```

---

## `WireGuardManager`

### Constructor
```python
WireGuardManager(
    runner: CommandRunner,
    store_dir: Path | None = None,        # default: default_store_dir()
    wireguard_dir: Path = Path("/etc/wireguard"),
)
```

### Methods

#### `install() → None`
ติดตั้ง WireGuard package:
1. `SystemClockPreflight.ensure_reasonable_clock()` — ตรวจ clock drift ก่อน (apt-get ใช้ SSL timestamp)
2. `apt-get update`
3. `apt-get install -y wireguard`

#### `init_config(name, output, force=False) → None`
สร้าง config template:
- เรียก `render_template(name)` เพื่อ generate placeholder config
- เขียนไฟล์ที่ `output` (raise `FileExistsError` ถ้ามีอยู่แล้วและ `force=False`)
- `chmod_private(output)` — ตั้ง permissions เป็น `600`

#### `validate_config(config: Path) → WireGuardValidationResult`
อ่าน config จาก path แล้วเรียก `validate_config_content()`

#### `save(config: Path, name: str) → None`
บันทึก config เข้า staging area:
1. validate ก่อน — ถ้า invalid raise `ValueError`
2. copy ไปยัง `saved_config_path(name)`
3. `chmod_private(target)`

#### `sync(name, config=None, restart=True) → None`
Deploy config เข้า `/etc/wireguard/` และ restart service:
1. validate
2. backup config เดิมเป็น `<timestamp>-pre-sync-backup.conf`
3. copy source → active config path
4. บันทึก history snapshot `<timestamp>-sync.conf`
5. `systemctl enable wg-quick@<name>`
6. `systemctl restart wg-quick@<name>` (ถ้า `restart=True`)

**ต้องรัน root** (เพราะเขียน `/etc/wireguard/`)

#### `unsync(name) → None`
ถอด WireGuard interface:
1. `systemctl disable --now wg-quick@<name>`
2. backup active config → `<timestamp>-unsync-backup.conf`
3. ลบ active config `/etc/wireguard/<name>.conf`

**ต้องรัน root**

#### `history(name) → None`
แสดง list ของ history snapshot IDs ใน `history_dir(name)`

#### `show(name, history_id, reveal_secrets=False) → None`
แสดง content ของ history snapshot — secrets ถูก mask ด้วย `mask_secrets()` โดย default

#### `print_status(name) → None`
แสดงสถานะ: tools (`wg`, `wg-quick`), config paths, systemd service status

---

## Path Methods

| Method | คืนค่า |
|--------|--------|
| `saved_config_path(name)` | `<store_dir>/configs/<name>.conf` |
| `history_dir(name)` | `<store_dir>/history/<name>/` |
| `active_config_path(name)` | `/etc/wireguard/<name>.conf` |
| `_snapshot_path(name, action)` | `<history_dir>/<UTC_timestamp>-<action>.conf` |

---

## Pure Functions

### `render_template(name: str) → str`
สร้าง WireGuard config template พร้อม placeholder values:
```ini
# vending-auto-config: wireguard
[Interface]
PrivateKey = <interface-private-key>
Address = 10.8.0.13/24

[Peer]
PublicKey = <peer-public-key>
PresharedKey = <peer-preshared-key>
AllowedIPs = 10.8.0.0/24
PersistentKeepalive = 25
Endpoint = vpn.example.com:51820
```

### `validate_config_content(content: str) → WireGuardValidationResult`
Validate WireGuard config string:

**ข้อกำหนด:**
- ต้องมี `[Interface]` section
- `[Interface]` ต้องมี `PrivateKey` และ `Address`
- ต้องมี `[Peer]` section อย่างน้อยหนึ่ง section
- แต่ละ `[Peer]` ต้องมี `PublicKey`, `AllowedIPs`, `Endpoint`

**Warning:** ถ้า value ยังเป็น `<placeholder>` (ขึ้นต้น `<` และลงท้าย `>`)

### `parse_wireguard_config(content: str) → dict[str, list[dict[str, str]]]`
Parse WireGuard INI config:
- คืน dict ของ section_name → list of section dicts
- ข้าม blank lines และ comment lines (`#`)
- `_strip_inline_comment()` ตัด inline comment (`# ...`) ออก

### `mask_secrets(content: str) → str`
แทน value ของ `PrivateKey` และ `PresharedKey` ด้วย `<hidden>`

```
PrivateKey = abc123... → PrivateKey = <hidden>
PresharedKey = xyz...  → PresharedKey = <hidden>
```

### `sanitize_interface_name(name: str) → str`
Validate interface name — รับเฉพาะ `[A-Za-z0-9_.-]+`
Raise `ValueError` ถ้าไม่ผ่าน

### `sanitize_history_id(history_id: str) → str`
Validate history ID — รับเฉพาะ `[A-Za-z0-9_.-]+`

### `chmod_private(path: Path) → None`
ตั้ง permissions เป็น `600` (user read+write only) — silently ignore errors

### `service_name(name: str) → str`
คืน `f"wg-quick@{name}"` — ชื่อ systemd service

### `default_store_dir() → Path`
```
$XDG_CONFIG_HOME/vending-auto-setup/wireguard/
# หรือถ้าไม่มี XDG_CONFIG_HOME:
~/.config/vending-auto-setup/wireguard/
```
รองรับ sudo: ถ้า `SUDO_USER` set จะใช้ home ของ user นั้น

---

## Workflow ตัวอย่าง

```bash
# 1. สร้าง template
vas wireguard init-config --name wg0 --output ./wg0.conf

# 2. แก้ไข wg0.conf ด้วย text editor

# 3. Validate
vas wireguard validate --config ./wg0.conf

# 4. บันทึกเข้า staging
vas wireguard save --name wg0 --config ./wg0.conf

# 5. Deploy (ต้อง root)
sudo vas wireguard sync --name wg0

# 6. ดูสถานะ
vas wireguard status --name wg0

# 7. ดู history
vas wireguard history --name wg0

# 8. ถ้าต้องการถอด
sudo vas wireguard unsync --name wg0
```

---

## Web API Endpoint Summary

ดูรายละเอียดใน [server.md](../server/server.md) — หัวข้อ WireGuard API

---

## Clock Preflight

ก่อน `install()` จะมีการตรวจ clock drift (`clock.py`) เพราะ apt-get ใช้ HTTPS ซึ่งต้องการ timestamp ที่ถูกต้อง ถ้า drift เกิน 300 วินาที จะรัน:

```bash
timedatectl set-ntp false
date -u -s @<network_epoch>
timedatectl set-ntp true
```
