# HomeOffice — CSS Tokens Reference

Paste this entire block into your page's `<style>` tag or root CSS file.

---

## Full Token Block

```css
/* ─── Fonts ─── */
/* Import in <head>: */
/* <link href="https://fonts.googleapis.com/css2?family=Bai+Jamjuree:wght@400;500;600;700&family=Anuphan:wght@300;400;500;600;700&display=swap" rel="stylesheet" /> */

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  /* ── Typography ── */
  font-family: 'Anuphan', 'Bai Jamjuree', system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;

  /* ── Color channels (RGB, no parentheses — used with rgb(var(--x) / alpha)) ── */
  --c-ink:     26 32 50;      /* #1a2032 — primary text, dark navy */
  --c-muted:   74 80 99;      /* #4a5063 — secondary text */
  --c-faint:  140 146 165;    /* #8c92a5 — placeholders, labels */
  --c-line:    26 32 50;      /* same as ink, used for borders with low alpha */
  --c-accent:  37 99 235;     /* #2563eb — primary blue */
  --c-card:   255 255 255;    /* #ffffff — card/surface background */
  --c-surface: 248 249 251;   /* #f8f9fb — subtle background tint */
  --c-page:   246 247 250;    /* #f6f7fa — page background */

  /* ── Semantic status colors (used in cf-zone variants) ── */
  --c-safe:    16 185 129;    /* #10b981 — green / success */
  --c-caution: 234 179 8;     /* #eab308 — yellow / warning */
  --c-danger:  239 68 68;     /* #ef4444 — red / error */
  --c-info:    37 99 235;     /* same as accent — blue / info */
  --c-free:    16 185 129;    /* green — free / active */

  /* ── Shadows ── */
  --shadow-sm: 0 1px 3px rgb(26 32 50 / 0.06), 0 1px 2px rgb(26 32 50 / 0.04);
  --shadow-md: 0 4px 16px rgb(26 32 50 / 0.08), 0 2px 6px rgb(26 32 50 / 0.05);
  --shadow-lg: 0 8px 32px rgb(26 32 50 / 0.10), 0 4px 12px rgb(26 32 50 / 0.07);

  /* ── Layout dimensions ── */
  --header-h:  52px;    /* sticky header height */
  --sidebar-w: 0px;     /* 240px at lg+ — set by media query */
  --savebar-h: 64px;    /* fixed bottom bar height */
  --radius:    0.75rem; /* standard card/button radius */
}

/* Desktop: sidebar appears */
@media (min-width: 1024px) {
  :root { --sidebar-w: 240px; }
}

/* ── Page background ── */
body {
  background: rgb(var(--c-page));
  color: rgb(var(--c-ink));
}
```

---

## Color Quick Reference

| Token | Value | Use |
|-------|-------|-----|
| `--c-ink` | `26 32 50` (#1a2032) | Primary text, headings |
| `--c-muted` | `74 80 99` (#4a5063) | Secondary text, subheadings |
| `--c-faint` | `140 146 165` (#8c92a5) | Labels, placeholders, eyebrows |
| `--c-line` | `26 32 50` | Borders at low alpha (0.08–0.12) |
| `--c-accent` | `37 99 235` (#2563eb) | Primary CTA, links, active state |
| `--c-card` | `255 255 255` | Card / panel backgrounds |
| `--c-surface` | `248 249 251` | Subtle surface, input backgrounds |
| `--c-page` | `246 247 250` | Page background |
| `--c-safe` | `16 185 129` (#10b981) | Success / green |
| `--c-caution` | `234 179 8` (#eab308) | Warning / yellow |
| `--c-danger` | `239 68 68` (#ef4444) | Error / red |

### Alpha Usage Pattern

All colors use the **RGB channel format** — combine with `rgb(var(--x) / alpha)`:

```css
/* ✅ Correct */
color: rgb(var(--c-ink));                    /* solid */
background: rgb(var(--c-accent) / 0.08);    /* 8% tint */
border: 1px solid rgb(var(--c-line) / 0.10); /* hairline */

/* ❌ Wrong — never hardcode hex */
color: #1a2032;
border: 1px solid #e5e7eb;
```

---

## Typography Tokens

```css
/* Display / headings / numbers → Bai Jamjuree */
.font-display { font-family: 'Bai Jamjuree', sans-serif; }

/* Tabular numbers (for stats, counters) → Bai Jamjuree */
.num {
  font-family: 'Bai Jamjuree', sans-serif;
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
}

/* Body (default) → Anuphan */
/* Already set on :root — no extra class needed */
```

### Type Scale

| Class / Element | Size | Weight | Font | Use |
|-----------------|------|--------|------|-----|
| `h1` + `.font-display` | 1.3–1.5rem | 700 | Bai Jamjuree | Page title |
| `h2` | 1.05rem | 600 | Bai Jamjuree | Section heading |
| `.cf-eyebrow` | 0.6rem | 700 | Anuphan | Category label above heading |
| Body default | 0.875rem | 400 | Anuphan | Body text |
| `.num` stat | 1.5–2rem | 700 | Bai Jamjuree | Large numbers in stats |
| Input / label | 0.82rem | 500 | Anuphan | Form fields |
| `cf-btn` | 0.82rem | 600 | Anuphan | Button text |

---

## Layout Variables

```css
--header-h:  52px;   /* Use on header height + sticky top offset calc */
--sidebar-w: 240px;  /* Desktop only — mobile = 0px. Fixed bars offset by this. */
--savebar-h: 64px;   /* Fixed bottom bar. Main padding-bottom uses this. */

/* Example usages: */
.save-bar { left: var(--sidebar-w, 240px); }          /* offset from sidebar */
.toast    { bottom: calc(var(--savebar-h, 64px) + 1rem); }
.main     { padding-bottom: calc(var(--savebar-h, 64px) + 0.5rem); }
.detail-panel { top: calc(var(--header-h, 52px) + 1rem); }
```

---

## Shadow Scale

```css
/* sm — for subtle card lift (rarely used by default) */
box-shadow: var(--shadow-sm);   /* 0 1px 3px / 0 1px 2px */

/* md — dropdowns, modals, toasts, mobile sidebar drawer */
box-shadow: var(--shadow-md);   /* 0 4px 16px / 0 2px 6px */

/* lg — large modals, sheet overlays */
box-shadow: var(--shadow-lg);   /* 0 8px 32px / 0 4px 12px */
```

> **Default cards have no box-shadow.** Use hairline borders to separate cards from background. Reserve `--shadow-md` for elements that float above the layout (dropdowns, toasts, mobile drawers).
