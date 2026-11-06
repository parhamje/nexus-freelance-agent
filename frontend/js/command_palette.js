import { api, esc } from './api.js';
import { toast } from './ui.js';
import { currentLang } from './i18n.js';
import { navigate, applyTheme } from './app.js';

let isOpen = false;
let selectedIndex = 0;
let debounceTimer = null;
let currentItems = [];

const PAGES_LIST = [
  { id: 'overview', titleFa: 'داشبورد', titleEn: 'Dashboard', icon: 'dashboard', section: 'pages', descFa: 'نمای کلی، آمار سیستم و پروژه‌های برتر', descEn: 'Overview, stats and top performer projects' },
  { id: 'discovered', titleFa: 'پروژه‌ها', titleEn: 'Projects', icon: 'folder', section: 'pages', descFa: 'تمام پروژه‌های کشف‌شده از پلتفرم‌ها', descEn: 'All discovered freelance projects' },
  { id: 'proposals', titleFa: 'پیشنهادها و پروپوزال‌ها', titleEn: 'Proposals', icon: 'file', section: 'pages', descFa: 'پیش‌نویس‌ها و پیشنهادهای ارسالی', descEn: 'Draft and submitted proposals' },
  { id: 'platforms', titleFa: 'کانال‌ها و پلتفرم‌ها', titleEn: 'Channels', icon: 'signal', section: 'pages', descFa: 'اتصال کارلنسر، پونیشا و لاگ اسکن‌ها', descEn: 'Platform connections & scan logs' },
  { id: 'analytics', titleFa: 'آمار و بینش‌ها', titleEn: 'Analytics', icon: 'chart', section: 'pages', descFa: 'نمودار عملکرد، درآمد و شانس برد', descEn: 'Performance charts & win rates' },
  { id: 'ai', titleFa: 'تأمین‌کنندگان هوش مصنوعی', titleEn: 'AI Providers', icon: 'cpu', section: 'pages', descFa: 'پیکربندی کلیدهای API و مدل‌ها', descEn: 'AI models & API keys' },
  { id: 'agentconfig', titleFa: 'تنظیمات ایجنت', titleEn: 'Agent Settings', icon: 'sliders', section: 'pages', descFa: 'استراتژی مناقصه، قوانین فیلتر و پرامپت‌ها', descEn: 'Bidding rules & autonomy' },
  { id: 'profile', titleFa: 'مشخصات و مهارت‌های شما', titleEn: 'Verified Profile', icon: 'user', section: 'pages', descFa: 'سوابق، رزومه و مهارت‌های تخصصی', descEn: 'Work history, skills & rates' },
  { id: 'settings', titleFa: 'تنظیمات عمومی', titleEn: 'Settings', icon: 'settings', section: 'pages', descFa: 'تنظیمات کلی سیستم و اعلان‌ها', descEn: 'General preferences' },
];

const ACTIONS_LIST = [
  {
    id: 'act-scan',
    titleFa: 'اسکن آنی پلتفرم‌ها',
    titleEn: 'Quick Scan Platforms',
    icon: 'zap',
    section: 'actions',
    descFa: 'استعلام فوری پروژه‌های جدید از کارلنسر و پونیشا',
    descEn: 'Trigger immediate background discovery',
    run: () => triggerQuickScan()
  },
  {
    id: 'act-theme',
    titleFa: 'تغییر حالت تم (روشن / تاریک)',
    titleEn: 'Toggle Dark / Light Mode',
    icon: 'moon',
    section: 'actions',
    descFa: 'سوییچ بین تم تیره و روشن نرم‌افزار',
    descEn: 'Switch dark/light theme',
    run: () => toggleThemeAction()
  },
  {
    id: 'act-lang',
    titleFa: 'تغییر زبان (فارسی / English)',
    titleEn: 'Toggle Language',
    icon: 'globe',
    section: 'actions',
    descFa: 'تغییر زبان رابط کاربری',
    descEn: 'Switch Persian / English',
    run: () => toggleLangAction()
  },
  {
    id: 'act-markread',
    titleFa: 'علامت‌گذاری همه اعلان‌ها به عنوان خوانده‌شده',
    titleEn: 'Mark All Notifications Read',
    icon: 'check',
    section: 'actions',
    descFa: 'صفر کردن نشانگر اعلان‌های جدید',
    descEn: 'Clear unread notification count',
    run: () => markAllNotificationsRead()
  },
];

function toggleThemeAction() {
  const current = localStorage.getItem('fa_theme') || 'light';
  const next = current === 'dark' ? 'light' : 'dark';
  localStorage.setItem('fa_theme', next);
  applyTheme();
}

function toggleLangAction() {
  const cur = currentLang();
  const next = cur === 'fa' ? 'en' : 'fa';
  localStorage.setItem('fa_lang', next);
  location.reload();
}

async function markAllNotificationsRead() {
  try {
    await api.post('/notifications/read-all');
    toast(currentLang() === 'en' ? 'All notifications marked as read' : 'تمام اعلان‌ها خوانده شدند', 'success');
    window.dispatchEvent(new CustomEvent('fa:refresh'));
    const bellBadge = document.getElementById('bell-badge');
    if (bellBadge) bellBadge.classList.add('hidden');
  } catch (e) {
    toast(e.message, 'error');
  }
}

export async function triggerQuickScan() {
  const btn = document.getElementById('btn-topbar-quick-scan');
  const icon = document.getElementById('topbar-scan-icon');
  const text = document.getElementById('topbar-scan-text');

  if (btn && btn.dataset.scanning === 'true') return;
  if (btn) {
    btn.dataset.scanning = 'true';
    btn.classList.add('is-scanning');
  }
  if (icon) icon.classList.add('animate-spin');
  const isEn = currentLang() === 'en';
  if (text) text.textContent = isEn ? 'Scanning...' : 'در حال اسکن...';

  toast(isEn ? '⚡ Scanning platforms for new projects...' : '⚡ در حال استعلام و اسکن پروژه‌های جدید از پلتفرم‌ها...', 'info', 4000);

  try {
    const res = await api.get('/platforms');
    const plats = res.items || [];
    const enabledPlats = plats.filter(p => p.enabled);
    if (!enabledPlats.length) {
      toast(isEn ? 'No enabled platforms to scan' : 'هیچ پلتفرم فعالی برای اسکن یافت نشد (ابتدا پلتفرم را فعال کنید)', 'error');
      return;
    }
    const results = await Promise.all(
      enabledPlats.map(p => api.post(`/platforms/${p.slug}/scan-now`).catch(e => ({ error: e.message })))
    );
    const hasSuccess = results.some(r => r && r.started);
    if (hasSuccess) {
      toast(isEn ? 'Scan initiated across platforms' : 'اسکن با موفقیت در پس‌زمینه آغاز شد؛ پروژه‌های جدید به‌زودی افزوده می‌شوند', 'success', 4000);
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent('fa:refresh'));
      }, 2500);
    } else {
      toast(isEn ? 'Could not trigger scan' : 'خطا در آغاز اسکن پلتفرم‌ها', 'error');
    }
  } catch (err) {
    toast(err.message || 'خطا در اجرای اسکن', 'error');
  } finally {
    setTimeout(() => {
      if (btn) {
        btn.dataset.scanning = 'false';
        btn.classList.remove('is-scanning');
      }
      if (icon) icon.classList.remove('animate-spin');
      if (text) text.textContent = isEn ? 'Quick Scan' : 'اسکن آنی';
    }, 1500);
  }
}

export function openCommandPalette() {
  const backdrop = document.getElementById('cmd-palette-backdrop');
  const input = document.getElementById('cmd-palette-input');
  if (!backdrop || !input) return;

  isOpen = true;
  backdrop.classList.remove('hidden');
  document.body.classList.add('overflow-hidden');
  input.value = '';
  selectedIndex = 0;
  loadDefaultItems();
  setTimeout(() => input.focus(), 50);
}

export function closeCommandPalette() {
  const backdrop = document.getElementById('cmd-palette-backdrop');
  if (!backdrop) return;
  isOpen = false;
  backdrop.classList.add('hidden');
  document.body.classList.remove('overflow-hidden');
}

async function loadDefaultItems() {
  const isEn = currentLang() === 'en';
  let recentProjects = [];
  try {
    const res = await api.get('/projects?limit=4');
    recentProjects = (res.items || []).map(p => ({
      id: `proj-${p.id}`,
      project: p,
      titleFa: p.title,
      titleEn: p.title,
      icon: 'briefcase',
      section: 'projects',
      descFa: `${p.platform_name || p.platform || ''} • امتیاز تطابق: ${p.match_score ?? 'در انتظار'}`,
      descEn: `${p.platform_name || p.platform || ''} • Match: ${p.match_score ?? 'Pending'}`,
    }));
  } catch {
    recentProjects = [];
  }

  currentItems = [
    ...ACTIONS_LIST,
    ...PAGES_LIST,
    ...recentProjects,
  ];
  selectedIndex = 0;
  renderPaletteResults();
}

async function performSearch(query) {
  const q = query.trim().toLowerCase();
  const isEn = currentLang() === 'en';

  if (!q) {
    await loadDefaultItems();
    return;
  }

  // Filter local actions and pages
  const matchedActions = ACTIONS_LIST.filter(a =>
    a.titleFa.toLowerCase().includes(q) ||
    a.titleEn.toLowerCase().includes(q) ||
    a.descFa.toLowerCase().includes(q) ||
    a.descEn.toLowerCase().includes(q)
  );

  const matchedPages = PAGES_LIST.filter(p =>
    p.titleFa.toLowerCase().includes(q) ||
    p.titleEn.toLowerCase().includes(q) ||
    p.id.toLowerCase().includes(q) ||
    p.descFa.toLowerCase().includes(q)
  );

  let matchedProjects = [];
  try {
    const res = await api.get(`/projects?limit=6&q=${encodeURIComponent(q)}`);
    matchedProjects = (res.items || []).map(p => ({
      id: `proj-${p.id}`,
      project: p,
      titleFa: p.title,
      titleEn: p.title,
      icon: 'briefcase',
      section: 'projects',
      descFa: `${p.platform_name || p.platform || ''} • امتیاز: ${p.match_score ?? '—'}`,
      descEn: `${p.platform_name || p.platform || ''} • Score: ${p.match_score ?? '—'}`,
    }));
  } catch {
    matchedProjects = [];
  }

  currentItems = [
    ...matchedActions,
    ...matchedProjects,
    ...matchedPages,
  ];
  selectedIndex = 0;
  renderPaletteResults();
}

function renderPaletteResults() {
  const container = document.getElementById('cmd-palette-results');
  if (!container) return;

  const isEn = currentLang() === 'en';

  if (!currentItems.length) {
    container.innerHTML = `
      <div class="p-8 text-center text-slate-400 dark:text-slate-500 text-sm">
        <svg class="w-8 h-8 mx-auto mb-2 opacity-40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        ${isEn ? 'No results found for your search' : 'هیچ موردی مطابق با جستجوی شما یافت نشد'}
      </div>
    `;
    return;
  }

  const sections = [
    { key: 'actions', titleFa: 'اقدامات سریع', titleEn: 'Quick Actions' },
    { key: 'projects', titleFa: 'پروژه‌ها', titleEn: 'Projects' },
    { key: 'pages', titleFa: 'صفحات و بخش‌ها', titleEn: 'Navigation Pages' },
  ];

  let html = '';
  let globalIndex = 0;

  for (const sec of sections) {
    const itemsInSec = currentItems.filter(item => item.section === sec.key);
    if (!itemsInSec.length) continue;

    html += `
      <div class="cmd-section-header">
        ${isEn ? sec.titleEn : sec.titleFa}
      </div>
    `;

    for (const item of itemsInSec) {
      const idx = globalIndex++;
      const isSelected = idx === selectedIndex;
      const title = isEn ? item.titleEn : item.titleFa;
      const desc = isEn ? item.descEn : item.descFa;

      let badgeHtml = '';
      if (item.section === 'projects' && item.project) {
        const score = item.project.match_score;
        if (score != null) {
          const scoreClass = score >= 75 ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' : score >= 50 ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/20' : 'bg-slate-500/15 text-slate-500 border-slate-500/20';
          badgeHtml = `<span class="px-2 py-0.5 rounded-full text-[10px] font-bold border ${scoreClass}">٪${score}</span>`;
        }
      }

      html += `
        <div class="cmd-item ${isSelected ? 'selected' : ''}" data-index="${idx}">
          <div class="cmd-item-icon">
            ${getIconSvg(item.icon)}
          </div>
          <div class="cmd-item-text">
            <div class="cmd-item-title">${esc(title)}</div>
            ${desc ? `<div class="cmd-item-desc">${esc(desc)}</div>` : ''}
          </div>
          ${badgeHtml}
          <div class="cmd-item-arrow">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
          </div>
        </div>
      `;
    }
  }

  container.innerHTML = html;

  container.querySelectorAll('.cmd-item').forEach(el => {
    el.addEventListener('mouseenter', () => {
      selectedIndex = parseInt(el.dataset.index, 10);
      updateSelectionClass();
    });
    el.addEventListener('click', () => {
      executeSelected();
    });
  });

  scrollSelectedIntoView();
}

function updateSelectionClass() {
  const container = document.getElementById('cmd-palette-results');
  if (!container) return;
  container.querySelectorAll('.cmd-item').forEach(el => {
    const idx = parseInt(el.dataset.index, 10);
    el.classList.toggle('selected', idx === selectedIndex);
  });
}

function scrollSelectedIntoView() {
  const container = document.getElementById('cmd-palette-results');
  if (!container) return;
  const selEl = container.querySelector(`.cmd-item[data-index="${selectedIndex}"]`);
  if (selEl) {
    selEl.scrollIntoView({ block: 'nearest' });
  }
}

function executeSelected() {
  if (selectedIndex < 0 || selectedIndex >= currentItems.length) return;
  const item = currentItems[selectedIndex];
  closeCommandPalette();

  if (item.section === 'actions' && typeof item.run === 'function') {
    item.run();
  } else if (item.section === 'projects' && item.project) {
    navigate('discovered', { detail: item.project.id });
    window.dispatchEvent(new CustomEvent('fa:open-project', { detail: item.project.id }));
  } else if (item.section === 'pages') {
    navigate(item.id);
  }
}

function getIconSvg(iconName) {
  switch (iconName) {
    case 'zap':
      return `<svg class="w-4 h-4 text-amber-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`;
    case 'moon':
      return `<svg class="w-4 h-4 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
    case 'globe':
      return `<svg class="w-4 h-4 text-sky-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`;
    case 'check':
      return `<svg class="w-4 h-4 text-emerald-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;
    case 'briefcase':
      return `<svg class="w-4 h-4 text-teal-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>`;
    case 'dashboard':
      return `<svg class="w-4 h-4 text-blue-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/></svg>`;
    case 'folder':
      return `<svg class="w-4 h-4 text-cyan-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;
    case 'file':
      return `<svg class="w-4 h-4 text-emerald-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`;
    case 'signal':
      return `<svg class="w-4 h-4 text-violet-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 20h.01"/><path d="M7 20v-4"/><path d="M12 20v-8"/><path d="M17 20V4"/></svg>`;
    case 'chart':
      return `<svg class="w-4 h-4 text-amber-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`;
    case 'cpu':
      return `<svg class="w-4 h-4 text-fuchsia-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>`;
    case 'sliders':
      return `<svg class="w-4 h-4 text-teal-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>`;
    case 'user':
      return `<svg class="w-4 h-4 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
    default:
      return `<svg class="w-4 h-4 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
  }
}

export function initCommandPalette() {
  const triggerBtn = document.getElementById('btn-topbar-search');
  const mobileTriggerBtn = document.getElementById('btn-mobile-search');
  const quickScanBtn = document.getElementById('btn-topbar-quick-scan');
  const backdrop = document.getElementById('cmd-palette-backdrop');
  const input = document.getElementById('cmd-palette-input');

  if (triggerBtn) {
    triggerBtn.addEventListener('click', openCommandPalette);
  }
  if (mobileTriggerBtn) {
    mobileTriggerBtn.addEventListener('click', openCommandPalette);
  }
  if (quickScanBtn) {
    quickScanBtn.addEventListener('click', triggerQuickScan);
  }

  if (backdrop) {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        closeCommandPalette();
      }
    });
  }

  if (input) {
    input.addEventListener('input', (e) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        performSearch(e.target.value);
      }, 150);
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (currentItems.length > 0) {
          selectedIndex = (selectedIndex + 1) % currentItems.length;
          updateSelectionClass();
          scrollSelectedIntoView();
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (currentItems.length > 0) {
          selectedIndex = (selectedIndex - 1 + currentItems.length) % currentItems.length;
          updateSelectionClass();
          scrollSelectedIntoView();
        }
      } else if (e.key === 'Enter') {
        e.preventDefault();
        executeSelected();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        closeCommandPalette();
      }
    });
  }

  // Global Keydown Listeners for Ctrl+K, Cmd+K, Escape
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (isOpen) {
        closeCommandPalette();
      } else {
        openCommandPalette();
      }
    } else if (e.key === 'Escape' && isOpen) {
      e.preventDefault();
      closeCommandPalette();
    }
  });
}
