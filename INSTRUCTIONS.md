# Project Instructions

## Directory Structure

```
vas/
├── src/
│   ├── server.py                        # Flask entry point — routes, SSE, context processors
│   ├── cli.py                           # CLI entry point (vas command)
│   │
│   ├── core/                            # Infrastructure กลาง (ไม่ depend on อะไรใน project)
│   │   ├── config.py                    # APP_VERSION, InstallConfig, DEFAULT_CONFIG
│   │   ├── database.py                  # SQLite wrapper (WAL mode, thread-local connections)
│   │   └── runner.py                    # CommandRunner — shell execution wrapper
│   │
│   ├── features/                        # Business logic แยกตาม domain
│   │   ├── display/
│   │   │   └── display.py               # DisplayConfigurator, xrandr, xinput, Xorg config
│   │   ├── wireguard/
│   │   │   └── manager.py               # WireGuardManager, config, history
│   │   ├── mqtt/
│   │   │   └── client.py                # MqttClient, publish_qr_scan
│   │   ├── qr/
│   │   │   ├── reader.py                # QR reader (evdev/hidraw), start/stop/get_reader
│   │   │   └── registry.py              # Device catalog, integrations, install/uninstall
│   │   └── packages/
│   │       ├── settings.py              # Package manifest, install queue, status checker
│   │       └── installers.py            # PhaseOneInstaller, apt/npm/docker install steps
│   │
│   ├── system/                          # OS/hardware layer
│   │   ├── audit.py                     # System log snapshots (create/list/read)
│   │   ├── clock.py                     # SystemClockPreflight, NTP sync check
│   │   ├── info.py                      # collect_os_info, print_os_info
│   │   ├── monitor.py                   # CPU/memory/disk/network metrics (SSE)
│   │   ├── status.py                    # collect_status, VpnStatus, QrReaderStatus, etc.
│   │   └── utils.py                     # require_linux, require_root, detect_ubuntu_codename
│   │
│   ├── services/                        # Process/daemon management
│   │   ├── server_service.py            # SystemD service install/start/stop for vas server
│   │   ├── reset.py                     # LifecycleManager, reset/uninstall components
│   │   └── updater.py                   # SelfUpdater — GitHub release download & replace
│   │
│   ├── mcp/                             # MCP server layer
│   │   ├── server.py                    # FastMCP app entry point
│   │   ├── service.py                   # McpServiceManager, systemd integration
│   │   └── tools/                       # MCP tool modules (mounted into FastMCP)
│   │       ├── display.py
│   │       ├── docker.py
│   │       ├── logs.py
│   │       ├── network.py
│   │       └── system.py
│   │
│   └── web/                             # Flask static assets & Jinja2 templates
│       ├── static/
│       │   ├── js/app.js
│       │   ├── app.css
│       │   └── homeoffice.css
│       └── templates/
│           ├── base.html                # Full layout (sidebar, header, SPA router)
│           ├── base_partial.html        # Partial layout for SPA fetch (X-VAS-Partial: 1)
│           ├── dashboard.html
│           ├── display.html
│           ├── monitor.html
│           ├── settings.html
│           └── …
│
├── public/
│   └── images/logo/                     # Package logos (wayland-logo.png, x11-logo.png, …)
├── INSTRUCTIONS.md                      # ← this file
├── CLAUDE.md                            # Claude project context
└── AGENTS.md                            # Agent instructions
```

## Import Convention

`PYTHONPATH=src` — ทุก import ใช้ path แบบ absolute จาก `src/`:

```python
from core.runner import CommandRunner
from core.config import InstallConfig
from core.database import init_db, log_audit

from features.display.display import DisplayConfigurator
from features.wireguard.manager import WireGuardManager
from features.mqtt.client import start_mqtt
from features.qr.reader import get_reader, start_reader
from features.qr.registry import load_installed_devices
from features.packages.settings import get_package_status
from features.packages.installers import PhaseOneInstaller

from system.status import collect_status, VpnStatus
from system.audit import create_system_log_snapshot
from system.clock import SystemClockPreflight
from system.info import collect_os_info
from system.utils import require_linux, require_root
from system.monitor import ...   # SSE metrics

from services.server_service import ServerServiceManager
from services.reset import LifecycleManager
from services.updater import SelfUpdater

from mcp.service import McpServiceManager
```

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `VAS_HOST` | `0.0.0.0` | Flask bind host |
| `VAS_PORT` | `8080` | Flask bind port |
| `VAS_DB` | `~/.config/vas/vas.db` | SQLite database path |
| `VAS_DEBUG` | `false` | Enable Flask debug mode |

## Setup

```bash
pip install -r requirements.txt
python -m src.server
# → http://localhost:8080
```

## Page Structure

Every content page is divided into **3 sections** stacked vertically with `gap-4`:

```
┌─────────────────────────────────────────────────┐
│  1. PAGE HEADER                                  │
│     Eyebrow · h1 · subtitle (static, never       │
│     changes when switching sub-tabs)             │
├─────────────────────────────────────────────────┤
│  2. SECTION MENU  (optional)                     │
│     Horizontal tab pills — shown only when page  │
│     has sub-sections; omit on single-section     │
│     pages                                        │
├─────────────────────────────────────────────────┤
│  3. CONTENT SECTION                              │
│     Active tab panel. May contain its own        │
│     nested sub-sections (cards, accordions, etc) │
└─────────────────────────────────────────────────┘
```

### 1 · Page Header

Static — does **not** change when the user switches sub-tabs.

```html
<div class="border-b border-line/10 pb-4">
  <p class="text-[0.6rem] font-bold uppercase tracking-[0.08em] text-faint">
    VAS · หน้าปัจจุบัน
  </p>
  <h1 class="font-display text-[1.35rem] font-bold text-ink mt-1.5">ชื่อหน้า</h1>
  <p class="text-[0.82rem] text-muted mt-1">คำอธิบายสั้นๆ</p>
</div>
```

### 2 · Section Menu (Tab Nav)

Horizontal pill row; omit entirely on pages with only one section.

```html
<nav class="bg-card border border-line/10 rounded-xl overflow-hidden">
  <div class="flex flex-row gap-0.5 px-2 py-2 overflow-x-auto">
    <button data-tab="tab-id"
            class="tab-btn px-3 py-2 rounded-lg text-[0.8rem] font-medium whitespace-nowrap
                   transition-colors bg-accent/8 text-accent font-semibold">
      <iconify-icon icon="lucide:…" width="13" height="13"></iconify-icon>
      Label
    </button>
    <!-- more tab buttons -->
  </div>
</nav>
```

**Rules:**
- Tab buttons use `gap-0.5` between pills (micro-spacing exception)
- Active pill: `bg-accent/8 text-accent font-semibold`
- Inactive pill: `text-muted hover:bg-surface hover:text-ink`
- Always `overflow-x-auto` for mobile scroll support

### 3 · Content Section

Wraps all tab panels. Only the active panel is visible.

```html
<div>
  <div id="tab-foo" class="tab-panel is-active flex flex-col gap-4">
    <!-- cards, forms, etc — nested as needed -->
  </div>
  <div id="tab-bar" class="tab-panel flex flex-col gap-4">
    <!-- … -->
  </div>
</div>
```

**Critical CSS** (in `{% block extra_styles %}` or `<style>` tag):

```css
.tab-panel { display: none; }
.tab-panel.is-active {
  display: flex;
  flex-direction: column;
  /* do NOT use display:block — gap-* has no effect on block containers */
}
```

**Content sub-sections** inside a tab panel use the same card pattern:

```html
<div class="bg-card border border-line/10 rounded-xl px-4 py-4 flex flex-col gap-4">
  <h2 class="text-[0.88rem] font-semibold text-ink">Section Title</h2>
  <!-- content -->
</div>
```

---

## Shell Layout Convention

### Sidebar (`base.html`)

| Element | Class / value | Notes |
|---|---|---|
| Sidebar width | `w-60` (240 px) | Fixed; `sticky lg:h-screen` |
| **Brand header** | `h-[52px]` exact | Must match nav bar height — use `flex items-center` not padding |
| Brand icon | `w-7 h-7 rounded-lg bg-accent` | Smaller than `-9` to fit 52px |
| Nav section label | `text-[0.56rem] uppercase tracking-[0.1em] text-faint` | `pt-3 pb-1` between sections |
| Nav link | `px-2.5 py-1.5 rounded-lg text-[0.8rem]` | Compact; `py-1.5` not `py-2` |
| **Footer** | version strip only | `VAS v0.1 · online` with green dot; no user info |

### Top Nav Bar (`base.html`)

| Element | Class / value | Notes |
|---|---|---|
| Background | `bg-white` | Pure white — no opacity/blur |
| Height | `h-[52px]` | Matches sidebar brand header exactly |
| Page title | `font-display text-[0.95rem] font-bold` | Injected by SPA router |
| **Account pill** | Right side, always visible | Avatar initials + machine name + chevron |

Account pill structure:

```html
<div class="flex items-center gap-2 px-2.5 py-1.5 rounded-lg
            hover:bg-surface transition-colors cursor-pointer
            border border-line/10">
  <div class="w-5 h-5 rounded-full bg-accent/10 text-accent
              text-[0.58rem] font-bold flex items-center justify-center">
    VM
  </div>
  <span class="text-[0.78rem] font-semibold text-ink hidden sm:block">
    {{ machine_name or "VAS" }}
  </span>
  <iconify-icon icon="lucide:chevron-down" width="12" height="12"
                class="text-faint hidden sm:block"></iconify-icon>
</div>
```

---

## UI Spacing Convention

**All layout-level spacing uses the `-4` scale (16 px).** This applies to:

- Gaps between sections/cards: `gap-4`
- Card internal padding: `px-4 py-4`
- Card header padding: `px-4 py-4`
- Tab panel gap: `flex flex-col gap-4`
- Form field groups: `gap-4`

**Micro-spacing exceptions (do not normalise to `-4`):**

| Use case | Class | px |
|---|---|---|
| Inline icon + text | `gap-2` | 8 |
| Form label → input | `gap-1.5` | 6 |
| Tab pill row | `gap-0.5` | 2 |
| List items (tight) | `gap-1` | 4 |
| Button internal | `px-3 py-2` or `px-4 py-2.5` | — |
| Form control | `px-3 py-2` | — |
| Sidebar nav link | `px-2.5 py-1.5` | sidebar-specific |
| Sidebar section gap | `pt-3 pb-1` per section | sidebar-specific |

## SPA Navigation

All pages extend `base_template` (injected by Flask context processor):

```python
# server.py
@app.context_processor
def inject_spa_context():
    is_partial = request.headers.get("X-VAS-Partial") == "1"
    return {
        "is_partial": is_partial,
        "base_template": "base_partial.html" if is_partial else "base.html",
    }
```

Every template starts with:
```html
{% extends base_template %}
```

**Page cleanup** — pages with intervals or SSE must register cleanup:

```javascript
window.__vasCleanup = window.__vasCleanup || [];
window.__vasCleanup.push(function () {
    if (timer) { clearInterval(timer); timer = null; }
    if (evtSource) { evtSource.close(); evtSource = null; }
});
```

## Confirm Modal Convention

**ห้ามใช้ `window.confirm()` เด็ดขาด** — ให้ใช้ `showConfirm()` ทุกครั้งที่ต้องการ confirmation dialog (ลบ, reset, action ที่ย้อนกลับไม่ได้)

### วิธีใช้

```javascript
window.showConfirm({
  title:   "ลบ [ชื่อ item]?",          // หัวข้อ — ระบุสิ่งที่จะลบ
  body:    "ข้อมูลทั้งหมดจะถูกลบ ไม่สามารถยกเลิกได้",  // คำอธิบายผลกระทบ
  okLabel: "ลบ",                        // label ปุ่ม confirm (default: "ลบ")
  onOk: function () {
    // action จริง เช่น fetch DELETE
  }
});
```

### HTML ที่ต้องใส่ในทุกหน้าที่มีการลบ

วาง modal ก่อน `{% endblock %}` ของ `{% block content %}`:

```html
<!-- ── Confirm Modal ──────────────────────────────────────── -->
<div id="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
  <div id="confirm-backdrop" onclick="window._confirmModal && window._confirmModal.cancel()"></div>
  <div id="confirm-box">
    <div class="flex items-start gap-3 mb-4">
      <div class="w-9 h-9 rounded-lg bg-danger/8 border border-danger/15 grid place-items-center flex-shrink-0">
        <iconify-icon icon="lucide:trash-2" width="16" height="16" class="text-danger"></iconify-icon>
      </div>
      <div class="min-w-0">
        <h2 id="confirm-title" class="text-[0.95rem] font-semibold text-ink leading-snug"></h2>
        <p id="confirm-body" class="text-[0.78rem] text-muted mt-1 leading-relaxed"></p>
      </div>
    </div>
    <div class="flex items-center justify-end gap-2 pt-3 border-t border-line/10">
      <button id="confirm-cancel"
              class="inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-line/15 rounded-lg bg-card text-ink text-[0.82rem] font-semibold hover:bg-surface transition-colors"
              onclick="window._confirmModal && window._confirmModal.cancel()">
        ยกเลิก
      </button>
      <button id="confirm-ok"
              class="inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-danger/20 rounded-lg bg-danger text-white text-[0.82rem] font-semibold hover:bg-red-600 transition-colors">
        <iconify-icon icon="lucide:trash-2" width="13" height="13"></iconify-icon>
        ลบ
      </button>
    </div>
  </div>
</div>
```

CSS ที่ต้องใส่ใน `<style>` ของหน้า:

```css
#confirm-modal { display:none; position:fixed; inset:0; z-index:9999; align-items:center; justify-content:center; }
#confirm-modal.is-open { display:flex; }
#confirm-backdrop { position:absolute; inset:0; background:rgb(var(--c-ink)/0.35); backdrop-filter:blur(2px); }
#confirm-box { position:relative; background:rgb(var(--c-card)); border:1px solid rgb(var(--c-line)/0.12); border-radius:1rem; box-shadow:0 8px 32px rgb(0 0 0/0.12); width:100%; max-width:400px; margin:1rem; padding:1.5rem; animation:fadeUp 0.18s ease forwards; }
```

JS helper ที่ต้องใส่ใน `{% block extra_scripts %}`:

```javascript
window.showConfirm = function (opts) {
  var modal = document.getElementById("confirm-modal");
  var btnOk = document.getElementById("confirm-ok");
  var clone = btnOk.cloneNode(true);
  btnOk.parentNode.replaceChild(clone, clone);
  btnOk = document.getElementById("confirm-ok");

  document.getElementById("confirm-title").textContent = opts.title || "ยืนยันการลบ";
  document.getElementById("confirm-body").textContent  = opts.body  || "";
  if (opts.okLabel) btnOk.childNodes[1].textContent = " " + opts.okLabel;

  window._confirmModal = {
    cancel: function () { modal.classList.remove("is-open"); window._confirmModal = null; }
  };
  btnOk.onclick = function () {
    modal.classList.remove("is-open"); window._confirmModal = null;
    if (opts.onOk) opts.onOk();
  };
  modal.classList.add("is-open");
  document.getElementById("confirm-cancel").focus();
};

// Escape key
document.addEventListener("keydown", function (e) {
  if (e.key === "Escape" && window._confirmModal) window._confirmModal.cancel();
});
```

### กฎ
- ปุ่ม OK ของ delete modal ใช้สี `bg-danger text-white` เสมอ
- backdrop คลิกแล้วปิด modal ได้
- Escape key ปิด modal ได้
- ใส่ `role="dialog"` และ `aria-modal="true"` ทุกครั้ง

## Accordion Card Convention

ใช้สำหรับแสดงรายการ config files, history entries, หรือ expandable detail — pattern นี้เป็น standard ของ VAS

### โครงสร้าง HTML

```html
<div class="bg-card border border-line/10 rounded-xl overflow-hidden" id="cfg-card-{key}">

  <!-- ── Header (clickable to toggle) ── -->
  <button type="button" onclick="toggleCfg('{key}')"
          class="w-full flex items-start gap-4 px-4 py-4 text-left hover:bg-surface/50 transition-colors">
    <!-- Icon box -->
    <div class="w-9 h-9 rounded-lg bg-surface flex items-center justify-center flex-shrink-0 mt-0.5">
      <iconify-icon icon="lucide:file-text" width="16" height="16" class="text-muted"></iconify-icon>
    </div>
    <!-- Content -->
    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2 flex-wrap">
        <span class="font-semibold text-[0.88rem] text-ink font-display">Title</span>
        <span class="zone zone-safe">OK</span>          <!-- zone badge: zone-safe / zone-caution / zone-mute -->
      </div>
      <code class="text-[0.68rem] text-faint font-mono block mt-0.5 truncate">/path/to/file</code>
      <p class="text-[0.73rem] text-muted mt-1 leading-snug">คำอธิบายสั้นๆ</p>
      <div class="flex items-center gap-1 mt-1.5">
        <iconify-icon icon="lucide:check-circle" width="11" height="11" class="text-safe"></iconify-icon>
        <span class="text-[0.68rem] text-safe">สถานะ</span>
      </div>
    </div>
    <!-- Chevron -->
    <iconify-icon icon="lucide:chevron-down" width="15" height="15"
                  class="text-faint flex-shrink-0 mt-1 transition-transform" id="chevron-{key}"></iconify-icon>
  </button>

  <!-- ── Expanded body (hidden by default) ── -->
  <div id="cfg-viewer-{key}" class="hidden border-t border-line/10">
    <!-- toolbar strip -->
    <div class="flex items-center justify-between px-4 py-3 bg-surface/40">
      <span class="text-[0.72rem] font-semibold text-muted">ป้ายกำกับ</span>
      <button type="button" class="inline-flex items-center gap-1 px-2.5 py-1 border border-line/15
                                   rounded-md bg-card text-[0.72rem] font-semibold text-muted
                                   hover:text-ink hover:bg-surface transition-colors">
        <iconify-icon icon="lucide:refresh-cw" width="11" height="11"></iconify-icon>Reload
      </button>
    </div>
    <!-- code viewer -->
    <pre class="config-pre" id="cfg-content-{key}">กำลังโหลด...</pre>
  </div>

</div>
```

### Zone Badge Classes

ใช้ `.zone` ร่วมกับ modifier (มาจาก `base.html` — ไม่ต้อง define เพิ่ม):

| Class | สี | ใช้เมื่อ |
|---|---|---|
| `zone-safe` | เขียว | OK / active / found |
| `zone-caution` | เหลือง | warning / missing / needs attention |
| `zone-danger` | แดง | error / critical |
| `zone-mute` | เทา | none / disabled / not applicable |
| `zone-info` | น้ำเงิน | info / in-progress |

```html
<span class="zone zone-safe">OK</span>
<span class="zone zone-caution">MISSING</span>
<span class="zone zone-mute">NONE</span>
```

### Code File Viewer (read-only textarea)

ใช้สำหรับแสดงเนื้อหาไฟล์ config — ใช้ `<textarea readonly>` ไม่ใช้ `<pre>` เพื่อให้ style consistent กับ editable textarea และ UX ดีกว่า (scroll, select-all):

```html
<textarea id="cfg-content-{key}" readonly spellcheck="false"
          class="w-full px-3 py-2.5 border-0 bg-surface text-ink text-[0.8rem] font-mono
                 leading-relaxed min-h-[200px] outline-none resize-y cursor-default select-all">
</textarea>
```

JS — set ด้วย `.value` ไม่ใช่ `.textContent`:

```javascript
document.getElementById("cfg-content-{key}").value = content;
```

**กฎ:**
- ใช้ `readonly` + `spellcheck="false"` ทุกครั้ง
- `border-0` แทน border ปกติ เพราะ viewer อยู่ใน card ที่มี border แล้ว
- `cursor-default` บอกผู้ใช้ว่าอ่านอย่างเดียว
- `resize-y` ให้ผู้ใช้ปรับความสูงได้
- ไม่ใช้ `<pre>` สำหรับแสดงไฟล์ config ใน VAS

### JS Toggle Pattern

```javascript
window.toggleCfg = function (key) {
  var viewer = document.getElementById("cfg-viewer-" + key);
  var chev   = document.getElementById("chevron-" + key);
  if (!viewer) return;
  var nowHidden = viewer.classList.toggle("hidden");
  if (chev) chev.style.transform = nowHidden ? "" : "rotate(180deg)";
  // ถ้าต้อง auto-load เมื่อเปิด:
  if (!nowHidden) loadContent(key);
};
```

### กฎ

- `overflow-hidden` บน wrapper card เสมอ (ไม่งั้น rounded-xl จะไม่ครอบ pre)
- Chevron หมุน `rotate(180deg)` เมื่อ expanded, กลับ `""` เมื่อ collapsed
- Toolbar strip ใช้ `bg-surface/40` + `px-4 py-3`
- Action buttons ใน toolbar: `px-2.5 py-1` (micro — ไม่ใช่ `px-3 py-2`)
- ไม่ใช้ dark background สำหรับ code viewer — ใช้ `rgb(var(--c-surface))` เสมอ

---

## Code Style

- **Python**: stdlib only where possible; type hints on public functions
- **Templates**: Tailwind utility classes via Play CDN; Iconify for icons (`lucide:*`, `simple-icons:*`)
- **JS**: vanilla ES5-compatible IIFE inside `{% block extra_scripts %}`; no bundler
- **Colors**: always use CSS variable aliases (`text-ink`, `bg-card`, `border-line/10`) — never hardcode hex
