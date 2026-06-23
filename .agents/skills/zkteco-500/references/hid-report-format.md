# ZKTeco QR500 — HID Report Format

## USB HID Boot Protocol (Keyboard)

เมื่อ QR500 อยู่ใน HID Keyboard mode, แต่ละ report มี 8 bytes:

```
Byte 0: Report ID (usually 0x00 or omitted)
Byte 1: Modifier keys bitmask
         bit 0 = Left Ctrl
         bit 1 = Left Shift
         bit 2 = Left Alt
         bit 3 = Left GUI
         bit 4 = Right Ctrl
         bit 5 = Right Shift
         bit 6 = Right Alt
         bit 7 = Right GUI
Byte 2: Reserved (always 0x00)
Byte 3: Keycode 1
Byte 4: Keycode 2
Byte 5: Keycode 3
Byte 6: Keycode 4
Byte 7: Keycode 5
Byte 8: Keycode 6
```

> **หมายเหตุ:** บาง driver อาจส่ง 9 bytes (มี report ID นำหน้า) บางตัวส่ง 8 bytes เริ่มจาก modifier
> ให้ลอง `xxd` เพื่อ verify byte layout จริงของ device

## HID Usage Codes (Keyboard Page 0x07)

```
0x00 = No event
0x04 = a/A        0x05 = b/B        0x06 = c/C
0x07 = d/D        0x08 = e/E        0x09 = f/F
0x0A = g/G        0x0B = h/H        0x0C = i/I
0x0D = j/J        0x0E = k/K        0x0F = l/L
0x10 = m/M        0x11 = n/N        0x12 = o/O
0x13 = p/P        0x14 = q/Q        0x15 = r/R
0x16 = s/S        0x17 = t/T        0x18 = u/U
0x19 = v/V        0x1A = w/W        0x1B = x/X
0x1C = y/Y        0x1D = z/Z

0x1E = 1/!        0x1F = 2/@        0x20 = 3/#
0x21 = 4/$        0x22 = 5/%        0x23 = 6/^
0x24 = 7/&        0x25 = 8/*        0x26 = 9/(
0x27 = 0/)

0x28 = Enter/Return   ← จุดสิ้นสุดของ QR scan
0x29 = Escape
0x2A = Backspace
0x2B = Tab
0x2C = Space
0x2D = -/_           0x2E = =/+
0x2F = [/{           0x30 = ]/}
0x31 = \/|           0x33 = ;/:
0x34 = '/"           0x35 = `/~
0x36 = ,/<           0x37 = ./>
0x38 = //?
```

## Shift Logic

ถ้า Byte 1 (modifier) มี bit 1 หรือ bit 5 set (Left/Right Shift):
- ตัวอักษร a–z → A–Z
- เลข → สัญลักษณ์ตาม keymap มาตรฐาน US

## Raw HID Report (Non-keyboard mode)

เมื่อ HID keyboard = **Close** ใน DEMO software, device ส่ง proprietary report format:
- Format อาจแตกต่างกันตาม firmware version
- ข้อมูล QR จะอยู่เป็น raw bytes ตามด้วย terminator (0x00 หรือ ENTER code)
- แนะนำให้ capture raw bytes ก่อนด้วย `xxd` เพื่อ reverse engineer format

## Debug Command

```bash
# Capture raw HID report bytes
sudo hexdump -C /dev/hidraw0
# สแกน QR แล้วดู bytes ที่ได้

# Alternative (Python one-liner)
python3 -c "
import hid, sys
d = hid.device()
d.open_path(b'/dev/hidraw0')
while True:
    data = d.read(64)
    if data: print([hex(x) for x in data])
"
```