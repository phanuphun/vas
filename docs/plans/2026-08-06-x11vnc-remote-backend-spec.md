---
tags: [spec, plan]
date: 2026-08-06
project: vas
status: draft
---

# Spec: x11vnc Remote Access — Backend Implementation

## Goal
ต่อ backend จริงให้กับ mockup ที่มีอยู่แล้ว (`src/web/templates/x11vnc.html`, route `/x11vnc` mock ใน `src/server.py`) และเพิ่มตัวเลือกติดตั้ง x11vnc ในหน้า "ซอฟต์แวร์ระบบ" ตาม user story ที่ approve แล้ว (9 AC) — เขียน/ควบคุม systemd service `x11vnc.service` ที่ mirror หน้าจอจริงออกให้เครื่องอื่น remote เข้ามาผ่าน VNC

## Data model changes
ไม่มี DB schema เปลี่ยน — ไม่ persist ค่า config (listen IP/port/display/user) ลง DB เลย ใช้ไฟล์ `/etc/systemd/system/x11vnc.service` บนดิสก์เป็น single source of truth (parse กลับมาแสดงผลตอนเปิดหน้า) เหมือนแนวทางที่ `vas_mcp/service.py` ใช้ (ไม่มี config table ให้ MCP เช่นกัน)

## Process flow

### 1. Status collection (`src/system/status.py`)
เพิ่มต่อจาก `collect_openssh_status()` (บรรทัด ~243-256 ปัจจุบัน) — ตาม pattern เดียวกับ `RemoteAccessStatus`/`collect_remote_access_status()`:

```python
@dataclass(frozen=True)
class X11vncConfig:
    listen_ip: str
    port: int
    display: str
    user: str

@dataclass(frozen=True)
class X11vncStatus:
    installed: bool
    version: str | None
    service_enabled: str
    service_active: str
    config: "X11vncConfig | None"   # None = ยังไม่เคย apply setup (ไม่มี unit file)
    password_set: bool
```

```python
def collect_x11vnc_status() -> X11vncStatus:
    if dev_fake_installed():
        return X11vncStatus(
            installed=True, version="x11vnc 0.9.16 (dev-mode)",
            service_enabled="enabled", service_active="active",
            config=X11vncConfig(listen_ip="10.8.0.56", port=5900, display=":0", user="first"),
            password_set=True,
        )
    x11vnc_path = shutil.which("x11vnc")
    return X11vncStatus(
        installed=x11vnc_path is not None,
        version=_read_version((x11vnc_path, "-version")) if x11vnc_path is not None else None,
        service_enabled=_read_command_first_line(("systemctl", "is-enabled", "x11vnc")),
        service_active=_read_command_first_line(("systemctl", "is-active", "x11vnc")),
        config=_parse_x11vnc_unit(),
        password_set=Path("/etc/x11vnc.pass").exists(),
    )
```

เพิ่ม private helper `_parse_x11vnc_unit() -> "X11vncConfig | None"`: อ่านไฟล์ `/etc/systemd/system/x11vnc.service` ถ้าไม่มีไฟล์ → `None`; ถ้ามี → regex ดึงค่า `User=(\S+)`, `-display (\S+)`, `-auth (\S+)`, `-rfbport (\d+)`, `-listen (\S+)` จากเนื้อไฟล์ (ไฟล์ multi-line ต่อด้วย `\` ตาม template — ต้อง join บรรทัดที่ลงท้าย `\` ก่อน regex) คืน `None` ทั้งก้อนถ้า parse ไม่ครบ (กัน state แปลกๆ ไม่ crash หน้าเว็บ)

หมายเหตุ: `x11vnc -version` เขียนเวอร์ชันออก **stderr** เสมอ (ยืนยันจาก man page) — `_read_version()` ที่มีอยู่แล้ว (บรรทัด 551-557) จัดการ fallback ไป stderr ให้อยู่แล้วถ้า stdout ว่าง จึงใช้ helper เดิมได้ตรงๆ ไม่ต้องเขียนใหม่

### 2. Feature module ใหม่ (`src/features/remote/x11vnc.py`)
Mirror `vas_mcp/service.py` (self-written systemd unit) ผสมกับ `features/remote/anydesk.py` (`service_action` + password ผ่าน stdin):

```python
SERVICE_NAME = "x11vnc"
SERVICE_UNIT = f"{SERVICE_NAME}.service"
SERVICE_PATH = Path("/etc/systemd/system") / SERVICE_UNIT
PASSWORD_PATH = Path("/etc/x11vnc.pass")
DEFAULT_PORT = 5900
DEFAULT_DISPLAY = ":0"
VALID_SERVICE_ACTIONS = ("start", "stop", "restart", "enable", "disable")

def render_service_file(listen_ip: str, port: int, display: str, user: str, home: str) -> str:
    # [Unit]/[Service]/[Install] ตาม template ที่ user ให้มาเป๊ะๆ — ExecStart ต่อบรรทัดด้วย "\"
    # เหมือนต้นฉบับ (ไม่ flatten เป็นบรรทัดเดียว เพื่อ diff เทียบง่ายกับ pattern ที่ user ทดสอบเองมาก่อน)
    ...

def _resolve_home(user: str) -> str:
    # dev_fake_installed() → คืน f"/home/{user}" ตรงๆ ไม่แตะ pwd
    # ปกติ → pwd.getpwnam(user).pw_dir, ValueError (ไม่มี user นี้จริง) ปล่อย propagate
    # ให้ route handler จับเป็น 400 (กัน apply setup ด้วย username ที่ไม่มีจริงในเครื่อง)
    ...

def apply_setup(runner: CommandRunner, listen_ip: str, port: int, display: str, user: str) -> tuple[bool, str]:
    # 1. validate: listen_ip ไม่ว่าง + เป็น IPv4 ที่ parse ได้ (ipaddress.ip_address), 1 <= port <= 65535,
    #    display ขึ้นต้นด้วย ":", user ไม่ว่าง — คืน (False, เหตุผล) ถ้าไม่ผ่าน ไม่แตะ filesystem เลย
    # 2. home = _resolve_home(user) — ValueError (user ไม่มีจริง) → (False, "ไม่พบ user ... ในเครื่อง")
    # 3. dev_fake_installed() → คืน (True, ข้อความ dev-mode) ทันที ไม่เขียนไฟล์/ไม่เรียก systemctl จริง
    #    (ต่างจาก McpServiceManager.install() ที่เช็คแค่ runner.dry_run — ตั้งใจเข้มกว่าเพื่อไม่ให้
    #    เผลอ PermissionError ตอน dev/test บนเครื่องที่ไม่ใช่ root/ไม่มี /etc/systemd/system)
    # 4. เขียนไฟล์จริง: SERVICE_PATH.write_text(render_service_file(...)), chmod 0o644
    # 5. runner.run(["systemctl", "daemon-reload"]); runner.run(["systemctl", "enable", "--now", SERVICE_UNIT])
    # 6. คืน (True, "บันทึกและเปิดใช้งาน x11vnc.service เรียบร้อย")
    # CommandExecutionError จาก runner.run(check=True ค่า default) ปล่อย propagate ให้ route handler จับ

def service_action(runner: CommandRunner, action: str) -> CommandResult:
    # เหมือน features/remote/anydesk.py service_action() เป๊ะ — เปลี่ยนแค่ SERVICE_NAME

def set_vnc_password(password: str) -> tuple[bool, str]:
    # เหมือน anydesk.set_unattended_password() แต่เรียก `x11vnc -storepasswd - PASSWORD_PATH`
    # (x11vnc รองรับอ่าน password จาก stdin ด้วย "-" แทน path แรก) ตามด้วย PASSWORD_PATH.chmod(0o644)
    # ถ้า dev_fake_installed() → คืน (True, ข้อความ dev-mode) ไม่แตะ filesystem
    # ตรวจ len(password) >= 8 ก่อนเรียกจริง (สอดคล้อง frontend minlength=8 ที่มีอยู่แล้ว)
```

### 3. Package manifest (`src/features/packages/settings.py`)
เพิ่มเข้า `PACKAGES` list ต่อจาก entry `anydesk` (บรรทัด ~317 ปัจจุบัน) หมวด `"remote"`:

```python
{
    "id":          "x11vnc",
    "name":        "x11vnc",
    "description": "VNC server — mirror หน้าจอจริงออกไปให้เครื่องอื่น remote เข้ามาใช้งาน",
    "logo":        None,
    "category":    "remote",
    "depends":     [],
    "children":    [],
    "check":       _which_check("x11vnc", ("x11vnc", "-version")),
    "install_cmds": [
        ["apt-get", "update"],
        ["apt-get", "install", "-y", "x11vnc"],
    ],
    "uninstall_cmds": [
        ["systemctl", "disable", "--now", "x11vnc"],
        ["apt-get", "purge", "-y", "x11vnc"],
    ],
    "uninstall_warning": "การถอน x11vnc จะปิดการเข้าถึงหน้าจอเครื่องนี้ผ่าน VNC ทันที",
},
```
ไม่ต้องแก้ `CATEGORIES` dict — `"remote": "Remote Access"` มีอยู่แล้ว

### 4. Routes (`src/server.py`)
แทนที่ mock route `/x11vnc` (บรรทัด ~440-460 ปัจจุบัน ค้นด้วย `def x11vnc_page`) ด้วยของจริง — pattern เดียวกับ `/mcp` (บรรทัด 476-513):

```python
@app.get("/x11vnc")
def x11vnc_page() -> str:
    from features.kiosk.manager import list_kiosk_linux_users
    status = collect_x11vnc_status()
    users = list_kiosk_linux_users()
    cfg = status.config
    return render_template(
        "x11vnc.html",
        vnc={
            "installed": status.installed,
            "version": status.version,
            "service_enabled": status.service_enabled,
            "service_active": status.service_active,
            "listen_ip": cfg.listen_ip if cfg else "",
            "port": cfg.port if cfg else DEFAULT_PORT,
            "display": cfg.display if cfg else DEFAULT_DISPLAY,
            "run_user": cfg.user if cfg else (users[0].username if users else ""),
            "password_set": status.password_set,
            "users": [
                {"username": u.username, "home": str(u.home), "uid": u.uid, "is_autologin": u.is_autologin}
                for u in users
            ],
        },
    )

@app.get("/api/x11vnc/status")
def x11vnc_status_api() -> dict[str, object]:
    s = collect_x11vnc_status()
    return {
        "status": "ok", "installed": s.installed, "version": s.version,
        "service_enabled": s.service_enabled, "service_active": s.service_active,
        "listen_ip": s.config.listen_ip if s.config else None,
        "port": s.config.port if s.config else None,
        "password_set": s.password_set,
    }

@app.post("/api/x11vnc/action")
def x11vnc_action_api() -> tuple[dict[str, object], int] | dict[str, object]:
    if _require_admin_user() is None:
        return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action", "")).strip()
    if action not in x11vnc_manager.VALID_SERVICE_ACTIONS:
        return {"status": "error", "errors": [f"Unknown x11vnc action: {action}"]}, 400
    try:
        result = x11vnc_manager.service_action(CommandRunner(), action)
    except CommandExecutionError as error:
        return {"status": "error", "errors": [str(error)]}, 500
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or f"systemctl {action} x11vnc ล้มเหลว"
        return {"status": "error", "errors": [detail]}, 500
    try:
        from core.database import log_audit as _db_audit
        _db_audit("x11vnc_service_action", {"action": action})
    except Exception:
        pass
    return {"status": "ok", "action": action}

@app.post("/api/x11vnc/apply")
def x11vnc_apply_api() -> tuple[dict[str, object], int] | dict[str, object]:
    if _require_admin_user() is None:
        return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
    payload = request.get_json(silent=True) or {}
    listen_ip = str(payload.get("listen_ip", "")).strip()
    display = str(payload.get("display", "")).strip() or x11vnc_manager.DEFAULT_DISPLAY
    user = str(payload.get("user", "")).strip()
    try:
        port = int(payload.get("port", x11vnc_manager.DEFAULT_PORT))
    except (TypeError, ValueError):
        return {"status": "error", "errors": ["Port ไม่ถูกต้อง"]}, 400
    try:
        ok, message = x11vnc_manager.apply_setup(CommandRunner(), listen_ip, port, display, user)
    except CommandExecutionError as error:
        return {"status": "error", "errors": [str(error)]}, 500
    if not ok:
        return {"status": "error", "errors": [message]}, 400
    try:
        from core.database import log_audit as _db_audit
        _db_audit("x11vnc_setup_applied", {"listen_ip": listen_ip, "port": port, "user": user})
    except Exception:
        pass
    return {"status": "ok", "message": message}

@app.post("/api/x11vnc/password")
def x11vnc_password_api() -> tuple[dict[str, object], int] | dict[str, object]:
    if _require_admin_user() is None:
        return {"status": "error", "errors": ["ไม่มีสิทธิ์"]}, 403
    payload = request.get_json(silent=True) or {}
    password = str(payload.get("password", ""))
    ok, message = x11vnc_manager.set_vnc_password(password)
    if not ok:
        return {"status": "error", "errors": [message]}, 400
    try:
        from core.database import log_audit as _db_audit
        _db_audit("x11vnc_password_set", {})
    except Exception:
        pass
    return {"status": "ok", "message": message}
```

แก้ `nav_status_api()` (บรรทัด ~2946-2963 ปัจจุบัน) เพิ่มบรรทัดใน `"installed"` dict:
```python
"x11vnc": fake or _shutil.which("x11vnc") is not None,
```

Import เพิ่มที่หัวไฟล์: `from features.remote import x11vnc as x11vnc_manager`, `from system.status import collect_x11vnc_status` (รวมกับ import เดิมที่ import `collect_remote_access_status` ฯลฯ อยู่แล้ว)

### 5. Frontend wiring (`src/web/templates/x11vnc.html`, `src/web/templates/base.html`)
- `base.html`: ลบคอมเมนต์ "MOCKUP" ที่ nav entry x11vnc แล้วเติม `data-nav-pkg="x11vnc" style="display:none;"` เข้า `extra_attrs` (ให้ behavior เหมือน wireguard/anydesk — ซ่อนจนกว่าจะติดตั้ง)
- `x11vnc.html` JS (`extra_scripts` block):
  - `data-vnc-action` click handler: เปลี่ยนจาก `setMsg(..., "ยังไม่เปิดใช้งาน backend...", "error")` เป็น `postJson("{{ url_for('x11vnc_action_api') }}", {action: ...})` ตาม pattern `postJson`/`refreshStatus` ใน `anydesk.html` (บรรทัด 255-283) ทุกตัวอักษร แค่เปลี่ยน endpoint/field ids
  - `submitVncSetup`: POST ไปที่ `{{ url_for('x11vnc_apply_api') }}` ด้วย `{listen_ip, port, display, user}` จาก field ids ที่มีอยู่แล้ว (`vnc-listen-ip`, `vnc-port`, `vnc-display`, `vnc-user`) สำเร็จแล้วเรียก `refreshStatus()` ในหน้าเดียวกัน (reload ค่า status card ไม่ reload ทั้งหน้า)
  - `submitVncPassword`: POST ไปที่ `{{ url_for('x11vnc_password_api') }}` ตาม pattern เดียวกับ `submitAnydeskPassword` ใน anydesk.html
  - เพิ่มฟังก์ชัน `refreshStatus()` ที่ fetch `{{ url_for('x11vnc_status_api') }}` แล้วอัปเดต text/zone ในแท็บสถานะ (mirror `anydesk.html` บรรทัด 268-296)
  - ลบ banner "หน้านี้เป็น mock-up" ที่อยู่บนสุดของ content block ออก (ของจริงแล้ว ไม่ต้องมี)

## API changes (endpoint ใหม่ทั้งหมด)
| Method | Path | Auth | หมายเหตุ |
|---|---|---|---|
| GET | `/x11vnc` | login | render หน้าเต็ม |
| GET | `/api/x11vnc/status` | login | poll สถานะ |
| POST | `/api/x11vnc/action` | root/admin | `{action}` → start/stop/restart/enable/disable |
| POST | `/api/x11vnc/apply` | root/admin | `{listen_ip, port, display, user}` → เขียน unit file + enable --now |
| POST | `/api/x11vnc/password` | root/admin | `{password}` → `x11vnc -storepasswd` |

`/api/nav/status` เพิ่ม key `x11vnc` ใน `installed` dict — ไม่ใช่ endpoint ใหม่ แค่แก้ response shape เดิม

## Frontend changes
- `x11vnc.html` — เปลี่ยน JS stub → fetch จริง (ไม่มีการแก้ layout/markup ที่ approve ไปแล้ว)
- `base.html` — เติม `data-nav-pkg="x11vnc"` ให้ nav item ที่มีอยู่

## Implementation routing
- backend-builder: required (`system/status.py`, `features/remote/x11vnc.py` ใหม่, `features/packages/settings.py`, `server.py`)
- frontend-builder: required แต่ scope เล็ก (แก้ JS ใน `x11vnc.html` ที่มีอยู่ + attribute เดียวใน `base.html`) — ทำต่อจาก backend เสร็จในรอบเดียวกันได้ ไม่ต้องแยก agent
- test-verifier: required
- pr-reviewer: required
- build order: backend ก่อน (routes ต้องมีจริงก่อน JS จะเรียกได้)

## Tests required
- `tests/test_packages_settings.py`: entry `x11vnc` อยู่ใน `PACKAGES`, `category == "remote"`, มี `install_cmds`/`uninstall_cmds` ไม่ว่าง
- `tests/test_x11vnc.py` (ใหม่):
  - `render_service_file()` คืน text ที่มีทุกบรรทัดตรงตาม template ต้นฉบับ (`User=`, `-display`, `-auth .../.Xauthority`, `-rfbport`, `-listen`, `Restart=on-failure`)
  - `apply_setup()` กับ `listen_ip=""` → `(False, ...)` ไม่เรียก `runner.run` เลย (mock runner แล้ว assert `run.call_count == 0`)
  - `apply_setup()` กับ `port=99999` → `(False, ...)`
  - `apply_setup()` ใน `VAS_DEV_FAKE_INSTALLED=1` → `(True, ...)` และไม่มีการเรียก `Path.write_text`/`runner.run` จริง (patch แล้ว assert not called)
  - `service_action()` กับ action นอก `VALID_SERVICE_ACTIONS` → raise `ValueError`
  - `set_vnc_password("")` → `(False, ...)`; password สั้นกว่า 8 ตัว → `(False, ...)`
- `tests/test_server.py`:
  - `GET /x11vnc` → 200, มีคำว่า `vnc-unit-preview` ใน body (ยืนยัน render ผ่าน ไม่ error)
  - `GET /api/x11vnc/status` → 200, `status == "ok"`
  - `POST /api/x11vnc/action` โดย user role `viewer`/ไม่ login → 403/redirect (ไม่ใช่ 200)
  - `GET /api/nav/status` → response `installed` มี key `"x11vnc"`

## Risks and open questions
- **Root privilege**: `apply_setup()`/`service_action()`/`set_vnc_password()` เขียนไฟล์ใน `/etc/` และเรียก `systemctl` จริง — ใช้งานได้เฉพาะตอน VAS server รันเป็น root บนเครื่อง Ubuntu จริง (เหมือน anydesk/openssh/mcp ทุกตัวที่มีอยู่แล้ว) การ test/dev ต้องพึ่ง `VAS_DEV_FAKE_INSTALLED=1` เท่านั้น — ไม่มีวิธี integration-test การเขียนไฟล์จริงในรอบนี้ (ยอมรับความเสี่ยงนี้ เพราะ pattern เดียวกับโค้ดเดิมทั้งหมดในโปรเจกต์)
- **`_parse_x11vnc_unit()` เปราะ**: ถ้ามีคนแก้ unit file เองด้วยมือ (ไม่ผ่านหน้าเว็บ) แล้ว format ไม่ตรง regex ที่คาดไว้ → `config=None` → หน้าเว็บแสดงฟอร์มว่างเหมือนยังไม่เคย apply (ไม่ crash แต่ข้อมูลเก่าที่ตั้งไว้ด้วยมือจะไม่โชว์) — ยอมรับได้ในรอบนี้ตาม AC ที่ approve (ไม่ได้ระบุ manual-edit-import)
- **Username ที่ไม่มีจริง**: ถ้า dropdown ส่ง username ที่ไม่มีในเครื่องมาจริง (เช่น race condition ลบ user ไปหลังโหลดหน้า) `_resolve_home()` จะ raise → ต้องจับใน route handler คืน 400 ที่ข้อความอ่านได้ ไม่ปล่อยเป็น 500 ดิบ
- **ไม่ตรวจว่า listen IP ชนกับ interface ที่มีอยู่จริงในเครื่องหรือไม่** (เช่น พิมพ์ IP ผิด ไม่ตรง wg0/eth0 ใดๆ เลย) — `x11vnc` เองจะ fail ตอน start ถ้า bind ไม่ได้ ซึ่งจะสะท้อนออกที่ `service_active=failed` ให้เห็นในแท็บสถานะอยู่แล้ว ไม่ต้อง validate ล่วงหน้าเพิ่ม (เกิน scope ที่ approve)

## Files that will change
- `src/system/status.py` — `X11vncConfig`, `X11vncStatus`, `collect_x11vnc_status()`, `_parse_x11vnc_unit()`
- `src/features/remote/x11vnc.py` — ใหม่ทั้งไฟล์
- `src/features/packages/settings.py` — เพิ่ม entry `x11vnc` ใน `PACKAGES`
- `src/server.py` — แทนที่ mock `/x11vnc`, เพิ่ม `/api/x11vnc/*` 4 endpoint, แก้ `nav_status_api()`
- `src/web/templates/x11vnc.html` — แก้เฉพาะ `extra_scripts` block (fetch จริงแทน stub) + ลบ mockup banner
- `src/web/templates/base.html` — เติม `data-nav-pkg="x11vnc"` ใน nav_link ที่มีอยู่
- `tests/test_x11vnc.py` — ใหม่
- `tests/test_packages_settings.py` — เพิ่ม assertion
- `tests/test_server.py` — เพิ่ม test case
- `CHANGELOG.md` — เพิ่ม entry ภาษาไทยตามธรรมเนียมโปรเจกต์ก่อน commit
