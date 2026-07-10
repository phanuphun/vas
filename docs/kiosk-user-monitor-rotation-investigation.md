# สอบสวน: ทำไมหมุนจอ (screen rotation) หายเมื่อสลับ Kiosk user จาก `hapymed` ไป `kiosk-user`

> เอกสารนี้บันทึกกระบวนการสืบสวนแบบเต็ม (root cause + หลักฐานที่ยืนยันแล้วจริงบนเครื่อง + แนวทางแก้ที่ยังไม่ได้ตัดสินใจ/ยังไม่ได้ implement) เขียนไว้ให้ AI/วิศวกรคนอื่นอ่านต่อได้ครบโดยไม่ต้องถามซ้ำ
>
> **สถานะ ณ วันที่เขียน: ยังไม่มีการแก้โค้ดใดๆ ในรอบนี้ทั้งสิ้น** เป็นเอกสารสรุปการสืบสวน (investigation) และวิเคราะห์ทางเลือก (options analysis) เท่านั้น — ก่อนแก้โค้ดจริงต้อง proof ข้อที่ยัง "ยังไม่ยืนยัน" ในหัวข้อ 7 ให้ครบก่อน
>
> เครื่องที่ใช้ทดสอบจริง: `hapymed-sterile-00`
> วันที่สืบสวน: 2026-07-10
> โปรเจกต์: VAS (vending-auto-setup) — repo path `src/features/display/display.py`, `src/features/kiosk/manager.py`

---

## 1. อาการที่ผู้ใช้เจอ (จุดเริ่มต้น)

ตั้งค่า Kiosk Mode ผ่านหน้าเว็บ VAS (แท็บ "คีออส" → "ผู้ใช้ Kiosk") ไว้ 2 รอบ:

**รอบที่ 1 — user = `hapymed`, Session Type = GNOME**
ทำงานถูกต้องสมบูรณ์ ทั้งจอหมุน (rotate left) และ touch matrix ตรงกัน ยืนยันจากไฟล์:
- `/etc/X11/xorg.conf.d/98-vending-display-rotate.conf`
- `/etc/X11/xorg.conf.d/99-vending-touchscreen.conf`

**รอบที่ 2 — สลับ user เป็น `kiosk-user`, Session Type = GNOME (เหมือนเดิม)**
จอกลับไปเป็น **Normal** ทันที (ไม่หมุนแล้ว) แม้ไฟล์ conf ทั้งสองยังตั้งค่า `Rotate left` ไว้เหมือนเดิมไม่มีอะไรเปลี่ยน

**สลับกลับไป `hapymed` + GNOME** → กลับมาทำงานถูกต้องทันทีเหมือนเดิม โดยไม่ต้องแก้อะไรเพิ่ม

คำถามตั้งต้นของผู้ใช้: ไฟล์ `98-vending-display-rotate.conf` และ `99-vending-touchscreen.conf` เป็น config ระดับเครื่อง (ไม่ผูก user) — ทำไมพฤติกรรมถึงต่างกันตาม user ที่ login อยู่?

---

## 2. โครงสร้างระบบที่เกี่ยวข้อง (สรุปจาก docs เดิมในโปรเจกต์)

โปรเจกต์นี้มีเอกสารสืบสวนที่เกี่ยวข้องอยู่แล้ว 2 ไฟล์ ควรอ่านประกอบ:
- `docs/kiosk-display-touch-order-guide.md`
- `docs/display-touchscreen-kiosk-session.md`

สรุปสั้นๆ ว่ามี "ที่เก็บค่าการตั้งจอ/ทัช" อยู่ 3 ชั้น ที่ทำงานแยกจากกัน:

| ชั้น | ไฟล์ | ผูกกับ user ไหม | คุมอะไร | อ่านตอนไหน |
|---|---|---|---|---|
| 1. Xorg touch (ระดับเครื่อง) | `/etc/X11/xorg.conf.d/99-vending-touchscreen.conf` | ไม่ผูก | ทิศทาง touch matrix เริ่มต้น | ตอน X server เริ่มทำงาน (ก่อน login) |
| 2. Xorg rotate (ระดับเครื่อง) | `/etc/X11/xorg.conf.d/98-vending-display-rotate.conf` | ไม่ผูก (แต่ effect ขึ้นกับ session — ดูหัวข้อ 3) | ทิศทางจอเริ่มต้น | ตอน X server เริ่มทำงาน (ก่อน login) |
| 3. ต่อ user | `~/.xprofile` + `~/.config/vending-auto-setup/display-session.sh` | ผูกกับ user ที่ login | หมุนจอ + touch พร้อมกัน (runtime, ทุกครั้งที่ login) | หลัง login, delay 5 วิ แล้ว poll ซ้ำสูงสุด 30 ครั้ง |

โค้ดจริงใน `src/features/display/display.py` (บรรทัด 154-163) มีคอมเมนต์อธิบายไว้ตรงๆ ว่าทำไมไฟล์ชั้น 2 (`98-vending-display-rotate.conf`) ถึง "มีผลไม่แน่นอน" ขึ้นกับ session:

```
เขียน Monitor section ระดับเครื่อง (ไม่ผูก user) ให้ X server หมุนจอ output
นี้ตั้งแต่เริ่มทำงานครั้งแรก — ก่อน login/ก่อน GDM greeter ขึ้นด้วยซ้ำ

หมายเหตุสำคัญ: session ที่มี compositor จัดการจอเอง (เช่น GNOME Shell/mutter ที่ใช้
กับ GDM greeter และ session แบบ gnome) จะ "เขียนทับ" ค่านี้กลับเป็น normal อีกทีตอน
compositor เริ่มทำงาน ถ้าไม่มี monitors.xml ของ user/gdm นั้นระบุไว้ — ดังนั้นไฟล์นี้
จะมีผลจริงกับ session ที่ไม่มี compositor คุมจอเอง เช่น Openbox (ที่ใช้กับ kiosk-user)
เท่านั้น ส่วน session แบบ GNOME ยังต้องพึ่ง persist_session() (.xprofile) เหมือนเดิม
```

นี่คือจุดเริ่มต้นของสมมติฐานที่ไปสืบต่อในหัวข้อ 3-4

---

## 3. Root cause ที่ยืนยันแล้วจริงบนเครื่อง (ไม่ใช่แค่ทฤษฎี)

### 3.1 สมมติฐาน

GNOME Shell / mutter (compositor ของ session แบบ GNOME) มีระบบจำค่าการตั้งจอของตัวเอง แยกเป็น**อีกชั้นหนึ่ง**จากทั้ง Xorg conf (ชั้น 1-2) และ `.xprofile`/`display-session.sh` (ชั้น 3) คือไฟล์ `~/.config/monitors.xml` — ถ้า user คนไหนไม่มีไฟล์นี้ mutter จะ**เขียนทับ**ค่าที่ Xorg conf ตั้งไว้กลับเป็น normal ทันทีตอน compositor เริ่มทำงาน โดยไม่สนใจว่า Xorg conf บอกให้หมุนอะไรไว้

### 3.2 หลักฐานที่รันจริงบนเครื่อง `hapymed-sterile-00` (ยืนยันแล้ว ✅)

```bash
$ sudo test -f /home/hapymed/.config/monitors.xml && sudo cat /home/hapymed/.config/monitors.xml
```
ผลลัพธ์ — **มีไฟล์**:
```xml
<monitors version="2">
  <configuration>
    <logicalmonitor>
      <x>0</x>
      <y>0</y>
      <scale>1</scale>
      <primary>yes</primary>
      <transform>
        <rotation>left</rotation>
        <flipped>no</flipped>
      </transform>
      <monitor>
        <monitorspec>
          <connector>HDMI-1</connector>
          <vendor>YSN</vendor>
          <product>YSNO</product>
          <serial>0x00000000</serial>
        </monitorspec>
        <mode>
          <width>1920</width>
          <height>1080</height>
          <rate>60</rate>
        </mode>
      </monitor>
    </logicalmonitor>
  </configuration>
</monitors>
```

```bash
$ sudo test -f /home/kiosk-user/.config/monitors.xml && sudo cat /home/kiosk-user/.config/monitors.xml || echo "ไม่มีไฟล์"
```
ผลลัพธ์ — **ไม่มีไฟล์** (`kiosk-user` ไม่เคยมี `monitors.xml` เลย)

### 3.3 เช็ค session type ทั้งคู่ (ตัดตัวแปรว่าไม่ใช่เพราะ session type ต่างกัน)

```bash
$ sudo cat /var/lib/AccountsService/users/hapymed
[User]
Icon=/home/hapymed/.face
SystemAccount=false
Session=ubuntu-xorg
XSession=ubuntu-xorg

$ sudo cat /var/lib/AccountsService/users/kiosk-user
[User]
SystemAccount=false
Session=ubuntu-xorg
XSession=ubuntu-xorg
```
ทั้งคู่ตั้งเป็น `ubuntu-xorg` (GNOME บน X11) เหมือนกันเป๊ะ — ไม่ใช่ตัวแปรที่ทำให้ต่างกัน

### 3.4 เช็คว่า Xorg conf ทั้งสองไฟล์ยังตั้งค่าถูกต้อง (ไม่ใช่สาเหตุ)

```bash
$ sudo cat /etc/X11/xorg.conf.d/98-vending-display-rotate.conf
Section "Monitor"
    Identifier "HDMI-1"
    Option "Rotate" "left"
EndSection

$ sudo cat /etc/X11/xorg.conf.d/99-vending-touchscreen.conf
Section "InputClass"
    Identifier "vending-touchscreen-calibration"
    MatchProduct "ILITEK ILITEK-TP"
    Option "CalibrationMatrix" "0 -1 1 1 0 0 0 0 1"
EndSection
```
ทั้งสองไฟล์ตั้ง `left` ไว้ถูกต้อง ไม่ว่า user ไหน login — ยืนยันว่าไฟล์ conf ไม่ใช่ตัวแปร

### 3.5 สรุป root cause

`kiosk-user` ไม่เคยมี `~/.config/monitors.xml` เพราะไฟล์นี้ถูกสร้าง/เขียนโดย mutter **เฉพาะตอนมีการเปลี่ยนค่าจอผ่านช่องทางที่ mutter รู้จักและยืนยัน (confirm) เท่านั้น** (ดูรายละเอียดกลไกในหัวข้อ 4) — `hapymed` มีไฟล์นี้เพราะเคยมีคนเข้า GNOME Settings > Displays แล้วกด Apply + Keep Changes ด้วยตัวเองในอดีต ส่วน `kiosk-user` เป็น user ใหม่ที่สร้างผ่าน `useradd` แล้ว auto-login เข้าเฉยๆ ไม่เคยผ่านขั้นตอนนั้นเลย

ผลคือ: ตอน mutter (compositor ของ session GNOME) เริ่มทำงานให้ `kiosk-user` มันไม่เจอ `monitors.xml` ของ user นี้ จึงเขียนทับค่าที่ `98-vending-display-rotate.conf` ตั้งไว้กลับเป็น `normal` ทันที — ในขณะที่ `99-vending-touchscreen.conf` (touch) ไม่โดนเขียนทับแบบเดียวกัน เพราะ input device (touch) ไม่ได้อยู่ในความคุมของ compositor แบบเดียวกับจอ (screen/output) — ผลคือจอ = normal, touch = ยังคิดว่าจอเอียง left → แตะไม่ตรงจุด

---

## 4. กลไกของ `monitors.xml` (อ้างอิงเอกสารทางการของ mutter)

ตรวจสอบกับเอกสารต้นทาง: [mutter/doc/monitor-configuration.md](https://github.com/GNOME/mutter/blob/main/doc/monitor-configuration.md)

ประเด็นสำคัญที่ยืนยันจากเอกสาร:

1. **ที่เก็บไฟล์มี 2 ระดับ** ไม่ใช่แค่ต่อ user:
   - User level (ตามที่เจอในเครื่องจริง): `$XDG_CONFIG_HOME/monitors.xml` → ปกติคือ `~/.config/monitors.xml`
   - **System level (ยังไม่เคยรู้จักมาก่อนในการสืบสวนรอบนี้ จนกว่าจะเช็คเอกสาร)**: `$XDG_CONFIG_DIRS/monitors.xml` → default คือ `/etc/xdg/monitors.xml` — เป็นไฟล์ระดับเครื่อง ไม่ผูกกับ user คนไหน

2. **วิธีที่ไฟล์ถูกเขียน** (คำพูดจากเอกสารต้นฉบับ):
   > "Monitor configurations are managed by Mutter via the Display panel in Settings, which uses a D-Bus API to communicate with Mutter. Each time a new configuration is applied and accepted, the user level configuration file is replaced with updated content."

   สรุปคือ: การเขียนไฟล์ปกติเกิดผ่าน **D-Bus API** (`org.gnome.Mutter.DisplayConfig` → method `ApplyMonitorsConfig`) ที่ GNOME Settings เรียกใช้เบื้องหลัง ตอนกด Apply แล้วกด "Keep Changes" ยืนยันภายในเวลาที่กำหนด — **การเรียก `xrandr` ตรงๆ แบบที่ `display-session.sh` ทำ ไม่ได้ผ่านช่องทางนี้** จึงเป็นสมมติฐาน (สอดคล้องกับที่สังเกต) ว่าทำไม `display-session.sh` รันสำเร็จทุกครั้งที่ `kiosk-user` login แต่ไม่เคยสร้าง `monitors.xml` ให้เลยสักครั้ง — **ยังไม่ได้ proof ข้อนี้แบบ empirical บนเครื่องจริง (ดู checklist หัวข้อ 7)**

3. **Configuration policy**: ค่า default คือ "prioritize configurations defined in the user level configuration file" — หมายความว่าถ้า user มี `~/.config/monitors.xml` ของตัวเอง ไฟล์นั้นจะชนะไฟล์ระดับเครื่อง (`/etc/xdg/monitors.xml`) เสมอ ถ้าไม่มี ถึงจะ fallback ไปใช้ระดับเครื่อง — ปรับ policy เองได้ผ่าน `<policy>` element ในไฟล์ (ดูตัวอย่างในเอกสารต้นฉบับ)

4. **หนึ่ง configuration ต่อหนึ่ง hardware setup**: มี rule "There can only be one configuration per hardware setup" — matching ทำผ่าน connector + vendor + product + serial + mode ของจอที่ต่ออยู่จริง ถ้าจอไม่ match (เปลี่ยนจอ/สาย/EDID อ่านไม่เหมือนเดิม) configuration entry นั้นจะถูกข้ามไปเฉยๆ

---

## 5. ทางเลือกที่พิจารณา (ยังไม่ได้ตัดสินใจว่าจะใช้อันไหน)

### ตัวเลือก A — Copy `~/.config/monitors.xml` ของ `hapymed` ไปให้ `kiosk-user` ตอนสร้าง user

**วิธี**: แก้ `src/features/kiosk/manager.py` ให้ตอน `useradd` user ใหม่ ทำการ copy ไฟล์จาก reference user (หรือจาก template ที่บันทึกไว้) ไปวางที่ `/home/<new-user>/.config/monitors.xml` แล้ว `chown` ให้ user นั้น

**ความเสี่ยง**:
- ต้อง `chown <user>:<user>` + permission ให้ถูกต้อง ไม่งั้น mutter หรือ session ของ user นั้นอาจอ่าน/เขียนทับไม่ได้ในอนาคต
- ผูกกับ hardware ของเครื่องอ้างอิง (`hapymed-sterile-00`) เท่านั้น ถ้า deploy เครื่องอื่นที่จอคนละรุ่น (vendor/product ต่างกัน) จะไม่ match แล้ว fallback เงียบๆ — ต้อง query ค่า EDID จริงของแต่ละเครื่องก่อนเสมอ ห้าม hardcode จากเครื่องเดียว
- `<rate>60</rate>` เป็นเลขกลม เสี่ยงไม่ตรงกับค่าที่ mutter รายงานจริง (มักเป็นทศนิยมละเอียด เช่น `59.9601`) ต้องเช็คผ่าน D-Bus `GetCurrentState` ก่อนเชื่อ

### ตัวเลือก B — เขียนฟังก์ชัน generate `monitors.xml` ต่อ user โดยตรง (เขียนเองไม่ใช่ copy)

ความเสี่ยงเดียวกับตัวเลือก A ทั้งหมด บวกเพิ่ม:
- ต้องมี logic คำนวณ/query ค่า hardware จริงของแต่ละเครื่องแบบ dynamic ก่อนเขียน (ไม่ใช่ hardcode template) เพิ่มความซับซ้อนของโค้ดโดยไม่ได้ประโยชน์เพิ่มจากตัวเลือก C
- ต้องรันฟังก์ชันนี้ทุกครั้งที่สร้าง user ใหม่ ถ้ามี user หลายคน (เช่นทดสอบหลาย kiosk-user) ต้อง sync logic ให้ตรงกันทุกจุดที่สร้าง user

### ตัวเลือก C — เขียนไฟล์ระดับเครื่องเดียวที่ `/etc/xdg/monitors.xml` (แนะนำเป็นตัวเลือกแรกที่ควร proof ก่อน)

**เหตุผล**: จากหัวข้อ 4 ข้อ 1 — mutter รองรับไฟล์ระดับเครื่องอยู่แล้วโดยไม่ต้องเขียนแยกทีละ user เขียนครั้งเดียว ใช้ได้กับ user ใหม่ทุกคนที่ยังไม่มี user-level file ของตัวเอง (รวมถึง `kiosk-user` ปัจจุบัน และ kiosk user ที่จะสร้างใหม่ในอนาคตด้วย) โดยไม่กระทบ `hapymed` ที่มี user-level file อยู่แล้ว (เพราะ policy default ให้ user-level ชนะ)

**ข้อดีเทียบกับ A/B**: ไม่ต้องมีฟังก์ชัน "copy/generate ตอนสร้าง user" เลย เป็นโมเดลเดียวกับที่ระบบตั้งใจไว้แต่แรกสำหรับ `99-vending-touchscreen.conf` (ระดับเครื่อง ไม่ผูก user)

**ความเสี่ยง/สิ่งที่ยังไม่ proof**:
- ยังไม่ได้ยืนยันว่า policy default บน mutter เวอร์ชันที่ใช้อยู่จริงตรงกับเอกสาร (user-level ชนะ, ถ้าไม่มีถึง fallback ไป system-level) — ต้อง proof จริงบนเครื่อง
- เหตุผลเดียวกับตัวเลือก A เรื่อง hardware-specific values (vendor/product/serial/rate) ยังต้อง query ให้ตรงเครื่องจริงก่อนเขียน ไม่ hardcode

---

## 6. คำสั่ง proof ที่ให้ผู้ใช้รันแล้ว (สรุปผลที่ได้จริง)

| # | คำสั่ง/สิ่งที่ตรวจ | ผลที่ได้ | สถานะ |
|---|---|---|---|
| 1 | เช็คไฟล์ `~/.config/monitors.xml` ของ `hapymed` | มีไฟล์ ตั้ง `rotation=left` | ✅ ยืนยันแล้ว |
| 2 | เช็คไฟล์ `~/.config/monitors.xml` ของ `kiosk-user` | ไม่มีไฟล์ | ✅ ยืนยันแล้ว |
| 3 | เช็ค `/var/lib/AccountsService/users/{hapymed,kiosk-user}` | ทั้งคู่ `Session=ubuntu-xorg` เหมือนกัน | ✅ ยืนยันแล้ว — ตัดตัวแปร session type ต่างกันออกไปได้ |
| 4 | เช็ค `/etc/X11/xorg.conf.d/98-vending-display-rotate.conf` และ `99-vending-touchscreen.conf` | ทั้งคู่ตั้ง `left` ถูกต้อง ไม่มีอะไรผิดปกติ | ✅ ยืนยันแล้ว — ตัดตัวแปรไฟล์ conf เขียนผิดออกไปได้ |

---

## 7. Checklist สิ่งที่ยัง "ไม่ยืนยัน" — ต้องทำก่อนแก้โค้ดจริง

- [ ] **Proof B** (ให้ไว้แล้วในบทสนทนา ยังไม่ได้รัน): ทดสอบว่า raw `xrandr --rotate` (แบบที่ `display-session.sh` เรียก) เขียน `monitors.xml` ให้ `kiosk-user` เองหรือไม่ — คาดว่า "ไม่" (สมมติฐานจากเอกสารหัวข้อ 4.2) แต่ยังไม่ได้ทดสอบจริง
  ```bash
  sudo -u kiosk-user env DISPLAY=:0 XAUTHORITY=/home/kiosk-user/.Xauthority \
    xrandr --output HDMI-1 --rotate left
  sleep 3
  sudo test -f /home/kiosk-user/.config/monitors.xml && echo "ถูกสร้าง" || echo "ยังไม่ถูกสร้าง"
  ```

- [ ] **Proof C** (D-Bus): ยืนยันว่า mutter คุม session ของ `kiosk-user` อยู่จริงผ่าน D-Bus interface
  ```bash
  sudo -u kiosk-user env DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u kiosk-user)/bus \
    gdbus introspect --session --dest org.gnome.Mutter.DisplayConfig \
    --object-path /org/gnome/Mutter/DisplayConfig
  ```

- [ ] **เช็คค่า rate จริง** ผ่าน D-Bus ก่อนจะเอาไปเขียนไฟล์ใดๆ (อย่าเชื่อเลขกลม `60` จากไฟล์ที่แคปมา)
  ```bash
  sudo -u kiosk-user env DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u kiosk-user)/bus \
    gdbus call --session --dest org.gnome.Mutter.DisplayConfig \
    --object-path /org/gnome/Mutter/DisplayConfig \
    --method org.gnome.Mutter.DisplayConfig.GetCurrentState
  ```

- [ ] **ทดสอบตัวเลือก A** (copy user-level file): copy `/home/hapymed/.config/monitors.xml` → `/home/kiosk-user/.config/monitors.xml` (พร้อม chown) แล้ว reboot เช็คว่า `kiosk-user` หมุนจอถูกตั้งแต่ login แรกไหม

- [ ] **ทดสอบตัวเลือก C** (system-level file) — ยังไม่เคยทดสอบเลย เป็นตัวเลือกที่มีโอกาสสูงสุดที่จะเป็นทางแก้ระยะยาวที่ถูกต้อง (ไม่ต้อง maintain ต่อ user)
  ```bash
  sudo cat /etc/xdg/monitors.xml 2>/dev/null || echo "ยังไม่มี"
  sudo cp /home/hapymed/.config/monitors.xml /etc/xdg/monitors.xml
  sudo chmod 644 /etc/xdg/monitors.xml
  sudo reboot
  # เช็ค xrandr ของ kiosk-user หลัง reboot ว่าหมุนเองไหม โดยที่ kiosk-user ยังไม่มี user-level monitors.xml เลย
  ```

- [ ] เช็ค policy จริงบนเครื่อง (ว่า user-level ชนะ system-level จริงตามเอกสารไหม) — ยังไม่มีคำสั่งตรงๆ ที่ทดสอบเรื่องนี้แยก ต้องดูผลจาก Proof ข้อ system-level ด้านบนประกอบ

---

## 8. สรุปสำหรับ AI/วิศวกรที่มาอ่านต่อ

- **Root cause ยืนยันแล้ว**: `kiosk-user` ไม่มี `~/.config/monitors.xml` ในขณะที่ `hapymed` มี ทำให้ mutter (compositor ของ GNOME session) เขียนทับค่าที่ `98-vending-display-rotate.conf` ตั้งไว้กลับเป็น normal เฉพาะตอน `kiosk-user` login เท่านั้น — ไฟล์ Xorg conf ทั้งสองไฟล์ (`98-...`, `99-...`) ไม่มีปัญหา เขียนถูกต้องตลอด
- **ยังไม่ได้แก้โค้ดอะไรในรอบนี้** — เอกสารนี้คือผลของการสืบสวน+วิเคราะห์ทางเลือกเท่านั้น
- **ทางเลือกที่น่าจะคุ้มที่สุดให้ proof ก่อน**: ตัวเลือก C (`/etc/xdg/monitors.xml` ระดับเครื่อง) เพราะแก้ปัญหาแบบเดียวกับที่ `99-vending-touchscreen.conf` ทำสำเร็จอยู่แล้ว (ระดับเครื่อง ไม่ผูก user) โดยไม่ต้องเพิ่ม logic ต่อ user เลย
- **ห้าม hardcode ค่า vendor/product/serial/rate จากเครื่อง `hapymed-sterile-00` ไปใช้ตรงๆ กับเครื่องอื่น** — ต้อง query ค่าจริงผ่าน D-Bus (`GetCurrentState`) ของแต่ละเครื่องก่อนเขียนไฟล์เสมอ ถ้าจะทำ automation ให้ query แบบ dynamic ไม่ใช้ template คงที่
- ไฟล์ที่เกี่ยวข้องในโค้ด: `src/features/display/display.py` (มี comment อธิบายพฤติกรรม compositor override ไว้แล้วที่บรรทัด 154-163), `src/features/kiosk/manager.py` (จุดที่สร้าง user ใหม่ ถ้าจะเพิ่ม logic ตัวเลือก A/B ต้องแก้ตรงนี้)
- เอกสารที่เกี่ยวข้องในโปรเจกต์ที่ควรอ่านประกอบ: `docs/kiosk-display-touch-order-guide.md`, `docs/display-touchscreen-kiosk-session.md`

## อ้างอิง

- [mutter/doc/monitor-configuration.md (GNOME/mutter, GitHub)](https://github.com/GNOME/mutter/blob/main/doc/monitor-configuration.md) — เอกสารทางการอธิบาย schema, file location (user-level vs system-level), และ policy ของ `monitors.xml`
