/* display.js — VAS Mockup: Display page interactivity */
/* Requires: app.js loaded first, window.VAS_MOCK = true */

const rotationDegrees = { normal: '0deg', left: '-90deg', right: '90deg', inverted: '180deg' };
const rotationLabels  = { normal: 'Normal', left: 'Left 90°', right: 'Right 90°', inverted: 'Inverted' };

let selectedRotation = 'normal';

// ── Rotation buttons ─────────────────────────────────────────────
function initRotationControls() {
  document.querySelectorAll('.rotation-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      selectedRotation = btn.dataset.rotation;
      document.querySelectorAll('.rotation-btn').forEach((b) => b.classList.remove('selected'));
      btn.classList.add('selected');
      applyRotationPreview();
      updateCommandPreview();
    });
  });
}

function applyRotationPreview() {
  const preview = document.getElementById('monitorPreview');
  const label   = document.getElementById('previewLabel');
  if (!preview) return;
  preview.style.transform = `rotate(${rotationDegrees[selectedRotation]})`;
  if (label) label.textContent = rotationLabels[selectedRotation] || selectedRotation;
}

// ── Command preview ───────────────────────────────────────────────
function updateCommandPreview() {
  const list = document.getElementById('commandPreviewList');
  if (!list) return;

  const output  = document.getElementById('displayOutput')?.value || 'eDP-1';
  const touch   = document.getElementById('touchDevice')?.value   || 'ILITEK Multi-Touch';
  const xdisp   = document.getElementById('xDisplay')?.value      || ':0';
  const persist = document.getElementById('persistSession')?.checked ?? true;
  const persistXorg = document.getElementById('persistXorg')?.checked ?? false;

  const dispArg  = xdisp ? ` --display '${xdisp}'` : '';
  const touchArg = touch ? ` --touch '${touch}'` : '';
  const outArg   = output ? ` --output '${output}'` : '';

  const items = [
    { label: 'Apply runtime', sudo: false,
      code: `vas display apply${dispArg}${outArg}${touchArg} --rotate ${selectedRotation}` },
  ];
  if (persist) {
    items.push({ label: 'Persist at login', sudo: false,
      code: `vas display persist-session${dispArg}${outArg}${touchArg} --rotate ${selectedRotation}` });
  }
  if (persistXorg) {
    items.push({ label: 'Persist touch in Xorg', sudo: true,
      code: `sudo vas display persist-xorg${touchArg} --rotate ${selectedRotation}` });
  }

  list.innerHTML = items.map((item) => `
    <div class="command-preview-item">
      <div class="command-label">
        <span>${item.label}</span>
        ${item.sudo ? '<span class="cf-zone cf-zone-caution" style="font-size:0.65rem;padding:0.1rem 0.35rem;">sudo</span>' : ''}
      </div>
      <div class="command-code">${escHtml(item.code)}</div>
    </div>`).join('');
}

// ── Wayland control ───────────────────────────────────────────────
function mockSetWayland(action) {
  const badge = document.getElementById('gdmWaylandBadge');
  const text  = document.getElementById('gdmWaylandText');
  if (action === 'disable') {
    badge?.classList.remove('cf-zone-caution');
    badge?.classList.add('cf-zone-safe');
    if (badge) badge.textContent = 'OK';
    if (text)  text.textContent = 'disabled (WaylandEnable=false) — /etc/gdm3/custom.conf';
    showToast('Wayland disabled in GDM.', 'success');
  } else {
    badge?.classList.remove('cf-zone-safe');
    badge?.classList.add('cf-zone-caution');
    if (badge) badge.textContent = 'WARN';
    if (text)  text.textContent = 'enabled/default — /etc/gdm3/custom.conf';
    showToast('Wayland enabled in GDM.', 'info');
  }
}

// ── Config file viewer ────────────────────────────────────────────
const mockConfigs = {
  gdm_custom: {
    path: '/etc/gdm3/custom.conf',
    content: `[daemon]
# Uncomment the line below to force the login screen to use Xorg
WaylandEnable=false

[security]

[xdmcp]

[chooser]

[debug]
# Uncomment the line below to turn on debugging
# Enable=true`,
  },
  xprofile: {
    path: '/home/vas/.xprofile',
    content: `#!/bin/bash
# VAS display session — managed by vas display persist-session
# Signature: vas-2.4.1

export DISPLAY=:0

xrandr --output eDP-1 --rotate normal
xinput map-to-output 'ILITEK Multi-Touch' eDP-1`,
  },
  display_script: {
    path: '/usr/local/bin/display-session.sh',
    content: `#!/bin/bash
# VAS display session script — managed by vas
# Signature: vas-2.4.1
set -euo pipefail

DISPLAY_SERVER=":0"
OUTPUT="eDP-1"
TOUCH="ILITEK Multi-Touch"
ROTATE="normal"

xrandr --display "$DISPLAY_SERVER" --output "$OUTPUT" --rotate "$ROTATE"
xinput map-to-output "$TOUCH" "$OUTPUT"`,
  },
  xorg_touchscreen: {
    path: '/etc/X11/xorg.conf.d/99-vas-touchscreen.conf',
    content: `# VAS Xorg touchscreen configuration
# Signature: vas-2.4.1
Section "InputClass"
    Identifier "VAS Touchscreen"
    MatchProduct "ILITEK Multi-Touch"
    Option "TransformationMatrix" "1 0 0 0 1 0 0 0 1"
EndSection`,
  },
};

function initConfigViewer() {
  document.querySelectorAll('[data-config-key]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key    = btn.dataset.configKey;
      const title  = btn.dataset.configTitle || key;
      const cfg    = mockConfigs[key] || { path: '(unknown)', content: '(not available)' };
      const viewer = document.getElementById('configFileViewer');
      if (!viewer) return;
      document.getElementById('configFileTitle').textContent = title;
      document.getElementById('configFilePath').textContent  = cfg.path;
      document.getElementById('configFileContent').textContent = cfg.content;
      viewer.hidden = false;
      viewer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  });

  document.getElementById('configViewerClose')?.addEventListener('click', () => {
    document.getElementById('configFileViewer').hidden = true;
  });
}

// ── Apply mock ────────────────────────────────────────────────────
function initApplyButton() {
  document.getElementById('applyDisplay')?.addEventListener('click', () => {
    const result = document.getElementById('applyResult');
    if (result) {
      result.className = 'apply-result';
      result.textContent = 'Applying...';
    }
    setTimeout(() => {
      if (result) {
        result.className = 'apply-result success';
        result.textContent = 'Applied — display rotation set to ' + rotationLabels[selectedRotation] + '.';
      }
      showToast('Display settings applied.', 'success');
    }, 800);
  });
}

// ── Refresh devices (mock) ────────────────────────────────────────
function initRefreshDevices() {
  document.getElementById('refreshDevices')?.addEventListener('click', () => {
    showToast('Devices refreshed (mock — no change).', 'info');
  });
}

// ── Wayland buttons ───────────────────────────────────────────────
function initWaylandButtons() {
  document.querySelectorAll('[data-wayland-action]').forEach((btn) => {
    btn.addEventListener('click', () => mockSetWayland(btn.dataset.waylandAction));
  });
}

// ── Controls update command preview on change ────────────────────
function initControlListeners() {
  ['displayOutput', 'touchDevice', 'xDisplay', 'persistSession', 'persistXorg'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', updateCommandPreview);
      el.addEventListener('input',  updateCommandPreview);
    }
  });
}

function escHtml(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Boot ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initRotationControls();
  initConfigViewer();
  initApplyButton();
  initRefreshDevices();
  initWaylandButtons();
  initControlListeners();
  applyRotationPreview();
  updateCommandPreview();
});
