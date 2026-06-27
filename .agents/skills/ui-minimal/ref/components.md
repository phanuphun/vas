# UI-Minimal — Component Reference (Tailwind)

All components use the Tailwind config from `ref/tokens.md`. Read that first.

---

## Component Index

| Component | Tailwind pattern |
|-----------|-----------------|
| Card | `bg-card border border-line/10 rounded-xl` |
| Stat card | Card + `flex flex-col gap-1 p-4` |
| Button (ghost) | `inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-line/15 rounded-lg bg-card text-ink text-[0.82rem] font-semibold hover:bg-surface transition-colors` |
| Button (primary) | Same + `bg-accent border-accent text-white hover:bg-blue-700` |
| Chip | `inline-flex items-center px-2 py-0.5 rounded-full text-[0.7rem] font-semibold bg-surface border border-line/10 text-muted` |
| Eyebrow | `text-[0.6rem] font-bold uppercase tracking-[0.08em] text-faint` |
| Iconbox | `w-9 h-9 border border-line/15 rounded-lg bg-surface text-ink grid place-items-center flex-shrink-0` |
| Zone badge | `inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.7rem] font-semibold border` |
| Input | `w-full px-3 py-2 border border-line/15 rounded-lg bg-card text-ink text-[0.82rem] outline-none focus:border-accent/60 focus:ring-2 focus:ring-accent/10 placeholder:text-faint transition` |
| Label | `text-[0.75rem] font-semibold text-muted` |
| Table | Custom CSS still needed for `tr:hover` row highlighting |
| Avatar | `w-8 h-8 rounded-full bg-surface border border-line/12 text-muted text-[0.65rem] font-bold font-display grid place-items-center flex-shrink-0 uppercase` |
| Toast | Custom CSS for border-left-width: 3px (Tailwind: `border-l-[3px]` ✅) |
| Hairline | `border border-line/10` / `border-t border-line/10` / `border-b border-line/10` |
| Spinner | Custom `.spin` class (see SKILL.md — uses 0.7s custom timing) |

---

## Card

```html
<!-- Basic card -->
<div class="bg-card border border-line/10 rounded-xl p-5">
  Content
</div>

<!-- Card with section header -->
<div class="bg-card border border-line/10 rounded-xl">
  <div class="flex items-center justify-between px-5 py-3 border-b border-line/10">
    <h2 class="text-[0.9rem] font-semibold text-ink">Section Title</h2>
    <button class="inline-flex items-center gap-1.5 px-3 py-1.5 border border-line/15 rounded-lg bg-card text-ink text-[0.82rem] font-semibold hover:bg-surface transition-colors">Action</button>
  </div>
  <div class="p-5">Content</div>
</div>
```

---

## Stat Card

```html
<!-- Stat row (3–4 cards) -->
<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
  <div class="bg-card border border-line/10 rounded-xl p-4 flex flex-col gap-1">
    <span class="font-display text-[1.75rem] font-bold text-ink leading-none">142</span>
    <span class="text-xs text-faint">ลูกค้าทั้งหมด</span>
  </div>
  <div class="bg-card border border-line/10 rounded-xl p-4 flex flex-col gap-1">
    <span class="font-display text-[1.75rem] font-bold text-safe leading-none">38</span>
    <span class="text-xs text-faint">ใหม่เดือนนี้</span>
  </div>
  <div class="bg-card border border-line/10 rounded-xl p-4 flex flex-col gap-1">
    <span class="font-display text-[1.75rem] font-bold text-danger leading-none">5</span>
    <span class="text-xs text-faint">รอดำเนินการ</span>
  </div>
</div>
```

---

## Buttons

```html
<!-- Ghost button (default) -->
<button class="inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-line/15 rounded-lg bg-card text-ink text-[0.82rem] font-semibold hover:bg-surface transition-colors cursor-pointer">
  ยกเลิก
</button>

<!-- Primary blue button -->
<button class="inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-accent rounded-lg bg-accent text-white text-[0.82rem] font-semibold hover:bg-blue-700 transition-colors cursor-pointer">
  บันทึก
</button>

<!-- Danger button -->
<button class="inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-danger/25 rounded-lg bg-card text-danger text-[0.82rem] font-semibold hover:bg-danger/5 transition-colors cursor-pointer">
  ลบ
</button>

<!-- Disabled + spinner -->
<button disabled class="inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-accent rounded-lg bg-accent text-white text-[0.82rem] font-semibold opacity-60 cursor-not-allowed">
  <span class="spin spin-white" style="width:13px;height:13px;"></span>
  กำลังบันทึก...
</button>

<!-- Small button (for table actions) -->
<button class="inline-flex items-center px-2.5 py-1 border border-line/15 rounded-md bg-card text-ink text-[0.75rem] font-semibold hover:bg-surface transition-colors cursor-pointer">
  แก้ไข
</button>
```

---

## Chips

```html
<!-- Neutral chip -->
<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[0.7rem] font-semibold bg-surface border border-line/10 text-muted">
  ทั้งหมด
</span>

<!-- Accent chip (blue count) -->
<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[0.7rem] font-semibold bg-accent/10 border border-accent/20 text-accent font-display tabular-nums">
  12
</span>

<!-- Green chip -->
<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[0.7rem] font-semibold bg-safe/8 border border-safe/20 text-[#0f766e]">
  สำเร็จ
</span>
```

---

## Eyebrow

```html
<p class="text-[0.6rem] font-bold uppercase tracking-[0.08em] text-faint">
  บัญชีของฉัน · สมาชิก
</p>
<h1 class="font-display text-[1.35rem] font-bold text-ink mt-1">แพ็กเกจสมาชิก</h1>
```

---

## Iconbox

```html
<!-- Default (ink) -->
<div class="w-9 h-9 border border-line/15 rounded-lg bg-surface text-ink grid place-items-center flex-shrink-0">
  <svg width="18" height="18" ...>...</svg>
</div>

<!-- Accent (blue) -->
<div class="w-9 h-9 border border-accent/28 rounded-lg bg-accent/6 text-accent grid place-items-center flex-shrink-0">
  <svg width="18" height="18" ...>...</svg>
</div>

<!-- Green -->
<div class="w-9 h-9 border border-safe/28 rounded-lg bg-safe/6 text-safe grid place-items-center flex-shrink-0">
  <svg width="18" height="18" ...>...</svg>
</div>
```

---

## Zone Badges (Status)

```html
<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.7rem] font-semibold border bg-safe/8 border-safe/22 text-[#0f766e]">สำเร็จ</span>
<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.7rem] font-semibold border bg-caution/10 border-caution/25 text-[#92660b]">รอดำเนินการ</span>
<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.7rem] font-semibold border bg-danger/8 border-danger/22 text-[#b1453a]">ล้มเหลว</span>
<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.7rem] font-semibold border bg-surface border-line/12 text-muted">ปิดใช้งาน</span>
<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.7rem] font-semibold border bg-accent/8 border-accent/20 text-accent">ข้อมูล</span>
```

| Variant | Tailwind classes |
|---------|-----------------|
| Safe (green) | `bg-safe/8 border-safe/22 text-[#0f766e]` |
| Caution (yellow) | `bg-caution/10 border-caution/25 text-[#92660b]` |
| Danger (red) | `bg-danger/8 border-danger/22 text-[#b1453a]` |
| Mute (gray) | `bg-surface border-line/12 text-muted` |
| Info (blue) | `bg-accent/8 border-accent/20 text-accent` |

---

## Tier Badges (T0–T3)

```html
<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[0.68rem] font-bold font-display tracking-[0.02em] bg-safe/10 text-[#0f766e]">T0 ทำเลย</span>
<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[0.68rem] font-bold font-display tracking-[0.02em] bg-safe/10 text-[#0f766e]">T1 บันทึก</span>
<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[0.68rem] font-bold font-display tracking-[0.02em] bg-caution/12 text-[#92660b]">T2 ส่งออก</span>
<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[0.68rem] font-bold font-display tracking-[0.02em] bg-danger/10 text-[#b1453a]">T3 จ่ายเงิน</span>
```

---

## Form Fields

```html
<div class="flex flex-col gap-1.5">
  <label class="text-[0.75rem] font-semibold text-muted">
    ชื่อ-นามสกุล <span class="text-danger">*</span>
  </label>
  <input
    type="text"
    placeholder="ระบุชื่อ-นามสกุล"
    class="w-full px-3 py-2 border border-line/15 rounded-lg bg-card text-ink text-[0.82rem] outline-none focus:border-accent/60 focus:ring-2 focus:ring-accent/10 placeholder:text-faint transition"
  />
</div>

<!-- Read-only field -->
<div class="flex flex-col gap-1.5">
  <label class="text-[0.75rem] font-semibold text-muted">คำนวณโดยระบบ</label>
  <div class="w-full px-3 py-2 border border-line/15 rounded-lg bg-surface text-muted text-[0.82rem] select-none">ค่าที่ระบบคำนวณ</div>
</div>

<!-- Textarea -->
<textarea
  rows="4"
  placeholder="รายละเอียด..."
  class="w-full px-3 py-2 border border-line/15 rounded-lg bg-card text-ink text-[0.82rem] outline-none focus:border-accent/60 focus:ring-2 focus:ring-accent/10 placeholder:text-faint transition resize-y"
></textarea>
```

---

## Callout Blocks (Alert)

```html
<!-- Info -->
<div class="flex items-start gap-2.5 px-4 py-3 rounded-lg text-[0.82rem] border bg-accent/5 border-accent/18 text-muted">
  <svg width="14" height="14" class="flex-shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
  </svg>
  <span>ปกติสั่งผ่านแชตได้ ไม่ต้องมาที่หน้านี้</span>
</div>

<!-- Success -->
<div class="flex items-start gap-2.5 px-4 py-3 rounded-lg text-[0.82rem] border bg-safe/6 border-safe/22 text-[#0f766e]">
  <svg width="14" height="14" class="flex-shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
  <span>บันทึกสำเร็จแล้ว</span>
</div>

<!-- Warning -->
<div class="flex items-start gap-2.5 px-4 py-3 rounded-lg text-[0.82rem] border bg-caution/8 border-caution/25 text-[#92660b]">
  <svg width="14" height="14" class="flex-shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
  </svg>
  <span>กรุณาตรวจสอบข้อมูลก่อนส่ง</span>
</div>

<!-- Error -->
<div class="flex items-start gap-2.5 px-4 py-3 rounded-lg text-[0.82rem] border bg-danger/6 border-danger/22 text-[#b1453a]">
  <svg width="14" height="14" class="flex-shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
  </svg>
  <span>เกิดข้อผิดพลาด กรุณาลองใหม่</span>
</div>
```

---

## Table

```html
<div class="overflow-x-auto">
  <table class="w-full border-collapse text-[0.82rem]">
    <thead>
      <tr>
        <th class="text-left px-3.5 py-2.5 text-[0.68rem] font-bold uppercase tracking-[0.06em] text-faint border-b border-line/10 whitespace-nowrap">ชื่อ</th>
        <th class="text-left px-3.5 py-2.5 text-[0.68rem] font-bold uppercase tracking-[0.06em] text-faint border-b border-line/10">สถานะ</th>
        <th class="text-left px-3.5 py-2.5 text-[0.68rem] font-bold uppercase tracking-[0.06em] text-faint border-b border-line/10"></th>
      </tr>
    </thead>
    <tbody>
      <tr class="hover:bg-surface transition-colors">
        <td class="px-3.5 py-2.5 border-b border-line/7 text-ink align-middle">สมชาย ใจดี</td>
        <td class="px-3.5 py-2.5 border-b border-line/7 align-middle">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[0.7rem] font-semibold border bg-safe/8 border-safe/22 text-[#0f766e]">สำเร็จ</span>
        </td>
        <td class="px-3.5 py-2.5 border-b border-line/7 align-middle">
          <button class="inline-flex items-center px-2.5 py-1 border border-line/15 rounded-md bg-card text-ink text-[0.75rem] font-semibold hover:bg-surface transition-colors">แก้ไข</button>
        </td>
      </tr>
    </tbody>
  </table>
</div>
```

---

## Avatar

```html
<!-- Initials -->
<div class="w-8 h-8 rounded-full bg-surface border border-line/12 text-muted text-[0.65rem] font-bold font-display grid place-items-center flex-shrink-0 uppercase">
  สช
</div>

<!-- Accent tint -->
<div class="w-8 h-8 rounded-full bg-accent/10 border border-line/12 text-accent text-[0.65rem] font-bold font-display grid place-items-center flex-shrink-0 uppercase">
  AN
</div>
```

---

## Toast

```html
<!-- Success toast (with left accent border) -->
<div class="flex items-center gap-2 px-3.5 py-2.5 rounded-xl text-[0.815rem] border border-l-[3px] bg-card shadow-md
            bg-[rgb(16_185_129/0.05)] border-[rgb(16_185_129/0.28)] border-l-[#10b981] text-[#0f766e]
            min-w-[220px] max-w-[360px]"
     style="animation: slideIn 0.2s ease;">
  <div class="w-[18px] h-[18px] rounded-full grid place-items-center flex-shrink-0 bg-[#10b981] text-white">
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
  </div>
  <span>บันทึกสำเร็จแล้ว</span>
</div>
```

> Note: `slideIn` animation is defined in custom CSS (see SKILL.md). Toast positioning uses `fixed bottom-... right-4 z-[9999]`.

---

## Spinner

```html
<!-- Use custom .spin class (defined in SKILL.md <style> block) -->
<!-- Reason: 0.7s timing is snappier than Tailwind's animate-spin (1s) -->

<!-- Muted spinner -->
<span class="spin"></span>

<!-- White spinner (inside primary button) -->
<span class="spin spin-white" style="width:13px;height:13px;"></span>

<!-- If you want to use Tailwind's built-in spinner instead: -->
<span class="inline-block w-4 h-4 border-2 border-line/20 border-t-accent rounded-full animate-spin"></span>
```

---

## Hairline Border Utilities

```html
<!-- Tailwind equivalents for hair-* -->
<div class="border border-line/10">All 4 sides</div>
<div class="border-t border-line/10">Top only</div>
<div class="border-b border-line/10">Bottom only</div>
<div class="border-r border-line/10">Right only</div>
```

---

## Mark (Inline Highlight)

```html
<p>สถานะ: <span class="bg-accent/8 text-accent px-1.5 py-0.5 rounded font-semibold text-[0.875em]">อนุมัติแล้ว</span></p>
```
