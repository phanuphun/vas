# UI-Minimal — Layout Reference (Tailwind)

All layout dimensions use CSS variables from `ref/tokens.md`. Read that file first.

---

## Standard App Shell

```html
<!-- Mobile: sidebar is fixed drawer. Desktop (lg+): sidebar is sticky in flex row. -->
<div class="flex flex-col lg:flex-row lg:items-start min-h-screen">

  <!-- Mobile overlay -->
  <div id="overlay" onclick="closeSidebar()"
       class="hidden fixed inset-0 bg-[rgb(26_32_50/0.32)] backdrop-blur-sm z-[299]"></div>
  <!-- JS toggle: overlay.classList.toggle('hidden') -->

  <!-- Sidebar (240px fixed drawer on mobile, sticky column on desktop) -->
  <aside id="sidebar"
         class="sidebar fixed top-0 left-0 bottom-0 w-60 bg-card border-r border-line/10 flex flex-col z-[300] -translate-x-full lg:translate-x-0 lg:sticky lg:h-screen lg:shadow-none shadow-md flex-shrink-0">
    <!-- content: see Sidebar Component below -->
  </aside>

  <!-- Right column -->
  <div class="flex-1 min-w-0 flex flex-col min-h-screen">
    <header class="sticky top-0 z-[100] bg-white/94 backdrop-blur-md border-b border-line/10">
      <!-- content: see Header Component below -->
    </header>
    <main class="flex-1 px-3 py-3.5 md:px-5 md:py-[1.125rem] lg:px-6 lg:py-5
                 pb-[calc(var(--savebar-h,64px)+env(safe-area-inset-bottom,0px)+0.5rem)] overflow-x-hidden">
      <div class="max-w-[1200px] mx-auto flex flex-col gap-4">
        <!-- Page content -->
      </div>
    </main>
  </div>

</div>
```

> **No save bar?** Replace `pb-[calc(...)]` with `pb-8`.

---

## Sidebar Component

```html
<aside id="sidebar" class="sidebar fixed top-0 left-0 bottom-0 w-60 bg-card border-r border-line/10 flex flex-col z-[300] -translate-x-full lg:translate-x-0 lg:sticky lg:h-screen flex-shrink-0">

  <!-- Brand row (must match header height: h-[52px]) -->
  <div class="flex items-center gap-2 h-[52px] px-4 border-b border-line/10 flex-shrink-0">
    <div class="w-[30px] h-[30px] border-[1.5px] border-ink rounded-lg grid place-items-center bg-white flex-shrink-0">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
      </svg>
    </div>
    <div class="flex-1 overflow-hidden">
      <div class="font-display text-[0.8rem] font-bold text-ink truncate">App Name</div>
      <div class="text-[0.58rem] text-faint mt-px">Company</div>
    </div>
    <!-- Mobile close button -->
    <button onclick="closeSidebar()" class="lg:hidden text-faint hover:text-ink p-1 rounded hover:bg-line/6 transition-colors">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>
  </div>

  <!-- Nav -->
  <nav class="sidebar-nav flex-1 overflow-y-auto py-3 flex flex-col gap-1">
    <div class="px-2 mb-2">
      <span class="text-[0.6rem] font-bold uppercase tracking-[0.08em] text-faint block px-2 mb-1">เมนูหลัก</span>

      <!-- Active nav item -->
      <a href="/" class="flex items-center gap-2 px-2.5 py-2 rounded-[0.6rem] min-h-[40px]
                          bg-accent/8 text-accent font-semibold text-[0.82rem] w-full">
        <span class="w-5 h-5 flex items-center justify-center flex-shrink-0 text-accent">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
        </span>
        <span class="flex-1">แดชบอร์ด</span>
      </a>

      <!-- Normal nav item -->
      <a href="/vpn" class="flex items-center gap-2 px-2.5 py-2 rounded-[0.6rem] min-h-[40px]
                             text-muted hover:bg-line/6 hover:text-ink transition-colors text-[0.82rem] font-medium w-full">
        <span class="w-5 h-5 flex items-center justify-center flex-shrink-0 text-faint">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </span>
        <span class="flex-1">VPN</span>
      </a>
    </div>
  </nav>

  <!-- Footer -->
  <div class="border-t border-line/10 px-4 py-3 flex-shrink-0">
    <div class="flex items-center gap-2">
      <div class="w-8 h-8 rounded-full bg-accent/10 text-accent text-[0.65rem] font-bold font-display grid place-items-center flex-shrink-0">VM</div>
      <div>
        <div class="text-[0.78rem] font-semibold text-ink">Machine Name</div>
        <div class="text-[0.62rem] text-faint">VAS</div>
      </div>
    </div>
  </div>

</aside>
```

**JS for mobile toggle:**
```js
function openSidebar()  { document.getElementById('sidebar').classList.remove('-translate-x-full'); document.getElementById('overlay').classList.remove('hidden'); }
function closeSidebar() { document.getElementById('sidebar').classList.add('-translate-x-full'); document.getElementById('overlay').classList.add('hidden'); }
```

---

## Header Component

```html
<header class="sticky top-0 z-[100] bg-white/94 backdrop-blur-md border-b border-line/10">
  <div class="flex items-center gap-3 px-4 h-[52px]">
    <!-- Hamburger (mobile only) -->
    <button onclick="openSidebar()" class="lg:hidden w-9 h-9 border border-line/15 rounded-lg bg-card text-ink flex items-center justify-center hover:bg-surface transition-colors flex-shrink-0">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
      </svg>
    </button>

    <!-- Page title -->
    <span class="font-display text-[0.95rem] font-bold text-ink whitespace-nowrap">ชื่อหน้า</span>

    <div class="flex-1"></div>

    <!-- Right actions -->
    <button class="inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-line/15 rounded-lg bg-card text-ink text-[0.82rem] font-semibold hover:bg-surface transition-colors">
      การดำเนินการ
    </button>
  </div>
</header>
```

---

## Page Heading Block

```html
<div class="mb-6">
  <p class="text-[0.6rem] font-bold uppercase tracking-[0.08em] text-faint">หมวดหมู่ · หน้าย่อย</p>
  <h1 class="font-display text-[1.35rem] font-bold text-ink mt-1">ชื่อหน้า</h1>
  <p class="text-[0.875rem] text-muted mt-1">คำอธิบายสั้นๆ ของหน้านี้</p>
</div>
```

---

## Fixed Bottom Save Bar

```html
<div class="fixed bottom-0 left-0 right-0 lg:left-[var(--sidebar-w,240px)]
            bg-white/96 backdrop-blur-md border-t border-line/10 z-[200]
            shadow-[0_-4px_20px_rgb(26_32_50/0.07)] safe-pb">
  <div class="max-w-[1400px] mx-auto px-4 py-2.5 flex items-center justify-between gap-3">
    <div class="flex items-center gap-2.5">
      <div class="w-9 h-9 border border-accent/28 rounded-lg bg-accent/6 text-accent grid place-items-center">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m9 12 2 2 4-4"/>
        </svg>
      </div>
      <div>
        <div class="flex items-center gap-1.5">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[0.7rem] font-semibold bg-accent/10 border border-accent/20 text-accent font-display tabular-nums">3</span>
          <span class="text-[0.82rem] font-semibold text-ink">รายการพร้อมบันทึก</span>
        </div>
        <div class="text-[0.68rem] text-faint">ส่งไปยัง Google Sheets</div>
      </div>
    </div>
    <button class="inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-accent rounded-lg bg-accent text-white text-[0.82rem] font-semibold hover:bg-blue-700 transition-colors">
      บันทึก 3 รายการ
    </button>
  </div>
</div>
```

---

## Content Grids

```html
<!-- Stat row (2 mobile, 4 sm+) -->
<div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
  <!-- cf-stat items -->
</div>

<!-- Main + Detail split (stacked mobile, 2-col desktop) -->
<div class="flex flex-col lg:grid lg:grid-cols-[1fr_360px] xl:grid-cols-[1fr_400px] gap-4 items-start">
  <div class="bg-card border border-line/10 rounded-xl"><!-- queue --></div>
  <div class="bg-card border border-line/10 rounded-xl lg:sticky lg:top-[calc(var(--header-h,52px)+0.75rem)] lg:max-h-[calc(100vh-9rem)] lg:overflow-y-auto"><!-- detail --></div>
</div>

<!-- 2-column form grid -->
<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
  <div><!-- field 1 --></div>
  <div><!-- field 2 --></div>
  <div class="sm:col-span-2"><!-- full-width field --></div>
</div>
```

---

## Toast Positioning

```html
<!-- Fixed toast container -->
<div id="toast-wrap"
     class="fixed bottom-[calc(var(--savebar-h,64px)+env(safe-area-inset-bottom,0px))] sm:bottom-6 lg:bottom-[calc(var(--savebar-h,64px)+1rem)]
            right-4 z-[9999] flex flex-col gap-1.5 max-w-[360px]">
</div>
```

---

## Modal / Dialog

```html
<!-- Backdrop -->
<div class="fixed inset-0 bg-[rgb(26_32_50/0.28)] backdrop-blur z-[400]" onclick="closeModal()"></div>

<!-- Dialog -->
<div class="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[401]
            w-[min(420px,calc(100vw-2rem))] p-6
            bg-card border border-line/10 rounded-xl shadow-lg">
  <div class="flex items-start gap-4">
    <div class="w-9 h-9 border border-caution/30 rounded-lg bg-caution/8 text-[#92660b] grid place-items-center flex-shrink-0">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    </div>
    <div>
      <h2 class="font-display text-[1rem] font-bold text-ink mb-1">หัวข้อ Dialog</h2>
      <p class="text-[0.875rem] text-muted leading-relaxed">รายละเอียดของ dialog</p>
    </div>
  </div>
  <div class="flex justify-end gap-2 mt-5">
    <button onclick="closeModal()" class="inline-flex items-center px-3.5 py-1.5 border border-line/15 rounded-lg bg-card text-ink text-[0.82rem] font-semibold hover:bg-surface transition-colors">ยกเลิก</button>
    <button class="inline-flex items-center px-3.5 py-1.5 border border-accent rounded-lg bg-accent text-white text-[0.82rem] font-semibold hover:bg-blue-700 transition-colors">ตกลง</button>
  </div>
</div>
```

---

## Chat Layout

```html
<div class="flex flex-col" style="height: calc(100vh - var(--header-h, 52px) - 2rem);">
  <!-- Messages -->
  <div class="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
    <!-- AI bubble -->
    <div class="flex gap-2.5 items-start">
      <div class="w-8 h-8 rounded-full bg-accent/10 text-accent text-[0.65rem] font-bold font-display grid place-items-center flex-shrink-0">AI</div>
      <div class="max-w-[80%] px-3.5 py-2.5 rounded-2xl rounded-bl text-[0.875rem] bg-surface border border-line/10 text-ink">สวัสดีครับ มีอะไรให้ช่วยไหม?</div>
    </div>
    <!-- User bubble -->
    <div class="flex justify-end">
      <div class="max-w-[80%] px-3.5 py-2.5 rounded-2xl rounded-br text-[0.875rem] bg-accent text-white">ขอดูรายงานยอดขาย</div>
    </div>
  </div>

  <!-- Composer -->
  <div class="flex gap-2 items-end px-3 py-3 border-t border-line/10 bg-card">
    <textarea rows="1" placeholder="พิมพ์คำสั่ง..." class="flex-1 px-3 py-2 border border-line/15 rounded-lg bg-card text-ink text-[0.82rem] outline-none focus:border-accent/60 focus:ring-2 focus:ring-accent/10 placeholder:text-faint transition resize-none min-h-[40px] max-h-[120px] overflow-y-auto"></textarea>
    <button class="inline-flex items-center gap-1.5 px-3.5 py-2 border border-accent rounded-lg bg-accent text-white text-[0.82rem] font-semibold hover:bg-blue-700 transition-colors flex-shrink-0">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
      ส่ง
    </button>
  </div>
</div>
```
