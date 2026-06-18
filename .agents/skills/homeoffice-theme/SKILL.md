---
name: homeoffice-theme
description: >
  Build HTML pages and UI components in HomeOffice Design System style.
  Flat, white, hairline-border SaaS. Full Thai font support (Bai Jamjuree + Anuphan).
  Use for any request involving HomeOffice UI, cf-* classes, or Thai-language SaaS pages.
triggers:
  - homeoffice
  - cf-card
  - cf-btn
  - cf-stat
  - hairline
  - Bai Jamjuree
  - Anuphan
  - ระบบหลังบ้าน
version: 2.0.0
---

# HomeOffice Design System — Skill Entry Point

> **How to use this skill:**
> This file is the entry point. For implementation, **always read the appropriate ref/ files** before writing any code:
>
> | Task | Read |
> |------|------|
> | CSS tokens, colors, shadows | `ref/tokens.md` |
> | Component HTML (cf-* classes) | `ref/components.md` |
> | Page layout, sidebar, header, grids | `ref/layouts.md` |
> | Tier system, zones, page patterns | `ref/patterns.md` |
>
> For a new full page: read **all four** ref files before writing a line of HTML.

---

## Design Principles

HomeOffice is a **flat, white, hairline-border** SaaS design system for Thai business apps.

- **White is the canvas.** No gradients, no card shadows by default. Separation via hairline borders (`1px solid rgb(var(--c-line) / 0.10)`).
- **Ink is always dark navy** `rgb(26 32 50)`, never pure black.
- **Accent is a single blue** `rgb(37 99 235)` — use sparingly for primary actions only.
- **Typography is bilingual**: Bai Jamjuree for display/headings/numbers, Anuphan for body text. Both support Thai.
- **Icons**: Lucide SVG only, `stroke-width="2"`, no emoji as UI elements.
- **Mobile-first**: base 390px → `md` 768px → `lg` 1024px.

---

## Quick Start: Minimal Page Shell

```html
<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Page Title — HomeOffice</title>
  <!-- Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Bai+Jamjuree:wght@400;500;600;700&family=Anuphan:wght@300;400;500;600;700&display=swap" rel="stylesheet" />
  <!-- Tokens (paste from ref/tokens.md) -->
  <style>/* tokens go here */</style>
</head>
<body>
  <div class="app-root">
    <!-- AppSidebar (240px on lg+) -->
    <aside class="sidebar hair-r">...</aside>

    <!-- Right column -->
    <div class="app-column">
      <header class="app-header hair-b">...</header>
      <main class="ho-main">
        <!-- Page eyebrow + heading -->
        <div class="page-head">
          <p class="cf-eyebrow">หมวดหมู่ · หน้าย่อย</p>
          <h1 class="font-display" style="font-size:1.35rem;font-weight:700">ชื่อหน้า</h1>
          <p style="color:rgb(var(--c-muted));font-size:0.875rem">คำอธิบายสั้นๆ</p>
        </div>

        <!-- Stat row -->
        <div class="stat-row">
          <div class="cf-stat">...</div>
          <div class="cf-stat">...</div>
          <div class="cf-stat">...</div>
        </div>

        <!-- Main card content -->
        <div class="cf-card">...</div>
      </main>
    </div>
  </div>
</body>
</html>
```

---

## File Reference Index

```
homeoffice-theme/
├── SKILL.md          ← You are here (entry point + quick start)
└── ref/
    ├── tokens.md     ← CSS custom properties, colors, shadows, layout vars
    ├── components.md ← All cf-* component classes with full HTML examples
    ├── layouts.md    ← Sidebar, header, main grid, sticky/fixed patterns
    └── patterns.md   ← Tier system, zone badges, page eyebrows, module taxonomy
```

**Read order for a new page build:**
1. `ref/tokens.md` — paste token block into `<style>`
2. `ref/layouts.md` — pick layout template
3. `ref/components.md` — pick components for the page content
4. `ref/patterns.md` — apply tier/zone/eyebrow conventions

---

## Core Rules (Never Violate)

1. **Colors always via CSS variables** — `rgb(var(--c-ink))` not `#1a2032`
2. **Hairline borders** — `1px solid rgb(var(--c-line) / 0.10)` not `border: 1px solid #ddd`
3. **No box-shadow on cards by default** — use `var(--shadow-md)` only for floating elements (modals, dropdowns, toasts)
4. **Lucide icons only** — inline SVG, `stroke-width="2"`, no emoji in UI
5. **Thai text uses Anuphan** (body) — display/headings/numbers use Bai Jamjuree
6. **Touch targets ≥ 44px** on mobile
7. **`cf-btn-primary` for one action per view** — don't use it for secondary actions
