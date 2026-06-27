# System Services — เอกสารระบบ

ไฟล์: `src/status.py`, `src/display.py`, `src/audit_log.py`, `src/clock.py`, `src/runner.py`, `src/updater.py`, `src/config.py`, `src/reset.py`, `src/os_info.py`

---

## Status Module (`status.py`)

### Data Classes

#### `ToolStatus`
```python
@dataclass(frozen=True)
class ToolStatus:
    name: str
    command: str
    installed: bool
    version: str | None
    path: str | None
```

#### `DisplaySessionStatus`
สถานะ session type ของ display (X11/Wayland)
```python
@dataclass(frozen=True)
class DisplaySessionStatus:
    session_type: str   # "x11", "wayland", "unknown"
    is_x11: bool
    source: str         # "XDG_SESSION_TYPE", "loginctl", "not detected"
```

#### `VpnStatus`
สถานะ WireGuard VPN ครบถ้วน รวมถึง handshake peers

#### `WebServerStatus`
สถานะ Flask dashboard service (host, port, url, service_enabled, service_active)

#### `RemoteAccessStatus`
สถานะ AnyDesk (installed, version, ID, status, service)

#### `OpenSshStatus`
สถานะ OpenSSH server daemon

#### `QrReaderStatus`
```python
@dataclass(frozen=True)
class QrReaderStatus:
    udev_rule_path: Path
    udev_rule_exists: bool
    udev_rule_has_signature: bool
    config_path: Path
    config_exists: bool
    detected_devices: tuple[str, ...]
    active_device: str | None
    reader_running: bool
    last_scan: str | None
```

#### `XorgTouchscreenConfigStatus` / `DisplaySessionConfigStatus` / `DisplaySessionScriptStatus` / `GdmWaylandStatus`
สถานะของแต่ละ config file

### Constants

```python
XORG_TOUCHSCREEN_CONFIG_PATH = Path("/etc/X11/xorg.conf.d/99-vending-touchscreen.conf")
GDM_CUSTOM_CONFIG_PATH       = Path("/etc/gdm3/custom.conf")
XORG_TOUCHSCREEN_SIGNATURE   = "# vending-auto-config: touchscreen-xorg"
DISPLAY_SESSION_SIGNATURE    = "# vending-auto-config: display-session"
DISPLAY_SESSION_SCRIPT_SIGNATURE = "# vending-auto-config: display-session-script"
```

### `_effective_home() → Path`
คืน home directory ของ user จริงแม้รัน sudo:
1. ถ้า `SUDO_USER` set → lookup จาก `pwd` module
2. Fallback: `Path.home()`

### Collect Functions

| Function | คืนค่า | คำอธิบาย |
|----------|--------|----------|
| `collect_status()` | `tuple[ToolStatus, ...]` | ตรวจ Git, Node, npm, PM2, Docker, AnyDesk |
| `collect_display_session_status()` | `DisplaySessionStatus` | ตรวจ session type จาก `XDG_SESSION_TYPE` หรือ `loginctl` |
| `collect_gdm_wayland_status()` | `GdmWaylandStatus` | อ่าน `WaylandEnable` จาก `/etc/gdm3/custom.conf` |
| `collect_xorg_touchscreen_config_status()` | `XorgTouchscreenConfigStatus` | ตรวจ signature ใน `/etc/X11/xorg.conf.d/99-vending-touchscreen.conf` |
| `collect_display_session_config_status()` | `DisplaySessionConfigStatus` | ตรวจ signature ใน `~/.xprofile` |
| `collect_display_session_script_status()` | `DisplaySessionScriptStatus` | ตรวจ signature และ executable bit ของ display script |
| `collect_vpn_status()` | `VpnStatus` | ตรวจ wg tools, config paths, systemd service, handshake peers |
| `collect_web_server_status()` | `WebServerStatus` | อ่าน config จาก ENV_PATH + ตรวจ systemd |
| `collect_remote_access_status()` | `RemoteAccessStatus` | ตรวจ anydesk binary + systemd |
| `collect_openssh_status()` | `OpenSshStatus` | ตรวจ sshd binary + systemd |
| `collect_qr_reader_status()` | `QrReaderStatus` | ตรวจ udev rule, detected devices, reader thread |

### `print_status() → None`
พิมพ์สถานะทั้งหมดในรูป human-readable text (ใช้โดย `vas check`)

### `collect_display_session_status()` — loginctl fallback
ถ้า `XDG_SESSION_TYPE` ไม่มี → scan loginctl sessions:
1. ถ้า `XDG_SESSION_ID` มี → `loginctl show-session <id> -p Type`
2. Fallback: `loginctl list-sessions` แล้ว iterate แต่ละ session

---

## Display Configurator (`display.py`)

### `DisplayConfigurator`

Class หลักสำหรับ configure display และ touchscreen ผ่าน X11 tools

```python
class DisplayConfigurator:
    def __init__(self, runner: CommandRunner) -> None
```

#### `apply_runtime(output, touch, rotate, x_display, xauthority)`
Apply display settings ทันที:
1. `xrandr --output <output> --rotate <rotate>`
2. `xinput set-prop <touch> "Coordinate Transformation Matrix" <matrix>`

#### `persist_xorg(touch, rotate, path)`
สร้าง Xorg InputClass config:
- เขียน `/etc/X11/xorg.conf.d/99-vending-touchscreen.conf`
- ต้องรัน root

#### `persist_session(output, touch, rotate, x_display, ...)`
บันทึก display config เข้า X session profile:

สร้าง/อัปเดต 2 ไฟล์:
1. **`~/.config/vending-auto-setup/display-session.sh`** — bash script ที่:
   - `sleep <delay_seconds>` รอ session พร้อม
   - วนรอ `xrandr` เห็น output (max `retries` ครั้ง)
   - วนรอ `xinput` เห็น touch device
   - Apply rotation และ coordinate matrix
   - chmod `755` และ chown ให้ user จริง
2. **`~/.xprofile`** — managed block เรียก script ด้านบนแบบ background (`&`)

#### `disable_wayland() / enable_wayland()`
แก้ไข `/etc/gdm3/custom.conf`:
- disable: เพิ่ม/เปลี่ยน `WaylandEnable=false`
- enable: comment out เป็น `#WaylandEnable=false`

### Pure Builders

#### `build_xorg_touchscreen_config(touch, matrix) → str`
สร้าง Xorg `InputClass` section

#### `build_display_session_script(output, touch, rotate, matrix, ...) → str`
สร้าง bash script สำหรับ persist_session

#### `build_display_session_block(script_path) → str`
สร้าง managed block สำหรับ `~/.xprofile`

#### `build_gdm_wayland_config(existing_content, enabled) → str`
แก้ไข `[daemon]` section ใน GDM custom.conf

#### `upsert_managed_block(existing_content, managed_block) → str`
แทนที่ managed block ระหว่าง BEGIN/END markers (หรือต่อท้ายถ้ายังไม่มี)

#### `remove_managed_block(existing_content) → str`
ลบ managed block ออกจาก content

### Touchscreen Detection

#### `get_udevadm_touchscreen_names(runner) → frozenset[str]`
อ่านจาก `udevadm info --export-db`:
- หา blocks ที่มี `E: ID_INPUT_TOUCHSCREEN=1`
- ดึง `E: NAME=` จาก block นั้น

#### `parse_xinput_device_map(output) → dict[str, int]`
Parse `xinput list` output → `{device_name: xinput_id}`

#### `list_touch_devices(runner, ...) → tuple[TouchDevice, ...]`
รวม udevadm names + xinput IDs:
1. Primary: udevadm names (kernel-level)
2. Fallback: filter xinput ด้วย `"touch"` ใน name

### Rotation Matrices

```python
ROTATION_MATRICES = {
    "normal":   ("1", "0", "0", "0",  "1", "0", "0", "0", "1"),
    "right":    ("0", "1", "0", "-1", "0", "1", "0", "0", "1"),
    "left":     ("0", "-1", "1", "1", "0", "0", "0", "0", "1"),
    "inverted": ("-1", "0", "1", "0", "-1", "1", "0", "0", "1"),
}
```

---

## Audit Log (`audit_log.py`)

บันทึกและอ่าน system log snapshots

### Storage Structure
```
~/.config/vending-auto-setup/logs/system/snapshots/<YYYYMMDDTHHMMSSZ>.log
```

### Functions

#### `create_system_log_snapshot(log_dir=None) → dict`
สร้าง snapshot ใหม่:
1. รวบรวม log จาก: `/var/log/auth.log`, `/var/log/syslog`, `/var/log/messages`, `/var/log/kern.log`
2. รวบรวมจาก `journalctl -n 500`
3. เขียนเป็น `.log` file พร้อม header
4. คืน `{"id": ..., "path": ..., "size": ..., "created": ...}`

#### `list_system_snapshots(limit=50) → tuple[dict, ...]`
คืน list snapshots เรียงจากใหม่ → เก่า (max 50)

#### `read_system_snapshot(snapshot_id) → dict`
อ่าน snapshot ตาม ID — `sanitize_snapshot_id()` ก่อนใช้ path

#### `sanitize_snapshot_id(snapshot_id) → str`
กรองเฉพาะ alphanumeric + `-`, `_`, `T`, `Z` — ป้องกัน path traversal

---

## Clock Preflight (`clock.py`)

ตรวจ system clock drift ก่อนรัน apt-get (ป้องกัน SSL errors เพราะ timestamp ผิด)

### `SystemClockPreflight`

```python
class SystemClockPreflight:
    def __init__(self, runner: CommandRunner, time_urls: tuple[str, ...] = DEFAULT_TIME_URLS)
```

#### `ensure_reasonable_clock() → None`
1. อ่าน network time ด้วย `read_clock_drift()`
2. ถ้า drift > 300 วินาที → set system time:
   ```bash
   timedatectl set-ntp false
   date -u -s @<network_epoch>
   timedatectl set-ntp true
   ```

#### `read_clock_drift() → ClockDrift | None`
อ่าน network time จาก HTTP headers (`Date:`) ของ Ubuntu mirror URLs

### `read_network_epoch(url) → int | None`
ส่ง HEAD request ไปยัง URL และอ่าน `Date` header

**Default URLs:**
- `http://us.archive.ubuntu.com/ubuntu/dists/jammy-updates/InRelease`
- `http://archive.ubuntu.com/ubuntu/dists/jammy-updates/InRelease`
- `http://security.ubuntu.com/ubuntu/dists/jammy-security/InRelease`
- `https://github.com`

---

## Command Runner (`runner.py`)

### `CommandRunner`

```python
class CommandRunner:
    def __init__(self, dry_run: bool = False) -> None
```

#### `run(args, check=True, stream=False) → CommandResult`
รัน subprocess command:
- `dry_run=True` → พิมพ์ command แต่ไม่ execute จริง
- `check=True` → raise `CommandExecutionError` ถ้า returncode != 0
- `stream=True` → ไม่ capture stdout/stderr (แสดงบน terminal โดยตรง)
- แสดง progress percentage ถ้า `start_progress()` ถูกเรียก

#### `start_progress(total) / stop_progress()`
ตั้งค่า progress counter — format output เป็น `[vending-auto-setup (N%)] - <command>`

### `CommandResult`
```python
@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
```

### `CommandExecutionError`
Raise เมื่อ command fail:
```
Command failed with exit code 1: apt-get install ...
<stderr content>
```

---

## Config (`config.py`)

### Constants

```python
APP_VERSION = "0.1.0"
QR_UDEV_RULE_PATH  = Path("/etc/udev/rules.d/99-qr500-bm.rules")
QR_UDEV_SIGNATURE  = "# managed by vas"
```

### `InstallConfig` (dataclass)
```python
@dataclass(frozen=True)
class InstallConfig:
    node_major: int = 22
    docker_version: str | None = None
    git_version: str | None = None
    ubuntu_codename: str = "jammy"
    docker_packages: tuple[str, ...] = (
        "docker-ce", "docker-ce-cli", "containerd.io",
        "docker-buildx-plugin", "docker-compose-plugin",
    )
```

### Path Functions

| Function | คืนค่า |
|----------|--------|
| `qr_config_dir()` | `~/.config/vas/` |
| `qr_config_path()` | `~/.config/vas/qr_config.json` |
| `main_config_path()` | `<project_root>/config.json` |

---

## Updater (`updater.py`)

### `SelfUpdater`

```python
class SelfUpdater:
    def __init__(self, runner, repo, version, install_dir, bin_dir)
```

#### `update() → None`
1. `ensure_runtime_packages()` — ติดตั้ง `python3-flask` ถ้าไม่มี
2. Download archive จาก GitHub (`archive_url()`)
3. Extract ใน temp directory
4. Replace `/opt/vending-auto-setup/` ด้วย `shutil.copytree()`
5. `install_wrappers()` — เขียน wrapper scripts

#### `archive_url() → str`
- `version="latest"` → `https://github.com/<repo>/archive/refs/heads/main.tar.gz`
- `version=<tag>` → `https://github.com/<repo>/archive/refs/tags/<tag>.tar.gz`

### `install_wrappers(install_dir, bin_dir) → None`
เขียน bash wrapper scripts ใน `/usr/local/bin/`:
- `vending-auto-setup` → `python3 -m cli`
- `vas` → `python3 -m cli`
- `vending-status` → `python3 -m status`

Wrapper format:
```bash
#!/usr/bin/env bash
PYTHONPATH=/opt/vending-auto-setup/src exec python3 -m cli "$@"
```

---

## System Utilities (`system.py`)

### `require_linux() → None`
Raise `SystemExit` ถ้าไม่ได้รันบน Linux

### `require_root() → None`
Raise `SystemExit` ถ้า effective UID != 0
