# Changelog

## [2026-06-23]

### OpenSSH Server
- เพิ่ม `vas install/reset --component openssh` ติดตั้งและรีเซ็ต openssh-server
- แสดงสถานะ OpenSSH ใน `vas check` และ dashboard

### HomeOffice Theme
- ย้าย web templates มาใช้ HomeOffice Design System (sidebar, cf-* components)
- เพิ่ม `homeoffice.css` และ `app.js` สำหรับ layout และ UI interactions

### QR Code Reader (ZKTeco QR500-BM)
- อ่าน QR ผ่าน hidraw HID keyboard mode พร้อม CLI (`vas qr`) และ web UI (`/qr`)
- SSE stream สำหรับ real-time scan, API start/stop/config
- ติดตั้ง udev rule ผ่าน `vas install --component qr-udev`
- เพิ่ม agent skill และเอกสารอ้างอิง ZKTeco QR500
