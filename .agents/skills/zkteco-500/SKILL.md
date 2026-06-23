---
name: zkteco-qr500
description: >
  Expert skill for working with the ZKTeco QR500-BM USB HID QR code reader on Linux (Ubuntu).
  Use this skill whenever the user asks about: reading QR codes programmatically from /dev/hidraw0
  or /dev/input/event*, configuring the QR500 device via USB-HID DEMO software, troubleshooting
  USB HID permissions (udev rules, plugdev group), implementing QR scan listeners in Python or
  Node.js without keyboard focus, or any ZKTeco QR reader integration in vending machine /
  access control systems. Also triggers on keywords: QR500, hidraw, HID keyboard mode,
  evdev, node-hid, ZKTeco scan, udev QR reader.
---

# ZKTeco QR500-BM — Linux Integration Skill

## Device Overview

| Property | Value |
|---|---|
| Model | QR500-B (black) / QR500-W (white) |
| Barcode support | QR Code, Data Matrix, PDF417, GS1 Databar, Code128/EAN128, UPC/EAN, Codabar, Code39/93 |
| RFID support | Mifare Ultralight, S50/S70, DESFire EV1, NTag (13.56MHz) |
| Communication | Wiegand (W26/W34/W66), RS485, **USB HID**, TCP/IP |
| Power | DC 12V (±5%) or USB 5V |
| Reading distance | QR ≥ 5cm, RFID Card ≥ 4cm |

**Key insight:** When connected via USB on Linux, the device presents as a USB HID device.
By default it may be in "HID Keyboard" mode (emulates keystrokes) — you must **turn this OFF**
via DEMO software if you want to read raw HID reports from `/dev/hidraw0` instead.

---

## Step 1 — Configure Device via DEMO Software (Windows required)

Before Linux integration, configure the device on a Windows machine first.

### Critical settings to verify:

1. Connect reader via USB → open ZKTeco DEMO software → select **USB-HID** port → click OK
2. Go to **Basic Settings-1** → click **Read configuration**
3. Set these parameters then click **Write configuration**:

| Parameter | Recommended value | Why |
|---|---|---|
| HID keyboard | **Close** | ปิดเพื่อให้อ่าน raw HID report ได้ ไม่ต้องพึ่ง keyboard focus |
| Work mode | Reader mode | สำหรับ connected reader (ไม่ใช่ standalone) |
| RS485 function switch | Close (ถ้าใช้ USB) | ไม่ต้องการ RS485 |

> ⚠️ **ถ้า HID keyboard = Open**: ข้อมูล QR จะถูกส่งออกเป็น keystrokes ไปยัง focused window เท่านั้น — ไม่เหมาะกับ vending machine ที่ไม่มี UI focus

4. Go to **Basic Settings-2** → verify:
   - QR code mode: `Not encrypted` (หรือ Custom encryption ถ้าใช้ checksum/SALT)
   - QR code effective time: 30s (default)

---

## Step 2 — Linux Setup (Ubuntu 22.04)

### 2.1 Identify the device

```bash
# หลังจากเสียบ USB
lsusb | grep -i ZK
# หรือ
dmesg | tail -20

# ดู hidraw nodes
ls /dev/hidraw*

# ดู vendor/product ID
cat /sys/class/hidraw/hidraw0/device/uevent
```

### 2.2 Create udev rule (avoid permission issues)

```bash
# สร้างไฟล์ rule
sudo nano /etc/udev/rules.d/99-zkteco-qr500.rules
```

เพิ่ม content (แทน `XXXX:YYYY` ด้วย vendor:product ID จริง เช่น `1b55:0c45`):

```
# ZKTeco QR500 QR Code Reader
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1b55", ATTRS{idProduct}=="0c45", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1b55", ATTRS{idProduct}=="0c45", MODE="0664", GROUP="plugdev"
```

```bash
# Reload rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# เพิ่ม user เข้า plugdev group
sudo usermod -aG plugdev $USER
# logout แล้ว login ใหม่
```

---

## Step 3A — Python Implementation

### Dependencies

```bash
pip install hidapi evdev
# หรือสำหรับ raw read approach
pip install pyusb
```

### Option A: evdev (อ่าน input event — ดีกว่าถ้า HID keyboard mode = Open)

```python
import evdev
import asyncio

def find_qr_device():
    """หา device ที่เป็น QR reader"""
    devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
    for device in devices:
        if 'ZK' in device.name or 'HID' in device.name.upper():
            return device
    raise RuntimeError("ไม่พบ ZKTeco QR reader")

async def read_qr_evdev(callback):
    """อ่าน QR code ผ่าน evdev (ไม่ต้องการ keyboard focus)"""
    device = find_qr_device()
    print(f"Connected to: {device.name} at {device.path}")
    
    # grab device เพื่อป้องกัน event ไปถึง OS keyboard input
    device.grab()
    
    buffer = []
    KEYMAP = {
        # evdev key codes → characters
        2:'1', 3:'2', 4:'3', 5:'4', 6:'5', 7:'6', 8:'7', 9:'8', 10:'9', 11:'0',
        16:'q', 17:'w', 18:'e', 19:'r', 20:'t', 21:'y', 22:'u', 23:'i', 24:'o', 25:'p',
        30:'a', 31:'s', 32:'d', 33:'f', 34:'g', 35:'h', 36:'j', 37:'k', 38:'l',
        44:'z', 45:'x', 46:'c', 47:'v', 48:'b', 49:'n', 50:'m',
        12:'-', 13:'=', 26:'[', 27:']', 39:';', 40:"'", 41:'`', 43:'\\',
        51:',', 52:'.', 53:'/',
    }
    
    try:
        async for event in device.async_read_loop():
            if event.type == evdev.ecodes.EV_KEY:
                key_event = evdev.categorize(event)
                if key_event.keystate == evdev.KeyEvent.key_down:
                    if key_event.scancode == 28:  # ENTER = end of scan
                        if buffer:
                            qr_data = ''.join(buffer)
                            await callback(qr_data)
                            buffer.clear()
                    elif key_event.scancode in KEYMAP:
                        buffer.append(KEYMAP[key_event.scancode])
    finally:
        device.ungrab()

# Usage
async def on_scan(data):
    print(f"QR Scanned: {data}")

asyncio.run(read_qr_evdev(on_scan))
```

### Option B: hidraw direct read (ดีกว่าถ้า HID keyboard mode = Close)

```python
import hid
import threading

# ZKTeco Vendor/Product ID (ตรวจสอบด้วย lsusb)
VENDOR_ID  = 0x1b55
PRODUCT_ID = 0x0c45

def read_qr_hidraw(callback):
    """อ่าน raw HID report จาก hidraw node"""
    device = hid.device()
    device.open(VENDOR_ID, PRODUCT_ID)
    device.set_nonblocking(False)
    
    print(f"Opened: {device.get_manufacturer_string()} {device.get_product_string()}")
    
    buffer = []
    HID_KEYMAP = {
        # HID usage codes → ASCII (Keyboard usage page 0x07)
        0x1E:'1', 0x1F:'2', 0x20:'3', 0x21:'4', 0x22:'5',
        0x23:'6', 0x24:'7', 0x25:'8', 0x26:'9', 0x27:'0',
        0x04:'a', 0x05:'b', 0x06:'c', 0x07:'d', 0x08:'e',
        0x09:'f', 0x0A:'g', 0x0B:'h', 0x0C:'i', 0x0D:'j',
        0x0E:'k', 0x0F:'l', 0x10:'m', 0x11:'n', 0x12:'o',
        0x13:'p', 0x14:'q', 0x15:'r', 0x16:'s', 0x17:'t',
        0x18:'u', 0x19:'v', 0x1A:'w', 0x1B:'x', 0x1C:'y', 0x1D:'z',
        0x2D:'-', 0x2E:'=',
    }
    
    try:
        while True:
            # HID report: [report_id, modifier, reserved, key1, key2, key3, key4, key5, key6]
            data = device.read(64)
            if data:
                # byte index 2 = modifier, index 4+ = key codes
                for key_code in data[4:10]:
                    if key_code == 0x28:  # ENTER
                        if buffer:
                            qr_data = ''.join(buffer)
                            callback(qr_data)
                            buffer.clear()
                    elif key_code != 0x00 and key_code in HID_KEYMAP:
                        buffer.append(HID_KEYMAP[key_code])
    except Exception as e:
        print(f"Error: {e}")
    finally:
        device.close()

def on_scan(data):
    print(f"QR Scanned: {data}")

# รัน background thread
t = threading.Thread(target=read_qr_hidraw, args=(on_scan,), daemon=True)
t.start()
```

---

## Step 3B — Node.js Implementation

### Dependencies

```bash
npm install node-hid
```

### Implementation

```typescript
import HID from 'node-hid';

const VENDOR_ID  = 0x1b55;
const PRODUCT_ID = 0x0c45;

// HID Usage → Character map
const HID_KEYMAP: Record<number, string> = {
  0x1E:'1', 0x1F:'2', 0x20:'3', 0x21:'4', 0x22:'5',
  0x23:'6', 0x24:'7', 0x25:'8', 0x26:'9', 0x27:'0',
  0x04:'a', 0x05:'b', 0x06:'c', 0x07:'d', 0x08:'e',
  0x09:'f', 0x0A:'g', 0x0B:'h', 0x0C:'i', 0x0D:'j',
  0x0E:'k', 0x0F:'l', 0x10:'m', 0x11:'n', 0x12:'o',
  0x13:'p', 0x14:'q', 0x15:'r', 0x16:'s', 0x17:'t',
  0x18:'u', 0x19:'v', 0x1A:'w', 0x1B:'x', 0x1C:'y', 0x1D:'z',
  0x2D:'-', 0x2E:'=',
};

export function startQRReader(onScan: (data: string) => void): () => void {
  const device = new HID.HID(VENDOR_ID, PRODUCT_ID);
  let buffer: string[] = [];

  device.on('data', (data: Buffer) => {
    // HID boot protocol: [report_id?, modifier, 0x00, key1..key6]
    for (let i = 4; i < 10; i++) {
      const keyCode = data[i];
      if (keyCode === 0x28) { // ENTER
        if (buffer.length > 0) {
          onScan(buffer.join(''));
          buffer = [];
        }
      } else if (keyCode !== 0x00 && HID_KEYMAP[keyCode]) {
        buffer.push(HID_KEYMAP[keyCode]);
      }
    }
  });

  device.on('error', (err: Error) => {
    console.error('QR Reader error:', err);
  });

  console.log('QR Reader listening...');
  
  // คืน cleanup function
  return () => device.close();
}

// Usage
const stop = startQRReader((data) => {
  console.log('Scanned:', data);
});

// process.on('SIGINT', stop);
```

---

## Step 4 — Debug Checklist

### ปัญหา: Permission denied on /dev/hidraw0

```bash
# ตรวจสอบ permission
ls -la /dev/hidraw*
# ควรได้: crw-rw-rw- หรือ crw-rw----

# ถ้า permission ยังไม่ถูก ให้ reload udev
sudo udevadm control --reload-rules && sudo udevadm trigger

# ตรวจสอบว่า user อยู่ใน plugdev group
groups $USER
```

### ปัญหา: ข้อมูลได้มาไม่ครบ / มี garbage characters

- ตรวจสอบว่า `HID keyboard` ใน DEMO software ตรงกับ implementation:
  - HID keyboard = **Open** → ใช้ `evdev` approach
  - HID keyboard = **Close** → ใช้ `hidraw` direct approach
- ตรวจสอบ KEYMAP: บาง firmware version อาจ shift byte index

### ปัญหา: device.read() timeout / no data

```bash
# ตรวจว่า device detected
dmesg | grep -i "hid\|usb" | tail -10

# ดู hidraw info
sudo udevadm info --query=all /dev/hidraw0

# ลอง cat raw bytes (CTRL+C หลัง scan)
sudo cat /dev/hidraw0 | xxd | head
```

### ปัญหา: QR500-BM มี suffix -BM หมายถึงอะไร

`-BM` = Bluetooth + Mifare variant (บาง market) แต่ logic HID USB เหมือนกัน

---

## Reference

- อ่าน `references/demo-software-params.md` สำหรับ parameter ทุกตัวใน DEMO software
- อ่าน `references/hid-report-format.md` สำหรับ byte layout ของ HID report