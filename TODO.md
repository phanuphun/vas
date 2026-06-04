# TODO

## สถานะปัจจุบัน

Phase 1 ติดตั้ง Git, Node.js, npm และ Docker ผ่าน bootstrap script ได้แล้ว

Phase 2 ส่วน display/touchscreen เริ่มทำแล้ว:

- ตรวจ X11/Wayland ผ่าน `vending-auto-setup check`
- หมุนจอ runtime ผ่าน `display apply`
- map touchscreen runtime ผ่าน `xinput`
- persist touchscreen matrix ผ่าน Xorg config
- persist display rotation ผ่าน session retry script
- มี virtual touchscreen POC สำหรับทดสอบใน VirtualBox

## WireGuard

เริ่ม implement WireGuard แล้ว

สิ่งที่ทำได้:

- ติดตั้ง `wireguard`
- ตรวจสถานะ command `wg`, `wg-quick`
- ตรวจ config ที่ save ใน app storage และ config ที่ active ใน `/etc/wireguard`
- ตรวจ service `wg-quick@<interface>` ว่า enabled/active หรือไม่
- สร้าง template config
- validate config ก่อน save/sync
- save config เข้า app storage โดยยังไม่ apply จริง
- sync config ไป `/etc/wireguard/<interface>.conf`
- backup config เดิมก่อน sync
- ตั้ง permission config เป็น `600`
- เก็บ history ของ config ที่ sync/unsync
- อ่าน history แบบ mask secret เป็นค่า default
- unsync เพื่อ disable service และนำ active config ออก
- รองรับ dry-run ก่อนทำจริง
- ติดตั้งเฉพาะ component ที่เลือกผ่าน `install --component`
- ถอนติดตั้งเฉพาะ component ที่เลือกผ่าน `uninstall --component`
- reset component ที่เลือกโดยถอน package/service และลบ config ที่โปรแกรมสร้าง
- reset Docker โดยไม่ลบ `/var/lib/docker`
- install preflight เช็กเวลาเครื่องกับ Ubuntu archive server และพยายามแก้ drift ก่อน `apt-get update`
- bootstrap script รองรับ `--install-cli` เพื่อติดตั้ง wrapper ลง `/usr/local/bin` โดยไม่ต้องใช้ `pip`
- เพิ่ม alias `vas`, command `--version`, และ `update` สำหรับ self-update จาก GitHub

คำสั่งหลัก:

```bash
vending-auto-setup wireguard status
```

```bash
sudo vending-auto-setup wireguard install
```

```bash
vending-auto-setup wireguard init-config --name wg0 --output ./wg0.conf
```

```bash
vending-auto-setup wireguard validate --config ./wg0.conf
```

```bash
vending-auto-setup wireguard save --name wg0 --config ./wg0.conf
```

```bash
sudo vending-auto-setup wireguard sync --name wg0
```

```bash
vending-auto-setup wireguard history --name wg0
```

```bash
vending-auto-setup wireguard show --name wg0 --id <history-id>
```

```bash
sudo vending-auto-setup wireguard unsync --name wg0
```

```bash
sudo vending-auto-setup install --component all
```

```bash
sudo vending-auto-setup install --component node --component docker
```

```bash
sudo vending-auto-setup uninstall --component docker
```

```bash
sudo vending-auto-setup reset --component all
```

ข้อควรระวัง:

- ห้าม generate หรือ commit private key ลง repo
- ห้าม print private key ลง terminal/log
- ต้อง backup config เดิมก่อนเขียนทับ
- ต้อง validate permission ของ `/etc/wireguard/*.conf`
- ควรใช้ `chmod 600` กับ config
- ต้องคิด flow กรณีเครื่องไม่มี internet หลังเชื่อม VPN

งานที่ควรปรับปรุงต่อ:

- เพิ่ม validation รูปแบบ key/base64 ให้เข้มขึ้นโดยยังไม่ leak secret
- เพิ่ม command restore จาก history
- เพิ่ม policy กำหนดจำนวน history สูงสุดหรือ rotate history
- เพิ่ม option เลือก `wg-quick up` แทน `systemctl restart` สำหรับบาง environment
- เพิ่ม integration test บน Ubuntu จริงที่มี `systemd` และ `wireguard`

## งานที่ควรปรับปรุงต่อ

- เพิ่ม command รวมสำหรับ setup display แบบครบชุด เช่น `display configure`
- เพิ่มการ detect output/touch device แบบ interactive หรือ auto-select
- เพิ่ม log ของ `display-session.sh`
- เพิ่ม check ว่า Docker daemon active หรือไม่
- เพิ่ม check ว่า user อยู่ใน `docker` group หรือไม่
- ทำ `.deb` package หลัง CLI stable
- พิจารณา apt repository หรือ managed package hosting หลังจาก POC เสถียร
