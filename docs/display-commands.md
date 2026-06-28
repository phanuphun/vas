# Display Commands — รายละเอียดทั้งหมด

## ภาพรวม

Display system จัดการ 3 ส่วน:
1. **Runtime** — xrandr + xinput ทำงานทันที ไม่ persist
2. **Session persist** — เขียน `~/.xprofile` + bash script เพื่อ auto-apply ทุกครั้ง login
3. **Xorg persist** — เขียน Xorg config ใน `/etc/X11/xorg.conf.d/` (boot-level)

Source files:
- `src/features/display/display.py` — logic หลัก
- `src/system/status.py` — collect status
- `src/server.py` — API endpoints + CLI routes

---

## CLI Commands

### `vas display status`

แสดง xrandr outputs และ xinput devices

```bash
vas display status --display :0
```

เรียก:
- `xrandr --query` → รายการ display outputs ที่ connected
- `xinput list` → รายการ input devices

---

### `vas display list-touch`

แสดง touchscreen devices ที่ detect ได้พร้อม xinput ID

```bash
vas display list-touch --display :0
```

ลำดับการ detect:
1. `udevadm info --export-db` — kernel-level, ไม่ต้องพึ่ง X session
2. cross-ref กับ `xinput list` เพื่อดึง xinput ID
3. fallback: กรอง device ที่มี "touch" ใน name

---

### `vas display apply`

Apply rotation ทันที (runtime) ไม่ persist หลัง reboot

```bash
vas display apply \
  --display :0 \
  --output Virtual1 \
  --touch 'Vending Virtual Touchscreen' \
  --rotate normal
```

สิ่งที่ทำ:
```bash
xrandr --output Virtual1 --rotate normal
xinput set-prop 'Vending Virtual Touchscreen' \
  'Coordinate Transformation Matrix' 1 0 0 0 1 0 0 0 1
```

**Rotation matrices:**

| Rotation | Matrix |
|---|---|
| `normal` | `1 0 0 0 1 0 0 0 1` |
| `right` | `0 1 0 -1 0 1 0 0 1` |
| `left` | `0 -1 1 1 0 0 0 0 1` |
| `inverted` | `-1 0 1 0 -1 1 0 0 1` |

---

### `vas display persist-session`

Persist rotation ผ่าน `~/.xprofile` — จะ apply ทุกครั้งที่ user login

```bash
vas display persist-session \
  --display :0 \
  --output Virtual1 \
  --touch 'Vending Virtual Touchscreen' \
  --rotate normal
```

ไฟล์ที่สร้าง/แก้ไข:

**1. `~/.config/vending-auto-setup/display-session.sh`** — bash script ที่รัน apply:
```bash
#!/usr/bin/env bash
set -euo pipefail
sleep 5
export DISPLAY=:0
OUTPUT='Virtual1'
TOUCH_DEVICE='Vending Virtual Touchscreen'
ROTATE='normal'
MATRIX='1 0 0 0 1 0 0 0 1'
RETRIES=30

# รอ display output พร้อม (poll ทุก 1 วิ)
for attempt in $(seq 1 "$RETRIES"); do
  if xrandr --query | grep -q "^${OUTPUT} connected"; then
    xrandr --output "$OUTPUT" --rotate "$ROTATE"
    break
  fi
  sleep 1
done

# รอ touchscreen พร้อม แล้ว set matrix
for attempt in $(seq 1 "$RETRIES"); do
  if xinput list --name-only | grep -Fxq "$TOUCH_DEVICE"; then
    xinput set-prop "$TOUCH_DEVICE" "Coordinate Transformation Matrix" $MATRIX
    exit 0
  fi
  sleep 1
done
```

**2. `~/.xprofile`** — เพิ่ม block ที่ managed โดย VAS:
```bash
# VAS DISPLAY SESSION BEGIN
# Managed by vending-auto-setup. Manual edits inside this block may be overwritten.
'/home/user/.config/vending-auto-setup/display-session.sh' &
# VAS DISPLAY SESSION END
```

> Script รันเป็น background process (`&`) เพื่อไม่บล็อก login session

---

### `vas display persist-xorg`

Persist rotation ระดับ Xorg config — ทำงานตั้งแต่ boot ไม่ต้องรอ session

```bash
sudo vas display persist-xorg \
  --touch 'Vending Virtual Touchscreen' \
  --rotate normal
```

เขียนไฟล์: `/etc/X11/xorg.conf.d/90-vending-touchscreen.conf`
```
# VAS XORG TOUCHSCREEN CONFIG
# Managed by vending-auto-setup. Manual edits may be overwritten.
Section "InputClass"
    Identifier "vending-touchscreen-calibration"
    MatchProduct "Vending Virtual Touchscreen"
    Option "CalibrationMatrix" "1 0 0 0 1 0 0 0 1"
EndSection
```

---

### `vas display disable-wayland`

ปิด Wayland ใน GDM เพื่อบังคับใช้ Xorg session

```bash
sudo vas display disable-wayland
```

แก้ไข: `/etc/gdm3/custom.conf`
```ini
[daemon]
WaylandEnable=false
```

### `vas display enable-wayland`

เปิด Wayland กลับมา

```bash
sudo vas display enable-wayland
```

```ini
[daemon]
#WaylandEnable=false
```

---

## API Endpoints

| Method | Path | คำอธิบาย |
|---|---|---|
| `GET` | `/api/display/devices` | list outputs + touch devices |
| `GET` | `/api/display/config-content?key=<k>` | อ่าน config file |
| `POST` | `/api/display/apply` | apply runtime rotation |
| `POST` | `/api/display/wayland` | enable/disable Wayland |
| `GET` | `/api/display/sim/status` | virtual touchscreen simulator status |
| `POST` | `/api/display/sim/start` | start virtual touchscreen |
| `POST` | `/api/display/sim/stop` | stop virtual touchscreen |

**POST `/api/display/apply` payload:**
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

**Config keys สำหรับ `/api/display/config-content`:**

| key | ไฟล์ |
|---|---|
| `gdm_custom` | `/etc/gdm3/custom.conf` |
| `xprofile` | `~/.xprofile` |
| `display_script` | `~/.config/vending-auto-setup/display-session.sh` |
| `xorg_touchscreen` | `/etc/X11/xorg.conf.d/90-vending-touchscreen.conf` |

---

## การทำงานเมื่อรันเป็น root

เมื่อ `vas server` รันด้วย `sudo` — display commands ใช้ `runuser -u $SUDO_USER` เพื่อรัน xrandr/xinput ใน X session ของ user จริง:

```bash
runuser -u username -- env DISPLAY=:0 xrandr --query
```

ไฟล์ที่เขียนใน home directory จะ `chown` กลับไปให้ `SUDO_USER` อัตโนมัติ
