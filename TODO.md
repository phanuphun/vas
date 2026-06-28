# TODO

## 🔧 การกำหนด Branch ในการ Install

**ปัญหา:** `install.sh` และ `updater.py` hardcode branch เป็น `main` เสมอ ไม่สามารถระบุ branch อื่นได้

**สิ่งที่ต้องแก้:**
- `scripts/install.sh` — รับ parameter `--branch <name>` และใช้ตัวแปร `BASE_URL` ที่อ้างอิง branch นั้น
- `src/updater.py` บรรทัด 57 — `archive_url()` hardcode `/refs/heads/main` ให้รับ branch แยกต่างหากจาก `--version` (ซึ่งปัจจุบันใช้สำหรับ Git tag เท่านั้น)

**เป้าหมาย:**
```bash
# ติดตั้งจาก branch refactor
wget -qO- https://.../install.sh | sudo bash -s -- --branch refactor --install-cli install --component all
```

---

## 🔄 การ Update (vas update)

**ปัญหา:** `vas update` ดึงจาก `main` branch เสมอเมื่อใช้ `--version latest` และไม่รองรับการระบุ branch

**สิ่งที่ต้องแก้:**
- `src/updater.py` — เพิ่ม parameter `--branch` แยกจาก `--version`
- `src/cli.py` บรรทัด 53 — เพิ่ม `update.add_argument("--branch", default="main")`
- `archive_url()` — ถ้าระบุ `--branch` ให้ใช้ `/refs/heads/<branch>` แทน `/refs/heads/main`

**เป้าหมาย:**
```bash
vas update --branch refactor   # ดึงจาก branch refactor
vas update                     # ยังคงดึงจาก main ตามเดิม
vas update --version 1.2.0     # ดึงจาก Git tag (พฤติกรรมเดิม)
```

---

## หมายเหตุ

- ทั้งสองปัญหามี root cause เดียวกัน คือ URL generation ใน `archive_url()` และ `install.sh`
- ควรแก้พร้อมกันและใช้ logic เดียวกันเพื่อให้พฤติกรรมสอดคล้องกัน
