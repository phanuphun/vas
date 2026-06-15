/* app.js — VAS Mockup: sidebar toggle + shared utilities */
window.VAS_MOCK = true;

// ── Sidebar ──────────────────────────────────────────────────────
function openSidebar() {
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('overlay').classList.add('visible');
}

function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('overlay').classList.remove('visible');
}

// ── Toast notifications ───────────────────────────────────────────
let _toastId = 0;

function showToast(message, type = 'info') {
  const wrap = document.getElementById('toast-wrap');
  if (!wrap) return;

  const id = ++_toastId;
  const icons = {
    success: `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
    error:   `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
    info:    `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
  };

  const toast = document.createElement('div');
  toast.className = `cf-toast cf-toast-${type}`;
  toast.dataset.id = id;
  toast.style.cssText = 'animation: slideIn 0.2s ease; cursor:pointer;';
  toast.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span>${message}</span>`;
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
  dialog.className = 'cf-card modal-dialog';
  dialog.id = 'confirm-modal-dialog';
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  dialog.setAttribute('aria-labelledby', 'confirm-modal-title');
  dialog.innerHTML = `
    <div class="modal-dialog-head">
      <div class="cf-iconbox" id="confirm-modal-icon" style="flex-shrink:0;"></div>
      <div class="modal-dialog-body">
        <h2 class="modal-dialog-title font-display" id="confirm-modal-title"></h2>
        <p class="modal-dialog-message" id="confirm-modal-message"></p>
      </div>
    </div>
    <div class="modal-dialog-actions">
      <button class="cf-btn" type="button" id="confirm-modal-cancel">ยกเลิก</button>
      <button class="cf-btn cf-btn-primary" type="button" id="confirm-modal-confirm">ยืนยัน</button>
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

  confirmBtn.className = variant === 'danger'
    ? 'cf-btn cf-btn-danger'
    : 'cf-btn cf-btn-primary';

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

  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideIn {
      from { opacity: 0; transform: translateX(20px); }
      to   { opacity: 1; transform: translateX(0); }
    }
  `;
  document.head.appendChild(style);
});
