/* logs.js — VAS Mockup: System Logs page interactivity */
/* Requires: app.js loaded first */

const MOCK_LOG_DIR = '/var/log/vas/snapshots';

const MOCK_SNAPSHOTS = [
  {
    id: '20260615-172445',
    path: `${MOCK_LOG_DIR}/20260615-172445.log`,
    size: 14238,
    content: `=== VAS System Log Snapshot ===
Collected: 2026-06-15 17:24:45 UTC
Host: vas-machine-01
Kernel: 6.5.0-35-generic

--- journalctl (vas service) ---
Jun 15 17:20:01 vas-machine-01 vas[1234]: INFO  Starting VAS server v1.4.2
Jun 15 17:20:02 vas-machine-01 vas[1234]: INFO  WireGuard interface wg0: UP
Jun 15 17:20:02 vas-machine-01 vas[1234]: INFO  Display session applied (eDP-1, normal)
Jun 15 17:20:03 vas-machine-01 vas[1234]: INFO  AnyDesk service: active
Jun 15 17:20:03 vas-machine-01 vas[1234]: INFO  Web server listening on :5000
Jun 15 17:22:15 vas-machine-01 vas[1234]: INFO  /api/display/apply called (output=eDP-1, rotate=normal)
Jun 15 17:24:00 vas-machine-01 vas[1234]: INFO  /api/wireguard/action called (action=sync)
Jun 15 17:24:01 vas-machine-01 vas[1234]: INFO  WireGuard sync: writing active config

--- systemctl status wg-quick@wg0 ---
● wg-quick@wg0.service - WireGuard via wg-quick(8) for wg0
     Loaded: loaded (/lib/systemd/system/wg-quick@.service; enabled)
     Active: active (exited) since Mon 2026-06-15 17:20:02 UTC; 4min 43s ago

--- systemctl status anydesk ---
● anydesk.service - AnyDesk
     Loaded: loaded (/etc/systemd/system/anydesk.service; enabled)
     Active: active (running) since Mon 2026-06-15 17:20:03 UTC; 4min 42s ago
    Process: ExecStart=/usr/bin/anydesk --service

--- xrandr output ---
Screen 0: minimum 8 x 8, current 1920 x 1080, maximum 32767 x 32767
eDP-1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 344mm x 194mm
   1920x1080     60.05*+
HDMI-1 disconnected (normal left inverted right x axis y axis)

--- xinput list ---
⎡ Virtual core pointer                    id=2  [master pointer (3)]
⎜   ↳ ILITEK Multi-Touch                 id=14 [slave  pointer (2)]
⎣ Virtual core keyboard                   id=3  [master keyboard (4)]
`,
  },
  {
    id: '20260614-091122',
    path: `${MOCK_LOG_DIR}/20260614-091122.log`,
    size: 9812,
    content: `=== VAS System Log Snapshot ===
Collected: 2026-06-14 09:11:22 UTC
Host: vas-machine-01
Kernel: 6.5.0-35-generic

--- journalctl (vas service) ---
Jun 14 09:08:00 vas-machine-01 vas[1188]: INFO  Starting VAS server v1.4.1
Jun 14 09:08:01 vas-machine-01 vas[1188]: WARN  WireGuard interface wg0: DOWN (config missing)
Jun 14 09:08:02 vas-machine-01 vas[1188]: INFO  Display session applied (eDP-1, normal)
Jun 14 09:08:02 vas-machine-01 vas[1188]: INFO  Web server listening on :5000
Jun 14 09:10:44 vas-machine-01 vas[1188]: INFO  /api/wireguard/save called

--- systemctl status wg-quick@wg0 ---
● wg-quick@wg0.service - WireGuard via wg-quick(8) for wg0
     Loaded: loaded (/lib/systemd/system/wg-quick@.service; enabled)
     Active: failed (Result: exit-code) since Sun 2026-06-14 09:08:01 UTC
     Process: ExecStart=/usr/bin/wg-quick up wg0 (code=exited, status=1/FAILURE)

--- xrandr output ---
Screen 0: minimum 8 x 8, current 1920 x 1080, maximum 32767 x 32767
eDP-1 connected primary 1920x1080+0+0 (normal)
   1920x1080     60.05*+
`,
  },
  {
    id: '20260610-163055',
    path: `${MOCK_LOG_DIR}/20260610-163055.log`,
    size: 7441,
    content: `=== VAS System Log Snapshot ===
Collected: 2026-06-10 16:30:55 UTC
Host: vas-machine-01
Kernel: 6.5.0-28-generic

--- journalctl (vas service) ---
Jun 10 16:25:00 vas-machine-01 vas[998]: INFO  Starting VAS server v1.4.0
Jun 10 16:25:01 vas-machine-01 vas[998]: INFO  Initial setup detected
Jun 10 16:25:02 vas-machine-01 vas[998]: INFO  Display: eDP-1 (1920x1080, normal)
Jun 10 16:28:11 vas-machine-01 vas[998]: INFO  AnyDesk ID registered: 123456789
Jun 10 16:30:00 vas-machine-01 vas[998]: INFO  WireGuard config saved

--- systemctl status vas ---
● vas.service - VAS Vending Agent System
     Loaded: loaded (/etc/systemd/system/vas.service; enabled)
     Active: active (running) since Tue 2026-06-10 16:25:00 UTC; 5min 55s ago
`,
  },
];

let _snapshots = [...MOCK_SNAPSHOTS];
let _activeId   = null;

function escHtml(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

function renderSnapshotList() {
  const list = document.getElementById('systemSnapshotList');
  if (!list) return;

  list.innerHTML = '';
  if (!_snapshots.length) {
    list.innerHTML = '<p style="padding:1rem;font-size:0.82rem;color:rgb(var(--c-faint));">No system log snapshots collected yet.</p>';
    return;
  }
  _snapshots.forEach((snap) => {
    const btn = document.createElement('button');
    btn.className = `log-entry-btn${_activeId === snap.id ? ' active' : ''}`;
    btn.dataset.snapshotId = snap.id;
    btn.innerHTML = `
      <span class="log-entry-id">${snap.id}</span>
      <span class="log-entry-meta">${formatBytes(snap.size)}</span>`;
    btn.addEventListener('click', () => showSnapshot(snap.id));
    list.appendChild(btn);
  });
}

function showSnapshot(id) {
  const snap = _snapshots.find((s) => s.id === id);
  if (!snap) return;
  _activeId = id;

  document.getElementById('systemLogTitle').textContent = snap.id;
  document.getElementById('systemLogPath').textContent  = snap.path;
  document.getElementById('systemLogContent').textContent = snap.content;

  document.querySelectorAll('.log-entry-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.snapshotId === id);
  });
}

function collectSnapshot() {
  const content = document.getElementById('systemLogContent');
  if (content) content.textContent = 'Collecting system logs...';

  setTimeout(() => {
    const now = new Date();
    const pad  = (n) => String(n).padStart(2, '0');
    const id   = `${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
    const newSnap = {
      id,
      path: `${MOCK_LOG_DIR}/${id}.log`,
      size: Math.floor(Math.random() * 8000) + 6000,
      content: `=== VAS System Log Snapshot ===\nCollected: ${new Date().toISOString().replace('T',' ').replace('Z',' UTC')}\nHost: vas-machine-01\n\n(Mock snapshot — real data available when connected to machine)\n\n--- journalctl (vas service, last 50 lines) ---\n${MOCK_SNAPSHOTS[0].content.split('---').slice(2, 4).join('---')}`,
    };
    _snapshots = [newSnap, ..._snapshots];
    renderSnapshotList();
    showSnapshot(id);
    showToast('System log snapshot collected.', 'success');
  }, 1200);
}

// ── Boot ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  renderSnapshotList();

  // Show first snapshot by default
  if (_snapshots.length) showSnapshot(_snapshots[0].id);

  document.getElementById('refreshSystemLogs')?.addEventListener('click', () => {
    showToast('List refreshed (mock).', 'info');
    renderSnapshotList();
  });

  document.getElementById('collectSystemLog')?.addEventListener('click', collectSnapshot);
});
