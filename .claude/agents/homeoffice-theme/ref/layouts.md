# HomeOffice — Layout Reference

All layout dimensions use CSS variables from `ref/tokens.md`. Read that file first.

---

## Standard App Shell

The full app shell: sidebar (240px desktop) + right column (header + main + fixed bottom bar).

```html
<div class="app-root">
  <!-- Sidebar (mobile: fixed drawer; desktop: sticky in flex row) -->
  <aside class="sidebar hair-r">...</aside>

  <!-- Right column: stacks header → main → (fixed savebar) -->
  <div class="app-column">
    <header class="app-header hair-b">...</header>
    <main class="ho-main">...</main>
    <!-- Optional: fixed bottom save bar -->
    <div class="save-bar hair-t">...</div>
  </div>
</div>
```

```css
/* ── Root ── */
.app-root {
  min-height: 100vh;
  display: flex;
  flex-direction: column;   /* mobile: stacked */
  align-items: stretch;
}

@media (min-width: 1024px) {
  .app-root {
    flex-direction: row;
    align-items: flex-start; /* REQUIRED for sidebar sticky */
  }
}

/* ── Right column ── */
.app-column {
  flex: 1;
  min-width: 0;             /* prevent flex blowout */
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

/* ── Main content ── */
.ho-main {
  flex: 1;
  padding: 0.875rem 0.75rem
    calc(var(--savebar-h, 64px) + env(safe-area-inset-bottom, 0px) + 0.5rem);
  overflow-x: hidden;
}

@media (min-width: 768px)  { .ho-main { padding: 1.125rem 1.25rem calc(var(--savebar-h, 64px) + 0.5rem); } }
@media (min-width: 1024px) { .ho-main { padding: 1.25rem 1.5rem  calc(var(--savebar-h, 64px) + 0.5rem); } }
```

> **If no save bar:** remove the `env(safe-area-inset-bottom)` padding and use `padding-bottom: 2rem` instead.

---

## Sidebar Component

240px sidebar with brand, nav sections, and footer.

```html
<!-- Mobile overlay (separate from sidebar) -->
<div class="sidebar-overlay" id="overlay" onclick="closeSidebar()"></div>

<!-- Sidebar -->
<aside class="sidebar hair-r" id="sidebar">

  <!-- Brand row — MUST match header height exactly -->
  <div class="sidebar-brand hair-b">
    <div class="brand-mark">
      <svg width="15" height="15" ...>...</svg>
    </div>
    <div class="brand-text">
      <div class="brand-name font-display">App Name</div>
      <div class="brand-sub">Company Name</div>
    </div>
    <!-- Mobile close button -->
    <button class="sidebar-close" onclick="closeSidebar()">
      <svg width="14" height="14" ...>✕</svg>
    </button>
  </div>

  <!-- Nav -->
  <nav class="sidebar-nav">
    <!-- Section -->
    <div class="nav-section">
      <span class="cf-eyebrow nav-heading">หัวข้อหมวด</span>
      
      <!-- Active nav item -->
      <button class="nav-item active">
        <span class="nav-icon"><svg ...>...</svg></span>
        <span class="nav-label">เมนูที่เลือก</span>
        <span class="nav-badge">5</span>  <!-- optional count badge -->
      </button>

      <!-- Normal nav item -->
      <button class="nav-item">
        <span class="nav-icon"><svg ...>...</svg></span>
        <span class="nav-label">เมนูปกติ</span>
      </button>

      <!-- Disabled / coming soon -->
      <button class="nav-item nav-item-dim" disabled>
        <span class="nav-icon"><svg ...>...</svg></span>
        <span class="nav-label">เร็วๆ นี้</span>
        <span class="nav-tag">เร็วๆ นี้</span>
      </button>
    </div>
  </nav>

  <!-- Footer -->
  <div class="sidebar-footer hair-t">
    <!-- Any footer content, e.g. user info, model picker -->
  </div>
</aside>
```

```css
/* ── Sidebar shell ── */
.sidebar {
  position: fixed;
  top: 0; left: 0; bottom: 0;
  width: 240px;
  background: rgb(var(--c-card));
  display: flex;
  flex-direction: column;
  z-index: 300;
  transform: translateX(-100%);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: var(--shadow-md);
}
.sidebar.open { transform: translateX(0); }

@media (min-width: 1024px) {
  .sidebar {
    transform: translateX(0);
    box-shadow: none;
    position: sticky;
    top: 0;
    height: 100vh;
    flex-shrink: 0;
    z-index: 10;  /* lower z-index — in normal flow, no overlap */
  }
}

/* ── Mobile overlay ── */
.sidebar-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgb(26 32 50 / 0.32);
  z-index: 299;
  backdrop-filter: blur(2px);
}
.sidebar-overlay.visible { display: block; }

/* ── Brand ── */
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  height: var(--header-h, 52px);  /* MUST match header height */
  padding: 0 1rem;
  flex-shrink: 0;
}
.brand-mark {
  width: 30px; height: 30px;
  border: 1.5px solid rgb(var(--c-ink));
  border-radius: 0.5rem;
  display: grid; place-items: center;
  background: #fff;
  flex-shrink: 0;
}
.brand-name { font-size: 0.8rem; font-weight: 700; color: rgb(var(--c-ink)); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.brand-sub  { font-size: 0.58rem; color: rgb(var(--c-faint)); margin-top: 1px; }
.brand-text { flex: 1; overflow: hidden; }

.sidebar-close {
  background: none; border: none;
  color: rgb(var(--c-faint)); cursor: pointer;
  padding: 4px; display: flex; align-items: center; justify-content: center;
  border-radius: 4px;
}
.sidebar-close:hover { color: rgb(var(--c-ink)); background: rgb(var(--c-line) / 0.06); }
@media (min-width: 1024px) { .sidebar-close { display: none; } }

/* ── Nav ── */
.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  scrollbar-width: thin;
  scrollbar-color: rgb(var(--c-line) / 0.12) transparent;
}
.nav-section { padding: 0 0.5rem; margin-bottom: 0.5rem; }
.nav-heading { display: block; padding: 0 0.5rem; margin-bottom: 0.25rem; }

.nav-item {
  width: 100%;
  display: flex; align-items: center; gap: 0.55rem;
  padding: 0.55rem 0.625rem;
  border-radius: 0.6rem;
  border: none; background: none;
  color: rgb(var(--c-muted));
  font-size: 0.82rem; font-weight: 500;
  cursor: pointer; text-align: left;
  transition: background 0.12s, color 0.12s;
  font-family: inherit;
  min-height: 40px;
}
.nav-item:hover:not(:disabled) { background: rgb(var(--c-line) / 0.06); color: rgb(var(--c-ink)); }
.nav-item.active { background: rgb(var(--c-accent) / 0.08); color: rgb(var(--c-accent)); font-weight: 600; }
.nav-item.active .nav-icon { color: rgb(var(--c-accent)); }
.nav-item-dim { opacity: 0.45; cursor: not-allowed; }

.nav-icon { width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; color: rgb(var(--c-faint)); }
.nav-label { flex: 1; }

.nav-badge {
  min-width: 18px; height: 18px;
  background: rgb(var(--c-accent)); color: #fff;
  border-radius: 9999px;
  font-size: 0.6rem; font-weight: 700;
  font-family: 'Bai Jamjuree', sans-serif;
  display: flex; align-items: center; justify-content: center;
  padding: 0 4px; flex-shrink: 0;
}

.nav-tag {
  font-size: 0.58rem; font-weight: 600;
  padding: 0.06rem 0.35rem;
  border-radius: 3px;
  background: rgb(var(--c-line) / 0.07);
  color: rgb(var(--c-faint));
  border: 1px solid rgb(var(--c-line) / 0.10);
  white-space: nowrap;
}

/* ── Footer ── */
.sidebar-footer { padding: 0.75rem 1rem; flex-shrink: 0; }
```

---

## Header Component

Sticky header with hamburger (mobile), page title, and optional actions.

```html
<header class="app-header hair-b">
  <div class="header-inner">
    <!-- Hamburger (mobile only) -->
    <button class="menu-btn" onclick="openSidebar()" aria-label="เปิดเมนู">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="3" y1="6" x2="21" y2="6"/>
        <line x1="3" y1="12" x2="21" y2="12"/>
        <line x1="3" y1="18" x2="21" y2="18"/>
      </svg>
    </button>

    <!-- Page title -->
    <div class="page-title font-display">ชื่อหน้า</div>

    <!-- Spacer -->
    <div style="flex:1;"></div>

    <!-- Right side actions (optional) -->
    <button class="cf-btn">การดำเนินการ</button>
  </div>
</header>
```

```css
.app-header {
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: 100;
}
.header-inner {
  padding: 0 1rem;
  height: var(--header-h, 52px);
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.page-title { font-size: 0.95rem; font-weight: 700; color: rgb(var(--c-ink)); white-space: nowrap; }

.menu-btn {
  width: 36px; height: 36px;
  border: 1px solid rgb(var(--c-line) / 0.14);
  border-radius: 0.5rem;
  background: rgb(var(--c-card));
  color: rgb(var(--c-ink));
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; flex-shrink: 0;
  transition: background 0.12s;
}
.menu-btn:hover { background: rgb(var(--c-surface)); }
@media (min-width: 1024px) { .menu-btn { display: none; } }
```

---

## Page Heading Block

Standard pattern at top of every main content page.

```html
<div class="page-head">
  <p class="cf-eyebrow">หมวดหมู่ · หน้าย่อย</p>
  <h1 class="font-display" style="font-size:1.35rem;font-weight:700;margin-top:0.2rem">ชื่อหน้า</h1>
  <p style="color:rgb(var(--c-muted));font-size:0.875rem;margin-top:0.3rem">คำอธิบายสั้นๆ ของหน้านี้</p>
</div>
```

```css
.page-head { margin-bottom: 1.5rem; }
```

---

## Fixed Bottom Bar (Save Bar)

Floating bar at bottom for batch actions (save, submit). Must offset left by sidebar width on desktop.

```html
<div class="save-bar hair-t">
  <div class="bar-inner">
    <div style="display:flex;align-items:center;gap:0.6rem;">
      <div class="cf-iconbox" style="border-color:rgb(var(--c-accent)/0.28);background:rgb(var(--c-accent)/0.06);color:rgb(var(--c-accent))">
        <svg width="15" height="15" ...>...</svg>
      </div>
      <div>
        <div style="display:flex;align-items:center;gap:0.4rem;">
          <span class="cf-chip cf-chip-accent num">3</span>
          <span style="font-size:0.82rem;font-weight:600">รายการพร้อมบันทึก</span>
        </div>
        <div style="font-size:0.68rem;color:rgb(var(--c-faint))">ส่งไปยัง Google Sheets</div>
      </div>
    </div>
    <button class="cf-btn cf-btn-primary">บันทึก 3 รายการ</button>
  </div>
</div>
```

```css
.save-bar {
  position: fixed;
  bottom: 0;
  left: 0; right: 0;           /* mobile: full width */
  background: rgba(255,255,255,0.96);
  backdrop-filter: blur(12px);
  z-index: 200;
  box-shadow: 0 -4px 20px rgb(26 32 50 / 0.07);
  padding-bottom: env(safe-area-inset-bottom, 0px);
}

@media (min-width: 1024px) {
  .save-bar { left: var(--sidebar-w, 240px); }  /* offset past sidebar */
}

.bar-inner {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0.65rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
```

---

## Content Grids

### Stat Row (3–4 cards)

```html
<div class="stat-row">
  <div class="cf-stat">...</div>
  <div class="cf-stat">...</div>
  <div class="cf-stat">...</div>
</div>
```

```css
.stat-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);  /* 2 columns mobile */
  gap: 0.75rem;
  margin-bottom: 1rem;
}
@media (min-width: 640px) {
  .stat-row { grid-template-columns: repeat(4, 1fr); }  /* 4 columns sm+ */
}
```

### Main + Detail Split (Queue + Detail Panel)

```html
<div class="work-area has-detail">
  <div class="cf-card queue-card">
    <!-- List / table -->
  </div>
  <div class="cf-card detail-card">
    <!-- Detail panel -->
  </div>
</div>
```

```css
.work-area { display: flex; flex-direction: column; gap: 1rem; }

@media (min-width: 1024px) {
  .work-area.has-detail {
    display: grid;
    grid-template-columns: 1fr 360px;
    gap: 1.125rem;
    align-items: start;
  }
  .detail-card {
    position: sticky;
    top: calc(var(--header-h, 52px) + 0.75rem);
    max-height: calc(100vh - 9rem);
    overflow-y: auto;
  }
}
@media (min-width: 1280px) {
  .work-area.has-detail { grid-template-columns: 1fr 400px; }
}
```

### Card Content Inner Max Width

```css
.content-inner {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
```

### 2-Column Form Layout

```html
<div class="form-grid">
  <div><!-- field 1 --></div>
  <div><!-- field 2 --></div>
  <div style="grid-column:1/-1"><!-- full-width field --></div>
</div>
```

```css
.form-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
}
@media (min-width: 640px) {
  .form-grid { grid-template-columns: 1fr 1fr; }
}
```

---

## Chat Layout

Used on pages with AI assistant chat (consult, help, linegroups pages).

```html
<div class="chat-layout">
  <!-- Messages area -->
  <div class="chat-messages" id="messages">
    <!-- cf-bubble elements -->
  </div>

  <!-- Composer (pinned bottom) -->
  <div class="cf-composer">
    <textarea class="cf-input" rows="1" placeholder="พิมพ์คำสั่ง..."></textarea>
    <button class="cf-btn cf-btn-primary">ส่ง</button>
  </div>
</div>
```

```css
.chat-layout {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-h, 52px) - 2rem);
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
```

---

## Toast Positioning

```css
.toast-wrap {
  position: fixed;
  bottom: calc(var(--savebar-h, 64px) + env(safe-area-inset-bottom, 0px));
  right: 1rem;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  max-width: 360px;
}

@media (min-width: 640px) {
  .toast-wrap { bottom: 1.5rem; }  /* above safe area, no savebar overlap on sm */
}
@media (min-width: 1024px) {
  .toast-wrap { bottom: calc(var(--savebar-h, 64px) + 1rem); }
}
```

---

## Modal / Dialog

```html
<!-- Backdrop -->
<div class="modal-backdrop" onclick="closeModal()"></div>

<!-- Dialog -->
<div class="cf-card modal-dialog" role="dialog" aria-modal="true">
  <div style="display:flex;align-items:flex-start;gap:1rem;">
    <div class="cf-iconbox" style="border-color:rgb(var(--c-caution)/0.3);background:rgb(var(--c-caution)/0.08);color:#92660b;flex-shrink:0;">
      <svg width="18" height="18" ...>⚠️icon</svg>
    </div>
    <div>
      <h2 style="font-size:1rem;font-weight:700;margin-bottom:0.5rem">หัวข้อ Dialog</h2>
      <p style="font-size:0.875rem;color:rgb(var(--c-muted));line-height:1.6">รายละเอียดของ dialog</p>
    </div>
  </div>
  <div style="display:flex;justify-content:flex-end;gap:0.5rem;margin-top:1.25rem;">
    <button class="cf-btn" onclick="closeModal()">ยกเลิก</button>
    <button class="cf-btn cf-btn-primary">ตกลง</button>
  </div>
</div>
```

```css
.modal-backdrop {
  position: fixed; inset: 0;
  background: rgb(26 32 50 / 0.28);
  backdrop-filter: blur(4px);
  z-index: 400;
}
.modal-dialog {
  position: fixed;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  z-index: 401;
  width: min(420px, calc(100vw - 2rem));
  padding: 1.5rem;
  box-shadow: var(--shadow-lg);
}
```
