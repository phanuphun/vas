# ZKTeco DEMO Software — Parameter Reference

## Basic Settings-1

| Parameter | Options | Notes |
|---|---|---|
| RS485 Address | 0–255 | 0 = broadcast (ใช้ได้กับทุก address) |
| Opening times | seconds | ใช้เมื่อ reader ต่อตรงกับ door lock |
| Serial number | read-only | Serial ของ device |
| RS485 function switch | Open / **Close** | Close ถ้าใช้ USB |
| RS485 automatic upload | Open / **Close** | Close ถ้าไม่ต้องการ auto upload |
| Work mode | **Reader mode** / Offline mode | Reader mode = ใช้เป็น peripheral reader |
| HID keyboard | Open / **Close** | **Close** = ส่ง raw HID report, **Open** = emulate keyboard |

## Basic Settings-2 (QR Code Parameters)

| Parameter | Options | Notes |
|---|---|---|
| QR code decryption key | string | ใช้เมื่อ mode = Custom encryption |
| QR code effective time | seconds (default 30) | หมดอายุ QR code หลังจาก X วินาที |
| Door ID | number | สำหรับ multi-door access control |
| QR code mode | **Not encrypted** / Custom encryption / Dynamic QR code | ใช้ Custom encryption ถ้ามี checksum/SALT logic |
| Light mode | Constantly bright / Intermittent / **Induction** | Induction = เปิดไฟเฉพาะเมื่อมีการสแกน ประหยัดไฟ |

## Basic Settings-2 (Wiegand Parameters)

| Parameter | Options | Notes |
|---|---|---|
| Wiegand mode | W26 / **W34** / W66 | เลือกตาม controller ที่รองรับ |
| Output format | Forward / **Reverse** output | |
| Whether to check | Open / Close | Output Wiegand check digit |
| Pulse Width | 1–99 × 10ms | Default 5 (= 50ms) |
| Pulse interval | 0–89 × 100 + 1000ms | Gap ระหว่าง Wiegand pulses |

## Basic Settings-3 (Card Reading Parameters)

| Parameter | Notes |
|---|---|
| App ID | Directory file number ของ CPU card (Hex) |
| File ID | File number ใน CPU card (Decimal) |
| Key ID | Key identifier สำหรับ external auth |
| CPU user key | Key สำหรับ decrypt CPU card content |
| Start block | Block เริ่มอ่าน MF card (default 1) |
| Start byte | Byte offset เริ่มอ่าน |
| MF user key | Sector key ของ Mifare card |
| Prior choice | CPU priority / MF card priority |
| Reading Card mode | UID หรือ Content ของ CPU/MF/ISO15693 card |

## Reader Operation (Section 4.4)

| Parameter | Notes |
|---|---|
| Read RTC | ดูเวลาปัจจุบันของ reader |
| Write RTC | ตั้งเวลา reader ให้ sync กับ PC |
| Control door | Remote open/close door (ถ้าต่อ door lock) |
| Voice control | เล่นเสียงจาก reader (Opcode 1–23 = preset, 255 = TTS) |
| Text data | Text สำหรับ TTS ถ้าใช้ GB2312 encoding |