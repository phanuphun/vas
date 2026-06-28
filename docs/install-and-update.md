# Install & Update — การทำงานอย่างละเอียด

## 1. Bootstrap Install (ครั้งแรก)

### คำสั่ง
```bash
wget -qO- https://raw.githubusercontent.com/phanuphun/vending-auto-setup/main/scripts/install.sh \
  | sudo bash -s -- --install-cli install --component all
```

### Flow
```
wget ดึง install.sh จาก GitHub (branch: main)
    ↓
bash รับ args: --install-cli install --component all
    ↓
install.sh ดาวน์โหลด source archive จาก GitHub
    ↓
แตกไฟล์ใน temp dir
    ↓
copy source → /opt/vending-auto-setup/
    ↓
สร้าง wrapper scripts ใน /usr/local/bin/
    ↓
ติดตั้ง components ที่ระบุ (all/git/node/docker ฯลฯ)
```

### Wrapper Scripts ที่สร้าง

| ไฟล์ | Module |
|---|---|
| `/usr/local/bin/vas` | `cli` |
| `/usr/local/bin/vending-auto-setup` | `cli` |
| `/usr/local/bin/vending-status` | `status` |

เนื้อหาของ wrapper:
```bash
#!/usr/bin/env bash
PYTHONPATH=/opt/vending-auto-setup/src exec python3 -m cli "$@"
```

### Components ที่รองรับ

```
all, git, node, docker, wireguard, anydesk, openssh, qr-udev
```

---

## 2. Self-Update (`vas update`)

### คำสั่ง
```bash
vas update                          # ดึง main branch (latest)
vas update --version 1.2.0         # ดึง Git tag v1.2.0
vas update --repo other/fork       # ดึงจาก repo อื่น
vas update --dry-run               # แสดงสิ่งที่จะทำ ไม่รันจริง
```

### Source Files
- `src/cli.py` — parse args, เรียก `SelfUpdater`
- `src/services/updater.py` — logic หลักทั้งหมด

### Flow ของ `SelfUpdater.update()`

```
1. archive_url()  → สร้าง URL สำหรับดาวน์โหลด
       ↓
2. ensure_runtime_packages()
       → ตรวจว่า flask import ได้ไหม
       → ถ้าไม่ได้ → apt-get install python3-flask
       ↓
3. urllib.request.urlretrieve(archive_url)
       → ดาวน์โหลด .tar.gz ลง temp dir
       ↓
4. extract_source_archive()
       → แตกไฟล์
       → validate ว่ามี src/cli.py (ป้องกัน archive ผิด)
       ↓
5. shutil.rmtree(install_dir)
       → ลบ /opt/vending-auto-setup เดิมทิ้ง
       ↓
6. shutil.copytree(source_dir, install_dir)
       → copy source ใหม่เข้าแทน
       ↓
7. install_wrappers()
       → เขียน wrapper scripts ใน /usr/local/bin/ ใหม่
```

### URL ที่ใช้ดาวน์โหลด (`archive_url()`)

```python
# version = "latest" → ดึง branch main เสมอ (hardcoded)
"https://github.com/{repo}/archive/refs/heads/main.tar.gz"

# version = "1.2.0" → ดึง Git tag
"https://github.com/{repo}/archive/refs/tags/1.2.0.tar.gz"
```

> ⚠️ **Known Issue:** ไม่รองรับการระบุ branch โดยตรง — ดู TODO.md

### Constants

| ค่า | Default |
|---|---|
| `DEFAULT_REPO` | `phanuphun/vending-auto-setup` |
| `DEFAULT_INSTALL_DIR` | `/opt/vending-auto-setup` |
| `bin_dir` | `/usr/local/bin` |
| `RUNTIME_PACKAGES` | `python3-flask` |

---

## 3. ความแตกต่าง install.sh กับ `vas update`

| | `install.sh` (bootstrap) | `vas update` |
|---|---|---|
| ใช้เมื่อ | ครั้งแรก (ยังไม่มี vas) | อัปเดตหลังจาก install แล้ว |
| ต้องการ | `wget` + `bash` | `vas` command |
| ดึงโค้ดจาก | URL ใน install.sh | `archive_url()` ใน updater.py |
| ติดตั้ง components | ✅ รองรับ | ❌ อัปเดตแค่ source + wrapper |
| dry-run | ❌ | ✅ `--dry-run` |

---

## 4. Dry-Run Mode

เมื่อใช้ `--dry-run` ทุก command จะแสดงแค่สิ่งที่จะทำ ไม่เขียนไฟล์จริง:

```
download https://github.com/phanuphun/vending-auto-setup/archive/refs/heads/main.tar.gz
ensure python3-flask
replace /opt/vending-auto-setup
write /usr/local/bin/vending-auto-setup
write /usr/local/bin/vas
write /usr/local/bin/vending-status
```
