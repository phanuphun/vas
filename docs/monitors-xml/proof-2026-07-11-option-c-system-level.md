# Proof: ตัวเลือก C (`/etc/xdg/monitors.xml` ระดับเครื่อง) แก้ปัญหาจอไม่หมุนตอนสลับ Kiosk user ได้จริง

> วันที่ทดสอบ: 2026-07-11
> เครื่องที่ใช้ทดสอบ: `ubuntu2204-first-test` (VirtualBox VM, Ubuntu 22.04 + GDM3) — **ไม่ใช่เครื่อง production `hapymed-sterile-00`**
> User ที่ใช้แทน `hapymed` เดิม: `first` (role เดียวกัน — user ที่เคยผ่าน GNOME Settings มาแล้วมี `monitors.xml` เป็นของตัวเอง)
> เอกสารต้นทางของการสืบสวนนี้: [`docs/kiosk-user-monitor-rotation-investigation.md`](../kiosk-user-monitor-rotation-investigation.md) — อ่านก่อนถ้ายังไม่เคยอ่าน จะเข้าใจ root cause และทางเลือกที่พิจารณาไว้ทั้งหมด
>
> **สรุปผลใน 1 บรรทัด**: copy ไฟล์ `~/.config/monitors.xml` (ที่มี rotation ตั้งไว้แล้ว) ไปวางที่ `/etc/xdg/monitors.xml` (ระดับเครื่อง ไม่ผูก user) แล้ว user คนอื่นที่ไม่มีไฟล์ของตัวเอง (`kiosk-user`) หมุนจอถูกต้องตั้งแต่ login แรกทันที — proof สำเร็จ ✅

---

## ส่วนที่ 1 — อธิบายแบบไม่เทคนิค (สำหรับทุกคนอ่านเข้าใจ)

### ปัญหาคืออะไร

เครื่อง vending ตั้งจอให้หมุน (เพราะจอติดตั้งแนวตั้ง) โดยตั้งค่าไว้ที่ระดับเครื่อง คิดว่าไม่ว่าใคร login เข้ามาก็ต้องหมุนเหมือนกันหมด แต่พบว่า:

- login ด้วย user คนที่ 1 (เคยเข้าไปตั้งค่าจอด้วยตัวเองผ่านเมนู Settings มาก่อน) → จอหมุนถูกต้อง
- login ด้วย user คนที่ 2 (user สำหรับ kiosk โดยเฉพาะ ไม่เคยมีใครเข้าไปตั้งค่าอะไรเลย) → จอกลับมาเป็นปกติ (ไม่หมุน) ทันที ทั้งที่ตั้งค่าระดับเครื่องไว้เหมือนกัน

สาเหตุคือ Ubuntu ที่ใช้ GNOME (หน้าตาระบบที่ผู้ใช้เห็น) มีระบบ "จำค่าการตั้งจอ" แยกเป็นของตัวเองต่อ 1 user คนไหนไม่เคยเข้าไปกดตั้งค่าจอด้วยตัวเองผ่านเมนู ก็จะไม่มี "ไฟล์จำค่า" นี้เลย พอไม่มีไฟล์นี้ ระบบ GNOME จะเข้าใจว่า "ยังไม่เคยตั้งอะไรไว้" แล้วเซ็ตจอกลับไปเป็นค่าเริ่มต้น (ไม่หมุน) ทันที ไม่สนใจว่าตั้งค่าระดับเครื่องไว้อย่างไร

### ทางแก้ที่ทดสอบวันนี้

แทนที่จะต้องไปสร้าง "ไฟล์จำค่า" แยกให้ user ทุกคนที่จะสร้างในอนาคต (ยุ่งยาก ต้องทำซ้ำทุกครั้ง) เราลองเอา "ไฟล์จำค่า" ของ user ที่ตั้งถูกต้องแล้ว ไปวางไว้ที่ตำแหน่งกลางของเครื่อง (ไม่ผูกกับ user คนไหน) เพื่อให้เป็น "ค่าเริ่มต้นสำรอง" — ถ้า user คนไหนไม่มีไฟล์ของตัวเอง ระบบจะไปอ่านไฟล์กลางนี้แทน

### ผลลัพธ์

**ได้ผลจริง** — user ตัวที่สอง (ที่ไม่เคยตั้งค่าอะไรเลย) หมุนจอถูกต้องทันทีตั้งแต่ login แรก โดยไม่ต้องไปตั้งค่าอะไรเพิ่มเลย

### ขั้นตอนถัดไป (ยังไม่ได้ทำ)

ตอนนี้เป็นแค่การพิสูจน์ว่า "แนวทางนี้ใช้ได้" ด้วยมือ (copy ไฟล์เอง) ยังไม่ได้เขียนเป็นโปรแกรมอัตโนมัติ ขั้นต่อไปคือต้องเขียนโค้ดให้ระบบทำขั้นตอนนี้เองอัตโนมัติตอนติดตั้งเครื่องใหม่ทุกครั้ง (ดึงค่าจริงของจอเครื่องนั้นๆ ไม่ใช่ copy ค่าจากเครื่องอื่นมาใช้ตรงๆ เพราะจอแต่ละรุ่น/เครื่องมีค่าทางเทคนิคไม่เหมือนกัน) และต้องทดสอบซ้ำบนเครื่อง vending จริงอีกครั้งก่อนใช้งานจริง (วันนี้ทดสอบบนเครื่องจำลอง/VM เท่านั้น)

---

## ส่วนที่ 2 — รายละเอียดทางเทคนิค (คำสั่งจริงที่ใช้ + ผลลัพธ์)

### สิ่งที่ต้องรู้ก่อนอ่าน

- `monitors.xml` คือไฟล์ config ของ **mutter** (compositor ของ GNOME) เก็บค่าการหมุนจอ/ตำแหน่งจอ มี 2 ระดับ:
  - User-level: `~/.config/monitors.xml` — ผูกกับ user คนเดียว, mutter เขียนให้เองเฉพาะตอน user กด **Apply + Keep Changes** ผ่าน Settings > Displays เท่านั้น (ผ่าน D-Bus API)
  - System-level: `/etc/xdg/monitors.xml` — ไม่ผูก user คนไหน, ใช้เป็น fallback เมื่อ user ที่ login ไม่มี user-level file ของตัวเอง (ตาม policy default ของ mutter — user-level ชนะเสมอถ้ามี)
- `xrandr` (คำสั่งที่ `display-session.sh`/VAS ใช้หมุนจอ runtime) เป็นคนละช่องทางกับ D-Bus โดยสิ้นเชิง — เรียก X server ตรงๆ ไม่ผ่าน mutter เลย

### ขั้นที่ 0 — เช็ค baseline ก่อนเริ่ม

```bash
sudo test -f /etc/xdg/monitors.xml && sudo cat /etc/xdg/monitors.xml || echo "ยังไม่มี system-level file — ตามคาด"
# → ยังไม่มี system-level file — ตามคาด

sudo test -f /home/kiosk-user/.config/monitors.xml && echo "มี user-level file แล้ว (ผิดคาด)" || echo "kiosk-user ยังไม่มี user-level file — ตามคาด"
# → kiosk-user ยังไม่มี user-level file — ตามคาด
```

ไฟล์ `~/.config/monitors.xml` ของ `first` (ใช้แทน role `hapymed`) ตอนเริ่มต้น **ยังไม่มี rotation** (ไม่มี tag `<transform>` เลย — เพราะยังไม่เคยหมุนจอผ่าน Settings มาก่อนบน VM นี้):

```xml
<monitors version="2">
  <configuration>
    <logicalmonitor>
      <x>0</x>
      <y>0</y>
      <scale>1</scale>
      <primary>yes</primary>
      <monitor>
        <monitorspec>
          <connector>Virtual1</connector>
          <vendor>unknown</vendor>
          <product>unknown</product>
          <serial>unknown</serial>
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

### ขั้นที่ 1 — Proof B: raw `xrandr` ไม่แก้ `monitors.xml` (ยืนยันสมมติฐานจากเอกสารต้นฉบับ)

หมุนจอผ่านหน้าเว็บ VAS (ปุ่ม "Left" + Apply ในหน้า "จอแสดงผล" — เบื้องหลังเรียก `xrandr` ตรงๆ แบบเดียวกับที่ `display-session.sh` ทำตอน login):

**ผลที่สังเกตได้**: จอหมุนจริงบนหน้าจอ **แต่ touch เพี้ยนเป็น Normal ทันที** (อาการเดียวกับปัญหาต้นเรื่องทั้งหมด — เพราะ mutter ไม่รู้จักการเปลี่ยนแปลงนี้)

เช็คไฟล์ว่ามีอะไรเปลี่ยนไหม:
```bash
cat /home/first/.config/monitors.xml | grep -A3 transform || echo "ไม่มี transform เพิ่มเข้ามา — ยืนยัน Proof B: raw xrandr ไม่แก้ monitors.xml"
# → ไม่มี transform เพิ่มเข้ามา — ยืนยัน Proof B: raw xrandr ไม่แก้ monitors.xml
```

**สรุป**: raw `xrandr` ไม่แตะ `monitors.xml` เลยไม่ว่าจอจะหมุนจริงแค่ไหนบนหน้าจอ — ยืนยันตรงตามสมมติฐานในเอกสารต้นฉบับ (หัวข้อ 4.2)

### ขั้นที่ 2 — หมุนจอผ่าน GNOME Settings จริง (ช่องทางที่เขียน `monitors.xml` ได้)

เข้า **Activities → Settings → Displays** → เลือก Orientation "Left" → **Apply** → **Keep Changes** (ต้องกดยืนยันภายในเวลาที่กำหนด ไม่งั้น revert อัตโนมัติ)

หลังจากนี้ `/home/first/.config/monitors.xml` มี `<transform><rotation>left</rotation>...>` เพิ่มเข้ามาจริง (ยืนยันด้วยตาเปล่าจากเนื้อหาไฟล์)

### ขั้นที่ 3 — Copy ไปเป็น system-level file

```bash
sudo cp /home/first/.config/monitors.xml /etc/xdg/monitors.xml
sudo chmod 644 /etc/xdg/monitors.xml
```

> ปลอดภัยที่จะ copy ค่าตรงๆ ในกรณีนี้เพราะเป็น**เครื่องเดียวกัน จอตัวเดียวกัน** — ค่า vendor/product/serial/rate ที่อยู่ในไฟล์เป็นค่าจริงของจอเครื่องนี้ (มาจาก mutter เขียนเองตอนกด Apply ผ่าน Settings จริง ไม่ใช่พิมพ์มือ) **ถ้าจะใช้ข้ามเครื่องต้อง query ค่าจริงของเครื่องปลายทางใหม่เสมอ** (ผ่าน D-Bus `GetCurrentState`) ห้ามเอาไฟล์นี้ไป copy ตรงๆ ข้ามเครื่อง

### ขั้นที่ 4 — สลับไป session ของ `kiosk-user`

ใช้ GDM **Switch User** (fast user switching) สลับจาก `first` ไปเป็น `kiosk-user` — **ข้อควรระวัง**: fast user switching ไม่ logout session เดิม แต่เปิด X server ใหม่คนละ display number ให้ user ที่สลับไป (เจอจริง: `first` อยู่ที่ `:1`, `kiosk-user` ได้ `:0` — เลข DISPLAY **สลับกันไปมาได้จริง ไม่ตายตัว** อย่าเดาเป็น `:0`/`:1` คงที่ ต้อง query หาใหม่ทุกครั้ง — ดูขั้นที่ 6)

### ขั้นที่ 5 — ยืนยันว่า `kiosk-user` ยังไม่มี user-level file (กัน false positive)

```bash
sudo test -f /home/kiosk-user/.config/monitors.xml && echo "มี user-level file แล้ว" || echo "ยังไม่มี ตามคาด"
# → ยังไม่มี ตามคาด
```

### ขั้นที่ 6 — หา DISPLAY + Xauthority จริงของ `kiosk-user`

ลองเดาค่า `:1`/`~/.Xauthority` แบบเดียวกับที่เคยเจอกับ `first` ก่อน แล้ว**ล้มเหลว**:
```bash
sudo -u kiosk-user env DISPLAY=:1 XAUTHORITY=/run/user/$(id -u kiosk-user)/gdm/Xauthority xrandr --query
# → Can't open display :1
```

เหตุผล: `:1` เป็น display ของ `first` เท่านั้น ไม่ใช่ของ `kiosk-user` — ต้องหาค่าจริงใหม่:

```bash
loginctl list-sessions --no-legend
# → 1 1001 kiosk-user seat0 tty2
#   3 1000 first            pts/0

sudo bash -c 'for pid in $(pgrep -u kiosk-user); do
  tr "\0" "\n" < /proc/$pid/environ 2>/dev/null | grep -m1 "^DISPLAY=" && echo "  (pid $pid $(cat /proc/$pid/comm 2>/dev/null))"
done | sort -u'
# → DISPLAY=:0
#     (pid 3126 gnome-shell)
#     ... (พบใน process อื่นๆ ของ kiosk-user อีกหลายสิบตัว ค่าตรงกันหมด)

sudo find /run/user/$(id -u kiosk-user) -iname "*auth*" 2>/dev/null
# → /run/user/1001/ICEauthority
#   /run/user/1001/gdm/Xauthority
```

### ขั้นที่ 7 — Proof สุดท้าย: เช็ค rotation จริงของ `kiosk-user`

```bash
sudo -u kiosk-user env DISPLAY=:0 XAUTHORITY=/run/user/1001/gdm/Xauthority xrandr --query
```

ผลลัพธ์:
```
Screen 0: minimum 1 x 1, current 1080 x 1920, maximum 16384 x 16384
Virtual1 connected primary 1080x1920+0+0 left (normal left inverted right x axis y axis) 0mm x 0mm
   800x600       60.00 +  60.32    56.25
   ...
```

**`1080x1920` (width/height สลับจาก 1920x1080) + keyword `left` ต่อท้าย = จอหมุนถูกต้องจริง** ทั้งที่ `kiosk-user` ไม่มี `~/.config/monitors.xml` เป็นของตัวเองเลยตลอดการทดสอบ

---

## สรุปสำหรับขั้นตอนถัดไป

1. **Implement เข้าโค้ดจริง**: เพิ่ม logic ใน `src/features/kiosk/manager.py` (หรือจุดที่เหมาะสม) ให้เขียน `/etc/xdg/monitors.xml` โดย query ค่า vendor/product/serial/rate จริงผ่าน D-Bus `org.gnome.Mutter.DisplayConfig.GetCurrentState` ของเครื่องนั้นๆ แบบ dynamic — **ห้าม hardcode/copy ค่าจากเครื่องทดสอบนี้ไปใช้เครื่องอื่น**
2. **Proof ที่ยังค้างอยู่** (ดู checklist เต็มใน [`docs/kiosk-user-monitor-rotation-investigation.md`](../kiosk-user-monitor-rotation-investigation.md) หัวข้อ 7):
   - Proof C (D-Bus introspect ยืนยันว่า mutter คุม session อยู่จริง) — ยังไม่ได้รันแยก
   - เช็ค policy ว่า user ที่มี user-level file อยู่แล้ว (เช่น `first`) ยังใช้ไฟล์ตัวเองต่อไป ไม่ถูก system-level file แทนที่ — ยังไม่ได้ proof แยก
3. **ทดสอบซ้ำบนเครื่อง production จริง** (`hapymed-sterile-00`) ก่อนขึ้นใช้งานจริง — proof รอบนี้ทำบน VM ทดสอบเท่านั้น
