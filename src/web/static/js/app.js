/* app.js — VAS: sidebar toggle + toast + confirm modal */

// ── Sidebar ──────────────────────────────────────────────────────
function openSidebar() {
  document.getElementById('sidebar').classList.remove('-translate-x-full');
  document.getElementById('overlay').classList.remove('hidden');
}

function closeSidebar() {
  document.getElementById('sidebar').classList.add('-translate-x-full');
  document.getElementById('overlay').classList.add('hidden');
}

// ── Button class constants ────────────────────────────────────────
const BTN_GHOST   = 'inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-line/15 rounded-lg bg-card text-ink text-[0.82rem] font-semibold hover:bg-surface transition-colors cursor-pointer';
const BTN_PRIMARY = 'inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-accent rounded-lg bg-accent text-white text-[0.82rem] font-semibold hover:bg-blue-700 transition-colors cursor-pointer';
const BTN_DANGER  = 'inline-flex items-center gap-1.5 px-3.5 py-1.5 border border-danger/25 rounded-lg bg-card text-danger text-[0.82rem] font-semibold hover:bg-danger/5 transition-colors cursor-pointer';

// ── Toast notifications ───────────────────────────────────────────
let _toastId = 0;

const TOAST_STYLES = {
  success: 'border-l-[3px] border-l-[#10b981] border-[rgb(16_185_129/0.28)] bg-[rgb(16_185_129/0.05)] text-[#0f766e]',
  error:   'border-l-[3px] border-l-[#ef4444] border-[rgb(239_68_68/0.28)] bg-[rgb(239_68_68/0.05)] text-[#b1453a]',
  info:    'border-l-[3px] border-l-[rgb(37_99_235)] border-[rgb(37_99_235/0.28)] bg-[rgb(37_99_235/0.05)] text-accent',
};

const TOAST_ICON_BG = {
  success: '#10b981',
  error:   '#ef4444',
  info:    'rgb(var(--c-accent))',
};

const TOAST_ICONS = {
  success: `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  error:   `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  info:    `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
};

function showToast(message, type = 'info') {
  const wrap = document.getElementById('toast-wrap');
  if (!wrap) return;

  const id = ++_toastId;
  const varStyle = TOAST_STYLES[type] || TOAST_STYLES.info;
  const iconBg = TOAST_ICON_BG[type] || TOAST_ICON_BG.info;
  const icon = TOAST_ICONS[type] || TOAST_ICONS.info;

  const toast = document.createElement('div');
  toast.className = `flex items-center gap-2 px-3.5 py-2.5 rounded-xl border text-[0.815rem] bg-card shadow-md min-w-[220px] max-w-[360px] cursor-pointer ${varStyle}`;
  toast.dataset.id = id;
  toast.style.animation = 'slideIn 0.2s ease';
  toast.innerHTML = `
    <div class="w-[18px] h-[18px] rounded-full grid place-items-center flex-shrink-0 text-white" style="background:${iconBg}">${icon}</div>
    <span>${message}</span>`;
  toast.addEventListener('click', () => removeToast(id));
  wrap.appendChild(toast);
  setTimeout(() => removeToast(id), 3500);
}

function removeToast(id) {
  const el = document.querySelector(`[data-id="${id}"]`);
  if (el) el.remove();
}

// ── Confirm modal ─────────────────────────────────────────────────
let _confirmResolve = null;

const CONFIRM_ICONS = {
  caution: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
  danger:  `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
  info:    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
};

const CONFIRM_ICON_STYLES = {
  caution: 'border-color:rgb(var(--c-caution)/0.3);background:rgb(var(--c-caution)/0.08);color:#92660b;',
  danger:  'border-color:rgb(var(--c-danger)/0.3);background:rgb(var(--c-danger)/0.08);color:rgb(var(--c-danger));',
  info:    'border-color:rgb(var(--c-accent)/0.3);background:rgb(var(--c-accent)/0.08);color:rgb(var(--c-accent));',
};

function ensureConfirmModal() {
  if (document.getElementById('confirm-modal-backdrop')) return;

  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.id = 'confirm-modal-backdrop';
  backdrop.addEventListener('click', () => closeConfirmModal(false));

  const dialog = document.createElement('div');
  dialog.className = 'modal-dialog';
  dialog.id = 'confirm-modal-dialog';
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  dialog.setAttribute('aria-labelledby', 'confirm-modal-title');
  dialog.innerHTML = `
    <div class="modal-dialog-head">
      <div class="w-9 h-9 border rounded-lg grid place-items-center flex-shrink-0" id="confirm-modal-icon" style="flex-shrink:0;"></div>
      <div class="modal-dialog-body">
        <h2 class="modal-dialog-title" id="confirm-modal-title"></h2>
        <p class="modal-dialog-message" id="confirm-modal-message"></p>
      </div>
    </div>
    <div class="modal-dialog-actions">
      <button class="${BTN_GHOST}" type="button" id="confirm-modal-cancel">ยกเลิก</button>
      <button class="${BTN_PRIMARY}" type="button" id="confirm-modal-confirm">ยืนยัน</button>
    </div>`;

  dialog.addEventListener('click', (e) => e.stopPropagation());
  document.body.appendChild(backdrop);
  document.body.appendChild(dialog);

  document.getElementById('confirm-modal-cancel').addEventListener('click', () => closeConfirmModal(false));
  document.getElementById('confirm-modal-confirm').addEventListener('click', () => closeConfirmModal(true));
}

function closeConfirmModal(confirmed = false) {
  const backdrop = document.getElementById('confirm-modal-backdrop');
  const dialog = document.getElementById('confirm-modal-dialog');
  if (!backdrop || !dialog) return;

  backdrop.classList.remove('is-visible');
  dialog.classList.remove('is-visible');
  document.body.classList.remove('modal-open');

  if (_confirmResolve) {
    const resolve = _confirmResolve;
    _confirmResolve = null;
    resolve(confirmed);
  }
}

function showConfirmModal({
  title = 'ยืนยันการดำเนินการ',
  message = '',
  confirmLabel = 'ยืนยัน',
  cancelLabel = 'ยกเลิก',
  variant = 'caution',
} = {}) {
  ensureConfirmModal();

  const backdrop = document.getElementById('confirm-modal-backdrop');
  const dialog = document.getElementById('confirm-modal-dialog');
  const iconBox = document.getElementById('confirm-modal-icon');
  const titleEl = document.getElementById('confirm-modal-title');
  const messageEl = document.getElementById('confirm-modal-message');
  const confirmBtn = document.getElementById('confirm-modal-confirm');
  const cancelBtn = document.getElementById('confirm-modal-cancel');

  iconBox.style.cssText = `flex-shrink:0;${CONFIRM_ICON_STYLES[variant] || CONFIRM_ICON_STYLES.caution}`;
  iconBox.innerHTML = CONFIRM_ICONS[variant] || CONFIRM_ICONS.caution;
  titleEl.textContent = title;
  messageEl.textContent = message;
  confirmBtn.textContent = confirmLabel;
  cancelBtn.textContent = cancelLabel;

  confirmBtn.className = variant === 'danger' ? BTN_DANGER : BTN_PRIMARY;

  return new Promise((resolve) => {
    _confirmResolve = resolve;
    document.body.classList.add('modal-open');
    requestAnimationFrame(() => {
      backdrop.classList.add('is-visible');
      dialog.classList.add('is-visible');
      cancelBtn.focus();
    });
  });
}

window.showConfirmModal = showConfirmModal;
window.closeConfirmModal = closeConfirmModal;

// ── Keyboard / escape ────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (document.getElementById('confirm-modal-dialog')?.classList.contains('is-visible')) {
    closeConfirmModal(false);
    return;
  }
  closeSidebar();
});

// ── Init ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (!document.getElementById('toast-wrap')) {
    const wrap = document.createElement('div');
    wrap.className = 'toast-wrap';
    wrap.id = 'toast-wrap';
    document.body.appendChild(wrap);
  }
  ensureConfirmModal();
});
