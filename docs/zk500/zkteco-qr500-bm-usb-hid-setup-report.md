# ZKTeco QR500-BM USB HID Setup Report
 
> **วันที่:** 2026-06-23  
> **เป้าหมาย:** เชื่อมต่อ QR500-BM กับ Mini PC (Ubuntu) เพื่ออ่านค่า QR code เข้าโปรแกรม Node.js โดยตรง สำหรับระบบ Vending Machine
 
---
 
## 1. อุปกรณ์ที่ใช้
 
| อุปกรณ์ | รายละเอียด |
|---|---|
| QR Code Reader | ZKTeco QR500-BM |
| การเชื่อมต่อ | Micro USB → Laptop (Windows, ทดสอบ) |
| Target OS | Ubuntu 22.04 Desktop (Mini PC) |
| Language | Node.js |
 
### พอร์ตบน QR500-BM (ด้านล่าง)
| พอร์ต | ประเภท | หน้าที่ |
|---|---|---|
| ซ้าย | USB-C | Power / Data |
| กลาง | Multi-pin connector | RS485 / Wiegand |
| ขวา | Mini connector | Data / Buzzer |
 
### Wiring Terminal (10 pin)
```
1=VCC  2=GND  3=485+  4=485-  5=WG0  6=WG1  7=/  8=/  9=/  10=/
```
 
---
 
## 2. การเชื่อมต่อครั้งแรก
 
เสียบ Micro USB จาก QR500-BM เข้า Laptop → **ไฟติด** → ตรวจสอบใน Device Manager
 
### สิ่งที่เห็นใน Device Manager
```
Human Interface Devices
├── USB Input Device   ← QR500-BM (interface 0)
└── USB Input Device   ← QR500-BM (interface 1)
 
Universal Serial Bus controllers
├── USB Composite Device  ← QR500-BM
└── USB Composite Device
```
 
**USB Composite Device** = device เดียวที่มีหลาย interface พร้อมกัน ไม่ได้ส่งต่อกัน แต่ทำงานคู่ขนาน
 
---
 
## 3. ทำความเข้าใจ Protocol ที่ QR500-BM รองรับ
 
QR500-BM รองรับ 3 communication mode:
 
### 3.1 HID (Human Interface Device)
- Device แกล้งทำเป็น **keyboard**
- เมื่อ scan QR → ส่งข้อมูลเหมือน keyboard พิมพ์
- OS รองรับอัตโนมัติ ไม่ต้อง driver พิเศษ
- **ต้องเปิด HID keyboard mode ผ่าน DEMO software ก่อน** (default = Close)
### 3.2 RS485
- Protocol สำหรับระบบ industrial / access control
- ส่งข้อมูลผ่านสาย 2 เส้น (485+, 485-)
- ต้องต่อสายเพิ่ม + USB-to-RS485 adapter
- Control ได้มากกว่า เหมาะกับ production
### 3.3 Wiegand
- Protocol เก่าสำหรับ access control โดยเฉพาะ
- ใช้กับ controller พิเศษ ไม่เหมาะกับ Mini PC ทั่วไป
---
 
## 4. ปัญหาแรก: ทดสอบ scan ใน Notepad ไม่ขึ้น
 
**สาเหตุ:** HID keyboard mode ถูก **disable โดย default**
 
ต้องใช้ **ZKTeco DEMO software** เพื่อ config ก่อน
 
---
 
## 5. Config ผ่าน DEMO Software (Windows)
 
### Download
จาก https://www.zkteco.com/en/QR_Reader/QR500-Series-Reader  
ไฟล์: **QR50 QR500 QR600 Config Demo** (7.06MB, 2021-11-23)
 
### ขั้นตอน
1. เปิด `QrCodeReaderDemo.exe`
2. เลือก **USB-HID** → กด **OK**
3. ไปที่ **Basic Setting-1**
4. กด **Find device** → Address = `100`
5. เปลี่ยน **HID keyboard** จาก `Close` → **`Open`**
6. กรอก **RS485 Address** = `100`
7. กด **Write configuration**
8. ทดสอบ scan QR ใน Notepad → **ขึ้นแล้ว ✓**
### Parameter Settings ที่สำคัญ (Basic Setting-1)
| Parameter | ค่าที่ใช้ | หมายความว่า |
|---|---|---|
| RS485 function switch | Close | ไม่ใช้ RS485 |
| Work mode | Reader mode | ทำงานเป็น reader |
| HID keyboard | **Open** | ส่งข้อมูลผ่าน USB เหมือน keyboard |
| Wiegand function switch | Close | ไม่ใช้ Wiegand |
| Baud rate | 115200 | ความเร็ว serial (ถ้าใช้ RS485) |
 
---
 
## 6. โครงสร้าง USB Interface ของ QR500-BM
 
```
QR500-BM
    │
    ▼
USB Composite Device
┌─────────────────────────────────────┐
│  Interface 0 (MI_00) → R400HID     │ → Raw HID data
│  Interface 1 (MI_01) → R400KEY     │ → Keyboard mode (HID keyboard)
└─────────────────────────────────────┘
         │                    │
         ▼                    ▼
   โปรแกรมเรา          Windows/OS
   อ่าน raw data        แจกให้ active window
   ได้โดยตรง           (Notepad, etc.)
```
 
| Interface | Product Name | หน้าที่ |
|---|---|---|
| MI_00 (interface 0) | R400HID | Raw HID data — โปรแกรม read ได้โดยตรง |
| MI_01 (interface 1) | R400KEY | Keyboard emulation — Windows ถือครอง |
 
---
 
## 7. อ่านค่าผ่าน Node.js บน Windows
 
### ติดตั้ง
```bash
npm install node-hid
```
 
### List devices
```javascript
// list-device.js
const HID = require('node-hid');
const devices = HID.devices();
console.log(JSON.stringify(devices, null, 2));
```
 
### Output ที่ได้ (ZKTeco devices)
```json
{
  "vendorId": 1046,
  "productId": 20512,
  "manufacturer": "ZKRFID",
  "product": "R400HID",
  "interface": 0
},
{
  "vendorId": 1046,
  "productId": 20512,
  "manufacturer": "ZKRFID",
  "product": "R400KEY",
  "interface": 1,
  "usage": 6
}
```
 
**vendorId: 1046, productId: 20512** = ZKTeco QR500-BM
 
---
 
## 8. ปัญหาบน Windows: MI_01 ถูก Windows ถือครอง
 
| Interface | Windows | สถานะ |
|---|---|---|
| MI_00 (R400HID) | ไม่ถือครอง | Open ได้ แต่ไม่ส่ง data event |
| MI_01 (R400KEY) | **ถือครองเป็น keyboard** | Open ได้แต่ read error |
 
**สรุป:** บน Windows อ่าน HID โดยตรงเข้าโปรแกรมโดยไม่ต้อง focus ไม่ได้
 
### วิธีที่ทำงานได้บน Windows (stdin)
```javascript
// read-stdin.js — ต้อง focus terminal ก่อน scan
const readline = require('readline');
 
const rl = readline.createInterface({
  input: process.stdin,
  terminal: false
});
 
rl.on('line', (line) => {
  const qrValue = line.trim();
  if (qrValue) {
    console.log('QR scanned:', qrValue);
    // ส่งต่อ MQTT ได้ตรงนี้
  }
});
```
 
**ข้อจำกัด:** ต้อง focus terminal — ไม่เหมาะกับ production ที่ผู้ใช้แตะ touchscreen ตลอด
 
---
 
## 9. ทำไม Linux/Ubuntu ถึงดีกว่า
 
### เปรียบเทียบ Windows vs Linux
 
| | Windows | Linux/Ubuntu |
|---|---|---|
| ต้องเปิด HID keyboard | ✓ (ถ้าอยากอ่านง่าย) | ✗ ไม่จำเป็น |
| ต้อง focus window | ✓ | ✗ |
| MI_01 ถูกถือครอง | ✓ | ✗ |
| อ่าน raw HID ได้ | ✗ | ✓ ผ่าน /dev/hidraw0 |
| เหมาะ production | ✗ | ✓ |
 
### Linux Path
```
QR500-BM → kernel hidraw driver → /dev/hidraw0 → โปรแกรมเรา
```
 
ไม่มีแนวคิด "active window" — อ่านได้ตลอดไม่ว่า focus จะอยู่ที่ไหน
 
---
 
## 10. `/dev/hidraw0` คืออะไร
 
**hidraw** = Linux kernel driver ที่เปิดช่องทางเข้าถึง HID device แบบ raw โดยตรง
 
- ข้อมูลไม่ถูก parse หรือแปลงโดย HID parser — ได้ bytes ดิบตรงๆ
- อ่านได้เหมือนอ่านไฟล์ปกติ
- มีตั้งแต่ Linux kernel 2.6.24 — Ubuntu 22.04 (kernel 5.15) รองรับเต็มรูปแบบ
- เสียบ USB → kernel สร้าง `/dev/hidraw0`, `/dev/hidraw1`, ... อัตโนมัติ
```bash
# ตรวจสอบหลังเสียบ QR reader
ls /dev/hidraw*
 
# ดูว่า hidraw0 เป็น device อะไร
cat /sys/class/hidraw/hidraw0/device/uevent
```
 
---
 
## 11. แผน Implementation บน Ubuntu
 
### ขั้นตอน
```bash
# 1. เสียบ QR reader แล้วหา hidraw device
ls /dev/hidraw*
 
# 2. ทดสอบ read raw (ต้อง sudo หรือ add user ใน group)
sudo cat /dev/hidraw0 | xxd
 
# 3. เพิ่ม permission (ไม่ต้อง sudo ทุกครั้ง)
sudo usermod -a -G plugdev $USER
# สร้าง udev rule
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5020", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/99-qr500.rules
sudo udevadm control --reload-rules
```
 
### Node.js บน Ubuntu
```javascript
// read-ubuntu.js
const HID = require('node-hid');
 
// หา QR500-BM โดย vendorId/productId
const deviceInfo = HID.devices().find(d =>
  d.vendorId === 0x0416 &&
  d.productId === 0x5020 &&
  d.interface === 0  // MI_00 = R400HID
);
 
if (!deviceInfo) {
  console.error('ไม่เจอ QR500-BM');
  process.exit(1);
}
 
const device = new HID.HID(deviceInfo.path);
 
let buffer = '';
 
device.on('data', (data) => {
  // แปลง HID keycode → ตัวอักษร
  const keycode = data[2];
  if (keycode === 0) return;
 
  if (keycode === 40) { // Enter = QR จบแล้ว
    console.log('QR scanned:', buffer);
    // TODO: ส่งต่อ MQTT
    buffer = '';
  } else {
    buffer += keycodeToChar(keycode);
  }
});
 
device.on('error', (err) => {
  console.error('HID error:', err);
});
 
function keycodeToChar(code) {
  const map = {
    4:'a',5:'b',6:'c',7:'d',8:'e',9:'f',10:'g',11:'h',12:'i',13:'j',
    14:'k',15:'l',16:'m',17:'n',18:'o',19:'p',20:'q',21:'r',22:'s',
    23:'t',24:'u',25:'v',26:'w',27:'x',28:'y',29:'z',
    30:'1',31:'2',32:'3',33:'4',34:'5',35:'6',36:'7',37:'8',38:'9',39:'0'
  };
  return map[code] || '';
}
 
console.log('Waiting for QR scan... (ไม่ต้อง focus)');
```
 
---
 
## 12. สรุป Lessons Learned
 
| ประเด็น | สิ่งที่เรียนรู้ |
|---|---|
| HID keyboard ต้อง config | Default = Close ต้องเปิดผ่าน DEMO software ก่อน |
| DEMO software | Windows only — ทำครั้งเดียว config ถูก save ใน firmware |
| Windows limitation | MI_01 ถูก OS ถือครอง อ่านตรงๆ ไม่ได้ |
| Linux advantage | /dev/hidraw0 อ่านได้โดยตรง ไม่ต้อง focus |
| Production target | Ubuntu — ไม่มีปัญหา focus ของ Windows เลย |
 
---
 
## 13. Next Steps
 
- [ ] ทดสอบบน Ubuntu Mini PC จริง
- [ ] หา `/dev/hidraw*` ที่ตรงกับ QR500-BM
- [ ] ทดสอบ read raw bytes และ decode QR string
- [ ] Integrate กับ MQTT publisher ของ vending system
- [ ] เพิ่ม udev rule เพื่อไม่ต้อง sudo
---
 
## 14. References
 
| หัวข้อ | URL |
|---|---|
| ZKTeco QR500 Official | https://www.zkteco.com/en/QR_Reader/QR500-Series-Reader |
| Linux hidraw kernel docs | https://docs.kernel.org/hid/hidraw.html |
| hidraw explained (บทความอ่านง่าย) | https://popovicu.com/posts/how-to-reverse-engineer-usb-hid-on-linux/ |
| node-hid library | https://github.com/node-hid/node-hid |
| Linux input event codes | https://www.kernel.org/doc/html/latest/input/event-codes.html |
| serialport (ถ้าใช้ RS485) | https://serialport.io/docs/ |