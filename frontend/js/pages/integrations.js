// Integrations: platforms, telegram, AI providers
import { api, fa, esc } from '../api.js';
import { badge, modal, confirmModal, spinner, emptyState, toast } from '../ui.js';
import { render, navigate } from '../app.js';
import { currentLang } from '../i18n.js';
import { icon } from '../icons.js';

export function channelSubTabs(activeKey) {
  const isEn = currentLang() === 'en';
  const tabs = [
    { id: 'platforms', label: isEn ? 'Freelance Platforms' : 'پلتفرم‌های فریلنسری', iconName: 'folder' },
    { id: 'ai', label: isEn ? 'AI Providers' : 'تأمین‌کنندگان هوش مصنوعی', iconName: 'cpu' },
    { id: 'telegram', label: isEn ? 'Telegram Bot' : 'ربات تلگرام', iconName: 'plane' },
  ];
  return `
    <div class="flex items-center gap-2 mb-6 overflow-x-auto pb-1">
      ${tabs.map(t => `
        <button class="sub-tab-pill ${activeKey === t.id ? 'active' : ''}" data-ch-nav="${t.id}">
          ${icon(t.iconName, 'w-3.5 h-3.5 inline me-1.5')}${t.label}
        </button>
      `).join('')}
    </div>
  `;
}

function bindChannelSubTabs(container) {
  container.querySelectorAll('[data-ch-nav]').forEach(b => {
    b.onclick = () => navigate(b.dataset.chNav);
  });
}

const CAP_FA = {
  fetch_projects: 'کشف پروژه', fetch_details: 'جزئیات', check_availability: 'بررسی موجودی',
  submit_proposal: 'ارسال API', submit_method: 'روش ارسال', verified: 'تأییدشده روی پلتفرم واقعی',
};

// ------------------------------ platforms -------------------------------- //
export const platforms = {
  title: () => 'اتصال پلتفرم‌ها',
  async render(container) {
    container.innerHTML = spinner();
    const data = await api.get('/platforms');
    container.innerHTML = `
      ${channelSubTabs('platforms')}
      <div class="text-xs text-neutral-500 mb-5 leading-6">
        هر پلتفرم کانکتور مستقل خودش را دارد. ارسال خودکار پیشنهاد فقط از طریق API رسمی/مجاز انجام می‌شود؛
        پلتفرم‌هایی که API عمومی ندارند در «گردش کار دستی» پشتیبانی می‌شوند: متن و قیمت آماده می‌شود و ارسال با تأیید خودتان انجام می‌گیرد.
      </div>
      <div class="grid md:grid-cols-2 gap-4">${data.items.map(platformCard).join('')}</div>`;
    bindChannelSubTabs(container);

    container.querySelectorAll('[data-plat]').forEach(card => {
      const slug = card.dataset.plat;
      card.querySelector('[data-toggle]').onchange = async (e) => {
        try {
          await api.put(`/platforms/${slug}`, { enabled: e.target.checked });
          toast(`پلتفرم ${e.target.checked ? 'فعال' : 'غیرفعال'} شد`, 'success');
        } catch (err) { toast(err.message, 'error'); e.target.checked = !e.target.checked; }
      };
      card.querySelector('[data-test]').onclick = async () => {
        toast('در حال تست اتصال…');
        try {
          const r = await api.post(`/platforms/${slug}/test`);
          toast(r.ok ? `✅ ${r.message}` : `❌ ${r.message}`, r.ok ? 'success' : 'error', 8000);
          render();
        } catch (err) { toast(err.message, 'error'); }
      };
      card.querySelector('[data-scan]').onclick = async () => {
        try { await api.post(`/platforms/${slug}/scan-now`); toast('اسکن آغاز شد؛ نتیجه در اعلان‌ها و لاگ اسکن دیده می‌شود', 'success'); }
        catch (err) { toast(err.message, 'error'); }
      };
      card.querySelector('[data-logs]').onclick = () => showScanLogs(slug);
      card.querySelector('[data-creds]').onclick = () => showCredentials(slug);
      card.querySelector('[data-interval]').onchange = async (e) => {
        await api.put(`/platforms/${slug}`, { scan_interval_minutes: Number(e.target.value) });
        toast('فاصله اسکن ذخیره شد', 'success');
      };
    });
  },
};

function platformCard(p) {
  const caps = p.capabilities || {};
  const statusColor = { connected: 'green', error: 'red', unknown: 'neutral', disconnected: 'neutral' }[p.connection_status] || 'neutral';
  const statusFa = { connected: 'متصل', error: 'خطا', unknown: 'تست نشده', disconnected: 'قطع' }[p.connection_status] || p.connection_status;
  return `<div class="card p-5 space-y-4 border border-slate-200/80 dark:border-slate-800 shadow-sm hover:shadow-md transition rounded-2xl" data-plat="${p.slug}">
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <span class="plat-logo shadow-xs" style="background:${{ karlancer: '#1c6d81', ponisha: '#2563eb', parscoders: '#0d9488', demo: '#64748b' }[p.slug] || '#64748b'}">${p.name.charAt(0)}</span>
        <div class="min-w-0">
          <div class="font-bold text-sm text-slate-800 dark:text-slate-100 flex items-center gap-2">
            <span>${p.name}</span>
            <span class="w-2 h-2 rounded-full ${p.enabled ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}" title="${p.enabled ? 'فعال' : 'غیرفعال'}"></span>
          </div>
          <a href="${esc(p.base_url)}" target="_blank" rel="noopener" class="text-[11px] text-slate-400 hover:text-teal-600 dark:hover:text-teal-400 transition truncate block">${esc(p.base_url)}</a>
        </div>
      </div>

      <!-- Modern Switch Toggle -->
      <label class="switch-toggle" title="${p.enabled ? 'پلتفرم فعال است' : 'پلتفرم غیرفعال است'}">
        <input type="checkbox" data-toggle ${p.enabled ? 'checked' : ''}>
        <span class="switch-slider"></span>
      </label>
    </div>

    <!-- Status Badges -->
    <div class="flex flex-wrap items-center gap-2">
      ${badge(statusFa, statusColor)}
      ${caps.verified ? badge('✓ تأییدشده', 'green') : badge('نیازمند تست', 'amber')}
      ${caps.submit_method === 'assisted' ? badge('ارسال دستی (تأیید دوبل)', 'sky') : caps.submit_method === 'api' ? badge('ارسال خودکار API', 'green') : ''}
      ${caps.requires_credentials ? badge('نیازمند کوکی ورود', 'amber') : ''}
    </div>

    ${p.last_error ? `<div class="text-[11px] text-rose-500 bg-rose-500/10 border border-rose-500/20 rounded-xl p-2.5 leading-relaxed">${esc(p.last_error.slice(0, 200))}</div>` : ''}

    <div class="flex flex-wrap items-center justify-between gap-2 text-xs pt-1">
      <div class="flex items-center gap-2">
        <label class="text-slate-500 dark:text-slate-400 font-medium">فاصله اسکن (دقیقه):</label>
        <input type="number" min="5" class="inp max-w-20 py-1 text-center font-bold font-sans text-xs" data-interval value="${p.scan_interval_minutes || 20}">
      </div>
      <div class="text-[11px] text-slate-400">آخرین اسکن موفق: ${fa.datetime(p.last_success_scan_at)}</div>
    </div>

    <!-- Action Buttons with Executive Styling -->
    <div class="flex flex-wrap items-center gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
      <button class="btn-action" data-test title="تست اتصال پلتفرم">
        ${icon('channels', 'w-3.5 h-3.5 text-teal-600 dark:text-teal-400')}
        <span>تست اتصال</span>
      </button>
      <button class="btn-action-primary" data-scan title="اجرای اسکن فوری">
        ${icon('refresh', 'w-3.5 h-3.5')}
        <span>اسکن فوری</span>
      </button>
      <button class="btn-action" data-logs title="مشاهده لاگ‌های اسکن">
        ${icon('reports', 'w-3.5 h-3.5 text-slate-500')}
        <span>لاگ اسکن</span>
      </button>
      <button class="btn-action" data-creds title="پیکربندی اطلاعات ورود">
        ${icon('settings', 'w-3.5 h-3.5 text-slate-500')}
        <span>اطلاعات ورود</span>
      </button>
    </div>
  </div>`;
}

async function showScanLogs(slug) {
  const data = await api.get(`/platforms/${slug}/scan-logs`);
  modal(`🧾 لاگ اسکن — ${slug}`, data.items.length ? `
    <table class="tbl"><thead><tr><th>زمان</th><th>وضعیت</th><th>یافته</th><th>جدید</th><th>تکراری</th><th>فیلتر</th><th>خطا</th></tr></thead>
    <tbody>${data.items.map(l => `<tr>
      <td class="text-[11px]">${fa.datetime(l.started_at)}</td>
      <td>${badge(l.status === 'success' ? 'موفق' : l.status === 'failed' ? 'ناموفق' : 'در اجرا', l.status === 'success' ? 'green' : l.status === 'failed' ? 'red' : 'amber')}</td>
      <td>${l.projects_found}</td><td>${l.projects_new}</td><td>${l.duplicates}</td><td>${l.filtered}</td>
      <td class="text-[10px] text-red-400 max-w-40 truncate">${esc(l.error || '')}</td>
    </tr>`).join('')}</tbody></table>` : emptyState('لاگی ثبت نشده است'));
}

function showCredentials(slug) {
  const m = modal(`اطلاعات ورود — ${slug}`, `
    <div class="space-y-3 text-xs">
      <p class="text-neutral-500 leading-6">اگر پلتفرم برای دسترسی به اطلاعات بیشتر نیاز به کوکی/توکن حساب شما دارد، اینجا (رمزنگاری‌شده) ذخیره می‌شود و هرگز در پاسخ‌های API بازگردانده نمی‌شود. برای پلتفرم‌های فعلی نیازی نیست.</p>
      <textarea id="creds-json" class="inp-area text-xs" placeholder='{"cookie": "..."}'></textarea>
      <div class="flex gap-2 justify-end">
        <button class="btn btn-danger" data-clear>حذف اطلاعات</button>
        <button class="btn btn-primary" data-save>ذخیره</button>
      </div>
    </div>`);
  m.body.querySelector('[data-save]').onclick = async () => {
    try {
      const creds = JSON.parse(m.body.querySelector('#creds-json').value || '{}');
      await api.put(`/platforms/${slug}/credentials`, { credentials: creds });
      toast('اطلاعات رمزنگاری و ذخیره شد', 'success'); m.close();
    } catch (e) { toast('JSON نامعتبر است', 'error'); }
  };
  m.body.querySelector('[data-clear]').onclick = async () => {
    await api.del(`/platforms/${slug}/credentials`);
    toast('حذف شد'); m.close();
  };
}

// ------------------------------ telegram --------------------------------- //
export const telegram = {
  title: () => 'ربات تلگرام',
  async render(container) {
    container.innerHTML = spinner();
    const [s, chats] = await Promise.all([
      api.get('/telegram/settings').catch(() => ({})),
      api.get('/telegram/chats').catch(() => ({ items: [] })),
    ]);

    const isConnected = s.connection_status === 'connected';
    const isError = s.connection_status === 'error';
    const botUser = s.bot_username ? s.bot_username.replace(/^@/, '') : '';
    const activeChatsCount = (chats.items || []).filter(c => c.authorized).length;

    container.innerHTML = `
      ${channelSubTabs('telegram')}

      <!-- Hero Header & Live Telemetry -->
      <div class="relative overflow-hidden rounded-2xl bg-gradient-to-r from-slate-900 via-slate-800 to-sky-950 p-6 border border-slate-700/60 shadow-xl mb-6 text-white">
        <div class="absolute -end-10 -bottom-10 w-48 h-48 bg-sky-500/10 rounded-full blur-3xl pointer-events-none"></div>
        <div class="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div class="flex items-center gap-4">
            <div class="w-14 h-14 rounded-2xl bg-gradient-to-tr from-sky-600 to-teal-400 p-0.5 shadow-lg shadow-sky-500/20 shrink-0 flex items-center justify-center">
              <div class="w-full h-full bg-slate-900/40 rounded-[14px] flex items-center justify-center text-white">
                ${icon('telegram', 'w-8 h-8')}
              </div>
            </div>
            <div>
              <div class="flex items-center gap-2.5">
                <h2 class="text-lg font-bold tracking-tight">مرکز ارتباط و ربات اختصاصی تلگرام</h2>
                ${isConnected ? `
                  <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                    <span>آنلاین و فعال</span>
                  </span>
                ` : isError ? `
                  <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                    <span class="w-2 h-2 rounded-full bg-rose-400"></span>
                    <span>خطای اتصال توکن</span>
                  </span>
                ` : `
                  <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-500/20 text-slate-300 border border-slate-600/40">
                    <span class="w-2 h-2 rounded-full bg-slate-400"></span>
                    <span>قطع اتصال</span>
                  </span>
                `}
              </div>
              <p class="text-xs text-slate-300/80 mt-1">
                پایش لحظه‌ای مناقصات، ارسال خودکار پروژه‌ها با امتیاز بالا، و دریافت تاییدیه پیشنهادها در پیام‌رسان تلگرام
              </p>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2 text-xs">
            <div class="px-3 py-1.5 rounded-xl bg-white/5 border border-white/10 flex items-center gap-2 backdrop-blur-xs">
              <span class="text-slate-400">ربات:</span>
              ${botUser ? `
                <a href="https://t.me/${botUser}" target="_blank" class="font-mono text-sky-400 hover:underline flex items-center gap-1 font-semibold">
                  @${esc(botUser)}
                  ${icon('external', 'w-3 h-3')}
                </a>
              ` : `<span class="text-slate-400 font-mono">تنظیم نشده</span>`}
            </div>
            <div class="px-3 py-1.5 rounded-xl bg-white/5 border border-white/10 flex items-center gap-2 backdrop-blur-xs">
              <span class="text-slate-400">چت‌های متصل:</span>
              <span class="font-bold text-emerald-400">${activeChatsCount} فعال</span>
            </div>
            <div class="px-3 py-1.5 rounded-xl bg-white/5 border border-white/10 flex items-center gap-2 backdrop-blur-xs">
              <span class="text-slate-400">حالت کار:</span>
              <span class="font-semibold text-teal-300">${s.enabled ? 'Polling پس‌زمینه' : 'غیرفعال'}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Main Studio Grid -->
      <div class="grid lg:grid-cols-12 gap-5 mb-6">

        <!-- Column 1: Credentials & Engine Controls (7 cols) -->
        <div class="lg:col-span-7 space-y-4">
          <div class="card p-5 border border-slate-200/80 dark:border-slate-800 shadow-xs space-y-4">
            <div class="flex items-center justify-between">
              <h3 class="font-bold text-sm flex items-center gap-2 text-slate-800 dark:text-slate-100">
                <span class="w-7 h-7 rounded-lg bg-teal-500/10 text-teal-500 flex items-center justify-center">
                  ${icon('cpu', 'w-4 h-4')}
                </span>
                <span>تنظیمات توکن ربات و موتور پردازش</span>
              </h3>
              ${s.last_check_at ? `
                <span class="text-[10px] text-slate-400 font-mono">بررسی: ${new Date(s.last_check_at).toLocaleTimeString('fa-IR')}</span>
              ` : ''}
            </div>

            <!-- Token Input with Show/Hide Toggle -->
            <div>
              <label class="lbl flex items-center justify-between">
                <span>توکن اختصاصی ربات (BotFather HTTP API Token)</span>
                ${s.has_token ? `
                  <span class="text-[10px] text-emerald-500 font-semibold flex items-center gap-1">
                    ${icon('check', 'w-3 h-3')} توکن ذخیره شده (${esc(s.bot_token_masked)})
                  </span>
                ` : `<span class="text-[10px] text-amber-500">توکن ثبت نشده</span>`}
              </label>
              <div class="relative mt-1">
                <input id="tg-token" type="password" class="inp pe-10 font-mono text-xs" placeholder="${s.has_token ? 'برای تغییر توکن، مقدار جدید را وارد کنید...' : '123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ...'}" autocomplete="off">
                <button type="button" id="toggle-token-vis" class="absolute end-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition p-1" title="نمایش/پنهان کردن توکن">
                  <span id="token-eye-icon">${icon('eye', 'w-4 h-4')}</span>
                </button>
              </div>
            </div>

            <!-- Toolbar Action Buttons -->
            <div class="flex flex-wrap items-center gap-2 pt-1">
              <button class="btn-action-primary" id="tg-save">
                ${icon('check', 'w-3.5 h-3.5')}
                <span>ذخیره و فعال‌سازی ربات</span>
              </button>
              <button class="btn-action" id="tg-test">
                ${icon('activity', 'w-3.5 h-3.5 text-teal-600')}
                <span>تست اتصال زنده</span>
              </button>
              <button class="btn-action" id="tg-send">
                ${icon('plane', 'w-3.5 h-3.5 text-sky-500')}
                <span>ارسال پیام تست همگانی</span>
              </button>
              ${s.has_token ? `
                <button class="btn-action text-rose-600 dark:text-rose-400 hover:border-rose-500/40" id="tg-disconnect">
                  ${icon('close', 'w-3.5 h-3.5 text-rose-500')}
                  <span>قطع اتصال</span>
                </button>
              ` : ''}
            </div>

            <!-- Engine Automation Preferences -->
            <div class="pt-4 border-t border-slate-200/80 dark:border-slate-800 space-y-3.5 text-xs">
              <div class="font-bold text-slate-700 dark:text-slate-200">رفتار هوشمند و قوانین ارسال</div>

              <div class="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-800">
                <div>
                  <div class="font-semibold text-slate-800 dark:text-slate-200">سرویس ربات تلگرام (Background Polling)</div>
                  <div class="text-[11px] text-slate-500">پاسخ‌گویی به فرامین (/projects, /scan, /status) و دکمه‌های تایید و صدور پیشنهاد</div>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" id="tg-enabled" class="sr-only peer" ${s.enabled ? 'checked' : ''}>
                  <div class="w-10 h-6 bg-slate-300 dark:bg-slate-700 peer-focus:outline-hidden rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-teal-600"></div>
                </label>
              </div>

              <div class="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-800">
                <div>
                  <div class="font-semibold text-slate-800 dark:text-slate-200">ارسال خودکار اعلان پروژه‌ها به تلگرام</div>
                  <div class="text-[11px] text-slate-500">ارسال کارت مشخصات پروژه‌های جدید کشف‌شده به همراه دکمه‌های تولید و ارسال پیشنهاد</div>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" id="tg-notify" class="sr-only peer" ${s.notify_enabled ? 'checked' : ''}>
                  <div class="w-10 h-6 bg-slate-300 dark:bg-slate-700 peer-focus:outline-hidden rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-teal-600"></div>
                </label>
              </div>

              <!-- Min Score Threshold Slider -->
              <div class="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-800 space-y-2">
                <div class="flex items-center justify-between">
                  <div>
                    <span class="font-semibold text-slate-800 dark:text-slate-200">فیلتر هوش مصنوعی (حداقل امتیاز تطابق)</span>
                    <span class="text-[11px] text-slate-500 block">فقط پروژه‌هایی که امتیاز ارزیابی هوش مصنوعی آنها برابر یا بالاتر از این حد باشد به تلگرام ارسال می‌شوند.</span>
                  </div>
                  <span id="minscore-badge" class="px-2.5 py-1 rounded-lg bg-teal-500/15 text-teal-600 dark:text-teal-400 font-bold font-mono text-sm">
                    ${s.notify_min_score || 0}%
                  </span>
                </div>
                <div class="flex items-center gap-3 pt-1">
                  <input type="range" id="tg-minscore-slider" min="0" max="100" value="${s.notify_min_score || 0}" class="w-full accent-teal-600 cursor-pointer">
                  <input type="number" id="tg-minscore" min="0" max="100" value="${s.notify_min_score || 0}" class="inp w-16 py-1 text-center font-mono text-xs">
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Column 2: Easy 3-Step Setup Guide & Direct Telegram Link (5 cols) -->
        <div class="lg:col-span-5 space-y-4">
          <div class="card p-5 border border-slate-200/80 dark:border-slate-800 shadow-xs flex flex-col justify-between h-full">
            <div>
              <div class="flex items-center gap-2 mb-3">
                <span class="w-7 h-7 rounded-lg bg-teal-500/10 text-teal-500 flex items-center justify-center">
                  ${icon('sparkles', 'w-4 h-4')}
                </span>
                <h3 class="font-bold text-sm text-slate-800 dark:text-slate-100">
                  اتصال خودکار و بدون دردسر (۳۰ ثانیه)
                </h3>
              </div>

              <p class="text-xs text-slate-500 dark:text-slate-400 mb-4 leading-relaxed">
                با توجه به اینکه هر کاربر ربات اختصاصی خودش را می‌سازد، نیازی به وارد کردن Chat ID یا کد فعال‌سازی نیست. کافیست ۳ مرحله زیر را انجام دهید:
              </p>

              <!-- Step 1-2-3 Visual List -->
              <div class="space-y-3 text-xs leading-relaxed">
                <div class="p-3 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-800 flex items-start gap-3">
                  <span class="w-6 h-6 rounded-lg bg-teal-500/20 text-teal-400 flex items-center justify-center font-black text-xs shrink-0 mt-0.5">۱</span>
                  <div>
                    <div class="font-bold text-slate-800 dark:text-slate-200">ساخت ربات در BotFather</div>
                    <div class="text-[11px] text-slate-500 mt-0.5">در تلگرام به <a href="https://t.me/BotFather" target="_blank" class="text-sky-500 font-bold hover:underline">@BotFather</a> بروید و دستور <code class="font-mono bg-white dark:bg-slate-800 px-1 rounded text-teal-400">/newbot</code> را ارسال کنید.</div>
                  </div>
                </div>

                <div class="p-3 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-800 flex items-start gap-3">
                  <span class="w-6 h-6 rounded-lg bg-teal-500/20 text-teal-400 flex items-center justify-center font-black text-xs shrink-0 mt-0.5">۲</span>
                  <div>
                    <div class="font-bold text-slate-800 dark:text-slate-200">ذخیره توکن در این صفحه</div>
                    <div class="text-[11px] text-slate-500 mt-0.5">توکن دریافتی را در کادر روبرو قرار داده و دکمه «ذخیره و فعال‌سازی ربات» را بزنید.</div>
                  </div>
                </div>

                <div class="p-3 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-800 flex items-start gap-3">
                  <span class="w-6 h-6 rounded-lg bg-teal-500/20 text-teal-400 flex items-center justify-center font-black text-xs shrink-0 mt-0.5">۳</span>
                  <div>
                    <div class="font-bold text-slate-800 dark:text-slate-200">شروع چت با ربات (Start)</div>
                    <div class="text-[11px] text-slate-500 mt-0.5">وارد ربات خود شوید و دکمه <b>Start</b> را لمس کنید؛ حساب شما به‌صورت خودکار متصل می‌شود!</div>
                  </div>
                </div>
              </div>

              <!-- Direct Action Button -->
              ${botUser ? `
                <a href="https://t.me/${botUser}" target="_blank" class="w-full flex items-center justify-center gap-2.5 py-3 px-4 rounded-xl bg-gradient-to-r from-teal-500 to-emerald-500 hover:from-teal-400 hover:to-emerald-400 text-slate-950 font-bold text-sm shadow-md shadow-teal-500/25 transition transform active:scale-[0.99] mt-4">
                  ${icon('telegram', 'w-5 h-5')}
                  <span>باز کردن ربات در تلگرام (@${esc(botUser)})</span>
                  ${icon('external', 'w-4 h-4 opacity-75')}
                </a>
              ` : `
                <a href="https://t.me/BotFather" target="_blank" class="w-full flex items-center justify-center gap-2.5 py-3 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs border border-slate-700 transition mt-4">
                  ${icon('telegram', 'w-4 h-4 text-sky-400')}
                  <span>باز کردن @BotFather برای ساخت ربات</span>
                  ${icon('external', 'w-3.5 h-3.5 opacity-60')}
                </a>
              `}
            </div>

            <!-- Zero Friction Notice -->
            <div class="mt-4 pt-4 border-t border-slate-200/60 dark:border-slate-800 text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
              💡 <b>کنترل دوطرفه و کامل:</b> تمامی کارهایی که در این پنل انجام می‌دهید (اسکن لحظه‌ای، فهرست پروژه‌ها، تولید هوشمند پیشنهاد با AI، ویرایش قیمت و تایید ارسال) از طریق دکمه‌های شیشه‌ای مستقیماً داخل تلگرام نیز در دسترس شماست.
            </div>
          </div>
        </div>
      </div>

      <!-- Full-Width Bottom Section: Connected Chats -->
      <div class="card p-5 border border-slate-200/80 dark:border-slate-800 shadow-xs">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 pb-3 border-b border-slate-200/60 dark:border-slate-800">
          <div>
            <h3 class="font-bold text-sm text-slate-800 dark:text-slate-100 flex items-center gap-2">
              <span class="w-6 h-6 rounded-md bg-emerald-500/10 text-emerald-500 flex items-center justify-center">
                ${icon('user', 'w-3.5 h-3.5')}
              </span>
              <span>چت‌های متصل به ربات (${chats.items.length})</span>
            </h3>
            <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              لیست کاربران یا گروه‌هایی که با ارسال پیام به ربات متصل شده‌اند و اعلان‌ها برای آنها ارسال می‌گردد.
            </p>
          </div>
        </div>

        ${chats.items.length ? `
          <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            ${chats.items.map(c => `
              <div class="p-3.5 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900/60 flex flex-col justify-between gap-3 shadow-2xs hover:border-teal-500/50 transition group" data-chat="${c.chat_id}">
                <div class="flex items-start justify-between gap-2">
                  <div class="flex items-center gap-2.5">
                    <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-slate-800 to-slate-700 text-teal-300 flex items-center justify-center font-bold text-sm shrink-0 shadow-xs">
                      ${(c.display_name || c.username || 'U')[0].toUpperCase()}
                    </div>
                    <div class="min-w-0">
                      <div class="font-bold text-xs text-slate-800 dark:text-slate-100 truncate">${esc(c.display_name || 'کاربر تلگرام')}</div>
                      ${c.username ? `
                        <a href="https://t.me/${esc(c.username)}" target="_blank" class="text-[11px] text-sky-500 hover:underline flex items-center gap-0.5">
                          @${esc(c.username)}
                        </a>
                      ` : `<span class="text-[10px] text-slate-400">بدون یوزرنیم</span>`}
                    </div>
                  </div>
                  <div>
                    ${badge(c.authorized ? 'فعال' : 'غیرفعال', c.authorized ? 'green' : 'neutral')}
                  </div>
                </div>

                <div class="flex items-center justify-between text-[11px] text-slate-400 bg-slate-50 dark:bg-slate-800/50 p-2 rounded-lg font-mono">
                  <span>Chat ID: <b class="text-slate-700 dark:text-slate-300 select-all">${esc(c.chat_id)}</b></span>
                  ${c.added_at ? `<span class="text-[10px]">${new Date(c.added_at).toLocaleDateString('fa-IR')}</span>` : ''}
                </div>

                <div class="flex items-center gap-1.5 pt-1">
                  <button class="btn flex-1 text-[11px] py-1 text-sky-600 dark:text-sky-400 hover:border-sky-500/40 flex items-center justify-center gap-1" data-send-single title="ارسال پیام تست به این چت">
                    ${icon('plane', 'w-3 h-3')}
                    <span>ارسال تست</span>
                  </button>
                  <button class="btn flex-1 text-[11px] py-1 ${c.authorized ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'}" data-toggle>
                    ${c.authorized ? 'غیرفعال‌سازی' : 'فعال‌سازی'}
                  </button>
                  <button class="btn btn-danger text-[11px] py-1 px-2.5" data-del title="حذف">
                    ${icon('trash', 'w-3 h-3')}
                  </button>
                </div>
              </div>
            `).join('')}
          </div>
        ` : `
          <div class="p-8 text-center rounded-xl border border-dashed border-slate-200 dark:border-slate-800">
            <div class="w-12 h-12 rounded-full bg-teal-500/10 text-teal-500 flex items-center justify-center mx-auto mb-3">
              ${icon('telegram', 'w-6 h-6')}
            </div>
            <h4 class="text-xs font-bold text-slate-700 dark:text-slate-200">هنوز هیچ چتی به ربات متصل نشده است</h4>
            <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-1 max-w-sm mx-auto">
              پس از ذخیره توکن، کافیست وارد ربات در تلگرام شوید و دکمه Start را لمس کنید تا حسابتان فوراً متصل و شناسایی شود.
            </p>
            ${botUser ? `
              <a href="https://t.me/${esc(botUser)}" target="_blank" class="inline-flex items-center gap-1.5 mt-3 px-4 py-2 rounded-xl bg-teal-600 hover:bg-teal-500 text-white text-xs font-bold transition">
                ${icon('telegram', 'w-4 h-4')}
                <span>باز کردن ربات در تلگرام</span>
              </a>
            ` : ''}
          </div>
        `}
      </div>
    `;

    // Minscore Slider & Number Sync
    const slider = container.querySelector('#tg-minscore-slider');
    const numInput = container.querySelector('#tg-minscore');
    const badgeEl = container.querySelector('#minscore-badge');
    if (slider && numInput && badgeEl) {
      slider.oninput = () => {
        numInput.value = slider.value;
        badgeEl.textContent = slider.value + '%';
      };
      numInput.oninput = () => {
        slider.value = numInput.value;
        badgeEl.textContent = numInput.value + '%';
      };
    }

    // Token Visibility Toggle
    const toggleVisBtn = container.querySelector('#toggle-token-vis');
    const tokenInput = container.querySelector('#tg-token');
    const eyeIconWrap = container.querySelector('#token-eye-icon');
    if (toggleVisBtn && tokenInput && eyeIconWrap) {
      let isVisible = false;
      toggleVisBtn.onclick = () => {
        isVisible = !isVisible;
        tokenInput.type = isVisible ? 'text' : 'password';
        eyeIconWrap.innerHTML = icon(isVisible ? 'eyeOff' : 'eye', 'w-4 h-4');
      };
    }

    // Save & Validate Settings
    container.querySelector('#tg-save').onclick = async () => {
      const token = container.querySelector('#tg-token').value.trim();
      const enabled = container.querySelector('#tg-enabled').checked;
      const notify = container.querySelector('#tg-notify').checked;
      const minscore = Number(container.querySelector('#tg-minscore').value);
      if (!token && !s.has_token) return toast('توکن ربات را وارد کنید', 'error');
      
      const saveBtn = container.querySelector('#tg-save');
      saveBtn.disabled = true;
      try {
        await api.put('/telegram/settings', {
          ...(token ? { bot_token: token } : {}),
          enabled,
          notify_enabled: notify,
          notify_min_score: minscore,
        });
        toast('تنظیمات ذخیره و اتصال ربات بررسی شد', 'success');
      } catch (err) {
        toast(`خطا در ذخیره‌سازی: ${err.message}`, 'error');
      }
      telegram.render(container);
    };

    // Live Connection Test
    container.querySelector('#tg-test').onclick = async () => {
      const testBtn = container.querySelector('#tg-test');
      testBtn.disabled = true;
      const r = await api.post('/telegram/test').catch(e => ({ ok: false, message: e.message }));
      testBtn.disabled = false;
      toast(r.ok ? `✅ ${r.message}` : `❌ ${r.message}`, r.ok ? 'success' : 'error', 6000);
      telegram.render(container);
    };

    // Broadcast Test Message to All Active Chats
    container.querySelector('#tg-send').onclick = async () => {
      const sendBtn = container.querySelector('#tg-send');
      sendBtn.disabled = true;
      const r = await api.post('/telegram/send-test', {}).catch(e => ({ ok: false, message: e.message }));
      sendBtn.disabled = false;
      toast(r.ok ? `✅ ${r.message}` : `❌ ${r.message}`, r.ok ? 'success' : 'error', 5000);
    };

    // Disconnect Bot
    const disconnectBtn = container.querySelector('#tg-disconnect');
    if (disconnectBtn) {
      disconnectBtn.onclick = () => confirmModal('آیا از قطع ارتباط ربات تلگرام اطمینان دارید؟', async () => {
        await api.post('/telegram/disconnect');
        toast('ارتباط ربات با سامانه قطع شد');
        telegram.render(container);
      });
    }

    // Individual Chat Actions
    container.querySelectorAll('[data-chat]').forEach(row => {
      const id = row.dataset.chat;
      const sendBtn = row.querySelector('[data-send-single]');
      if (sendBtn) {
        sendBtn.onclick = async () => {
          sendBtn.disabled = true;
          const r = await api.post('/telegram/send-test', { chat_id: id }).catch(e => ({ ok: false, message: e.message }));
          sendBtn.disabled = false;
          toast(r.ok ? `✅ پیام آزمایشی به چت ${id} ارسال شد` : `❌ ${r.message}`, r.ok ? 'success' : 'error');
        };
      }
      const toggleBtn = row.querySelector('[data-toggle]');
      if (toggleBtn) {
        toggleBtn.onclick = async () => {
          await api.post(`/telegram/chats/${id}/toggle`);
          toast('وضعیت چت تغییر یافت', 'success');
          telegram.render(container);
        };
      }
      const delBtn = row.querySelector('[data-del]');
      if (delBtn) {
        delBtn.onclick = () => confirmModal(`آیا چت ${id} حذف شود؟`, async () => {
          await api.del(`/telegram/chats/${id}`);
          toast('چت حذف شد');
          telegram.render(container);
        });
      }
    });

    bindChannelSubTabs(container);
  },
};

// ------------------------------ AI providers ----------------------------- //
export const ai = {
  title: () => 'تأمین‌کنندگان هوش مصنوعی',
  async render(container) {
    container.innerHTML = spinner();
    const [providers, cfg] = await Promise.all([api.get('/ai/providers'), api.get('/agent-config')]);
    const roles = [['analyzer', 'تحلیلگر پروژه'], ['proposal', 'تولیدکننده پیشنهاد'], ['quality', 'بازبین کیفیت'], ['copilot', 'دستیار هوشمند']];
    container.innerHTML = `
      ${channelSubTabs('ai')}
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-bold text-sm">تأمین‌کنندگان هوش مصنوعی / AI Providers</h3>
        <button class="btn btn-primary text-xs flex items-center gap-1.5" id="add-provider">
          ${icon('sparkles', 'w-3.5 h-3.5')} <span>افزودن تأمین‌کننده</span>
        </button>
      </div>
      <div class="grid md:grid-cols-2 xl:grid-cols-3 gap-3 mb-6">
        ${providers.items.length ? providers.items.map(providerCard).join('') : emptyState('هیچ تأمین‌کننده‌ای ثبت نشده است')}
      </div>
      <div class="card p-4">
        <h3 class="font-bold text-sm mb-3">🎯 انتخاب مدل برای هر نقش (مستقل)</h3>
        <div class="grid md:grid-cols-2 gap-3">
          ${roles.map(([role, label]) => roleSelect(role, label, cfg.model_assignments?.[role], providers.items)).join('')}
        </div>
        <div class="flex justify-end mt-3"><button class="btn btn-primary" id="save-roles">ذخیره نقش‌ها</button></div>
      </div>`;

    container.querySelector('#add-provider').onclick = () => providerForm(null, providers.provider_types);
    container.querySelectorAll('[data-provider]').forEach(card => {
      const id = Number(card.dataset.provider);
      card.querySelector('[data-test]').onclick = async () => {
        toast('در حال تست…');
        const r = await api.post(`/ai/providers/${id}/test`).catch(e => ({ ok: false, message: e.message }));
        toast(r.ok ? `✅ ${r.message}` : `❌ ${r.message}`, r.ok ? 'success' : 'error', 9000);
        ai.render(container);
      };
      card.querySelector('[data-models]').onclick = async () => {
        const r = await api.post(`/ai/providers/${id}/refresh-models`).catch(e => ({ detail: e.message }));
        if (r.models) { toast(`${r.models.length} مدل دریافت شد`, 'success'); ai.render(container); }
        else toast(r.detail || 'دریافت مدل‌ها ناموفق بود', 'error');
      };
      card.querySelector('[data-edit]').onclick = () => providerForm(providers.items.find(p => p.id === id), providers.provider_types);
      card.querySelector('[data-del]').onclick = () => confirmModal('این تأمین‌کننده حذف شود؟', async () => {
        try { await api.del(`/ai/providers/${id}`); toast('حذف شد'); ai.render(container); }
        catch (e) { toast(e.message, 'error'); }
      });
    });
    container.querySelector('#save-roles').onclick = async () => {
      const body = {};
      container.querySelectorAll('[data-role]').forEach(sel => {
        const [providerId, model] = sel.value.split('::');
        body[sel.dataset.role] = providerId ? { provider_id: Number(providerId), model: model || null } : null;
      });
      await api.put('/agent-config/model-assignments', body);
      toast('نقش‌های مدل ذخیره شد', 'success');
    };
    bindChannelSubTabs(container);
  },
};

function roleSelect(role, label, assigned, providers) {
  return `<div><label class="lbl">${label}</label>
    <select class="inp" data-role="${role}">
      <option value="">— انتخاب کنید —</option>
      ${providers.map(p => {
        const models = (p.models?.length ? p.models : [p.default_model].filter(Boolean));
        return models.map(mo => {
          const val = `${p.id}::${mo}`;
          const sel = assigned && Number(assigned.provider_id) === p.id && (assigned.model || null) === (mo || null) ? 'selected' : '';
          return `<option value="${val}" ${sel}>${esc(p.name)} — ${esc(mo)}</option>`;
        }).join('');
      }).join('')}
    </select></div>`;
}

function providerCard(p) {
  return `<div class="card p-5 space-y-3" data-provider="${p.id}">
    <div class="flex items-start justify-between gap-2">
      <div class="flex-1">
        <div class="font-bold text-sm text-slate-800 dark:text-slate-100">${esc(p.name)}</div>
        <div class="text-[11px] text-slate-400 font-mono mt-0.5" dir="ltr">${esc(p.base_url)}</div>
      </div>
      ${badge(p.is_active ? 'فعال' : 'غیرفعال', p.is_active ? 'green' : 'neutral')}
    </div>
    <div class="text-[11px] text-slate-500 dark:text-slate-400">نوع: ${({ openai_compatible: 'OpenAI سازگار', anthropic: 'Anthropic', ollama: 'Ollama' })[p.provider_type] || p.provider_type} · مدل پیش‌فرض: ${esc(p.default_model || '—')}</div>
    <div class="flex flex-wrap gap-1.5">
      ${badge(p.connection_status === 'connected' ? 'متصل' : p.connection_status === 'error' ? 'خطا' : 'تست نشده', p.connection_status === 'connected' ? 'green' : p.connection_status === 'error' ? 'red' : 'neutral')}
      ${p.models?.length ? badge(`${p.models.length} مدل`, 'sky') : ''}
    </div>
    <div class="flex flex-wrap gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
      <button class="btn-action" data-test>${icon('activity', 'w-3.5 h-3.5 text-teal-600')}<span>تست اتصال</span></button>
      <button class="btn-action" data-models>${icon('refresh', 'w-3.5 h-3.5 text-sky-600')}<span>دریافت مدل‌ها</span></button>
      <button class="btn-action" data-edit>${icon('edit', 'w-3.5 h-3.5 text-slate-500')}<span>ویرایش</span></button>
      <button class="btn-action text-rose-600 dark:text-rose-400 hover:border-rose-500/40" data-del>${icon('trash', 'w-3.5 h-3.5 text-rose-500')}<span>حذف</span></button>
    </div>
  </div>`;
}

function providerForm(existing, types) {
  const typeFa = { openai_compatible: 'OpenAI سازگار (استاندارد)', anthropic: 'Anthropic Claude', ollama: 'Ollama (محلی/آفلاین)' };

  const PRESETS = [
    {
      id: 'gemini',
      name: 'Google Gemini',
      type: 'openai_compatible',
      url: 'https://generativelanguage.googleapis.com/v1beta/openai',
      defaultModel: 'gemini-1.5-flash',
      hint: 'دریافت کلید رایگان از Google AI Studio (aistudio.google.com)',
      costIn: 0.000075,
      costOut: 0.0003,
      icon: '🌟'
    },
    {
      id: 'openai',
      name: 'OpenAI',
      type: 'openai_compatible',
      url: 'https://api.openai.com/v1',
      defaultModel: 'gpt-4o-mini',
      hint: 'تهیه کلید API از platform.openai.com',
      costIn: 0.00015,
      costOut: 0.0006,
      icon: '🟢'
    },
    {
      id: 'deepseek',
      name: 'DeepSeek',
      type: 'openai_compatible',
      url: 'https://api.deepseek.com/v1',
      defaultModel: 'deepseek-chat',
      hint: 'مدل قدرتمند و بسیار اقتصادی از platform.deepseek.com',
      costIn: 0.00014,
      costOut: 0.00028,
      icon: '🐋'
    },
    {
      id: 'openrouter',
      name: 'OpenRouter',
      type: 'openai_compatible',
      url: 'https://openrouter.ai/api/v1',
      defaultModel: 'google/gemini-flash-1.5',
      hint: 'دسترسی به بیش از ۲۰۰ مدل با یک کلید از openrouter.ai',
      costIn: 0.0001,
      costOut: 0.0002,
      icon: '🔵'
    },
    {
      id: 'groq',
      name: 'Groq Cloud',
      type: 'openai_compatible',
      url: 'https://api.groq.com/openai/v1',
      defaultModel: 'llama-3.3-70b-versatile',
      hint: 'پردازش فوق‌سریع چیپ LPU از console.groq.com',
      costIn: 0.0001,
      costOut: 0.0001,
      icon: '⚡'
    },
    {
      id: 'ollama',
      name: 'Ollama (محلی)',
      type: 'ollama',
      url: 'http://localhost:11434',
      defaultModel: 'llama3:latest',
      hint: 'سرویس محلی آفلاین روی پورت 11434 — بدون نیاز به کلید API',
      costIn: 0,
      costOut: 0,
      icon: '🦙'
    },
    {
      id: 'anthropic',
      name: 'Anthropic Claude',
      type: 'anthropic',
      url: 'https://api.anthropic.com',
      defaultModel: 'claude-3-5-sonnet-20241022',
      hint: 'کلید اختصاصی از console.anthropic.com',
      costIn: 0.003,
      costOut: 0.015,
      icon: '🟣'
    }
  ];

  const modalTitle = existing ? 'ویرایش تأمین‌کننده هوش مصنوعی' : 'افزودن تأمین‌کننده هوش مصنوعی';
  const modalSubtitle = 'پیکربندی کلید API و دریافت خودکار مدل‌ها جهت ارزیابی و امتیازدهی به پروژه‌ها';

  const m = modal(modalTitle, `
    <div class="space-y-4 text-sm" dir="rtl">
      <!-- 2-Column Grid for Rectangular Landscape Modal -->
      <div class="grid lg:grid-cols-12 gap-5 items-start">

        <!-- RIGHT COLUMN (Col 1: Presets & Provider Credentials) - 6 cols -->
        <div class="lg:col-span-6 space-y-3.5">
          <!-- 1. Quick Presets Selection -->
          <div class="p-3 rounded-2xl bg-slate-50 dark:bg-white/[0.03] border border-slate-100 dark:border-white/5">
            <label class="lbl mb-1.5">
              <span>انتخاب سریع ارائه‌دهنده (Preset)</span>
              <span class="text-[10px] text-teal-600 dark:text-teal-400 font-normal">تکمیل با ۱ کلیک</span>
            </label>
            <div class="flex flex-wrap gap-1.5" id="preset-chips">
              ${PRESETS.map(p => `
                <button type="button" class="preset-chip ${existing?.name?.toLowerCase().includes(p.id) ? 'active' : ''}" data-preset="${p.id}">
                  <span>${p.icon}</span>
                  <span>${p.name}</span>
                </button>
              `).join('')}
            </div>
          </div>

          <!-- 2. Name & Protocol Type -->
          <div class="grid sm:grid-cols-2 gap-3">
            <div>
              <label class="lbl" for="f-name"><span>نام نمایشی</span></label>
              <input id="f-name" class="inp" placeholder="Google Gemini" value="${esc(existing?.name || '')}">
            </div>
            <div>
              <label class="lbl" for="f-type"><span>نوع پروتکل</span></label>
              <select id="f-type" class="inp">
                ${types.map(ty => `<option value="${ty}" ${existing?.provider_type === ty ? 'selected' : ''}>${typeFa[ty] || ty}</option>`).join('')}
              </select>
            </div>
          </div>

          <!-- 3. Base URL -->
          <div>
            <label class="lbl" for="f-url">
              <span>Base URL (آدرس سرویس)</span>
              <span class="text-[10px] text-slate-400 font-mono">بدون اسلش انتهایی</span>
            </label>
            <div style="direction: ltr;">
              <input id="f-url" class="inp font-mono text-xs" dir="ltr" placeholder="https://api.openai.com/v1" value="${esc(existing?.base_url || '')}" style="text-align: left; direction: ltr;">
            </div>
          </div>

          <!-- 4. API Key with Visibility Toggle -->
          <div>
            <label class="lbl" for="f-key">
              <span>API Key ${existing?.api_key_masked ? `(کلید فعال: ${esc(existing.api_key_masked)})` : ''}</span>
              <span id="key-hint" class="text-[10px] text-teal-600 dark:text-teal-400 font-normal"></span>
            </label>
            <div class="relative" style="direction: ltr;">
              <input id="f-key" class="inp font-mono text-xs" dir="ltr" type="password" placeholder="sk-... or AIzaSy..." style="padding-right: 2.75rem; text-align: left; direction: ltr;">
              <button type="button" id="toggle-key-vis" class="absolute right-2.5 top-1/2 -translate-y-1/2 p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition cursor-pointer flex items-center justify-center" title="نمایش/مخفی‌سازی کلید">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
            </div>
            <div id="key-guide" class="text-[11px] text-slate-500 dark:text-slate-400 mt-1">💡 کلید API اختصاصی خود را وارد یا Paste کنید.</div>
          </div>

          <!-- 5. Active Status Switch -->
          <div class="flex items-center justify-between p-3 rounded-2xl bg-slate-50/50 dark:bg-white/[0.02] border border-slate-100 dark:border-white/5">
            <div>
              <div class="text-xs font-bold text-slate-800 dark:text-slate-100">فعال بودن تأمین‌کننده</div>
              <div class="text-[10px] text-slate-400 mt-0.5">ایجنت می‌تواند از مدل‌های این تأمین‌کننده برای نقش‌ها استفاده کند</div>
            </div>
            <label class="switch-toggle">
              <input type="checkbox" id="f-active" ${!existing || existing.is_active ? 'checked' : ''}>
              <span class="switch-slider"></span>
            </label>
          </div>
        </div>

        <!-- LEFT COLUMN (Col 2: Models & Token Pricing) - 6 cols -->
        <div class="lg:col-span-6 space-y-3.5">
          <!-- Models Auto-Loading Card -->
          <div class="p-4 rounded-2xl bg-teal-500/5 dark:bg-teal-500/10 border border-teal-500/20 space-y-3">
            <div class="flex items-center justify-between flex-wrap gap-2">
              <label class="lbl mb-0" for="f-model-select">
                <span class="flex items-center gap-1.5 font-bold text-slate-800 dark:text-slate-100">
                  <span class="text-teal-600 dark:text-teal-400">${icon('sparkles', 'w-4 h-4')}</span>
                  <span>مدل پیش‌فرض (شناسایی خودکار)</span>
                </span>
              </label>
              <button type="button" id="btn-fetch-models" class="btn-action text-xs py-1 px-3 flex items-center gap-1.5 text-teal-700 dark:text-teal-300 hover:border-teal-500/40 cursor-pointer">
                <span id="fetch-icon">${icon('refresh', 'w-3.5 h-3.5')}</span>
                <span id="fetch-text">دریافت مدل‌ها</span>
              </button>
            </div>

            <!-- Live Model Status Message -->
            <div id="model-status" class="text-[11px] flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
              <span>💡 با وارد کردن آدرس و کلید API، فهرست مدل‌ها به‌صورت خودکار فراخوانی می‌شود.</span>
            </div>

            <!-- Populated Select Dropdown -->
            <div id="model-select-wrapper">
              <select id="f-model-select" class="inp text-xs font-vazir" style="direction: rtl; text-align: right;">
                <option value="">— ابتدا کلید API را وارد کنید یا دکمه دریافت مدل‌ها را بزنید —</option>
              </select>
            </div>

            <!-- Custom Model Input (shown if user selects custom model) -->
            <div id="manual-model-wrap" class="hidden pt-1">
              <label class="text-[10px] font-bold text-slate-500 dark:text-slate-400 mb-1 block">شناسه مدل دلخواه (Manual Model ID):</label>
              <div style="direction: ltr;">
                <input id="f-model-manual" class="inp text-xs font-mono" dir="ltr" placeholder="مثال: gpt-4o یا claude-3-5-sonnet" value="${esc(existing?.default_model || '')}" style="text-align: left; direction: ltr;">
              </div>
            </div>

            <!-- Detected Models Pills Container (Quick Selection Preview) -->
            <div id="detected-models-box" class="hidden pt-2.5 border-t border-teal-500/20">
              <div class="text-[10px] font-bold text-slate-500 dark:text-slate-400 mb-1.5 flex items-center justify-between">
                <span>مدل‌های شناسایی‌شده (برای انتخاب کلیک کنید):</span>
                <span id="detected-count" class="text-teal-600 dark:text-teal-400 font-sans"></span>
              </div>
              <div class="flex flex-wrap gap-1 max-h-24 overflow-y-auto" id="detected-pills"></div>
            </div>
          </div>

          <!-- Advanced Token Pricing Card -->
          <div class="p-3.5 rounded-2xl bg-slate-50 dark:bg-white/[0.03] border border-slate-100 dark:border-white/5 space-y-2.5">
            <div class="flex items-center justify-between">
              <div class="font-bold text-xs text-slate-800 dark:text-slate-200">⚙️ برآورد هزینه مصرف توکن (اختیاری)</div>
              <span class="text-[10px] text-slate-400">برای محاسبه گزارش‌های مالی</span>
            </div>
            <div class="grid sm:grid-cols-2 gap-3 pt-1">
              <div>
                <label class="lbl text-[11px]">هزینه ورودی به ازای ۱K توکن ($)</label>
                <div style="direction: ltr;">
                  <input id="f-ci" type="number" step="0.00001" class="inp text-xs font-mono" dir="ltr" placeholder="0.00015" value="${existing?.cost_per_1k_input ?? ''}" style="text-align: left; direction: ltr;">
                </div>
              </div>
              <div>
                <label class="lbl text-[11px]">هزینه خروجی به ازای ۱K توکن ($)</label>
                <div style="direction: ltr;">
                  <input id="f-co" type="number" step="0.00001" class="inp text-xs font-mono" dir="ltr" placeholder="0.0006" value="${existing?.cost_per_1k_output ?? ''}" style="text-align: left; direction: ltr;">
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Bottom Actions Bar across full width -->
      <div class="flex items-center justify-end gap-2.5 pt-3.5 border-t border-slate-100 dark:border-white/10 mt-1">
        <button type="button" class="btn-action px-5" data-x>انصراف</button>
        <button type="button" class="btn-action-primary px-6" data-s>
          ${icon('check', 'w-4 h-4')}
          <span>${existing ? 'بروزرسانی تأمین‌کننده' : 'ذخیره تأمین‌کننده'}</span>
        </button>
      </div>
    </div>
  `, { wide: true, subtitle: modalSubtitle });

  // DOM Elements
  const fName = m.body.querySelector('#f-name');
  const fType = m.body.querySelector('#f-type');
  const fUrl = m.body.querySelector('#f-url');
  const fKey = m.body.querySelector('#f-key');
  const fCi = m.body.querySelector('#f-ci');
  const fCo = m.body.querySelector('#f-co');
  const fActive = m.body.querySelector('#f-active');
  const fModelSelect = m.body.querySelector('#f-model-select');
  const fModelManual = m.body.querySelector('#f-model-manual');
  const manualModelWrap = m.body.querySelector('#manual-model-wrap');
  const modelStatus = m.body.querySelector('#model-status');
  const btnFetch = m.body.querySelector('#btn-fetch-models');
  const fetchIcon = m.body.querySelector('#fetch-icon');
  const keyGuide = m.body.querySelector('#key-guide');
  const toggleKeyVis = m.body.querySelector('#toggle-key-vis');

  let fetchedModels = existing?.models || [];
  let isFetching = false;

  // Function to populate model select dropdown
  function populateModelSelect(models, preferredModel = '') {
    const currentVal = preferredModel || existing?.default_model || fModelManual.value || '';
    if (!models || models.length === 0) {
      fModelSelect.innerHTML = `<option value="">— مدلی دریافت نشد؛ مدل دلخواه را وارد کنید —</option><option value="__custom__">✏️ وارد کردن دستی شناسه مدل...</option>`;
      manualModelWrap.classList.remove('hidden');
      return;
    }

    // Sort models, prioritizing user-friendly flash, mini, chat models
    const sorted = [...models].sort((a, b) => {
      const aPri = (a.includes('flash') || a.includes('mini') || a.includes('chat') || a.includes('turbo')) ? 0 : 1;
      const bPri = (b.includes('flash') || b.includes('mini') || b.includes('chat') || b.includes('turbo')) ? 0 : 1;
      if (aPri !== bPri) return aPri - bPri;
      return a.localeCompare(b);
    });

    fModelSelect.innerHTML = `
      <option value="">— انتخاب مدل هوشمند پیش‌فرض (${models.length} مدل موجود) —</option>
      ${sorted.map(mo => `
        <option value="${esc(mo)}" ${mo === currentVal ? 'selected' : ''}>${esc(mo)}</option>
      `).join('')}
      <option value="__custom__">✏️ وارد کردن مدل دیگر به‌صورت دستی...</option>
    `;

    if (currentVal && models.includes(currentVal)) {
      fModelSelect.value = currentVal;
      fModelSelect.style.direction = 'ltr';
      fModelSelect.style.textAlign = 'left';
      manualModelWrap.classList.add('hidden');
    } else if (currentVal) {
      fModelSelect.value = '__custom__';
      fModelSelect.style.direction = 'rtl';
      fModelSelect.style.textAlign = 'right';
      manualModelWrap.classList.remove('hidden');
      fModelManual.value = currentVal;
    } else if (sorted.length > 0) {
      fModelSelect.value = sorted[0];
      fModelSelect.style.direction = 'ltr';
      fModelSelect.style.textAlign = 'left';
      fModelManual.value = sorted[0];
    }

    const detectedBox = m.body.querySelector('#detected-models-box');
    const detectedPills = m.body.querySelector('#detected-pills');
    const detectedCount = m.body.querySelector('#detected-count');

    if (detectedBox && detectedPills && models.length > 0) {
      detectedBox.classList.remove('hidden');
      detectedCount.textContent = `(${models.length} مدل)`;
      detectedPills.innerHTML = sorted.slice(0, 10).map(mo => `
        <button type="button" class="px-2 py-0.5 rounded-md text-[10px] font-mono bg-slate-100 dark:bg-white/10 text-slate-700 dark:text-slate-300 hover:bg-teal-500/20 hover:text-teal-600 dark:hover:text-teal-300 transition cursor-pointer" data-quick-model="${esc(mo)}">
          ${esc(mo)}
        </button>
      `).join('');

      detectedPills.querySelectorAll('[data-quick-model]').forEach(btn => {
        btn.onclick = () => {
          const targetModel = btn.dataset.quickModel;
          fModelSelect.value = targetModel;
          fModelSelect.style.direction = 'ltr';
          fModelSelect.style.textAlign = 'left';
          manualModelWrap.classList.add('hidden');
          fModelManual.value = targetModel;
        };
      });
    }
  }

  // Handle Model Select changes
  fModelSelect.onchange = () => {
    if (fModelSelect.value === '__custom__') {
      fModelSelect.style.direction = 'rtl';
      fModelSelect.style.textAlign = 'right';
      manualModelWrap.classList.remove('hidden');
      fModelManual.focus();
    } else if (fModelSelect.value) {
      fModelSelect.style.direction = 'ltr';
      fModelSelect.style.textAlign = 'left';
      manualModelWrap.classList.add('hidden');
      fModelManual.value = fModelSelect.value;
    } else {
      fModelSelect.style.direction = 'rtl';
      fModelSelect.style.textAlign = 'right';
      manualModelWrap.classList.add('hidden');
      fModelManual.value = '';
    }
  };

  // If existing models already present, populate immediately
  if (existing?.models?.length) {
    populateModelSelect(existing.models, existing.default_model);
    modelStatus.innerHTML = `
      <span class="text-emerald-500 font-bold">✓</span>
      <span class="text-emerald-600 dark:text-emerald-400 font-semibold">تعداد ${existing.models.length} مدل فعال در پایگاه داده موجود است.</span>
    `;
  }

  // Function to fetch models from server
  async function triggerFetchModels(quiet = false) {
    if (isFetching) return;
    const url = fUrl.value.trim().rstrip ? fUrl.value.trim().replace(/\/+$/, '') : fUrl.value.trim();
    const key = fKey.value.trim();
    const type = fType.value;

    if (!url) {
      if (!quiet) toast('لطفاً ابتدا Base URL را وارد کنید', 'error');
      return;
    }

    if (type !== 'ollama' && !key && !existing?.api_key_masked) {
      if (!quiet) toast('لطفاً کلید API را وارد کنید تا مدل‌ها بارگذاری شوند', 'error');
      return;
    }

    isFetching = true;
    fetchIcon.innerHTML = `<span class="inline-block w-3.5 h-3.5 border-2 border-teal-500 border-t-transparent rounded-full animate-spin"></span>`;
    modelStatus.innerHTML = `
      <span class="inline-block w-3.5 h-3.5 border-2 border-teal-500 border-t-transparent rounded-full animate-spin"></span>
      <span class="text-teal-600 dark:text-teal-400 font-medium">در حال اتصال به «${esc(url)}» و بارگذاری خودکار مدل‌ها…</span>
    `;

    try {
      const res = await api.post('/ai/providers/fetch-models', {
        provider_type: type,
        base_url: url,
        api_key: key || null,
        existing_provider_id: existing?.id || null
      });

      if (res && res.models && res.models.length > 0) {
        fetchedModels = res.models;
        modelStatus.innerHTML = `
          <span class="text-emerald-500 font-bold">✓</span>
          <span class="text-emerald-600 dark:text-emerald-400 font-semibold">تعداد ${res.models.length} مدل با موفقیت شناسایی و بارگذاری شد.</span>
        `;
        populateModelSelect(res.models);
        if (!quiet) toast(`${res.models.length} مدل از سرور دریافت شد`, 'success');
      } else {
        throw new Error(res.message || 'هیچ مدلی در پاسخ سرور یافت نشد');
      }
    } catch (err) {
      modelStatus.innerHTML = `
        <span class="text-rose-500 font-bold">✕</span>
        <span class="text-rose-600 dark:text-rose-400 font-medium">خطا در دریافت مدل‌ها: ${esc(err.message || 'اتصال ناموفق')}</span>
      `;
      if (!quiet) toast(err.message || 'خطا در دریافت مدل‌ها', 'error');
    } finally {
      isFetching = false;
      fetchIcon.innerHTML = icon('refresh', 'w-3.5 h-3.5');
    }
  }

  // Button click triggers fetch
  btnFetch.onclick = () => triggerFetchModels(false);

  // Debounced auto-fetch on typing or pasting API Key & URL
  let debounceTimer = null;
  function onCredentialsChanged() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      const url = fUrl.value.trim();
      const key = fKey.value.trim();
      const type = fType.value;
      if (url && (key.length >= 8 || type === 'ollama' || (existing && !key))) {
        triggerFetchModels(true);
      }
    }, 600);
  }

  fKey.addEventListener('input', onCredentialsChanged);
  fKey.addEventListener('paste', () => setTimeout(onCredentialsChanged, 50));
  fUrl.addEventListener('input', onCredentialsChanged);

  // Password visibility toggle
  toggleKeyVis.onclick = () => {
    const isPass = fKey.type === 'password';
    fKey.type = isPass ? 'text' : 'password';
    toggleKeyVis.innerHTML = isPass
      ? `<svg class="w-4 h-4 text-teal-600 dark:text-teal-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`
      : `<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
  };

  // Preset chips click handling
  m.body.querySelectorAll('[data-preset]').forEach(chip => {
    chip.onclick = () => {
      const pid = chip.dataset.preset;
      const p = PRESETS.find(x => x.id === pid);
      if (!p) return;

      m.body.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');

      fName.value = p.name;
      fType.value = p.type;
      fUrl.value = p.url;
      fCi.value = p.costIn ?? '';
      fCo.value = p.costOut ?? '';
      keyGuide.innerHTML = `<span class="text-teal-600 dark:text-teal-400 font-medium">💡 ${p.hint}</span>`;

      if (p.id === 'ollama') {
        fKey.value = '';
        fKey.placeholder = 'No API Key needed for local Ollama';
        triggerFetchModels(false);
      } else {
        fKey.placeholder = `sk-... or API key (${p.name})`;
        fKey.focus();
        if (fKey.value.trim().length >= 8) {
          triggerFetchModels(false);
        } else {
          modelStatus.innerHTML = `<span>💡 کلید API مربوط به <b>${p.name}</b> را وارد کنید تا مدل‌ها بارگذاری شوند.</span>`;
        }
      }
    };
  });

  // Modal Cancel & Save
  m.body.querySelector('[data-x]').onclick = m.close;
  m.body.querySelector('[data-s]').onclick = async () => {
    const selectedModel = fModelSelect.value === '__custom__'
      ? fModelManual.value.trim()
      : (fModelSelect.value || fModelManual.value.trim() || null);

    const body = {
      name: fName.value.trim() || 'AI Provider',
      provider_type: fType.value,
      base_url: fUrl.value.trim(),
      api_key: fKey.value.trim() || null,
      default_model: selectedModel,
      models: fetchedModels,
      is_active: fActive.checked,
      cost_per_1k_input: fCi.value ? Number(fCi.value) : null,
      cost_per_1k_output: fCo.value ? Number(fCo.value) : null,
    };

    if (!body.base_url) {
      toast('آدرس Base URL الزامی است', 'error');
      fUrl.focus();
      return;
    }

    try {
      if (existing) {
        await api.put(`/ai/providers/${existing.id}`, body);
      } else {
        await api.post('/ai/providers', body);
      }
      toast('تأمین‌کننده با موفقیت ذخیره شد', 'success');
      m.close();
      render();
    } catch (e) {
      toast(e.message || 'خطا در ذخیره‌سازی', 'error');
    }
  };
}
