// App bootstrap: auth, router, theme, nav, notifications bell, WS wiring
import { api, getToken, setToken, esc } from './api.js';
import { applyLang, currentLang, setLang, t } from './i18n.js';
import { bindUnlockOnce, playChime, setSoundPrefs, toast, h, modal } from './ui.js';
import { connectWS, onEvent } from './ws.js';
import { PAGES } from './pages/index.js';
import { icon } from './icons.js';
import { initCommandPalette } from './command_palette.js';

// Executive Rail Navigation with dedicated SVG icon keys & concise single-word localized labels
const RAIL_NAV = [
  { id: 'analytics', iconName: 'chart', label: 'RATE', faLabel: 'آمار' },
  { id: 'overview', iconName: 'star', label: 'OVERVIEW', faLabel: 'داشبورد' },
  { id: 'discovered', iconName: 'folder', label: 'PROJECTS', faLabel: 'پروژه‌ها' },
  { id: 'proposals', iconName: 'reports', label: 'REPORTS', faLabel: 'پیشنهادها' },
  { id: 'platforms', iconName: 'channels', label: 'CHANNELS', faLabel: 'کانال‌ها' },
  { id: 'settings', iconName: 'settings', label: 'SETTINGS', faLabel: 'تنظیمات' },
];

// Mapping sub-pages to their parent category for seamless tab highlighting
const PARENT_CATEGORY = {
  overview: 'overview',
  discovered: 'discovered',
  recommended: 'discovered',
  skipped: 'discovered',
  approved: 'discovered',
  proposals: 'proposals',
  submitted: 'proposals',
  platforms: 'platforms',
  ai: 'platforms',
  telegram: 'platforms',
  analytics: 'analytics',
  logs: 'analytics',
  settings: 'settings',
  agentconfig: 'settings',
  profile: 'settings',
  prompts: 'settings',
  notifications: 'settings',
};

// ---------------- theme ----------------
export function applyTheme() {
  const theme = localStorage.getItem('fa_theme') || 'light';
  document.documentElement.classList.toggle('dark', theme === 'dark');
  const iconBox = document.getElementById('theme-icon-box');
  if (iconBox) {
    iconBox.innerHTML = icon(theme === 'dark' ? 'sun' : 'moon', 'w-4 h-4');
  }
}

// ---------------- router ----------------
export function navigate(page, params = {}) {
  const hash = params && Object.keys(params).length
    ? `#/${page}?${new URLSearchParams(params)}` : `#/${page}`;
  if (location.hash !== hash) location.hash = hash; else render();
}

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [page, qs] = raw.split('?');
  return { page: page || 'overview', params: Object.fromEntries(new URLSearchParams(qs || '')) };
}

let renderToken = 0;

export async function render() {
  const { page, params } = parseHash();
  const def = PAGES[page] || PAGES.overview;
  const token = ++renderToken;

  const parentKey = PARENT_CATEGORY[page] || 'overview';

  // Update topbar badges
  const agentBadgeEl = document.getElementById('agent-status-badge');
  if (agentBadgeEl) agentBadgeEl.textContent = currentLang() === 'en' ? 'Autonomous Agent Active' : 'ایجنت هوشمند فعال';

  refreshPlatformHubPill();

  // Highlight Rail Item with signature white circular bubble
  document.querySelectorAll('.rail-item').forEach(el => {
    el.classList.toggle('active', el.dataset.page === parentKey);
  });

  const container = document.getElementById('page-content');
  if (!container) return;
  container.innerHTML = '';

  try {
    await def.render(container, params, () => token === renderToken);
  } catch (e) {
    if (e && e.status === 401) return; // global handler logs out
    container.innerHTML = `<div class="card p-6 text-sm text-red-500">خطا در بارگذاری صفحه: ${e.message || e}</div>`;
  }
}

// ---------------- bell / notifications ----------------
export async function refreshBell() {
  try {
    const { unread } = await api.get('/notifications/unread-count');
    const badgeEl = document.getElementById('bell-badge');
    if (badgeEl) {
      badgeEl.textContent = unread > 99 ? '+99' : unread;
      badgeEl.classList.toggle('hidden', !unread);
    }
  } catch { /* ignore */ }
}

async function loadBellDropdown() {
  const box = document.getElementById('bell-dropdown');
  const isEn = currentLang() === 'en';
  let items = [];
  try {
    const res = await api.get('/notifications?limit=20');
    items = res.items || [];
  } catch {
    items = [];
  }

  const unreadCount = items.filter(n => !n.is_read).length;

  const headerHtml = `
    <div class="notif-header">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full ${unreadCount > 0 ? 'bg-rose-500 animate-pulse' : 'bg-emerald-500'}"></span>
        <span class="text-xs font-bold text-slate-800 dark:text-slate-100">${isEn ? 'Notifications' : 'مرکز اعلان‌ها'}</span>
        ${unreadCount > 0 ? `<span class="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/15 text-rose-600 dark:text-rose-400">${unreadCount} ${isEn ? 'new' : 'جدید'}</span>` : ''}
      </div>
      ${items.length ? `
        <button id="mark-all" class="text-[11px] font-semibold text-teal-700 dark:text-teal-400 hover:underline flex items-center gap-1 transition">
          ${icon('check', 'w-3.5 h-3.5')}
          <span>${isEn ? 'Mark all read' : 'خواندن همه'}</span>
        </button>` : ''}
    </div>
  `;

  const itemsHtml = items.length ? items.map(n => {
    const isErr = n.type?.includes('failed') || n.type?.includes('error') || (n.title && n.title.includes('ناموفق'));
    const isWon = n.type?.includes('won') || n.type?.includes('bid');
    const isAnalysis = n.type?.includes('analysis');

    let iconName = 'bell';
    let iconBg = 'bg-slate-100 dark:bg-white/10 text-slate-600 dark:text-slate-300';
    if (isErr) {
      iconName = 'close';
      iconBg = 'bg-rose-500/15 text-rose-600 dark:text-rose-400';
    } else if (isWon) {
      iconName = 'trophy';
      iconBg = 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400';
    } else if (isAnalysis) {
      iconName = 'sparkles';
      iconBg = 'bg-amber-500/15 text-amber-600 dark:text-amber-400';
    }

    return `
      <div class="notif-item ${n.is_read ? 'is-read' : ''}" data-nid="${n.id}">
        <div class="notif-icon-box ${iconBg}">
          ${icon(iconName, 'w-4 h-4')}
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-xs font-semibold text-slate-800 dark:text-slate-100 flex items-center justify-between gap-2">
            <span class="line-clamp-1">${esc(n.title)}</span>
            ${!n.is_read ? '<span class="w-2 h-2 rounded-full bg-rose-500 shrink-0"></span>' : ''}
          </div>
          ${n.body ? `<div class="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-relaxed line-clamp-2">${esc(n.body)}</div>` : ''}
          <div class="text-[10px] text-slate-400 dark:text-slate-500 mt-1.5 flex items-center gap-1">
            ${icon('clock', 'w-3 h-3 text-slate-400')}
            <span>${new Date(n.created_at).toLocaleString(isEn ? 'en-US' : 'fa-IR')}</span>
          </div>
        </div>
      </div>
    `;
  }).join('') : `
    <div class="p-8 text-center">
      <div class="w-10 h-10 rounded-full bg-slate-100 dark:bg-white/5 mx-auto flex items-center justify-center text-slate-400 mb-2">
        ${icon('bell', 'w-5 h-5')}
      </div>
      <div class="text-xs font-semibold text-slate-600 dark:text-slate-300">${isEn ? 'No notifications' : 'هیچ اعلانی وجود ندارد'}</div>
      <div class="text-[11px] text-slate-400 dark:text-slate-500 mt-1">${isEn ? 'All caught up!' : 'همه رویدادها بررسی شده‌اند.'}</div>
    </div>
  `;

  const footerHtml = `
    <div class="p-2 border-t border-slate-100 dark:border-white/5 text-center bg-slate-50/50 dark:bg-white/[0.02]">
      <a href="#/notifications" class="text-[11px] font-semibold text-slate-500 hover:text-teal-600 dark:text-slate-400 dark:hover:text-teal-400 transition block py-1" id="notif-view-all">
        ${isEn ? 'View all notifications history →' : 'مشاهده تاریخچه کامل اعلان‌ها ←'}
      </a>
    </div>
  `;

  box.innerHTML = headerHtml + `<div class="max-h-80 overflow-y-auto">${itemsHtml}</div>` + footerHtml;

  box.querySelectorAll('[data-nid]').forEach(el => {
    el.onclick = async () => {
      const id = el.dataset.nid;
      const n = items.find(x => String(x.id) === id);
      await api.post(`/notifications/${id}/read`);
      box.classList.add('hidden');
      refreshBell();
      if (n && n.project_id) navigate('discovered', { detail: n.project_id });
    };
  });

  const markAll = box.querySelector('#mark-all');
  if (markAll) {
    markAll.onclick = async () => {
      await api.post('/notifications/read-all');
      box.classList.add('hidden');
      refreshBell();
    };
  }

  const viewAll = box.querySelector('#notif-view-all');
  if (viewAll) {
    viewAll.onclick = () => {
      box.classList.add('hidden');
    };
  }
}

// ---------------- platform & engine hub ----------------
function timeAgo(dateStr) {
  if (!dateStr) return currentLang() === 'en' ? 'Never scanned' : 'تاکنون اسکن نشده';
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  const isEn = currentLang() === 'en';
  if (diff < 60) return isEn ? 'Just now' : 'چند لحظه پیش';
  if (diff < 3600) {
    const mins = Math.floor(diff / 60);
    return isEn ? `${mins}m ago` : `${mins} دقیقه پیش`;
  }
  if (diff < 86400) {
    const hours = Math.floor(diff / 3600);
    return isEn ? `${hours}h ago` : `${hours} ساعت پیش`;
  }
  const days = Math.floor(diff / 86400);
  return isEn ? `${days}d ago` : `${days} روز پیش`;
}

async function refreshPlatformHubPill() {
  const labelEl = document.getElementById('platform-hub-label');
  const badgesBox = document.getElementById('platform-hub-badges');
  if (!labelEl || !badgesBox) return;

  const isEn = currentLang() === 'en';
  try {
    const [platRes, aiRes] = await Promise.all([
      api.get('/platforms').catch(() => ({ items: [] })),
      api.get('/ai/providers').catch(() => ({ items: [] }))
    ]);
    const platforms = platRes.items || [];
    const aiProviders = aiRes.items || [];

    const enabledPlats = platforms.filter(p => p.enabled && p.slug !== 'demo');
    const activeAi = aiProviders.find(p => p.is_active);

    if (enabledPlats.length > 0) {
      labelEl.textContent = isEn ? `${enabledPlats.length} Channels Live` : `${enabledPlats.length} پلتفرم فعال`;
    } else {
      labelEl.textContent = isEn ? 'Channels & AI' : 'کانال‌ها و AI';
    }

    const kPlat = platforms.find(p => p.slug === 'karlancer');
    const pPlat = platforms.find(p => p.slug === 'ponisha');

    const kStatus = kPlat?.enabled ? (kPlat.connection_status === 'connected' ? 'bg-emerald-400' : 'bg-rose-400') : 'bg-slate-400';
    const pStatus = pPlat?.enabled ? (pPlat.connection_status === 'connected' ? 'bg-emerald-400' : 'bg-rose-400') : 'bg-slate-400';
    const aiStatus = activeAi?.connection_status === 'connected' ? 'bg-emerald-400' : 'bg-slate-400';

    badgesBox.innerHTML = `
      <span class="platform-mini-badge w-5 h-5 rounded-full ring-2 ring-white dark:ring-slate-800 -ms-1.5 first:ms-0 flex items-center justify-center text-[10px] font-black text-white bg-blue-600 relative shrink-0" title="Karlancer: ${kPlat?.enabled ? (kPlat.connection_status || 'متصل') : 'غیرفعال'}">
        K
        <span class="status-dot-mini absolute -bottom-0.5 -end-0.5 w-2 h-2 rounded-full ring-1 ring-white dark:ring-slate-800 ${kStatus}"></span>
      </span>
      <span class="platform-mini-badge w-5 h-5 rounded-full ring-2 ring-white dark:ring-slate-800 -ms-1.5 first:ms-0 flex items-center justify-center text-[10px] font-black text-white bg-emerald-600 relative shrink-0" title="Ponisha: ${pPlat?.enabled ? (pPlat.connection_status || 'متصل') : 'غیرفعال'}">
        P
        <span class="status-dot-mini absolute -bottom-0.5 -end-0.5 w-2 h-2 rounded-full ring-1 ring-white dark:ring-slate-800 ${pStatus}"></span>
      </span>
      <span class="platform-mini-badge w-5 h-5 rounded-full ring-2 ring-white dark:ring-slate-800 -ms-1.5 first:ms-0 flex items-center justify-center text-[10px] font-black text-white bg-teal-600 relative shrink-0" title="AI: ${activeAi?.name || 'آماده'}">
        ✦
        <span class="status-dot-mini absolute -bottom-0.5 -end-0.5 w-2 h-2 rounded-full ring-1 ring-white dark:ring-slate-800 ${aiStatus}"></span>
      </span>
    `;
  } catch {
    /* ignore */
  }
}

async function loadPlatformHubDropdown() {
  const box = document.getElementById('platform-hub-dropdown');
  if (!box) return;
  const isEn = currentLang() === 'en';

  box.innerHTML = `
    <div class="p-6 text-center text-xs text-slate-400">
      <div class="inline-block w-5 h-5 border-2 border-teal-500 border-t-transparent rounded-full animate-spin mb-2"></div>
      <div>${isEn ? 'Checking service health...' : 'در حال استعلام وضعیت سرویس‌ها...'}</div>
    </div>
  `;

  let platforms = [];
  let aiProviders = [];
  try {
    const [platRes, aiRes] = await Promise.all([
      api.get('/platforms'),
      api.get('/ai/providers')
    ]);
    platforms = platRes.items || [];
    aiProviders = aiRes.items || [];
  } catch (err) {
    box.innerHTML = `<div class="p-4 text-xs text-rose-500 text-center">${esc(err.message)}</div>`;
    return;
  }

  const enabledCount = platforms.filter(p => p.enabled && p.slug !== 'demo').length;
  const activeAi = aiProviders.find(p => p.is_active);

  const mainPlatforms = platforms.filter(p => p.slug !== 'demo');
  const platItemsHtml = mainPlatforms.map(p => {
    const isKarlancer = p.slug === 'karlancer';
    const isPonisha = p.slug === 'ponisha';
    const initial = isKarlancer ? 'K' : isPonisha ? 'P' : 'PC';
    const iconBg = isKarlancer ? 'bg-blue-600 text-white' : isPonisha ? 'bg-emerald-600 text-white' : 'bg-amber-600 text-white';

    const isConnected = p.connection_status === 'connected';
    const isEnabled = p.enabled;

    let badgeClass = 'bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-800 dark:border-slate-700';
    let badgeText = isEn ? 'Disabled' : 'غیرفعال';

    if (isEnabled) {
      if (isConnected) {
        badgeClass = 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/20';
        badgeText = isEn ? 'Connected' : 'متصل و فعال';
      } else {
        badgeClass = 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/20';
        badgeText = isEn ? 'Error' : 'خطا در اتصال';
      }
    }

    return `
      <div class="hub-item">
        <div class="hub-item-left">
          <div class="hub-item-icon ${iconBg}">
            ${initial}
          </div>
          <div class="hub-item-info">
            <div class="flex items-center gap-1.5">
              <span class="hub-item-name">${esc(p.name)}</span>
              <span class="px-1.5 py-0.5 rounded-md text-[10px] font-bold border ${badgeClass}">${badgeText}</span>
            </div>
            <div class="hub-item-meta mt-0.5">
              ${isEn ? 'Last scan: ' : 'آخرین اسکن: '}${timeAgo(p.last_scan_at || p.last_success_scan_at)}
            </div>
          </div>
        </div>
        <div>
          ${isEnabled ? `
            <button class="hub-quick-scan-btn px-2.5 py-1 rounded-lg text-[11px] font-bold bg-teal-500/10 hover:bg-teal-500 hover:text-white text-teal-600 dark:text-teal-400 transition flex items-center gap-1" data-slug="${p.slug}">
              <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              <span>${isEn ? 'Scan' : 'اسکن'}</span>
            </button>
          ` : `
            <button class="hub-enable-btn px-2 py-1 rounded-lg text-[10px] font-semibold text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition" data-slug="${p.slug}">
              ${isEn ? 'Configure' : 'پیکربندی'}
            </button>
          `}
        </div>
      </div>
    `;
  }).join('');

  const aiHtml = activeAi ? `
    <div class="hub-item">
      <div class="hub-item-left">
        <div class="hub-item-icon bg-gradient-to-tr from-teal-600 to-indigo-600 text-white">
          ✦
        </div>
        <div class="hub-item-info">
          <div class="flex items-center gap-1.5">
            <span class="hub-item-name">${esc(activeAi.name)}</span>
            <span class="px-1.5 py-0.5 rounded-md text-[10px] font-bold border bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/20">${isEn ? 'Active' : 'مدل فعال'}</span>
          </div>
          <div class="hub-item-meta mt-0.5 font-mono text-[10px] truncate max-w-[170px]" dir="ltr">
            ${esc(activeAi.default_model || 'Standard')}
          </div>
        </div>
      </div>
      <div>
        <button id="hub-goto-ai-btn" class="px-2 py-1 rounded-lg text-[11px] font-semibold text-teal-600 dark:text-teal-400 hover:underline">
          ${isEn ? 'Settings' : 'تنظیمات'}
        </button>
      </div>
    </div>
  ` : `
    <div class="p-3 text-center text-xs text-amber-500 bg-amber-500/10">
      ${isEn ? 'No active AI Provider configured' : 'تأمین‌کننده هوش مصنوعی فعال نیست'}
    </div>
  `;

  box.innerHTML = `
    <div class="hub-header">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full ${enabledCount > 0 ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}"></span>
        <span class="text-xs font-bold text-slate-800 dark:text-slate-100">${isEn ? 'Platform & Engine Status' : 'وضعیت کانال‌ها و موتور هوش مصنوعی'}</span>
        <span class="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-teal-500/15 text-teal-700 dark:text-teal-300">${enabledCount} ${isEn ? 'active' : 'فعال'}</span>
      </div>
      <button id="hub-refresh-action" class="text-slate-400 hover:text-teal-600 transition p-1" title="${isEn ? 'Refresh' : 'بروزرسانی'}">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
      </button>
    </div>

    <div class="hub-section-title">${isEn ? 'Freelance Channels' : 'کانال‌های فریلنسری'}</div>
    ${platItemsHtml}

    <div class="hub-section-title">${isEn ? 'AI Reasoning Engine' : 'مغز هوش مصنوعی و تحلیل'}</div>
    ${aiHtml}

    <div class="hub-footer">
      <button id="hub-goto-platforms-btn" class="text-teal-700 dark:text-teal-400 font-bold hover:underline flex items-center gap-1 transition">
        <span>${isEn ? 'Manage Channels' : 'مدیریت کامل پلتفرم‌ها'}</span>
        <svg class="w-3 h-3 rotate-180" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
      <button id="hub-scan-all-btn" class="px-2.5 py-1 rounded-full text-[11px] font-bold bg-teal-600 text-white hover:bg-teal-700 transition flex items-center gap-1">
        <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        <span>${isEn ? 'Scan All' : 'اسکن همه'}</span>
      </button>
    </div>
  `;

  box.querySelectorAll('.hub-quick-scan-btn').forEach(btn => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      const slug = btn.dataset.slug;
      btn.disabled = true;
      btn.innerHTML = `<span class="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin"></span>`;
      try {
        await api.post(`/platforms/${slug}/scan-now`);
        toast(isEn ? `Scan started for ${slug}` : `اسکن پلتفرم ${slug} آغاز شد`, 'success');
        setTimeout(() => loadPlatformHubDropdown(), 1500);
      } catch (err) {
        toast(err.message, 'error');
        btn.disabled = false;
        btn.innerHTML = `<span>${isEn ? 'Scan' : 'اسکن'}</span>`;
      }
    };
  });

  box.querySelectorAll('.hub-enable-btn').forEach(btn => {
    btn.onclick = () => {
      box.classList.add('hidden');
      document.getElementById('platform-hub-btn')?.classList.remove('is-active');
      navigate('platforms');
    };
  });

  box.querySelector('#hub-goto-platforms-btn')?.addEventListener('click', () => {
    box.classList.add('hidden');
    document.getElementById('platform-hub-btn')?.classList.remove('is-active');
    navigate('platforms');
  });

  box.querySelector('#hub-goto-ai-btn')?.addEventListener('click', () => {
    box.classList.add('hidden');
    document.getElementById('platform-hub-btn')?.classList.remove('is-active');
    navigate('ai');
  });

  box.querySelector('#hub-refresh-action')?.addEventListener('click', () => {
    loadPlatformHubDropdown();
  });

  box.querySelector('#hub-scan-all-btn')?.addEventListener('click', async () => {
    box.classList.add('hidden');
    document.getElementById('platform-hub-btn')?.classList.remove('is-active');
    const { triggerQuickScan } = await import('./command_palette.js');
    triggerQuickScan();
  });
}

// ---------------- build navigation ----------------
function buildNav() {
  const nav = document.getElementById('main-nav');
  if (!nav) return;

  const isEn = currentLang() === 'en';

  nav.innerHTML = RAIL_NAV.map(item => {
    const label = isEn ? item.label : (item.faLabel || t(item.id) || item.label);
    return `
      <div class="rail-item" data-page="${item.id}" title="${label}">
        <div class="rail-item-icon-box">
          ${icon(item.iconName, 'w-5 h-5')}
        </div>
        <span class="rail-item-label">${label}</span>
      </div>
    `;
  }).join('');

  nav.querySelectorAll('.rail-item').forEach(el => {
    el.onclick = () => {
      navigate(el.dataset.page);
      document.getElementById('sidebar')?.classList.remove('open');
      document.getElementById('sidebar-backdrop')?.classList.add('hidden');
    };
  });
}

function showApp(show) {
  const app = document.getElementById('app-view');
  const login = document.getElementById('login-view');
  if (app) app.classList.toggle('hidden', !show);
  if (login) login.classList.toggle('hidden', show);
}

// ---------------- boot ----------------
async function boot() {
  applyTheme();
  applyLang();
  bindUnlockOnce();
  buildNav();
  initCommandPalette();

  // Back Button
  const btnBack = document.getElementById('btn-back');
  if (btnBack) {
    btnBack.onclick = () => {
      const { page } = parseHash();
      if (page === 'overview') return;
      navigate('overview');
    };
  }

  // Theme Toggle
  const btnTheme = document.getElementById('btn-theme');
  if (btnTheme) {
    btnTheme.onclick = () => {
      const cur = localStorage.getItem('fa_theme') || 'light';
      const next = cur === 'dark' ? 'light' : 'dark';
      localStorage.setItem('fa_theme', next);
      applyTheme();
    };
  }

  // Language Toggle
  const btnLang = document.getElementById('btn-lang');
  if (btnLang) {
    btnLang.onclick = () => {
      const next = currentLang() === 'fa' ? 'en' : 'fa';
      setLang(next);
      buildNav();
      render();
      btnLang.textContent = next === 'fa' ? 'EN' : 'فا';
    };
    btnLang.textContent = currentLang() === 'fa' ? 'EN' : 'فا';
  }

  // Mobile menu button
  const btnMenu = document.getElementById('btn-menu');
  if (btnMenu) {
    btnMenu.onclick = () => {
      document.getElementById('sidebar')?.classList.add('open');
      document.getElementById('sidebar-backdrop')?.classList.remove('hidden');
    };
  }

  const sidebarBackdrop = document.getElementById('sidebar-backdrop');
  if (sidebarBackdrop) {
    sidebarBackdrop.onclick = () => {
      document.getElementById('sidebar')?.classList.remove('open');
      sidebarBackdrop.classList.add('hidden');
    };
  }

  // Bell Notifications Button
  const btnBell = document.getElementById('btn-bell');
  const bellDropdown = document.getElementById('bell-dropdown');
  if (btnBell && bellDropdown) {
    btnBell.onclick = async (e) => {
      e.stopPropagation();
      if (bellDropdown.classList.contains('hidden')) {
        await loadBellDropdown();
        bellDropdown.classList.remove('hidden');
      } else {
        bellDropdown.classList.add('hidden');
      }
    };
    document.addEventListener('click', (e) => {
      if (!bellDropdown.contains(e.target) && !btnBell.contains(e.target)) {
        bellDropdown.classList.add('hidden');
      }
    });
  }

  // Sound Chime Button
  const btnSound = document.getElementById('btn-sound');
  if (btnSound) {
    btnSound.onclick = async () => {
      const prefs = await api.get('/notifications/preferences');
      const next = !prefs.sound_enabled;
      await api.put('/notifications/preferences', { sound_enabled: next });
      setSoundPrefs(next, prefs.volume);
      const iconBox = document.getElementById('sound-icon-box');
      if (iconBox) {
        iconBox.innerHTML = icon(next ? 'sound' : 'soundOff', 'w-4 h-4');
      }
      toast(next ? 'صدای اعلان فعال شد' : 'صدای اعلان خاموش شد');
      if (next) playChime();
    };
  }

  // Platform Hub Status Toggle
  const platformHubBtn = document.getElementById('platform-hub-btn');
  const platformHubDropdown = document.getElementById('platform-hub-dropdown');
  if (platformHubBtn && platformHubDropdown) {
    platformHubBtn.onclick = async (e) => {
      e.stopPropagation();
      const isHidden = platformHubDropdown.classList.contains('hidden');
      if (isHidden) {
        platformHubBtn.classList.add('is-active');
        await loadPlatformHubDropdown();
        platformHubDropdown.classList.remove('hidden');
      } else {
        platformHubBtn.classList.remove('is-active');
        platformHubDropdown.classList.add('hidden');
      }
    };
    document.addEventListener('click', (e) => {
      if (!platformHubDropdown.contains(e.target) && !platformHubBtn.contains(e.target)) {
        platformHubBtn.classList.remove('is-active');
        platformHubDropdown.classList.add('hidden');
      }
    });
  }

  // Profile Quick Menu Toggle
  const userProfileBtn = document.getElementById('user-profile-btn');
  const userQuickMenu = document.getElementById('user-quick-menu');
  if (userProfileBtn && userQuickMenu) {
    userProfileBtn.onclick = (e) => {
      e.stopPropagation();
      userQuickMenu.classList.toggle('hidden');
    };
    document.addEventListener('click', (e) => {
      if (!userQuickMenu.contains(e.target)) {
        userQuickMenu.classList.add('hidden');
      }
    });

    document.getElementById('menu-btn-profile')?.addEventListener('click', () => {
      userQuickMenu.classList.add('hidden');
      navigate('profile');
    });
    document.getElementById('menu-btn-onboard')?.addEventListener('click', () => {
      userQuickMenu.classList.add('hidden');
      showOnboardingWizard();
    });
    document.getElementById('menu-btn-settings')?.addEventListener('click', () => {
      userQuickMenu.classList.add('hidden');
      navigate('settings');
    });
    document.getElementById('menu-btn-logout')?.addEventListener('click', () => {
      userQuickMenu.classList.add('hidden');
      setToken('');
      showApp(false);
    });
  }

  // ================= Nexus Authentication Suite =================
  const authTabSignin = document.getElementById('auth-tab-signin');
  const authTabSignup = document.getElementById('auth-tab-signup');
  const formSignin = document.getElementById('form-signin');
  const formSignup = document.getElementById('form-signup');
  const authAlert = document.getElementById('auth-alert');

  function showAuthAlert(message, type = 'error') {
    if (!authAlert) return;
    const isErr = type === 'error';
    authAlert.className = `text-xs p-3 rounded-xl mb-4 font-medium flex items-center gap-2.5 border ${
      isErr
        ? 'border-red-500/30 bg-red-500/10 text-red-400'
        : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
    }`;
    const iconSvg = isErr
      ? `<svg class="w-4 h-4 shrink-0 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`
      : `<svg class="w-4 h-4 shrink-0 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`;
    authAlert.innerHTML = `${iconSvg}<span>${message}</span>`;
    authAlert.classList.remove('hidden');
  }

  function hideAuthAlert() {
    if (authAlert) authAlert.classList.add('hidden');
  }

  // Animated Tab & Form Switching
  const authTabsWrap = document.getElementById('auth-tabs-wrap');
  const formsViewport = document.getElementById('auth-forms-viewport');
  const formHeader = document.querySelector('.nexus-form-header');
  const titleEl = document.getElementById('auth-panel-title');
  const subEl = document.getElementById('auth-panel-sub');

  let activeAuthTab = 'signin';

  function switchAuthTab(targetTab) {
    if (activeAuthTab === targetTab) return;
    activeAuthTab = targetTab;
    hideAuthAlert();

    const isSigningIn = targetTab === 'signin';

    // 1. Sliding indicator glider
    authTabSignin?.classList.toggle('active', isSigningIn);
    authTabSignup?.classList.toggle('active', !isSigningIn);
    authTabsWrap?.classList.toggle('signup-active', !isSigningIn);

    // 2. Crossfade header text
    if (formHeader) {
      formHeader.classList.add('is-switching');
      setTimeout(() => {
        if (titleEl) titleEl.textContent = isSigningIn ? 'ورود به پنل کاربری' : 'ایجاد حساب کاربری';
        if (subEl) subEl.textContent = isSigningIn
          ? 'جهت دسترسی به داشبورد و ابزارهای هوشمند وارد شوید'
          : 'اطلاعات حساب کاربری خود را جهت ثبت‌نام وارد کنید';
        formHeader.classList.remove('is-switching');
      }, 140);
    }

    // 3. Sliding forms with height adaptation
    if (formsViewport && formSignin && formSignup) {
      formSignin.classList.remove('hidden');
      formSignup.classList.remove('hidden');
      const currentHeight = formsViewport.offsetHeight;
      formsViewport.style.height = `${currentHeight}px`;

      if (isSigningIn) {
        // Switching to Sign In: Signup slides out to left, Signin enters from right
        formSignup.classList.remove('is-active', 'is-inactive-right');
        formSignup.classList.add('is-inactive-left');

        formSignin.classList.remove('is-inactive-left', 'is-inactive-right');
        formSignin.classList.add('is-active');
      } else {
        // Switching to Sign Up: Signin slides out to right, Signup enters from left
        formSignin.classList.remove('is-active', 'is-inactive-left');
        formSignin.classList.add('is-inactive-right');

        formSignup.classList.remove('is-inactive-left', 'is-inactive-right');
        formSignup.classList.add('is-active');
      }

      const targetForm = isSigningIn ? formSignin : formSignup;
      const targetHeight = targetForm.scrollHeight;

      requestAnimationFrame(() => {
        formsViewport.style.height = `${targetHeight}px`;
      });

      setTimeout(() => {
        if (formsViewport) formsViewport.style.height = '';
      }, 340);
    }
  }

  authTabSignin?.addEventListener('click', () => switchAuthTab('signin'));
  authTabSignup?.addEventListener('click', () => switchAuthTab('signup'));

  // Password Reveal / Hide Toggles
  document.querySelectorAll('.auth-toggle-pwd').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-target');
      const input = document.getElementById(targetId);
      if (!input) return;
      const isPwd = input.type === 'password';
      input.type = isPwd ? 'text' : 'password';
      btn.querySelector('.eye-open')?.classList.toggle('hidden', isPwd);
      btn.querySelector('.eye-closed')?.classList.toggle('hidden', !isPwd);
    });
  });

  // Sign In Form Handler
  if (formSignin) {
    formSignin.addEventListener('submit', async (e) => {
      e.preventDefault();
      hideAuthAlert();
      const submitBtn = document.getElementById('btn-submit-signin');
      const originalText = submitBtn ? submitBtn.innerHTML : '';
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span>در حال بررسی اطلاعات...</span>`;
      }
      try {
        const username = document.getElementById('login-username')?.value.trim();
        const password = document.getElementById('login-password')?.value;
        const data = await api.post('/auth/login', { username, password }, { noAuthRedirect: true });
        setToken(data.access_token);
        await start();
      } catch (ex) {
        showAuthAlert(ex.message || 'نام کاربری یا رمز عبور نامعتبر است.');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalText;
        }
      }
    });
  }

  // Sign Up Form Handler
  if (formSignup) {
    formSignup.addEventListener('submit', async (e) => {
      e.preventDefault();
      hideAuthAlert();

      const username = document.getElementById('signup-username')?.value.trim();
      const password = document.getElementById('signup-password')?.value;
      const confirmPassword = document.getElementById('signup-confirm-password')?.value;

      if (!username || username.length < 3) {
        showAuthAlert('نام کاربری باید حداقل ۳ کاراکتر باشد.');
        return;
      }
      if (/\s/.test(username)) {
        showAuthAlert('نام کاربری نباید شامل فاصله باشد.');
        return;
      }
      if (!password || password.length < 6) {
        showAuthAlert('رمز عبور باید حداقل ۶ کاراکتر باشد.');
        return;
      }
      if (password !== confirmPassword) {
        showAuthAlert('رمز عبور و تکرار آن یکسان نیستند.');
        return;
      }

      const submitBtn = document.getElementById('btn-submit-signup');
      const originalText = submitBtn ? submitBtn.innerHTML : '';
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span>در حال ساخت حساب کاربری...</span>`;
      }

      try {
        const data = await api.post('/auth/register', { username, password }, { noAuthRedirect: true });
        showAuthAlert('ثبت‌نام شما با موفقیت انجام شد! در حال هدایت به پنل نکسوس...', 'success');
        setToken(data.access_token);
        setTimeout(async () => {
          await start();
          toast(`خوش آمدید ${data.username}! حساب شما فعال شد.`);
          showOnboardingWizard(data.username);
        }, 500);
      } catch (ex) {
        showAuthAlert(ex.message || 'خطا در ثبت‌نام کاربر جدید.');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalText;
        }
      }
    });
  }

  window.showOnboardingWizard = showOnboardingWizard;
  window.addEventListener('fa:logout', () => { showApp(false); });
  window.addEventListener('hashchange', render);
  window.addEventListener('fa:refresh', () => render());

  let lastConfigToastTime = 0;
  onEvent(async (data) => {
    if (data.type === 'notification') {
      const isConfigMissing = (data.notification?.title || '').includes('پیکربندی نشده است') || (data.notification?.body || '').includes('پیکربندی نشده است');
      const kind = data.event_kind === 'analysis.failed' || (data.event_kind === 'submission.update' && (data.data?.status || '').includes('fail')) ? 'error' : 'info';

      // Throttle configuration errors so repeated scans don't barrage the screen
      if (isConfigMissing) {
        const now = Date.now();
        if (now - lastConfigToastTime < 30000) {
          refreshBell();
          return;
        }
        lastConfigToastTime = now;
      }

      toast(`<b>${esc(data.notification.title)}</b>${data.notification.body ? `<div class="text-[11px] opacity-90 mt-1">${esc(data.notification.body)}</div>` : ''}`, kind, 6000);
      if (kind !== 'error') playChime();
      refreshBell();
      if (['project.new', 'analysis.done', 'proposal.ready', 'submission.update'].includes(data.event_kind)) {
        window.dispatchEvent(new CustomEvent('fa:refresh'));
      }
    }
  });

  if (getToken()) await start(); else showApp(false);
}

async function start() {
  let me = null;
  try {
    me = await api.get('/auth/me');
    const menuUsername = document.getElementById('menu-username');
    if (menuUsername && me && me.username) {
      menuUsername.textContent = me.username;
    }
  } catch {
    showApp(false);
    return;
  }
  showApp(true);

  // Restore sound prefs
  try {
    const prefs = await api.get('/notifications/preferences');
    setSoundPrefs(prefs.sound_enabled, prefs.volume);
    const iconBox = document.getElementById('sound-icon-box');
    if (iconBox) {
      iconBox.innerHTML = icon(prefs.sound_enabled ? 'sound' : 'soundOff', 'w-4 h-4');
    }
  } catch { /* ignore */ }

  connectWS();
  refreshBell();
  if (!location.hash) location.hash = '#/overview';
  render();

  // If newly registered or profile is completely unconfigured, open onboarding wizard
  try {
    const prof = await api.get('/developer-profile');
    if (!prof.full_name && (!prof.skills || prof.skills.length === 0) && !sessionStorage.getItem('onboarding_dismissed')) {
      sessionStorage.setItem('onboarding_dismissed', '1');
      setTimeout(() => showOnboardingWizard(me?.username || ''), 600);
    }
  } catch { /* ignore */ }
}

export async function showOnboardingWizard(username = '') {
  let profile = null;
  try {
    profile = await api.get('/developer-profile').catch(() => null);
  } catch (e) {
    console.error('Failed loading profile for onboarding', e);
  }

  const existingSkills = (profile?.skills || []).map(s => s.name);
  const popularSkills = [
    'Python', 'FastAPI', 'Django', 'React', 'JavaScript',
    'Node.js', 'Web Scraping', 'Telegram Bot', 'WordPress',
    'Docker', 'PostgreSQL', 'UI/UX Design', 'AI & LLM'
  ];

  const m = modal('🚀 راه‌اندازی اولیه و تکمیل مشخصات فریلنسر', `
    <div class="space-y-4 text-xs text-slate-300">
      <div class="p-3.5 rounded-xl bg-teal-500/10 border border-teal-500/20 text-teal-300 text-xs leading-relaxed flex items-start gap-2.5">
        <span class="text-base">✨</span>
        <div>
          <b>خوش آمدید ${esc(username || 'همکار گرامی')}!</b><br>
          برای اینکه هوش مصنوعی نکسوس بتواند پروژه‌های متناسب با تخصص شما را در کارلنسر و پونیشا شناسایی کرده و پیشنهادهای هدفمند بنویسد، اطلاعات اولیه زیر را تکمیل نمایید:
        </div>
      </div>

      <!-- Full Name & Title -->
      <div class="grid sm:grid-cols-2 gap-3">
        <div>
          <label class="lbl block mb-1">نام و نام خانوادگی</label>
          <input id="ob-fullname" class="inp" placeholder="مثال: پارسا راد" value="${esc(profile?.full_name || '')}">
        </div>
        <div>
          <label class="lbl block mb-1">عنوان شغلی و حوزه فعالیت</label>
          <input id="ob-summary" class="inp" placeholder="مثال: توسعه‌دهنده پایتون، وب و ربات" value="${esc(profile?.summary || '')}">
        </div>
      </div>

      <!-- Skills Chips -->
      <div>
        <label class="lbl block mb-1.5">مهارت‌ها و فناوری‌های شما (کلیک برای انتخاب سریع)</label>
        <div class="flex flex-wrap gap-1.5 mb-2.5" id="ob-skills-chips">
          ${popularSkills.map(s => {
            const isSelected = existingSkills.some(es => es.toLowerCase() === s.toLowerCase());
            return `
              <button type="button" class="ob-chip px-2.5 py-1 rounded-lg text-xs font-medium transition cursor-pointer border ${isSelected ? 'bg-teal-500 text-slate-950 border-teal-400 font-bold' : 'bg-slate-800/80 text-slate-300 border-slate-700 hover:border-slate-500'}" data-skill="${esc(s)}">
                ${isSelected ? '✓ ' : '+ '}${esc(s)}
              </button>
            `;
          }).join('')}
        </div>
        <input id="ob-extra-skills" class="inp font-mono text-xs" placeholder="مهارت‌های دیگر (با کاما جدا کنید، مثلاً: Golang, Vue, Redis)">
      </div>

      <!-- Platforms to Scan -->
      <div>
        <label class="lbl block mb-1.5">پلتفرم‌های مدنظر برای پایش خودکار</label>
        <div class="grid sm:grid-cols-2 gap-2.5">
          <label class="flex items-center gap-2.5 p-3 rounded-xl bg-slate-800/50 border border-slate-700/80 hover:border-teal-500/50 transition cursor-pointer">
            <input type="checkbox" id="ob-plat-karlancer" checked class="rounded border-slate-600 bg-slate-900 text-teal-500 focus:ring-teal-400">
            <div>
              <div class="font-bold text-slate-100 flex items-center gap-1.5">
                <span>کارلنسر (Karlancer)</span>
                <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
              </div>
              <div class="text-[11px] text-slate-400">پایش مناقصات برنامه‌نویسی و وب</div>
            </div>
          </label>

          <label class="flex items-center gap-2.5 p-3 rounded-xl bg-slate-800/50 border border-slate-700/80 hover:border-teal-500/50 transition cursor-pointer">
            <input type="checkbox" id="ob-plat-ponisha" checked class="rounded border-slate-600 bg-slate-900 text-teal-500 focus:ring-teal-400">
            <div>
              <div class="font-bold text-slate-100 flex items-center gap-1.5">
                <span>پونیشا (Ponisha)</span>
                <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
              </div>
              <div class="text-[11px] text-slate-400">کشف سریع فرصت‌های فریلنسری</div>
            </div>
          </label>
        </div>
      </div>

      <!-- Min Budget Filter -->
      <div>
        <label class="lbl block mb-1">حداقل بودجه مطلوب پروژه‌ها (تومان - اختیاری)</label>
        <input id="ob-budget" type="number" class="inp font-mono" placeholder="مثال: ۲۰۰۰۰۰۰ (پروژه‌های زیر این مبلغ فیلتر می‌شوند)" value="${profile?.min_acceptable_budget || ''}">
      </div>

      <!-- Action Buttons -->
      <div class="pt-3 border-t border-slate-800 flex items-center justify-between gap-3">
        <button type="button" class="btn text-slate-400 hover:text-slate-200" id="ob-btn-skip">
          رد کردن این مرحله
        </button>
        <button type="button" class="btn-action-primary text-xs py-2 px-4 flex items-center gap-1.5" id="ob-btn-save">
          <span>ذخیره و شروع کار با نکسوس 🚀</span>
        </button>
      </div>
    </div>
  `);

  const selectedSkills = new Set(existingSkills);
  m.body.querySelectorAll('.ob-chip').forEach(btn => {
    btn.onclick = () => {
      const s = btn.dataset.skill;
      if (selectedSkills.has(s)) {
        selectedSkills.delete(s);
        btn.classList.remove('bg-teal-500', 'text-slate-950', 'border-teal-400', 'font-bold');
        btn.classList.add('bg-slate-800/80', 'text-slate-300', 'border-slate-700');
        btn.textContent = '+ ' + s;
      } else {
        selectedSkills.add(s);
        btn.classList.add('bg-teal-500', 'text-slate-950', 'border-teal-400', 'font-bold');
        btn.classList.remove('bg-slate-800/80', 'text-slate-300', 'border-slate-700');
        btn.textContent = '✓ ' + s;
      }
    };
  });

  m.body.querySelector('#ob-btn-skip').onclick = () => {
    m.close();
  };

  m.body.querySelector('#ob-btn-save').onclick = async () => {
    const saveBtn = m.body.querySelector('#ob-btn-save');
    saveBtn.disabled = true;
    saveBtn.textContent = 'در حال ذخیره‌سازی...';

    try {
      const fullName = m.body.querySelector('#ob-fullname').value.trim();
      const summary = m.body.querySelector('#ob-summary').value.trim();
      const extraSkillsStr = m.body.querySelector('#ob-extra-skills').value.trim();
      const budgetVal = m.body.querySelector('#ob-budget').value.trim();

      if (extraSkillsStr) {
        extraSkillsStr.split(/[,،]+/).forEach(s => {
          const clean = s.trim();
          if (clean) selectedSkills.add(clean);
        });
      }

      const allSkillsList = Array.from(selectedSkills);

      await api.put('/developer-profile', {
        full_name: fullName || username || null,
        summary: summary || null,
        preferred_technologies: allSkillsList,
        min_acceptable_budget: budgetVal ? Number(budgetVal) : null,
      });

      for (const s of allSkillsList) {
        await api.post('/developer-profile/skills', {
          name: s,
          level: 4,
          is_core: true,
        }).catch(() => {});
      }

      const karlancer = m.body.querySelector('#ob-plat-karlancer')?.checked ?? true;
      const ponisha = m.body.querySelector('#ob-plat-ponisha')?.checked ?? true;
      await api.put('/platforms/karlancer', { enabled: karlancer }).catch(() => {});
      await api.put('/platforms/ponisha', { enabled: ponisha }).catch(() => {});

      toast('🎉 پروفایل شما با موفقیت ذخیره شد! نکسوس پروژه‌ها را متناسب با تخصص شما اولویت‌بندی می‌کند.', 'success', 6000);
      m.close();
      window.dispatchEvent(new CustomEvent('fa:refresh'));
    } catch (err) {
      toast(`خطا در ذخیره‌سازی: ${err.message}`, 'error');
      saveBtn.disabled = false;
      saveBtn.textContent = 'ذخیره و شروع کار با نکسوس 🚀';
    }
  };
}

boot();
