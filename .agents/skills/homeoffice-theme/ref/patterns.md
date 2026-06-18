# HomeOffice — Design Patterns Reference

Recurring patterns across all 28 pages of the HomeOffice showcase. Use these as templates when building new pages.

---

## Tier Badge System (T0–T3)

Every action in HomeOffice is classified into one of four tiers. The tier determines what approval or authentication is required before Claude executes it.

| Tier | Class | Color | Thai Label | Meaning | Requires |
|------|-------|-------|------------|---------|----------|
| T0 | `cf-tier cf-tier-0` | Green | ทำเลย | Read-only / instant | No approval |
| T1 | `cf-tier cf-tier-1` | Green | บันทึก | Writes data (reversible) | Confirm only |
| T2 | `cf-tier cf-tier-2` | Yellow | ส่งออกนอก | External integration | Explicit approval |
| T3 | `cf-tier cf-tier-3` | Red | จ่ายเงิน | Financial / payment | Strict approval |

```html
<!-- Tier badge examples -->
<span class="cf-tier cf-tier-0">T0 ทำเลย</span>
<span class="cf-tier cf-tier-1">T1 บันทึก</span>
<span class="cf-tier cf-tier-2">T2 ส่งออก</span>
<span class="cf-tier cf-tier-3">T3 จ่ายเงิน</span>
```

### Tier Usage in Action Lists

Pages list AI-executable actions with their tier. Use this pattern on "autopilot" pages:

```html
<div class="cf-card">
  <div style="padding:1rem 1.25rem;" class="hair-b">
    <h2 style="font-size:0.9rem;font-weight:600">สิ่งที่ AI ทำได้</h2>
  </div>
  <div style="padding:0.5rem 0.75rem;">
    <!-- Action row -->
    <div style="display:flex;align-items:center;gap:0.75rem;padding:0.6rem 0.5rem;border-radius:0.5rem;">
      <span class="cf-tier cf-tier-0">T0</span>
      <div style="flex:1;">
        <div style="font-size:0.82rem;font-weight:600">ดูรายงานยอดขาย</div>
        <div style="font-size:0.72rem;color:rgb(var(--c-faint))">ดึงข้อมูลและสรุปให้</div>
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:0.75rem;padding:0.6rem 0.5rem;border-radius:0.5rem;">
      <span class="cf-tier cf-tier-1">T1</span>
      <div style="flex:1;">
        <div style="font-size:0.82rem;font-weight:600">บันทึกใบเสร็จ</div>
        <div style="font-size:0.72rem;color:rgb(var(--c-faint))">บันทึกรายการลงระบบ</div>
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:0.75rem;padding:0.6rem 0.5rem;border-radius:0.5rem;">
      <span class="cf-tier cf-tier-3">T3</span>
      <div style="flex:1;">
        <div style="font-size:0.82rem;font-weight:600">โอนเงินซัพพลายเออร์</div>
        <div style="font-size:0.72rem;color:rgb(var(--c-faint))">ต้องได้รับการอนุมัติก่อน</div>
      </div>
    </div>
  </div>
</div>
```

---

## cf-zone — Full Status System

Use `cf-zone` for status badges in tables and detail views:

| Variant | When to use |
|---------|-------------|
| `cf-zone-safe` | Success, active, paid, saved |
| `cf-zone-caution` | Warning, pending approval, in review |
| `cf-zone-danger` | Error, failed, expired, critical |
| `cf-zone-free` | Running, processing, in progress |
| `cf-zone-info` | Information, optional, neutral note |
| `cf-zone-mute` | Disabled, inactive, archived |
| `cf-zone-neutral` | Pending, queued, not started |

```html
<!-- Example status mapping -->
<span class="cf-zone cf-zone-safe">ชำระแล้ว</span>
<span class="cf-zone cf-zone-caution">รอตรวจสอบ</span>
<span class="cf-zone cf-zone-danger">เกินกำหนด</span>
<span class="cf-zone cf-zone-free">กำลังประมวลผล</span>
<span class="cf-zone cf-zone-mute">ปิดใช้งาน</span>
<span class="cf-zone cf-zone-neutral">รอดำเนินการ</span>
```

---

## Page Eyebrow Convention

Every page has a two-level eyebrow above the heading. The pattern is: **Module · Page**.

| Module | Thai | Pages |
|--------|------|-------|
| ทีมหลังบ้าน | Back office | cfo, tax, hr, admin, stock |
| ทีมหน้าบ้าน | Front office | crm, linegroups, sales, marketing |
| บัญชีของฉัน | My account | consult, help, subscription, privacy |
| ระบบ | System | audit, members, settings |

```html
<!-- Examples: -->
<p class="cf-eyebrow">ทีมหลังบ้าน · บัญชีและการเงิน</p>
<p class="cf-eyebrow">ทีมหน้าบ้าน · ลูกค้า CRM</p>
<p class="cf-eyebrow">บัญชีของฉัน · ข้อมูลส่วนตัว</p>
<p class="cf-eyebrow">ระบบ · การตรวจสอบ Audit</p>
```

---

## Module Taxonomy (28 Pages)

### ทีมหลังบ้าน (Back Office)
| Page | Route | Description |
|------|-------|-------------|
| บัญชีและการเงิน | `/cfo` | P&L, cash flow, budget tracking |
| ภาษี | `/tax` | VAT, withholding tax, submissions |
| HR & เงินเดือน | `/hr` | Payroll, leave management, staff |
| การดำเนินงาน | `/admin` | Operations, procurement, utilities |
| คลังสินค้า | `/stock` | Inventory, stock levels, reorder |

### ทีมหน้าบ้าน (Front Office)
| Page | Route | Description |
|------|-------|-------------|
| ลูกค้า CRM | `/crm` | Customer list, contacts, history |
| LINE Groups | `/linegroups` | LINE group chat management |
| ยอดขาย | `/sales` | Sales pipeline, orders, quotes |
| การตลาด | `/marketing` | Campaigns, promotions, analytics |

### บัญชีของฉัน (My Account)
| Page | Route | Description |
|------|-------|-------------|
| ปรึกษา AI | `/consult` | General AI assistant chat |
| ช่วยเหลือ | `/help` | Help center, documentation |
| สมาชิก | `/subscription` | Plan management, billing |
| ความเป็นส่วนตัว | `/privacy` | Data privacy settings |

### ระบบ (System)
| Page | Route | Description |
|------|-------|-------------|
| Audit Log | `/audit` | Activity log, action history |
| สมาชิกทีม | `/members` | Team members, roles, permissions |
| ตั้งค่า | `/settings` | App configuration |

### หน้าหลัก (Home)
| Page | Route | Description |
|------|-------|-------------|
| Dashboard | `/` | Overview, recent activity |
| Design System | `/design` | Component showcase (reference) |

---

## "ปกติสั่งผ่านแชตได้" Info Tip

Appears on most backend/system pages to inform users that the action can be done via AI chat without using the UI directly. Always use `cf-info` class.

```html
<div class="cf-info" style="margin-bottom:1.5rem;">
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/>
    <line x1="12" y1="16" x2="12" y2="12"/>
    <line x1="12" y1="8" x2="12.01" y2="8"/>
  </svg>
  <span>ปกติสั่งผ่านแชตได้ ไม่ต้องมาที่หน้านี้ หน้านี้ใช้สำหรับตรวจสอบหรือแก้ไขข้อมูลโดยตรง</span>
</div>
```

---

## Standard Page Pattern: Data Module

The most common pattern for data-heavy backend pages (cfo, hr, stock, crm, etc.).

```html
<main class="ho-main">
  <div class="content-inner">

    <!-- 1. Page heading -->
    <div class="page-head">
      <p class="cf-eyebrow">ทีมหลังบ้าน · คลังสินค้า</p>
      <h1 class="font-display" style="font-size:1.35rem;font-weight:700;margin-top:0.2rem">คลังสินค้า</h1>
      <p style="color:rgb(var(--c-muted));font-size:0.875rem;margin-top:0.3rem">จัดการสต็อกสินค้าและการเบิกจ่าย</p>
    </div>

    <!-- 2. Info tip -->
    <div class="cf-info">
      <svg ...>...</svg>
      <span>ปกติสั่งผ่านแชตได้ ไม่ต้องมาที่หน้านี้</span>
    </div>

    <!-- 3. Stat row -->
    <div class="stat-row">
      <div class="cf-stat">
        <span class="cf-stat-val num">1,248</span>
        <span class="cf-stat-label">รายการทั้งหมด</span>
      </div>
      <div class="cf-stat">
        <span class="cf-stat-val num" style="color:rgb(var(--c-danger))">23</span>
        <span class="cf-stat-label">ใกล้หมด</span>
      </div>
      <div class="cf-stat">
        <span class="cf-stat-val num" style="color:rgb(var(--c-caution))">5</span>
        <span class="cf-stat-label">รอเติมสต็อก</span>
      </div>
      <div class="cf-stat">
        <span class="cf-stat-val num">142k</span>
        <span class="cf-stat-label">มูลค่ารวม (฿)</span>
      </div>
    </div>

    <!-- 4. Main content card -->
    <div class="cf-card">
      <div class="hair-b" style="padding:0.75rem 1.25rem;display:flex;align-items:center;justify-content:space-between;gap:0.75rem;">
        <h2 style="font-size:0.875rem;font-weight:600">รายการสินค้า</h2>
        <div style="display:flex;gap:0.5rem;">
          <button class="cf-btn">ส่งออก</button>
          <button class="cf-btn cf-btn-primary">+ เพิ่มสินค้า</button>
        </div>
      </div>
      <div style="overflow-x:auto;">
        <table class="cf-table">
          <thead>
            <tr><th>ชื่อสินค้า</th><th>คงเหลือ</th><th>สถานะ</th><th></th></tr>
          </thead>
          <tbody>
            <tr>
              <td>สินค้า A</td>
              <td class="num">150</td>
              <td><span class="cf-zone cf-zone-safe">ปกติ</span></td>
              <td><button class="cf-btn" style="padding:0.25rem 0.6rem;font-size:0.75rem;">แก้ไข</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 5. AI Actions card -->
    <div class="cf-card">
      <div class="hair-b" style="padding:0.75rem 1.25rem;">
        <h2 style="font-size:0.875rem;font-weight:600">สิ่งที่ AI ทำได้</h2>
      </div>
      <div style="padding:0.5rem 0.75rem;">
        <!-- Tier action rows -->
      </div>
    </div>

  </div>
</main>
```

---

## Standard Page Pattern: AI Chat Module

Used on pages that are primarily a chat interface (consult, help, linegroups AI).

```html
<main class="ho-main" style="padding:0;">
  <div style="max-width:900px;margin:0 auto;height:calc(100vh - var(--header-h, 52px));display:flex;flex-direction:column;">

    <!-- Chat messages -->
    <div style="flex:1;overflow-y:auto;padding:1.25rem;display:flex;flex-direction:column;gap:0.875rem;">
      
      <!-- AI bubble -->
      <div style="display:flex;gap:0.625rem;align-items:flex-start;">
        <div class="cf-ava" style="background:rgb(var(--c-accent)/0.10);color:rgb(var(--c-accent))">AI</div>
        <div class="cf-bubble cf-bubble-ai">สวัสดีครับ มีอะไรให้ช่วยไหม?</div>
      </div>

      <!-- User bubble -->
      <div style="display:flex;justify-content:flex-end;">
        <div class="cf-bubble cf-bubble-user">ขอดูรายงานยอดขายเดือนนี้</div>
      </div>

    </div>

    <!-- Composer (pinned bottom) -->
    <div class="cf-composer hair-t">
      <textarea class="cf-input" rows="1" placeholder="พิมพ์คำถามหรือคำสั่ง..." style="resize:none;min-height:40px;max-height:120px;overflow-y:auto;"></textarea>
      <button class="cf-btn cf-btn-primary" style="flex-shrink:0;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>
        ส่ง
      </button>
    </div>
  </div>
</main>
```

---

## Sidebar Nav Sections (Standard Structure)

Based on actual HomeOffice sidebar across all pages:

```html
<nav class="sidebar-nav">

  <!-- หน้าหลัก -->
  <div class="nav-section">
    <span class="cf-eyebrow nav-heading">หน้าหลัก</span>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>🏠</svg></span>
      <span class="nav-label">Dashboard</span>
    </button>
  </div>

  <!-- ทีมหลังบ้าน -->
  <div class="nav-section">
    <span class="cf-eyebrow nav-heading">ทีมหลังบ้าน</span>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>💰</svg></span>
      <span class="nav-label">บัญชีและการเงิน</span>
    </button>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>📄</svg></span>
      <span class="nav-label">ภาษี</span>
    </button>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>👥</svg></span>
      <span class="nav-label">HR & เงินเดือน</span>
    </button>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>⚙️</svg></span>
      <span class="nav-label">การดำเนินงาน</span>
    </button>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>📦</svg></span>
      <span class="nav-label">คลังสินค้า</span>
    </button>
  </div>

  <!-- ทีมหน้าบ้าน -->
  <div class="nav-section">
    <span class="cf-eyebrow nav-heading">ทีมหน้าบ้าน</span>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>👤</svg></span>
      <span class="nav-label">ลูกค้า CRM</span>
    </button>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>💬</svg></span>
      <span class="nav-label">LINE Groups</span>
    </button>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>📈</svg></span>
      <span class="nav-label">ยอดขาย</span>
    </button>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>📣</svg></span>
      <span class="nav-label">การตลาด</span>
    </button>
  </div>

  <!-- บัญชีของฉัน -->
  <div class="nav-section">
    <span class="cf-eyebrow nav-heading">บัญชีของฉัน</span>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>🤖</svg></span>
      <span class="nav-label">ปรึกษา AI</span>
    </button>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>❓</svg></span>
      <span class="nav-label">ช่วยเหลือ</span>
    </button>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>💳</svg></span>
      <span class="nav-label">สมาชิก</span>
    </button>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>🔒</svg></span>
      <span class="nav-label">ความเป็นส่วนตัว</span>
    </button>
  </div>

  <!-- ระบบ -->
  <div class="nav-section">
    <span class="cf-eyebrow nav-heading">ระบบ</span>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>📋</svg></span>
      <span class="nav-label">Audit Log</span>
    </button>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>👥</svg></span>
      <span class="nav-label">สมาชิกทีม</span>
    </button>
    <button class="nav-item">
      <span class="nav-icon"><svg ...>⚙️</svg></span>
      <span class="nav-label">ตั้งค่า</span>
    </button>
  </div>

</nav>
```

---

## Autopilot Action Card Pattern

Used to list what the AI assistant can do on each page. Always shown at the bottom of data pages.

```html
<div class="cf-card">
  <div class="hair-b" style="padding:0.75rem 1.25rem;display:flex;align-items:center;gap:0.5rem;">
    <div class="cf-iconbox" style="width:1.75rem;height:1.75rem;border-color:rgb(var(--c-accent)/0.25);background:rgb(var(--c-accent)/0.07);color:rgb(var(--c-accent))">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>
      </svg>
    </div>
    <div>
      <h2 style="font-size:0.85rem;font-weight:600">Autopilot Actions</h2>
      <p style="font-size:0.7rem;color:rgb(var(--c-faint))">สิ่งที่ AI สามารถทำได้ในหน้านี้</p>
    </div>
  </div>
  <div style="padding:0.5rem 0.75rem;display:flex;flex-direction:column;gap:0.125rem;">

    <div style="display:flex;align-items:center;gap:0.75rem;padding:0.55rem 0.5rem;border-radius:0.5rem;transition:background 0.1s;">
      <span class="cf-tier cf-tier-0">T0</span>
      <div style="flex:1;min-width:0;">
        <div style="font-size:0.82rem;font-weight:500;color:rgb(var(--c-ink))">ดึงข้อมูลและสรุป</div>
        <div style="font-size:0.7rem;color:rgb(var(--c-faint));margin-top:1px">วิเคราะห์โดยไม่แก้ไขข้อมูล</div>
      </div>
    </div>

    <div style="display:flex;align-items:center;gap:0.75rem;padding:0.55rem 0.5rem;border-radius:0.5rem;transition:background 0.1s;">
      <span class="cf-tier cf-tier-1">T1</span>
      <div style="flex:1;min-width:0;">
        <div style="font-size:0.82rem;font-weight:500;color:rgb(var(--c-ink))">บันทึกและแก้ไขข้อมูล</div>
        <div style="font-size:0.7rem;color:rgb(var(--c-faint));margin-top:1px">ต้องยืนยันก่อนทำ</div>
      </div>
    </div>

    <div style="display:flex;align-items:center;gap:0.75rem;padding:0.55rem 0.5rem;border-radius:0.5rem;transition:background 0.1s;">
      <span class="cf-tier cf-tier-2">T2</span>
      <div style="flex:1;min-width:0;">
        <div style="font-size:0.82rem;font-weight:500;color:rgb(var(--c-ink))">ส่งออกไปบริการภายนอก</div>
        <div style="font-size:0.7rem;color:rgb(var(--c-faint));margin-top:1px">ต้องได้รับการอนุมัติ</div>
      </div>
    </div>

    <div style="display:flex;align-items:center;gap:0.75rem;padding:0.55rem 0.5rem;border-radius:0.5rem;transition:background 0.1s;">
      <span class="cf-tier cf-tier-3">T3</span>
      <div style="flex:1;min-width:0;">
        <div style="font-size:0.82rem;font-weight:500;color:rgb(var(--c-ink))">โอนเงินหรือชำระค่าใช้จ่าย</div>
        <div style="font-size:0.7rem;color:rgb(var(--c-faint));margin-top:1px">ต้องการการอนุมัติขั้นสูง</div>
      </div>
    </div>

  </div>
</div>
```

---

## Subscription / Plan Card Pattern

Used on `/subscription` page. Shows plan tiers in a card grid.

```html
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem;">

  <!-- Free plan -->
  <div class="cf-card" style="padding:1.5rem;">
    <p class="cf-eyebrow" style="margin-bottom:0.5rem">ฟรี</p>
    <div style="font-size:1.75rem;font-weight:700;font-family:'Bai Jamjuree'">฿0<span style="font-size:0.875rem;font-weight:400;color:rgb(var(--c-faint))">/เดือน</span></div>
    <p style="font-size:0.82rem;color:rgb(var(--c-muted));margin-top:0.5rem;margin-bottom:1.25rem">เหมาะสำหรับทดลองใช้</p>
    <ul style="list-style:none;display:flex;flex-direction:column;gap:0.5rem;margin-bottom:1.25rem;">
      <li style="display:flex;gap:0.5rem;font-size:0.82rem;align-items:flex-start;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;margin-top:2px"><polyline points="20 6 9 17 4 12"/></svg>
        10 AI credits/วัน
      </li>
    </ul>
    <button class="cf-btn" style="width:100%;justify-content:center;">แผนปัจจุบัน</button>
  </div>

  <!-- Pro plan (highlighted) -->
  <div class="cf-card" style="padding:1.5rem;border-color:rgb(var(--c-accent)/0.3);box-shadow:0 0 0 3px rgb(var(--c-accent)/0.08);">
    <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;">
      <p class="cf-eyebrow">Pro</p>
      <span class="cf-chip cf-chip-accent" style="font-size:0.62rem;">แนะนำ</span>
    </div>
    <div style="font-size:1.75rem;font-weight:700;font-family:'Bai Jamjuree'">฿990<span style="font-size:0.875rem;font-weight:400;color:rgb(var(--c-faint))">/เดือน</span></div>
    <p style="font-size:0.82rem;color:rgb(var(--c-muted));margin-top:0.5rem;margin-bottom:1.25rem">สำหรับธุรกิจขนาดเล็ก</p>
    <ul style="list-style:none;display:flex;flex-direction:column;gap:0.5rem;margin-bottom:1.25rem;">
      <li style="display:flex;gap:0.5rem;font-size:0.82rem;align-items:flex-start;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;margin-top:2px"><polyline points="20 6 9 17 4 12"/></svg>
        Unlimited AI credits
      </li>
    </ul>
    <button class="cf-btn cf-btn-primary" style="width:100%;justify-content:center;">อัปเกรด</button>
  </div>

</div>
```

---

## Audit Log / Activity Table Pattern

Used on `/audit` page for chronological event log.

```html
<div class="cf-card">
  <div class="hair-b" style="padding:0.75rem 1.25rem;">
    <h2 style="font-size:0.875rem;font-weight:600">ประวัติกิจกรรม</h2>
  </div>
  <div>
    <!-- Log row -->
    <div style="display:flex;align-items:flex-start;gap:0.875rem;padding:0.875rem 1.25rem;border-bottom:1px solid rgb(var(--c-line)/0.07);">
      <div class="cf-ava" style="font-size:0.6rem;background:rgb(var(--c-accent)/0.10);color:rgb(var(--c-accent));flex-shrink:0;margin-top:2px;">AN</div>
      <div style="flex:1;min-width:0;">
        <div style="font-size:0.82rem;font-weight:500;color:rgb(var(--c-ink))">บันทึกใบเสร็จ #INV-2024-001</div>
        <div style="font-size:0.72rem;color:rgb(var(--c-faint));margin-top:2px">ผู้ใช้: admin · 12 มิ.ย. 2026 14:32</div>
      </div>
      <span class="cf-tier cf-tier-1">T1</span>
    </div>
  </div>
</div>
```

---

## Members / Team Management Pattern

Used on `/members` page.

```html
<div class="cf-card">
  <div class="hair-b" style="padding:0.75rem 1.25rem;display:flex;align-items:center;justify-content:space-between;">
    <h2 style="font-size:0.875rem;font-weight:600">สมาชิกทีม</h2>
    <button class="cf-btn cf-btn-primary">+ เชิญสมาชิก</button>
  </div>
  <!-- Member row -->
  <div style="display:flex;align-items:center;gap:0.875rem;padding:0.875rem 1.25rem;border-bottom:1px solid rgb(var(--c-line)/0.07);">
    <div class="cf-ava">สช</div>
    <div style="flex:1;">
      <div style="font-size:0.875rem;font-weight:500">สมชาย ใจดี</div>
      <div style="font-size:0.72rem;color:rgb(var(--c-faint))">somchai@company.com</div>
    </div>
    <span class="cf-chip">Admin</span>
    <button class="cf-btn" style="font-size:0.75rem;padding:0.25rem 0.6rem;">...</button>
  </div>
</div>
```

---

## Key Vue 3 Patterns (for Vue projects)

```vue
<!-- Transition for modals -->
<Transition name="modal">
  <div v-if="show" class="modal-backdrop">
    <div class="cf-card modal-dialog">...</div>
  </div>
</Transition>

<style>
.modal-enter-active, .modal-leave-active { transition: all 0.18s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; transform: translate(-50%, -48%) scale(0.97); }
</style>

<!-- Transition for slide-in panels -->
<Transition name="slide-in">
  <div v-if="selected" class="cf-card detail-card">...</div>
</Transition>

<style>
.slide-in-enter-active, .slide-in-leave-active { transition: all 0.2s ease; }
.slide-in-enter-from { opacity: 0; transform: translateY(10px); }
.slide-in-leave-to   { opacity: 0; transform: translateY(10px); }
@media (min-width: 1024px) {
  .slide-in-enter-from { opacity: 0; transform: translateX(14px); }
  .slide-in-leave-to   { opacity: 0; transform: translateX(14px); }
}
</style>

<!-- Toast TransitionGroup -->
<TransitionGroup name="t">
  <div v-for="toast in toasts" :key="toast.id" class="cf-toast">...</div>
</TransitionGroup>

<style>
.t-enter-active, .t-leave-active { transition: all 0.22s ease; }
.t-enter-from { opacity: 0; transform: translateX(30px) scale(0.96); }
.t-leave-to   { opacity: 0; transform: translateX(30px) scale(0.96); }
</style>
```

---

## Icon Conventions

Always use **Lucide** SVG icons with these attributes:

```html
<svg
  width="16"
  height="16"
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
>
  <!-- Lucide path data -->
</svg>
```

| Use case | Size | stroke-width |
|----------|------|--------------|
| Nav icons | 15×15 | 2 |
| Button icons | 14–15×14–15 | 2 |
| Brand/logo mark | 15×15 | 2 |
| Callout/alert icons | 14×14 | 2 |
| Large iconbox | 18×18 | 2 |
| Close/X buttons | 14×14 | 2.5 |
| Check marks in buttons | 15×15 | 2 |
| Spinner-adjacent | 13–14×13–14 | 2 |

**Never** use emoji as icon substitutes in production UI.
