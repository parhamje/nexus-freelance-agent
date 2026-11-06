// UI helpers: DOM builder, toasts, modals + original WebAudio chime (no copyrighted audio)
import { icon } from './icons.js';

export function h(html) {
  const tpl = document.createElement('template');
  tpl.innerHTML = html.trim();
  return tpl.content.firstElementChild;
}

export function toast(message, kind = 'info', timeout = 5000) {
  const box = document.getElementById('toast-container');
  if (!box) return;

  const rawKey = String(message).replace(/<[^>]*>?/gm, '').trim();

  // 1. Deduplication: If identical message is already displayed, increment counter
  const existingToasts = Array.from(box.querySelectorAll('.toast'));
  const match = existingToasts.find(t => t.dataset.toastKey === rawKey);
  if (match) {
    const badgeEl = match.querySelector('.toast-counter');
    const curCount = parseInt(match.dataset.count || '1', 10) + 1;
    match.dataset.count = String(curCount);
    if (badgeEl) {
      badgeEl.textContent = `×${curCount}`;
      badgeEl.classList.remove('hidden');
    }
    match.classList.remove('pulse-toast');
    void match.offsetWidth;
    match.classList.add('pulse-toast');
    clearTimeout(match._timer);
    if (timeout) match._timer = setTimeout(() => dismissToast(match), timeout);
    return;
  }

  // 2. Cap visible toasts to maximum 3 to prevent screen flooding
  const activeToasts = box.querySelectorAll('.toast');
  if (activeToasts.length >= 3) {
    dismissToast(activeToasts[0]);
  }

  const iconSvg = kind === 'error'
    ? `<svg class="w-4 h-4 text-rose-400 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`
    : kind === 'success'
    ? `<svg class="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`
    : `<svg class="w-4 h-4 text-sky-400 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`;

  const el = h(`
    <div class="toast ${kind} group" data-toast-key="${rawKey.replace(/"/g, '&quot;')}" data-count="1">
      ${iconSvg}
      <div class="flex-1 min-w-0 text-xs leading-relaxed text-slate-100">
        ${message}
      </div>
      <span class="toast-counter hidden px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-white/20 text-white shrink-0 self-start"></span>
      <button class="toast-close opacity-60 hover:opacity-100 p-0.5 text-slate-300 hover:text-white shrink-0 transition cursor-pointer" title="بستن">✕</button>
    </div>
  `);

  el.querySelector('.toast-close').onclick = () => dismissToast(el);
  box.appendChild(el);

  if (timeout) el._timer = setTimeout(() => dismissToast(el), timeout);
  updateClearAllButton();
}

function dismissToast(el) {
  if (!el || !el.parentNode) return;
  el.style.opacity = '0';
  el.style.transform = 'translateY(10px) scale(0.95)';
  setTimeout(() => {
    el.remove();
    updateClearAllButton();
  }, 200);
}

function updateClearAllButton() {
  const box = document.getElementById('toast-container');
  if (!box) return;
  let clearBtn = document.getElementById('toast-clear-all');
  const count = box.querySelectorAll('.toast').length;
  if (count > 1) {
    if (!clearBtn) {
      clearBtn = h(`
        <div id="toast-clear-all" class="flex justify-end mb-1">
          <button class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-800/95 text-slate-300 hover:text-white hover:bg-slate-700 shadow-lg backdrop-blur-md border border-slate-700/80 transition flex items-center gap-1 cursor-pointer">
            <span>✕ بستن همه اعلان‌ها</span>
          </button>
        </div>
      `);
      clearBtn.querySelector('button').onclick = () => {
        box.querySelectorAll('.toast').forEach(t => t.remove());
        clearBtn.remove();
      };
      box.insertBefore(clearBtn, box.firstChild);
    }
  } else if (clearBtn) {
    clearBtn.remove();
  }
}

export function modal(title, bodyHtml, { wide = false, subtitle = '' } = {}) {
  const root = document.getElementById('modal-root');
  const backdrop = h(`<div class="modal-backdrop"><div class="modal-box p-5 sm:p-6 ${wide ? 'modal-wide max-w-4xl' : 'max-w-2xl'}"></div></div>`);
  const box = backdrop.firstElementChild;
  box.innerHTML = `
    <div class="flex items-start justify-between pb-3 mb-3.5 border-b border-slate-100 dark:border-white/10">
      <div>
        <h3 class="font-bold text-base text-slate-900 dark:text-white flex items-center gap-2">${title}</h3>
        ${subtitle ? `<p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">${subtitle}</p>` : ''}
      </div>
      <button class="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/10 transition cursor-pointer shrink-0" data-close title="بستن">✕</button>
    </div>
    <div class="modal-body">${bodyHtml}</div>`;
  const close = () => backdrop.remove();
  backdrop.addEventListener('click', e => { if (e.target === backdrop) close(); });
  box.querySelector('[data-close]').onclick = close;
  root.appendChild(backdrop);
  return { box, close, body: box.querySelector('.modal-body') };
}

export function confirmModal(message, onYes, { danger = true, yesLabel = 'بله، ادامه' } = {}) {
  const m = modal('تأیید عملیات', `<p class="text-sm leading-7">${message}</p>
    <div class="flex gap-2 justify-end mt-5">
      <button class="btn" data-no>انصراف</button>
      <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-yes>${yesLabel}</button>
    </div>`);
  m.body.querySelector('[data-no]').onclick = m.close;
  m.body.querySelector('[data-yes]').onclick = async () => { m.close(); await onYes(); };
}

export function spinner(label = 'در حال بارگذاری…') {
  return `<div class="flex items-center justify-center py-16 text-neutral-500 gap-3">
    <span class="inline-block w-5 h-5 border-2 border-gold-500 border-t-transparent rounded-full animate-spin"></span>${label}</div>`;
}

export function emptyState(text = 'موردی نیست') {
  return `<div class="text-center py-16 text-neutral-500">
    <div class="text-4xl mb-3 opacity-40">🗂</div><p class="text-sm">${text}</p></div>`;
}

export function badge(text, color = 'neutral') {
  const map = {
    neutral: 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20',
    gold: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30',
    green: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30',
    red: 'bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30',
    amber: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30',
    sky: 'bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/30',
    emerald: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30',
    zinc: 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 border-zinc-500/20',
  };
  return `<span class="badge ${map[color] || map.neutral}">${text}</span>`;
}

export function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    if (btn) { const old = btn.textContent; btn.textContent = 'کپی شد ✓'; setTimeout(() => btn.textContent = old, 1500); }
  });
}

// ------------------------------------------------------------------ //
// Original notification chime - synthesized, subtle two-note bell     //
// (E5 -> B5, soft attack, exponential decay; generated at runtime,    //
//  no copyrighted audio).                                             //
// ------------------------------------------------------------------ //
let audioCtx = null;
let volume = 0.6;
let soundOn = true;

export function setSoundPrefs(on, vol) { soundOn = !!on; volume = Math.max(0, Math.min(1, vol ?? 0.6)); }
export function soundEnabled() { return soundOn; }

export function unlockAudio() {
  if (!audioCtx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (Ctx) audioCtx = new Ctx();
  }
  if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
}

function note(ctx, freq, start, dur, peak) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  const filter = ctx.createBiquadFilter();
  osc.type = 'sine';
  osc.frequency.value = freq;
  filter.type = 'lowpass';
  filter.frequency.value = 3200;
  gain.gain.setValueAtTime(0, ctx.currentTime + start);
  gain.gain.linearRampToValueAtTime(peak * volume, ctx.currentTime + start + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + start + dur);
  osc.connect(filter); filter.connect(gain); gain.connect(ctx.destination);
  osc.start(ctx.currentTime + start); osc.stop(ctx.currentTime + start + dur + 0.05);
}

export function playChime() {
  if (!soundOn) return;
  unlockAudio();
  if (!audioCtx || audioCtx.state !== 'running') return; // respect autoplay policy
  try {
    note(audioCtx, 659.25, 0, 0.5, 0.22);      // E5
    note(audioCtx, 987.77, 0.14, 0.75, 0.18);  // B5
    note(audioCtx, 1318.5, 0.16, 0.6, 0.05);   // subtle overtone
  } catch { /* audio unavailable */ }
}

export function bindUnlockOnce() {
  const unlock = () => { unlockAudio(); document.removeEventListener('pointerdown', unlock); };
  document.addEventListener('pointerdown', unlock, { once: true });
}

// ------------------------------------------------------------------ //
// Executive Pagination Component (Smart Windowing + RTL / LTR aware) //
// ------------------------------------------------------------------ //
export function renderPagination({ total, limit = 6, offset = 0, isEn = false, label = 'پروژه' }) {
  if (total <= 0) return '';
  const numLimit = Math.max(1, Number(limit) || 6);
  const numOffset = Math.max(0, Number(offset) || 0);
  const currentPage = Math.floor(numOffset / numLimit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / numLimit));
  const startItem = total === 0 ? 0 : numOffset + 1;
  const endItem = Math.min(numOffset + numLimit, total);

  // Smart window calculation for numbered page pills
  const pages = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (currentPage <= 3) {
      for (let i = 2; i <= Math.min(4, totalPages - 1); i++) pages.push(i);
      pages.push('...');
      pages.push(totalPages);
    } else if (currentPage >= totalPages - 2) {
      pages.push('...');
      for (let i = Math.max(2, totalPages - 3); i <= totalPages; i++) pages.push(i);
    } else {
      pages.push('...');
      pages.push(currentPage - 1);
      pages.push(currentPage);
      pages.push(currentPage + 1);
      pages.push('...');
      pages.push(totalPages);
    }
  }

  // Prev / Next icons (RTL aware: in RTL Next moves left, Prev moves right)
  const prevIcon = isEn ? icon('chevronLeft', 'w-3.5 h-3.5') : icon('chevronRight', 'w-3.5 h-3.5');
  const nextIcon = isEn ? icon('chevronRight', 'w-3.5 h-3.5') : icon('chevronLeft', 'w-3.5 h-3.5');

  return `
    <div class="pagination-container" dir="${isEn ? 'ltr' : 'rtl'}">
      <!-- Info & Per-Page Controls -->
      <div class="flex items-center gap-3.5 text-xs text-slate-500 dark:text-slate-400 flex-wrap">
        <div class="flex items-center gap-1.5 font-medium">
          ${isEn 
            ? `Showing <span class="font-bold text-slate-800 dark:text-white">${startItem}</span> to <span class="font-bold text-slate-800 dark:text-white">${endItem}</span> of <span class="font-bold text-teal-600 dark:text-teal-400">${total}</span> ${label}s`
            : `نمایش <span class="font-bold text-slate-800 dark:text-white">${startItem.toLocaleString('fa-IR')}</span> تا <span class="font-bold text-slate-800 dark:text-white">${endItem.toLocaleString('fa-IR')}</span> از مجموع <span class="font-bold text-teal-600 dark:text-teal-400">${total.toLocaleString('fa-IR')}</span> ${label}`
          }
        </div>
        <div class="h-3.5 w-px bg-slate-200 dark:bg-slate-700 hidden sm:block"></div>
        <div class="flex items-center gap-1.5">
          <span class="text-[11px]">${isEn ? 'Per page:' : 'تعداد در صفحه:'}</span>
          <select class="pagination-limit-select">
            <option value="6" ${numLimit === 6 ? 'selected' : ''}>6</option>
            <option value="12" ${numLimit === 12 ? 'selected' : ''}>12</option>
            <option value="24" ${numLimit === 24 ? 'selected' : ''}>24</option>
            <option value="48" ${numLimit === 48 ? 'selected' : ''}>48</option>
          </select>
        </div>
      </div>

      <!-- Page Controls -->
      <div class="flex items-center gap-1 sm:gap-1.5 flex-wrap justify-center">
        <!-- Prev Button -->
        <button type="button" class="pagination-btn pagination-nav-btn ${currentPage <= 1 ? 'disabled' : ''}" data-page="${currentPage - 1}" ${currentPage <= 1 ? 'disabled' : ''} title="${isEn ? 'Previous page' : 'صفحه قبل'}">
          ${prevIcon}
          <span class="text-xs font-vazir">${isEn ? 'Prev' : 'قبلی'}</span>
        </button>

        <!-- Numbered Page Pills -->
        ${pages.map(p => {
          if (p === '...') {
            return `<span class="pagination-ellipsis">…</span>`;
          }
          const isActive = p === currentPage;
          return `
            <button type="button" class="pagination-btn ${isActive ? 'active' : ''}" data-page="${p}">
              ${isEn ? p : p.toLocaleString('fa-IR')}
            </button>
          `;
        }).join('')}

        <!-- Next Button -->
        <button type="button" class="pagination-btn pagination-nav-btn ${currentPage >= totalPages ? 'disabled' : ''}" data-page="${currentPage + 1}" ${currentPage >= totalPages ? 'disabled' : ''} title="${isEn ? 'Next page' : 'صفحه بعد'}">
          <span class="text-xs font-vazir">${isEn ? 'Next' : 'بعدی'}</span>
          ${nextIcon}
        </button>
      </div>
    </div>
  `;
}

export function bindPagination(container, { onPageChange, onLimitChange }) {
  if (!container) return;
  container.querySelectorAll('.pagination-btn[data-page]:not([disabled])').forEach(btn => {
    btn.onclick = (e) => {
      e.preventDefault();
      const page = Number(btn.dataset.page);
      if (page && onPageChange) onPageChange(page);
    };
  });
  const limitSel = container.querySelector('.pagination-limit-select');
  if (limitSel && onLimitChange) {
    limitSel.onchange = () => {
      onLimitChange(Number(limitSel.value));
    };
  }
}
