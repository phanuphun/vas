# monitors.xml — เอกสารเฉพาะทาง

โฟลเดอร์นี้รวมเอกสารทั้งหมดที่เกี่ยวกับปัญหา/การแก้ไขเรื่องไฟล์ `monitors.xml` ของ GNOME (mutter) — สาเหตุที่ทำให้การหมุนจอ (screen rotation) ไม่ persist เวลาสลับ Kiosk user บนเครื่อง vending

แยกออกมาเป็นโฟลเดอร์ของตัวเองเพราะหัวข้อนี้มีความซับซ้อนเฉพาะทาง (พฤติกรรมของ GNOME/mutter, D-Bus, GDM session management) และคาดว่าจะมีเอกสารเพิ่มเติมตามมาอีก (implementation, proof บนเครื่อง production จริง, retrospective หลัง deploy ฯลฯ)

## เอกสารที่เกี่ยวข้อง (นอกโฟลเดอร์นี้)

- [`docs/kiosk-user-monitor-rotation-investigation.md`](../kiosk-user-monitor-rotation-investigation.md) — เอกสารสืบสวนต้นฉบับ: อาการ, root cause, ทางเลือกที่พิจารณา (A/B/C), checklist สิ่งที่ต้อง proof ก่อนแก้โค้ดจริง **อ่านไฟล์นี้ก่อนเป็นอันดับแรก** เพื่อเข้าใจบริบททั้งหมด
- [`docs/kiosk-display-touch-order-guide.md`](../kiosk-display-touch-order-guide.md) — ลำดับการตั้งค่าจอ/touch สำหรับ kiosk
- [`docs/display-touchscreen-kiosk-session.md`](../display-touchscreen-kiosk-session.md) — กลไก session/`.xprofile`/`display-session.sh`

## เอกสารในโฟลเดอร์นี้

| ไฟล์ | เนื้อหา | สถานะ |
|---|---|---|
| [`proof-2026-07-11-option-c-system-level.md`](./proof-2026-07-11-option-c-system-level.md) | Proof ว่าตัวเลือก C (`/etc/xdg/monitors.xml` ระดับเครื่อง) แก้ปัญหาได้จริง — ทดสอบบน VM `ubuntu2204-first-test` | ✅ proof สำเร็จ, ยังไม่ implement เป็นโค้ดจริง |

## สถานะโดยรวมของเรื่องนี้ (อัปเดตล่าสุด: 2026-07-11)

- Root cause: ยืนยันแล้ว (`kiosk-user` ไม่มี `~/.config/monitors.xml` ของตัวเอง → mutter เขียนทับค่า rotate กลับเป็น normal)
- ทางแก้ที่เลือก: ตัวเลือก C (system-level `/etc/xdg/monitors.xml`) — **proof บน VM สำเร็จแล้ว**
- ยังไม่ทำ: implement logic เขียนไฟล์นี้อัตโนมัติเข้า `src/features/kiosk/manager.py` (ต้อง query ค่า vendor/product/serial/rate จริงผ่าน D-Bus แบบ dynamic ต่อเครื่อง ห้าม hardcode), proof ซ้ำบนเครื่อง production จริง (`hapymed-sterile-00`), เช็ค policy user-level vs system-level ให้ครบ
