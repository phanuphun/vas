# HomeOffice — Component Reference (cf-* Classes)

All components use CSS custom properties from `ref/tokens.md`. Read that first.

---

## Component Index

| Class | Category | Description |
|-------|----------|-------------|
| `cf-card` | Container | White card with hairline border |
| `cf-stat` | Data | Statistic card (number + label) |
| `cf-btn` / `cf-btn-primary` | Action | Buttons |
| `cf-chip` / `cf-chip-accent` | Label | Small inline badges |
| `cf-eyebrow` | Typography | Category label above headings |
| `cf-mark` | Highlight | Inline text highlight |
| `cf-iconbox` | Icon | Bordered icon container |
| `cf-zone` | Status | Status badge (colored) |
| `cf-tier` | Status | Tier badge (T0–T3) |
| `cf-input` / `cf-label` | Form | Input field and label |
| `cf-input-ro` | Form | Read-only / auto-filled field |
| `cf-composer` + `cf-bubble` | Chat | Chat message composer + bubble |
| `cf-table` | Data | Styled table |
| `cf-ava` | Avatar | User / entity avatar |
| `cf-toast` | Feedback | Toast notification |
| `cf-screen` + `cf-phone` | Showcase | Mobile phone frame |
| `cf-good` / `cf-warn` / `cf-bad` / `cf-info` | Callout | Alert/callout blocks |
| `cf-step` | Progress | Step/progress indicator |
| `cf-spin` | Loading | Spinner |
| `hair` / `hair-t` / `hair-b` / `hair-r` | Border | Hairline border utilities |
| `font-display` | Typography | Switch to Bai Jamjuree |
| `num` | Typography | Tabular-nums Bai Jamjuree |
| `cf-light` | Container | Light/muted surface section |

---

## cf-card

White card with hairline border. The fundamental content container.

```html
<div class="cf-card">
  Content goes here
</div>
```

```css
.cf-card {
  background: rgb(var(--c-card));
  border: 1px solid rgb(var(--c-line) / 0.10);
  border-radius: var(--radius, 0.75rem);
  /* No box-shadow by default — separation by border only */
}
```

**Variants:**
```html
<!-- Card with section header -->
<div class="cf-card">
  <div class="card-head hair-b" style="padding:1rem 1.25rem;display:flex;align-items:center;justify-content:space-between;">
    <h2 style="font-size:0.9rem;font-weight:600">Section Title</h2>
    <button class="cf-btn">Action</button>
  </div>
  <div style="padding:1.25rem">
    Content
  </div>
</div>
```

---

## cf-stat

Statistic card with a large number and descriptive label. Used in rows of 3–4 at the top of pages.

```html
<!-- Stat row (3-4 cards) -->
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0.75rem;">
  <div class="cf-stat">
    <span class="cf-stat-val num">142</span>
    <span class="cf-stat-label">ลูกค้าทั้งหมด</span>
  </div>
  <div class="cf-stat">
    <span class="cf-stat-val num" style="color:rgb(var(--c-safe))">38</span>
    <span class="cf-stat-label">ใหม่เดือนนี้</span>
  </div>
  <div class="cf-stat">
    <span class="cf-stat-val num" style="color:rgb(var(--c-danger))">5</span>
    <span class="cf-stat-label">รอดำเนินการ</span>
  </div>
</div>
```

```css
.cf-stat {
  background: rgb(var(--c-card));
  border: 1px solid rgb(var(--c-line) / 0.10);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.cf-stat-val {
  font-family: 'Bai Jamjuree', sans-serif;
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1;
  color: rgb(var(--c-ink));
}
.cf-stat-label {
  font-size: 0.75rem;
  color: rgb(var(--c-faint));
}
```

---

## cf-btn / cf-btn-primary

```html
<!-- Ghost button (default) -->
<button class="cf-btn">ยกเลิก</button>

<!-- Primary blue button — use only for the main CTA -->
<button class="cf-btn cf-btn-primary">บันทึก</button>

<!-- Disabled state -->
<button class="cf-btn cf-btn-primary" disabled>กำลังบันทึก...</button>

<!-- With spinner -->
<button class="cf-btn cf-btn-primary" disabled>
  <span class="cf-spin" style="border-top-color:#fff;border-color:rgba(255,255,255,0.3);"></span>
  กำลังโหลด...
</button>

<!-- Danger/destructive -->
<button class="cf-btn" style="color:rgb(var(--c-danger));border-color:rgb(var(--c-danger)/0.25);">ลบ</button>
```

```css
.cf-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.45rem 0.9rem;
  border: 1px solid rgb(var(--c-line) / 0.14);
  border-radius: 0.5rem;
  background: rgb(var(--c-card));
  color: rgb(var(--c-ink));
  font-family: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.12s, border-color 0.12s;
}
.cf-btn:hover { background: rgb(var(--c-surface)); }
.cf-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.cf-btn-primary {
  background: rgb(var(--c-accent));
  border-color: rgb(var(--c-accent));
  color: #fff;
}
.cf-btn-primary:hover { background: #1d4ed8; border-color: #1d4ed8; }
```

---

## cf-chip / cf-chip-accent

Small inline badge. Used for counts, tags, status labels.

```html
<!-- Neutral chip -->
<span class="cf-chip">ทั้งหมด</span>

<!-- Accent chip (blue count) -->
<span class="cf-chip cf-chip-accent num">12</span>

<!-- Green chip -->
<span class="cf-chip" style="background:rgb(var(--c-safe)/0.08);color:#0f766e;border-color:rgb(var(--c-safe)/0.20)">สำเร็จ</span>
```

```css
.cf-chip {
  display: inline-flex;
  align-items: center;
  padding: 0.12rem 0.45rem;
  border-radius: 9999px;
  font-size: 0.7rem;
  font-weight: 600;
  background: rgb(var(--c-surface));
  border: 1px solid rgb(var(--c-line) / 0.10);
  color: rgb(var(--c-muted));
  white-space: nowrap;
}
.cf-chip-accent {
  background: rgb(var(--c-accent) / 0.10);
  border-color: rgb(var(--c-accent) / 0.20);
  color: rgb(var(--c-accent));
}
```

---

## cf-eyebrow

Small uppercase category label placed above a page heading.

```html
<p class="cf-eyebrow">บัญชีของฉัน · สมาชิก</p>
<h1 class="font-display">แพ็กเกจสมาชิก</h1>
```

```css
.cf-eyebrow {
  font-size: 0.6rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(var(--c-faint));
}
```

---

## cf-mark

Inline text highlight — draws attention to key terms.

```html
<p>สถานะ: <span class="cf-mark">อนุมัติแล้ว</span></p>
```

```css
.cf-mark {
  background: rgb(var(--c-accent) / 0.08);
  color: rgb(var(--c-accent));
  padding: 0.1em 0.35em;
  border-radius: 0.3rem;
  font-weight: 600;
  font-size: 0.875em;
}
```

---

## cf-iconbox

Bordered square icon container. Used for page/section icons.

```html
<!-- Default (ink) -->
<div class="cf-iconbox">
  <svg width="18" height="18" ...>...</svg>
</div>

<!-- Accent (blue) -->
<div class="cf-iconbox" style="border-color:rgb(var(--c-accent)/0.28);background:rgb(var(--c-accent)/0.06);color:rgb(var(--c-accent))">
  <svg width="18" height="18" ...>...</svg>
</div>

<!-- Green -->
<div class="cf-iconbox" style="border-color:rgb(var(--c-safe)/0.28);background:rgb(var(--c-safe)/0.06);color:rgb(var(--c-safe))">
  <svg width="18" height="18" ...>...</svg>
</div>
```

```css
.cf-iconbox {
  width: 2.25rem;
  height: 2.25rem;
  border: 1px solid rgb(var(--c-line) / 0.14);
  border-radius: 0.5rem;
  background: rgb(var(--c-surface));
  color: rgb(var(--c-ink));
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
```

---

## cf-zone (Status Badge)

Colored status badge. Seven variants covering all states.

```html
<span class="cf-zone cf-zone-safe">สำเร็จ</span>
<span class="cf-zone cf-zone-caution">รอดำเนินการ</span>
<span class="cf-zone cf-zone-danger">ล้มเหลว</span>
<span class="cf-zone cf-zone-free">กำลังทำงาน</span>
<span class="cf-zone cf-zone-info">ข้อมูล</span>
<span class="cf-zone cf-zone-mute">ปิดการใช้งาน</span>
<span class="cf-zone cf-zone-neutral">รอ</span>
```

```css
.cf-zone {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.18rem 0.55rem;
  border-radius: 9999px;
  font-size: 0.7rem;
  font-weight: 600;
  white-space: nowrap;
  border: 1px solid transparent;
}

/* Variants */
.cf-zone-safe    { background: rgb(var(--c-safe)    / 0.08); color: #0f766e; border-color: rgb(var(--c-safe)    / 0.22); }
.cf-zone-caution { background: rgb(var(--c-caution) / 0.10); color: #92660b; border-color: rgb(var(--c-caution) / 0.25); }
.cf-zone-danger  { background: rgb(var(--c-danger)  / 0.08); color: #b1453a; border-color: rgb(var(--c-danger)  / 0.22); }
.cf-zone-free    { background: rgb(var(--c-free)    / 0.08); color: #0f766e; border-color: rgb(var(--c-free)    / 0.22); }
.cf-zone-info    { background: rgb(var(--c-info)    / 0.08); color: rgb(var(--c-accent)); border-color: rgb(var(--c-info) / 0.20); }
.cf-zone-mute    { background: rgb(var(--c-line)    / 0.05); color: rgb(var(--c-faint)); border-color: rgb(var(--c-line) / 0.10); }
.cf-zone-neutral { background: rgb(var(--c-surface)); color: rgb(var(--c-muted)); border-color: rgb(var(--c-line) / 0.12); }
```

---

## cf-tier (Tier Badge)

Tier classification badge. See `ref/patterns.md` for the T0–T3 system semantics.

```html
<span class="cf-tier cf-tier-0">T0 ทำเลย</span>
<span class="cf-tier cf-tier-1">T1 บันทึก</span>
<span class="cf-tier cf-tier-2">T2 ส่งออก</span>
<span class="cf-tier cf-tier-3">T3 จ่ายเงิน</span>
```

```css
.cf-tier {
  display: inline-flex;
  align-items: center;
  padding: 0.15rem 0.5rem;
  border-radius: 0.35rem;
  font-size: 0.68rem;
  font-weight: 700;
  font-family: 'Bai Jamjuree', sans-serif;
  letter-spacing: 0.02em;
}

.cf-tier-0 { background: rgb(var(--c-safe)    / 0.10); color: #0f766e; }
.cf-tier-1 { background: rgb(var(--c-safe)    / 0.10); color: #0f766e; }
.cf-tier-2 { background: rgb(var(--c-caution) / 0.12); color: #92660b; }
.cf-tier-3 { background: rgb(var(--c-danger)  / 0.10); color: #b1453a; }
```

---

## cf-input / cf-label

Form field components.

```html
<div style="display:flex;flex-direction:column;gap:0.35rem;">
  <label class="cf-label" for="name">ชื่อ-นามสกุล <span style="color:rgb(var(--c-danger))">*</span></label>
  <input class="cf-input" id="name" type="text" placeholder="ระบุชื่อ-นามสกุล" />
</div>

<!-- Read-only / auto-computed field -->
<div style="display:flex;flex-direction:column;gap:0.35rem;">
  <label class="cf-label">คำนวณโดยระบบ</label>
  <div class="cf-input cf-input-ro">ค่าที่ระบบคำนวณ</div>
</div>

<!-- Textarea -->
<textarea class="cf-input" rows="4" placeholder="รายละเอียด..."></textarea>
```

```css
.cf-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: rgb(var(--c-muted));
}

.cf-input {
  width: 100%;
  padding: 0.55rem 0.75rem;
  border: 1px solid rgb(var(--c-line) / 0.14);
  border-radius: 0.5rem;
  background: rgb(var(--c-card));
  color: rgb(var(--c-ink));
  font-family: inherit;
  font-size: 0.82rem;
  outline: none;
  transition: border-color 0.12s, box-shadow 0.12s;
}
.cf-input:focus {
  border-color: rgb(var(--c-accent) / 0.6);
  box-shadow: 0 0 0 3px rgb(var(--c-accent) / 0.10);
}
.cf-input::placeholder { color: rgb(var(--c-faint)); }

.cf-input-ro {
  background: rgb(var(--c-surface));
  color: rgb(var(--c-muted));
  cursor: default;
  user-select: none;
}
```

---

## cf-good / cf-warn / cf-bad / cf-info (Callout Blocks)

Alert/notice callout blocks.

```html
<!-- Info tip (most common — "ปกติสั่งผ่านแชตได้") -->
<div class="cf-info">
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
  </svg>
  <span>ปกติสั่งผ่านแชตได้ ไม่ต้องมาที่หน้านี้</span>
</div>

<!-- Success callout -->
<div class="cf-good">
  <svg ...>...</svg>
  <span>บันทึกสำเร็จแล้ว</span>
</div>

<!-- Warning callout -->
<div class="cf-warn">
  <svg ...>...</svg>
  <span>กรุณาตรวจสอบข้อมูลก่อนส่ง</span>
</div>

<!-- Error callout -->
<div class="cf-bad">
  <svg ...>...</svg>
  <span>เกิดข้อผิดพลาด กรุณาลองใหม่</span>
</div>
```

```css
.cf-good, .cf-warn, .cf-bad, .cf-info {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 0.75rem 1rem;
  border-radius: 0.6rem;
  font-size: 0.82rem;
  line-height: 1.5;
  border: 1px solid;
}

.cf-good { background: rgb(var(--c-safe)    / 0.06); border-color: rgb(var(--c-safe)    / 0.22); color: #0f766e; }
.cf-warn { background: rgb(var(--c-caution) / 0.08); border-color: rgb(var(--c-caution) / 0.25); color: #92660b; }
.cf-bad  { background: rgb(var(--c-danger)  / 0.06); border-color: rgb(var(--c-danger)  / 0.22); color: #b1453a; }
.cf-info { background: rgb(var(--c-info)    / 0.05); border-color: rgb(var(--c-info)    / 0.18); color: rgb(var(--c-muted)); }
```

---

## cf-table

Styled data table.

```html
<div style="overflow-x:auto;">
  <table class="cf-table">
    <thead>
      <tr>
        <th>ชื่อ</th>
        <th>สถานะ</th>
        <th>วันที่</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>สมชาย ใจดี</td>
        <td><span class="cf-zone cf-zone-safe">สำเร็จ</span></td>
        <td class="num" style="font-size:0.82rem">2026-06-12</td>
        <td><button class="cf-btn" style="padding:0.25rem 0.6rem;font-size:0.75rem">รายละเอียด</button></td>
      </tr>
    </tbody>
  </table>
</div>
```

```css
.cf-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.cf-table th {
  text-align: left;
  padding: 0.6rem 0.875rem;
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgb(var(--c-faint));
  border-bottom: 1px solid rgb(var(--c-line) / 0.10);
  white-space: nowrap;
}
.cf-table td {
  padding: 0.7rem 0.875rem;
  border-bottom: 1px solid rgb(var(--c-line) / 0.07);
  color: rgb(var(--c-ink));
  vertical-align: middle;
}
.cf-table tr:last-child td { border-bottom: none; }
.cf-table tr:hover td { background: rgb(var(--c-surface)); }
```

---

## cf-spin (Spinner)

Inline CSS spinner for loading states. Always placed inside buttons or loading containers.

```html
<!-- Inside button -->
<button class="cf-btn cf-btn-primary" disabled>
  <span class="cf-spin" style="border-top-color:#fff;border-color:rgba(255,255,255,0.3);width:13px;height:13px;"></span>
  กำลังโหลด...
</button>

<!-- Standalone (muted) -->
<span class="cf-spin"></span>
```

```css
.cf-spin {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgb(var(--c-line) / 0.15);
  border-top-color: rgb(var(--c-accent));
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }
```

---

## cf-ava (Avatar)

User/entity avatar — initials or image.

```html
<!-- Initials avatar -->
<div class="cf-ava">สช</div>

<!-- Colored variants -->
<div class="cf-ava" style="background:rgb(var(--c-accent)/0.12);color:rgb(var(--c-accent))">AN</div>

<!-- Image avatar -->
<div class="cf-ava" style="padding:0;overflow:hidden;">
  <img src="avatar.jpg" alt="User" style="width:100%;height:100%;object-fit:cover;" />
</div>
```

```css
.cf-ava {
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  background: rgb(var(--c-surface));
  border: 1px solid rgb(var(--c-line) / 0.12);
  color: rgb(var(--c-muted));
  font-size: 0.65rem;
  font-weight: 700;
  font-family: 'Bai Jamjuree', sans-serif;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
```

---

## cf-toast

Toast notification. Usually teleported to `<body>` with `position: fixed`.

```html
<!-- Success toast -->
<div class="cf-toast cf-toast-success">
  <span class="toast-icon">
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  </span>
  <span>บันทึกสำเร็จแล้ว</span>
</div>
```

```css
.cf-toast {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.65rem 0.875rem;
  border-radius: 0.75rem;
  font-size: 0.815rem;
  border: 1px solid;
  border-left-width: 3px;
  background: rgb(var(--c-card));
  box-shadow: var(--shadow-md);
  min-width: 220px;
  max-width: 360px;
}

.cf-toast-success { background: rgb(16 185 129 / 0.05); border-color: rgb(16 185 129 / 0.28); border-left-color: #10b981; color: #0f766e; }
.cf-toast-error   { background: rgb(239 68 68 / 0.05);  border-color: rgb(239 68 68 / 0.26);  border-left-color: #ef4444; color: #b1453a; }
.cf-toast-info    { background: rgb(37 99 235 / 0.04);  border-color: rgb(37 99 235 / 0.20);  border-left-color: rgb(var(--c-accent)); color: rgb(var(--c-ink)); }

.toast-icon {
  width: 18px; height: 18px;
  border-radius: 50%;
  display: grid; place-items: center;
  flex-shrink: 0;
  background: currentColor; /* gets override below */
}
.cf-toast-success .toast-icon { background: #10b981; color: #fff; }
.cf-toast-error   .toast-icon { background: #ef4444; color: #fff; }
.cf-toast-info    .toast-icon { background: rgb(var(--c-accent)); color: #fff; }
```

---

## cf-composer + cf-bubble (Chat)

Used on pages with AI chat interface (help, consult, linegroups pages).

```html
<div class="cf-composer">
  <textarea class="cf-input" rows="1" placeholder="พิมพ์คำสั่ง..." style="resize:none;"></textarea>
  <button class="cf-btn cf-btn-primary">ส่ง</button>
</div>

<!-- Chat messages -->
<div style="display:flex;flex-direction:column;gap:0.75rem;">
  <!-- User bubble (right) -->
  <div style="display:flex;justify-content:flex-end;">
    <div class="cf-bubble cf-bubble-user">คำถามของผู้ใช้</div>
  </div>
  <!-- AI bubble (left) -->
  <div style="display:flex;justify-content:flex-start;gap:0.5rem;">
    <div class="cf-ava">AI</div>
    <div class="cf-bubble cf-bubble-ai">คำตอบจาก AI</div>
  </div>
</div>
```

```css
.cf-composer {
  display: flex;
  gap: 0.5rem;
  align-items: flex-end;
  padding: 0.75rem;
  border-top: 1px solid rgb(var(--c-line) / 0.10);
  background: rgb(var(--c-card));
}

.cf-bubble {
  max-width: 80%;
  padding: 0.6rem 0.875rem;
  border-radius: 1rem;
  font-size: 0.875rem;
  line-height: 1.5;
}
.cf-bubble-user {
  background: rgb(var(--c-accent));
  color: #fff;
  border-bottom-right-radius: 0.25rem;
}
.cf-bubble-ai {
  background: rgb(var(--c-surface));
  border: 1px solid rgb(var(--c-line) / 0.10);
  color: rgb(var(--c-ink));
  border-bottom-left-radius: 0.25rem;
}
```

---

## Hairline Border Utilities

Quick border utilities using hairline (1px, low alpha) borders.

```html
<div class="hair">All 4 sides</div>
<div class="hair-t">Top only</div>
<div class="hair-b">Bottom only</div>
<div class="hair-r">Right only</div>
```

```css
.hair   { border: 1px solid rgb(var(--c-line) / 0.10); }
.hair-t { border-top: 1px solid rgb(var(--c-line) / 0.10); }
.hair-b { border-bottom: 1px solid rgb(var(--c-line) / 0.10); }
.hair-r { border-right: 1px solid rgb(var(--c-line) / 0.10); }
```

---

## cf-step (Step / Progress Indicator)

Multi-step workflow progress.

```html
<div class="cf-step-row">
  <div class="cf-step cf-step-done">
    <span class="step-num">1</span>
    <span class="step-label">อัปโหลดไฟล์</span>
  </div>
  <div class="step-connector"></div>
  <div class="cf-step cf-step-active">
    <span class="step-num">2</span>
    <span class="step-label">ตรวจสอบ</span>
  </div>
  <div class="step-connector"></div>
  <div class="cf-step">
    <span class="step-num">3</span>
    <span class="step-label">บันทึก</span>
  </div>
</div>
```

```css
.cf-step-row { display: flex; align-items: center; gap: 0; }

.cf-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}

.step-num {
  width: 28px; height: 28px;
  border-radius: 50%;
  border: 2px solid rgb(var(--c-line) / 0.15);
  background: rgb(var(--c-surface));
  color: rgb(var(--c-faint));
  font-family: 'Bai Jamjuree', sans-serif;
  font-size: 0.72rem;
  font-weight: 700;
  display: grid; place-items: center;
}

.cf-step-done .step-num  { background: rgb(var(--c-safe));   border-color: rgb(var(--c-safe));   color: #fff; }
.cf-step-active .step-num{ background: rgb(var(--c-accent)); border-color: rgb(var(--c-accent)); color: #fff; }

.step-label { font-size: 0.65rem; color: rgb(var(--c-faint)); white-space: nowrap; }
.cf-step-active .step-label { color: rgb(var(--c-accent)); font-weight: 600; }

.step-connector {
  flex: 1; height: 1px;
  background: rgb(var(--c-line) / 0.12);
  min-width: 2rem;
}
```

---

## cf-light

Light/muted background section — for aside content or subtle containers.

```html
<div class="cf-light">
  <p style="font-size:0.82rem;color:rgb(var(--c-muted))">ข้อมูลเพิ่มเติม</p>
</div>
```

```css
.cf-light {
  background: rgb(var(--c-surface));
  border: 1px solid rgb(var(--c-line) / 0.08);
  border-radius: var(--radius);
  padding: 0.875rem 1rem;
}
```

---

## cf-screen + cf-phone (Mobile Showcase Frame)

Used on showcase pages to display mobile UI mockups inside a phone frame.

```html
<div class="cf-screen">
  <div class="cf-phone">
    <!-- Mobile UI content -->
    <div style="padding:1rem">Phone content here</div>
  </div>
</div>
```

```css
.cf-screen {
  display: flex;
  justify-content: center;
  padding: 2rem;
  background: rgb(var(--c-surface));
  border-radius: var(--radius);
}

.cf-phone {
  width: 375px;
  min-height: 667px;
  background: rgb(var(--c-card));
  border-radius: 2rem;
  border: 1px solid rgb(var(--c-line) / 0.12);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
```
