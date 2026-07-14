# คู่มือติดตั้ง Kiosk แบบ Manual — Ubuntu 22.04 LTS + Xorg (ปิด Wayland) + Openbox + Chromium

> เอกสารนี้เขียนสำหรับติดตั้ง **แบบมือ ไม่พึ่งฟังก์ชัน Kiosk ของ VAS เลย** — ทุกไฟล์/ทุกคำสั่งเป็นสิ่งที่ต้องรันเองบนเครื่องจริงผ่าน terminal (SSH หรือหน้าจอเครื่องโดยตรง) ทุกคำสั่งใช้ `sudo`
>
> อ้างอิงรูปแบบไฟล์/คีย์เดียวกับที่ VAS ใช้จริง (`/etc/gdm3/custom.conf`, `/var/lib/AccountsService/users/<user>`) เพื่อไม่ให้ตีกันถ้าในอนาคตมีการติดตั้ง VAS เพิ่มบนเครื่องเดียวกัน แต่ทุกขั้นตอนด้านล่างทำเองล้วนๆ ไม่เรียก `vas` เลยสักคำสั่ง

---

## 0. ภาพรวมลำดับขั้นตอน

1. ตรวจสอบ/ตั้งค่า Network ของ OS ให้ใช้งานได้ก่อน (ต้องผ่านก่อนไปข้อถัดไปเสมอ)
2. อัปเดตระบบ + ติดตั้ง Xorg + GDM3
3. ปิด Wayland บังคับใช้ X11
4. ติดตั้ง Openbox + เครื่องมือเสริม (unclutter, x11-xserver-utils)
5. ติดตั้ง Chromium (แบบ .deb ไม่ใช่ snap — เหตุผลอธิบายในข้อ 5)
6. สร้าง Linux user แยกสำหรับ kiosk
7. ตั้ง Auto-login ให้ user นั้นผ่าน GDM3
8. ตั้ง Session Type ของ user นั้นเป็น Openbox
9. เขียนสคริปต์ `~/.config/openbox/autostart` — รอ network พร้อมจริงก่อนค่อยเปิด Chromium แบบ kiosk
10. ล็อกดาวน์เพิ่มเติม (ปิด screensaver, ซ่อนเมาส์, กัน crash)
11. Reboot ทดสอบ + Checklist ตรวจสอบ
12. Troubleshooting

---

## 1. ตรวจสอบ/ตั้งค่า Network ของ OS ก่อนเริ่ม (ทำก่อนเสมอ)

Kiosk ต้องพึ่งเน็ตให้พร้อม**ก่อน** Chromium จะโหลดหน้าเว็บได้ ถ้าข้ามขั้นนี้ไปเลย ปัญหาที่เจอบ่อยสุดคือบูตเครื่องเสร็จแล้ว Chromium เปิดเร็วกว่าที่ NIC/DHCP จะพร้อม กลายเป็นหน้า `ERR_INTERNET_DISCONNECTED` ค้างอยู่

### 1.1 เช็คว่ามี interface อะไรบ้าง และตัวไหนต่อสายจริง

```bash
ip a
# หรือดูเฉพาะที่ขึ้น "state UP"
ip -brief link
```

หา interface ที่ต้องการใช้งาน (เช่น `eth0`, `enp2s0` สำหรับสาย LAN, `wlan0` สำหรับ Wi-Fi)

### 1.2 เช็คว่า NetworkManager คุม interface นั้นอยู่ไหม

Ubuntu 22.04 Desktop ใช้ NetworkManager เป็นค่าเริ่มต้น (Ubuntu Server ใช้ netplan + systemd-networkd ตรงๆ) เช็คก่อนว่าเครื่องนี้ใช้ตัวไหน:

```bash
systemctl is-active NetworkManager
nmcli device status
```

ถ้า `nmcli device status` ขึ้น interface เป็น `unmanaged` แปลว่า netplan ตั้งไว้ให้ systemd-networkd คุมแทน — ดูข้อ 1.3

### 1.3 ตั้งค่า IP ผ่าน netplan (แนะนำสำหรับเครื่อง kiosk — ใช้ Static IP กันเน็ตหลุดเวลา DHCP server รีสตาร์ท)

```bash
ls /etc/netplan/
sudo nano /etc/netplan/01-kiosk-network.yaml
```

ตัวอย่าง Static IP (แก้ `eth0`, IP, gateway ตามหน้างานจริง):

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: no
      addresses:
        - 192.168.1.50/24
      routes:
        - to: default
          via: 192.168.1.1
      nameservers:
        addresses: [8.8.8.8, 1.1.1.1]
```

หรือถ้าจะใช้ DHCP ปกติ:

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: yes
```

ใช้คำสั่งนี้ทดสอบก่อน apply จริง (กันเน็ตหลุดถ้า config ผิด จะ auto-revert ใน 120 วิ):

```bash
sudo netplan try
```

ถ้า apply ผ่านแล้วโอเค:

```bash
sudo netplan apply
```

### 1.4 ทดสอบว่าเน็ตใช้งานได้จริง (ping + DNS + HTTP)

รันครบทั้ง 3 ชั้นนี้ อย่าเช็คแค่ ping เฉยๆ — ping ผ่านไม่ได้แปลว่า DNS/HTTP จะผ่านด้วย:

```bash
# 1) เช็ค gateway ตอบไหม (ชั้น L2/L3)
ip route | grep default
ping -c 3 $(ip route | awk '/default/ {print $3}')

# 2) เช็ค DNS resolve ได้ไหม
resolvectl status
getent hosts google.com

# 3) เช็คว่า HTTP(S) ออกเน็ตได้จริง ไม่ใช่แค่ resolve DNS ได้
curl -Is https://www.google.com | head -1
```

ถ้าจะเปิดหน้าเว็บภายใน (intranet/VPN) ให้ทดสอบตรง URL จริงที่จะใช้ใน kiosk เลย:

```bash
curl -Is https://your-app-url.example.com | head -1
```

### 1.5 บังคับให้ระบบ "รอเน็ตพร้อมจริง" ก่อนถือว่า boot เสร็จ

ค่า default ของ Ubuntu บางเครื่องไม่รอ `network-online.target` ให้ enable ให้ชัดเจน — ขั้นตอน autostart ในข้อ 9 จะ poll ซ้ำอีกชั้นด้วย แต่การเปิดสวิตช์นี้ช่วยลดโอกาสที่ NIC ยังไม่ up เลยตั้งแต่ต้น:

```bash
sudo systemctl enable systemd-networkd-wait-online.service
# ถ้าเครื่องใช้ NetworkManager แทน (Desktop):
sudo systemctl enable NetworkManager-wait-online.service
```

---

## 2. อัปเดตระบบ + ติดตั้ง Xorg + GDM3

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y \
  xserver-xorg \
  x11-xserver-utils \
  xinit \
  gdm3
```

ระหว่างติดตั้ง `gdm3` ถ้ามี dialog ถามว่าจะใช้ display manager ตัวไหนเป็นค่า default ให้เลือก `gdm3`

---

## 3. ปิด Wayland — บังคับ GDM ให้ใช้ X11 เสมอ

เครื่องมือปรับจอ/ทัชสกรีน (`xrandr`, `xinput`) และ autostart แบบ script ทำงานกับ X11 เท่านั้น ต้องปิด Wayland ก่อนเริ่มขั้นถัดไป

```bash
sudo nano /etc/gdm3/custom.conf
```

แก้ให้ section `[daemon]` มีบรรทัดนี้ (ไม่ต้องลบบรรทัดอื่นที่มีอยู่แล้ว):

```ini
[daemon]
WaylandEnable=false
```

บันทึกแล้ว restart GDM (หรือ reboot ทั้งเครื่องก็ได้ ปลอดภัยกว่าถ้ายังไม่มั่นใจ):

```bash
sudo systemctl restart gdm3
```

ยืนยันว่าเข้า X11 จริง (รันหลัง login เข้า desktop แล้ว):

```bash
echo $XDG_SESSION_TYPE   # ต้องขึ้น "x11" ไม่ใช่ "wayland"
```

---

## 4. ติดตั้ง Openbox + เครื่องมือเสริม

```bash
sudo apt install -y \
  openbox \
  obconf \
  unclutter \
  xterm
```

- `openbox` — window manager แบบเบา ไม่มี desktop shell/dock/notification ให้หลุดออกจาก kiosk ได้เหมือน GNOME
- `obconf` — GUI ปรับ config ของ Openbox (ใช้ตอนตั้งค่าครั้งแรกเท่านั้น ไม่จำเป็นสำหรับ kiosk ที่ตั้งเสร็จแล้ว)
- `unclutter` — ซ่อน mouse cursor อัตโนมัติเมื่อไม่ได้ขยับ (ตู้ vending ไม่ควรเห็นลูกศรเมาส์ค้างจอ)
- `xterm` — เผื่อ debug เข้า terminal ผ่าน Openbox เวลามีปัญหา (ลบทิ้งได้ทีหลังถ้าไม่ต้องการ)

---

## 5. ติดตั้ง Chromium — แนะนำใช้ .deb ไม่ใช่ snap

Ubuntu 22.04 ตัด `chromium-browser` .deb ธรรมดาออกแล้ว แพ็กเกจ `chromium-browser` ที่ apt เสนอให้เป็นแค่ transitional package ที่ไปดึง **snap** มาแทน ซึ่งมีปัญหากับงาน kiosk หลายอย่าง: เปิดช้ากว่า, sandbox ของ snap บล็อกการเข้าถึงบางโฟลเดอร์, auto-refresh ของ snap อาจรีสตาร์ทแอปเองระหว่างใช้งาน

**ทางเลือกที่แนะนำ — ติดตั้งแบบ .deb ผ่าน PPA:**

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:xtradeb/apps
sudo apt update
sudo apt install -y chromium
```

ตรวจสอบว่าติดตั้งเป็น .deb จริง ไม่ใช่ snap:

```bash
which chromium
# ต้องได้ path แบบ /usr/bin/chromium ไม่ใช่ /snap/bin/chromium
dpkg -l | grep chromium
```

**ทางเลือกสำรอง** ถ้าไม่สะดวกเพิ่ม PPA (ยอมรับข้อจำกัดของ snap ได้): ใช้ `sudo apt install -y chromium-browser` ตรงๆ — สคริปต์ autostart ในข้อ 9 ของคู่มือนี้เขียนให้รองรับทั้ง 2 ชื่อ binary (`chromium` และ `chromium-browser`) อยู่แล้ว

---

## 6. สร้าง Linux user แยกสำหรับ kiosk

ห้ามใช้ user แอดมินตัวเองรัน kiosk ตรงๆ — แยก user ใหม่เพื่อจำกัดสิทธิ์และกันการตั้งค่าไปชนกับ session ของแอดมิน:

```bash
sudo useradd -m -c "Kiosk User" -s /bin/bash kiosk-user
sudo usermod -aG video,input,plugdev kiosk-user
```

ไม่ต้องตั้งรหัสผ่าน — เพราะจะ auto-login ผ่าน GDM (ข้ามการเช็ครหัสผ่านโดยดีไซน์) ถ้าต้องการ SSH หรือเลือก login เองจากหน้า greeter ค่อยตั้งทีหลังด้วย `sudo passwd kiosk-user`

---

## 7. ตั้ง Auto-login ผ่าน GDM3

แก้ไฟล์เดียวกับข้อ 3 (`/etc/gdm3/custom.conf`) เพิ่ม 2 คีย์นี้ใน `[daemon]` (ไม่ต้องลบ `WaylandEnable=false` ที่ตั้งไว้แล้ว):

```bash
sudo nano /etc/gdm3/custom.conf
```

```ini
[daemon]
WaylandEnable=false
AutomaticLoginEnable=true
AutomaticLogin=kiosk-user
```

---

## 8. ตั้ง Session Type ของ kiosk-user เป็น Openbox

GDM ต้องรู้ว่า login เข้า `kiosk-user` แล้วให้เปิด session แบบไหน — ไฟล์นี้แยกจาก `custom.conf` ข้อ 7 คนละเรื่องกัน (custom.conf ตอบว่า "auto-login ไหม", ไฟล์นี้ตอบว่า "login แล้วเจอ session อะไร"):

```bash
sudo mkdir -p /var/lib/AccountsService/users
sudo nano /var/lib/AccountsService/users/kiosk-user
```

ใส่เนื้อหานี้:

```ini
[User]
Session=openbox
XSession=openbox
SystemAccount=false
```

```bash
sudo chown kiosk-user:kiosk-user /var/lib/AccountsService/users/kiosk-user
```

ตรวจสอบว่ามี session `openbox` ให้ GDM เลือกจริง (มาจากแพ็กเกจ `openbox` ที่ลงในข้อ 4):

```bash
ls /usr/share/xsessions/
# ต้องเห็นไฟล์ openbox.desktop
```

---

## 9. เขียนสคริปต์ Autostart ของ Openbox

Openbox ไม่มี session manager คอยจัดการเหมือน GNOME — ต้องเขียนสคริปต์เองให้ครบ 4 อย่าง: (1) ตั้งพื้นหลังกันจอเทา (2) ปิด screensaver/screen blank (3) **รอ network พร้อมจริงก่อน** (4) เปิด Chromium แบบ kiosk พร้อม restart loop กันแอป crash

```bash
sudo -u kiosk-user mkdir -p /home/kiosk-user/.config/openbox
sudo -u kiosk-user nano /home/kiosk-user/.config/openbox/autostart
```

ใส่เนื้อหานี้ (แก้ `KIOSK_URL` เป็น URL จริงที่จะเปิด):

```bash
#!/usr/bin/env bash

KIOSK_URL="https://your-app-url.example.com"
LOG_FILE="$HOME/.config/openbox/kiosk-launch.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "$(date -Iseconds) $*" >> "$LOG_FILE"; }

# 1) พื้นหลังดำ กันเห็นสีเทาดิบของ X root window ตอน Chromium ยังไม่ขึ้น
xsetroot -solid "#000000" 2>/dev/null || true

# 2) ปิด screensaver / DPMS / screen blank — ตู้ kiosk ต้องไม่ดับจอเอง
xset s off
xset s noblank
xset -dpms

# 3) ซ่อน mouse cursor เมื่อไม่ขยับ (ต้องติดตั้ง unclutter จากข้อ 4 แล้ว)
unclutter -idle 1 -root &

# 4) รอ network พร้อมจริงก่อนเปิดเบราว์เซอร์ — เช็ค 2 ชั้น: DNS resolve ได้ + HTTP ตอบจริง
HOSTNAME=$(echo "$KIOSK_URL" | sed -E 's#^[a-zA-Z]+://##; s#/.*##; s#:.*##')
MAX_WAIT=60
log "waiting for network to host: $HOSTNAME (max ${MAX_WAIT}s)"
i=0
while [ "$i" -lt "$MAX_WAIT" ]; do
  if getent hosts "$HOSTNAME" >/dev/null 2>&1 && \
     curl -Is --max-time 3 "$KIOSK_URL" >/dev/null 2>&1; then
    log "network ready after ${i}s"
    break
  fi
  sleep 1
  i=$((i + 1))
done
if [ "$i" -ge "$MAX_WAIT" ]; then
  log "WARNING: network not confirmed ready after ${MAX_WAIT}s — opening chromium anyway"
fi

# 5) เผื่อเครื่องมี binary ชื่อ chromium-browser แทน chromium (แล้วแต่วิธีติดตั้งในข้อ 5)
if ! command -v chromium >/dev/null 2>&1 && command -v chromium-browser >/dev/null 2>&1; then
  chromium() { chromium-browser "$@"; }
fi
if ! command -v chromium >/dev/null 2>&1; then
  log "ERROR: ไม่พบคำสั่ง chromium หรือ chromium-browser ใน PATH"
  exit 1
fi

# 6) เปิด Chromium แบบ kiosk พร้อม flag ป้องกันหลุดออกจากโหมด kiosk
CHROME_FLAGS=(
  --kiosk
  --no-first-run
  --disable-translate
  --disable-infobars
  --noerrdialogs
  --disable-suggestions-service
  --disable-save-password-bubble
  --overscroll-history-navigation=0
  --disable-pinch
  --disable-features=Translate,OverscrollHistoryNavigation,TouchpadOverscrollHistoryNavigation
)

# 7) Restart loop — ถ้า Chromium ปิดตัว/crash ให้เปิดใหม่อัตโนมัติ (ไม่ปล่อยให้จอค้างดำ)
while true; do
  log "starting chromium"
  chromium "${CHROME_FLAGS[@]}" "$KIOSK_URL" >> "$LOG_FILE" 2>&1
  log "chromium exited — restarting in 2s"
  sleep 2
done &
```

ตั้งสิทธิ์ executable:

```bash
sudo chmod +x /home/kiosk-user/.config/openbox/autostart
sudo chown -R kiosk-user:kiosk-user /home/kiosk-user/.config
```

---

## 10. ล็อกดาวน์เพิ่มเติม (กันหลุดออกจาก kiosk / กันเครื่อง sleep)

### 10.1 ปิด suspend/sleep/hibernate ระดับระบบ (สำคัญมากสำหรับตู้ที่เปิด 24 ชม.)

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

### 10.2 ปิด popup แจ้งอัปเดตอัตโนมัติของ Chromium (ถ้าใช้ apt/.deb เวอร์ชันมี auto-update)

เพิ่ม flag `--simulate-outdated-no-au` หรือปิด service อัปเดตของแพ็กเกจนั้นแยกตามที่มา (PPA ส่วนใหญ่ไม่ auto-update บังคับ ต่างจาก snap ที่ auto-refresh ตามรอบของ snapd)

### 10.3 ปิดคีย์ลัดหลุดออกจาก Openbox (ถ้ามีคีย์บอร์ดต่ออยู่กับตู้)

แก้ `~/.config/openbox/rc.xml` ของ `kiosk-user` — ลบ/comment ทิ้งทุก `<keybind>` ที่ผูกกับ `A-Tab` (สลับหน้าต่าง), `W-e` (เปิด terminal), หรือคีย์ลัดอื่นที่ default มากับ Openbox หากไม่มีคีย์บอร์ดต่อจริงบนตู้ ข้ามขั้นนี้ได้

---

## 11. Reboot ทดสอบ + Checklist

```bash
sudo reboot
```

หลัง boot เสร็จ เช็คตามลำดับนี้:

| # | เช็คอะไร | คำสั่ง/วิธีเช็ค | ผลที่ควรเห็น |
|---|---|---|---|
| 1 | เข้า X11 ไม่ใช่ Wayland | `echo $XDG_SESSION_TYPE` (รันใน terminal ของ kiosk-user) | `x11` |
| 2 | Login เป็น kiosk-user อัตโนมัติจริง | `loginctl list-sessions` | เห็น session ของ `kiosk-user` มี Seat |
| 3 | Session type เป็น Openbox | `loginctl show-session <ID> -p Type -p Class` | ไม่ใช่ gnome |
| 4 | Network พร้อมก่อน Chromium ขึ้น | `cat /home/kiosk-user/.config/openbox/kiosk-launch.log` | เห็นบรรทัด "network ready after Ns" |
| 5 | Chromium เปิดเต็มจอ ไม่มี address bar | ดูจอจริง | เต็มจอ ไม่มี UI เบราว์เซอร์ |
| 6 | Chromium ไม่ดับจอ/เข้า screensaver | รอ 10+ นาทีแล้วดูจอ | จอยังสว่างอยู่ |
| 7 | Crash แล้วเปิดใหม่เองจริง | `pkill chromium` แล้วรอ | Chromium เด้งกลับมาเองใน ~2 วิ |

---

## 12. Troubleshooting

**จอค้างสีเทา ไม่มี Chromium ขึ้นเลย**
เช็ค `kiosk-launch.log` — ถ้าไม่มีไฟล์เลยหรือว่างเปล่า แปลว่า `autostart` ไม่ถูกเรียก ตรวจสอบสิทธิ์ executable (`ls -l ~/.config/openbox/autostart` ต้องมี `x`) และ session type ว่าเป็น `openbox` จริง (`cat /var/lib/AccountsService/users/kiosk-user`)

**Chromium ขึ้น `ERR_INTERNET_DISCONNECTED` ทั้งที่เน็ตต่อจริง**
แปลว่า loop รอ network ในข้อ 9 timeout ก่อนเน็ตจะพร้อม — เพิ่มค่า `MAX_WAIT` ในสคริปต์ หรือเช็คว่า `systemd-networkd-wait-online`/`NetworkManager-wait-online` (ข้อ 1.5) enable อยู่จริงไหม (`systemctl is-enabled NetworkManager-wait-online.service`)

**Login วนกลับไปหน้า GDM greeter ไม่เข้า desktop เลย**
มักเกิดจาก session `openbox` หาไม่เจอ — เช็ค `ls /usr/share/xsessions/openbox.desktop` มีจริงไหม (ถ้าไม่มี แปลว่าแพ็กเกจ `openbox` ยังไม่ถูกติดตั้งสมบูรณ์ ให้รัน `sudo apt install --reinstall openbox`)

**`chromium: command not found`**
เช็คว่าติดตั้งสำเร็จจริง (`dpkg -l | grep chromium` หรือ `snap list | grep chromium`) — ถ้าใช้ snap ต้อง restart session ก่อน `PATH` ของ snap bin จะพร้อม (`/snap/bin` ต้องอยู่ใน `$PATH` ของ user นั้น)

**อยากยกเลิก kiosk กลับไปใช้เครื่องปกติ**

```bash
sudo nano /etc/gdm3/custom.conf   # ลบ AutomaticLoginEnable / AutomaticLogin ออก
sudo rm /var/lib/AccountsService/users/kiosk-user
sudo systemctl restart gdm3
```
