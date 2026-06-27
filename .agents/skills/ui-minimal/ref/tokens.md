# UI-Minimal — Tokens & Tailwind Config Reference

---

## Tailwind Config (paste into `<script>` after CDN)

```js
tailwind.config = {
  theme: {
    extend: {
      colors: {
        // Map to CSS vars so opacity modifiers work: bg-accent/10, border-line/10, etc.
        ink:     'rgb(var(--c-ink)     / <alpha-value>)',
        muted:   'rgb(var(--c-muted)   / <alpha-value>)',
        faint:   'rgb(var(--c-faint)   / <alpha-value>)',
        accent:  'rgb(var(--c-accent)  / <alpha-value>)',
        card:    'rgb(var(--c-card)    / <alpha-value>)',
        surface: 'rgb(var(--c-surface) / <alpha-value>)',
        page:    'rgb(var(--c-page)    / <alpha-value>)',
        safe:    'rgb(var(--c-safe)    / <alpha-value>)',
        caution: 'rgb(var(--c-caution) / <alpha-value>)',
        danger:  'rgb(var(--c-danger)  / <alpha-value>)',
        line:    'rgb(var(--c-line)    / <alpha-value>)',
      },
      fontFamily: {
        display: ['Bai Jamjuree', 'sans-serif'],
        body: ['Anuphan', 'system-ui', 'sans-serif'],
      },
    }
  }
}
```

---

## CSS Variables (paste into `<style>` in `<head>`)

```css
:root {
  --c-ink:     26 32 50;      /* #1a2032 — primary text, dark navy */
  --c-muted:   74 80 99;      /* #4a5063 — secondary text */
  --c-faint:  140 146 165;    /* #8c92a5 — placeholders, labels */
  --c-line:    26 32 50;      /* same as ink — used for borders with low alpha */
  --c-accent:  37 99 235;     /* #2563eb — primary blue */
  --c-card:   255 255 255;    /* #ffffff */
  --c-surface: 248 249 251;   /* #f8f9fb — subtle background */
  --c-page:   246 247 250;    /* #f6f7fa — page background */
  --c-safe:    16 185 129;    /* #10b981 — success / green */
  --c-caution: 234 179 8;     /* #eab308 — warning / yellow */
  --c-danger:  239 68 68;     /* #ef4444 — error / red */
  --header-h:  52px;
  --sidebar-w: 0px;           /* 240px at lg+ — set below */
  --savebar-h: 64px;
}
@media (min-width: 1024px) { :root { --sidebar-w: 240px; } }
```

---

## Color Quick Reference

| Tailwind class | Value | Use |
|----------------|-------|-----|
| `text-ink` / `bg-ink` | `#1a2032` | Primary text, headings |
| `text-muted` | `#4a5063` | Secondary text |
| `text-faint` | `#8c92a5` | Labels, placeholders |
| `text-accent` / `bg-accent` | `#2563eb` | Primary CTA, links |
| `bg-card` | `#ffffff` | Card surfaces |
| `bg-surface` | `#f8f9fb` | Subtle background, inputs |
| `bg-page` | `#f6f7fa` | Page background |
| `text-safe` / `bg-safe` | `#10b981` | Success |
| `text-caution` / `bg-caution` | `#eab308` | Warning |
| `text-danger` / `bg-danger` | `#ef4444` | Error |
| `border-line/10` | `rgba(26,32,50,0.10)` | Standard hairline border |
| `border-line/7` | `rgba(26,32,50,0.07)` | Subtle row divider |
| `border-line/14` | `rgba(26,32,50,0.14)` | Button border |

### Opacity modifier pattern
```html
<!-- bg-{color}/{opacity} -->
<div class="bg-accent/10">   <!-- rgb(37 99 235 / 0.10) -->
<div class="border border-line/10">  <!-- hairline -->
<div class="text-safe">      <!-- solid safe color -->
<div class="bg-safe/8">      <!-- 8% safe tint -->
```

---

## Typography

| Class | Font | Size | Weight | Use |
|-------|------|------|--------|-----|
| `font-display` | Bai Jamjuree | — | — | Headings, numbers |
| `font-body` | Anuphan | — | — | Body (already default) |
| `text-[1.35rem] font-display font-bold` | Bai Jamjuree | 1.35rem | 700 | Page title (h1) |
| `text-[0.9rem] font-semibold` | Anuphan | 0.9rem | 600 | Section heading (h2) |
| `text-[0.6rem] font-bold uppercase tracking-[0.08em] text-faint` | — | 0.6rem | 700 | Eyebrow label |
| `text-[0.875rem]` | Anuphan | 0.875rem | 400 | Body text |
| `text-[0.82rem]` | Anuphan | 0.82rem | — | Small body, buttons |
| `font-display text-[1.75rem] font-bold tabular-nums` | Bai Jamjuree | 1.75rem | 700 | Stat number |

---

## What Tailwind Replaces vs. What Needs Custom CSS

### Tailwind handles ✅
- All spacing, padding, margin
- All colors with opacity modifiers
- Flex, grid, gap layouts
- Border radius, border width
- Text size, weight, family
- Hover, focus states
- Shadow utilities (`shadow-md`, `shadow-lg`)
- Transition (`transition-colors`, `transition-all`)
- Position utilities (sticky, fixed, absolute)
- Responsive prefixes (`md:`, `lg:`)

### Still needs custom CSS ❌
| What | Why |
|------|-----|
| `@keyframes spin` | Custom 0.7s timing (Tailwind's `animate-spin` is 1s) |
| `@keyframes slideIn` / `fadeUp` | Custom animations not in Tailwind |
| Sidebar `cubic-bezier` transition | Tailwind transition doesn't support custom easing in CDN mode |
| `scrollbar-width: thin` | No Tailwind equivalent |
| `env(safe-area-inset-bottom)` | No Tailwind equivalent |
| `backdrop-filter: blur(12px)` | Use `backdrop-blur-md` (Tailwind has this ✅) |
