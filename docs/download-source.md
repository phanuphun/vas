# Download Source — Feature Spec

> **Status:** Mock-up เท่านั้น — ยังไม่ได้ implement  
> **หน้า UI:** `/apps` → tab "แหล่งดาวน์โหลด"  
> **อัปเดตล่าสุด:** 2026-07-01

---

## ภาพรวม

Download Source คือระบบที่ให้ผู้ดูแลระบบกำหนดได้ว่า VAS จะดึง package แต่ละตัวมาจากที่ไหน มีสองโหมดหลัก:

| โหมด | คำอธิบาย | เหมาะกับ |
|------|-----------|---------|
| **VAS Default** | ดึงจาก internet ตาม URL ใน package manifest (latest version) | Development, lab |
| **On-Premise Server** | ดึงจาก server ภายในองค์กรที่ lock version เอาไว้ | Production, air-gapped |

---

## Data Model (เสนอ)

### Global Config

เก็บใน SQLite หรือ `~/.config/vas/sources.json`:

```json
{
  "global_source": "default",
  "onpremise": {
    "base_url": "https://packages.internal.company.com",
    "api_token": "<encrypted>",
    "verified": false,
    "last_checked": null
  },
  "package_overrides": {
    "node": "default",
    "docker": "onpremise"
  }
}
```

### Source Resolution Order

```
package_overrides[pkg_id]  →  fallback to  →  global_source  →  fallback to  →  "default"
```

---

## On-Premise Server API Spec

Server ต้องรองรับ endpoint ต่อไปนี้ (VAS Package API v1):

### `GET /vas/api/v1/packages`

คืน list ของ package ทั้งหมดที่ server provide พร้อม version ที่ pin ไว้:

```json
{
  "spec_version": "1.0",
  "packages": [
    {
      "id": "node",
      "version": "22.14.0",
      "install_method": "apt",
      "apt": {
        "repo_url": "https://packages.internal.company.com/apt/node22",
        "gpg_key_url": "https://packages.internal.company.com/apt/node22.gpg",
        "package_name": "nodejs"
      }
    },
    {
      "id": "pm2",
      "version": "5.3.1",
      "install_method": "npm",
      "npm": {
        "registry": "https://packages.internal.company.com/npm"
      }
    },
    {
      "id": "docker",
      "version": "26.1.4",
      "install_method": "apt",
      "apt": {
        "repo_url": "https://packages.internal.company.com/apt/docker",
        "gpg_key_url": "https://packages.internal.company.com/apt/docker.gpg",
        "package_name": "docker-ce"
      }
    }
  ]
}
```

### `GET /vas/api/v1/health`

ใช้ทดสอบการเชื่อมต่อ:

```json
{ "status": "ok", "server": "VAS Package Mirror", "spec_version": "1.0" }
```

### Authentication

ส่ง `Authorization: Bearer <api_token>` header ถ้าตั้งค่า token เอาไว้

---

## แผนการ Implement (To-Do)

### Phase 1 — Config storage

- [ ] เพิ่ม `SourceConfig` dataclass ใน `src/core/config.py`
- [ ] สร้าง `src/features/packages/source_resolver.py`  
  - `resolve_source(pkg_id) → SourceConfig`
  - `test_connection(base_url, token) → (ok: bool, msg: str)`
- [ ] เพิ่ม API endpoints:
  - `GET /api/apps/sources` — คืน config ปัจจุบัน
  - `POST /api/apps/sources` — บันทึก config ใหม่
  - `POST /api/apps/sources/test` — ทดสอบ on-prem URL

### Phase 2 — Package installer integration

- [ ] แก้ `src/features/packages/installers.py` ให้รับ `source: SourceConfig` parameter
- [ ] สร้าง `build_install_cmds(pkg, source)` ที่แทนที่ URL ใน `install_cmds` ด้วย on-prem URL
- [ ] เพิ่ม `source_override` field ใน package manifest

### Phase 3 — UI activation

- [ ] Enable การ save ใน tab "แหล่งดาวน์โหลด" (ปัจจุบัน disabled)
- [ ] เพิ่ม connection test feedback (spinner → success/error badge)
- [ ] Enable per-package override dropdown

---

## Security Considerations

- **API Token** ต้องเข้ารหัสก่อนเก็บ — ห้ามเก็บ plaintext ใน DB
- **HTTPS only** — ห้าม allow HTTP สำหรับ on-prem URL ใน production mode
- **Certificate validation** — ควร support custom CA cert สำหรับ internal PKI
- **URL validation** — validate ว่า base_url เป็น valid HTTPS URL ก่อน save

---

## ไฟล์ที่เกี่ยวข้อง

| ไฟล์ | บทบาท |
|------|--------|
| `src/web/templates/apps.html` | UI mock-up (tab แหล่งดาวน์โหลด) |
| `src/features/packages/settings.py` | Package manifest + install queue |
| `src/features/packages/installers.py` | Install command execution |
| `src/core/config.py` | Config dataclasses (ต้องเพิ่ม SourceConfig) |
