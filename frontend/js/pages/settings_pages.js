// Configuration & system pages: agent config, profile, notifications, prompts, analytics, logs, settings
import { api, fa, esc, platformBadge, STATUS_FA } from '../api.js';
import { badge, modal, confirmModal, spinner, emptyState, toast, setSoundPrefs, playChime } from '../ui.js';
import { applyTheme, navigate } from '../app.js';
import { currentLang, t } from '../i18n.js';
import { icon } from '../icons.js';

export function settingsSubTabs(activeKey) {
  const isEn = currentLang() === 'en';
  const tabs = [
    { id: 'settings', label: isEn ? 'General' : 'تنظیمات عمومی', iconName: 'settings' },
    { id: 'agentconfig', label: isEn ? 'Agent Engine' : 'موتور هوشمند', iconName: 'sparkles' },
    { id: 'ai', label: isEn ? 'AI Providers' : 'تأمین‌کنندگان AI', iconName: 'cpu' },
    { id: 'telegram', label: isEn ? 'Telegram Bot' : 'ربات تلگرام', iconName: 'plane' },
    { id: 'profile', label: isEn ? 'Developer Profile' : 'پروفایل من', iconName: 'user' },
    { id: 'prompts', label: isEn ? 'Prompt Studio' : 'استودیو پرامپت', iconName: 'reports' },
    { id: 'logs', label: isEn ? 'System Logs' : 'لاگ‌های سیستم', iconName: 'activity' },
  ];
  return `
    <div class="sub-tabs-scroll gap-2 mb-5">
      ${tabs.map(t => `
        <button class="sub-tab-pill ${activeKey === t.id ? 'active' : ''}" data-set-nav="${t.id}">
          ${icon(t.iconName, 'w-3.5 h-3.5 inline me-1.5')}${t.label}
        </button>
      `).join('')}
    </div>
  `;
}

function bindSettingsSubTabs(container) {
  container.querySelectorAll('[data-set-nav]').forEach(b => {
    b.onclick = () => navigate(b.dataset.setNav);
  });
}

// ------------------------------ agent config ----------------------------- //
export const agentconfig = {
  title: () => 'تنظیمات ایجنت',
  async render(container) {
    container.innerHTML = spinner();
    const cfg = await api.get('/agent-config');
    const f = cfg.filters || {};
    container.innerHTML = `
      ${settingsSubTabs('agentconfig')}
      <div class="grid lg:grid-cols-2 gap-4">
        <div class="card p-5 space-y-3 border border-slate-200/80 dark:border-slate-800">
          <h3 class="font-bold text-sm flex items-center gap-2">
            ${icon('search', 'w-4 h-4 text-teal-600')}
            <span>موتور کشف هوشمند / Discovery Engine</span>
          </h3>
          <div class="grid grid-cols-2 gap-3">
            <div><label class="lbl">فاصله اسکن سراسری (دقیقه)</label><input id="c-interval" type="number" min="5" class="inp" value="${cfg.scan_interval_minutes}"></div>
            <div><label class="lbl">حداکثر پروژه در هر اسکن</label><input id="c-max" type="number" min="1" max="100" class="inp" value="${cfg.max_projects_per_scan}"></div>
          </div>
          <div><label class="lbl">کلیدواژه‌های شامل (با کاما — اگر خالی باشد همه)</label><input id="c-inc" class="inp" value="${esc((f.include_keywords || []).join('، '))}"></div>
          <div><label class="lbl">کلیدواژه‌های مستثنی (با کاما)</label><input id="c-exc" class="inp" value="${esc((f.exclude_keywords || []).join('، '))}"></div>
          <div class="grid grid-cols-2 gap-3">
            <div><label class="lbl">حداقل بودجه (تومان)</label><input id="c-bmin" type="number" class="inp" value="${f.budget_min ?? ''}"></div>
            <div><label class="lbl">حداکثر بودجه (تومان)</label><input id="c-bmax" type="number" class="inp" value="${f.budget_max ?? ''}"></div>
          </div>
          <div><label class="lbl">دسته‌بندی‌های مجاز (با کاما — خالی = همه)</label><input id="c-cats" class="inp" value="${esc((f.categories || []).join('، '))}"></div>
        </div>
        <div class="card p-5 space-y-3 border border-slate-200/80 dark:border-slate-800">
          <h3 class="font-bold text-sm flex items-center gap-2">
            ${icon('target', 'w-4 h-4 text-teal-600')}
            <span>قواعد تصمیم و آستانه هوشمند</span>
          </h3>
          <div><label class="lbl">حداقل امتیاز پیشنهاد ارسال (پیش‌فرض ۷۰): ${cfg.min_recommendation_score}</label>
            <input id="c-score" type="range" min="0" max="100" value="${cfg.min_recommendation_score}" class="w-full accent-gold-500"></div>
          <div><label class="lbl">حداقل کیفیت پیشنهاد (پیش‌فرض ۷۵): ${cfg.quality_threshold}</label>
            <input id="c-quality" type="range" min="0" max="100" value="${cfg.quality_threshold}" class="w-full accent-gold-500"></div>
          <div><label class="lbl">حداکثر تلاش تولید پیشنهاد</label><input id="c-attempts" type="number" min="1" max="5" class="inp" value="${cfg.max_generation_attempts}"></div>
          <div class="text-[11px] text-neutral-500 leading-6">حد آستانه ۷۰ یعنی فقط پروژه‌هایی که تحلیلگر امتیاز ≥۷۰ و توصیه BID بدهند به صفحه «پیشنهادشده» می‌روند. این منطق شفاف است و همین‌جا قابل تنظیم.</div>
        </div>
      </div>
      <div class="flex justify-end mt-4"><button class="btn btn-primary" id="c-save">ذخیره تنظیمات</button></div>`;

    container.querySelector('#c-save').onclick = async () => {
      const split = v => v.split(/[،,]/).map(s => s.trim()).filter(Boolean);
      try {
        await api.put('/agent-config', {
          scan_interval_minutes: Number(container.querySelector('#c-interval').value),
          max_projects_per_scan: Number(container.querySelector('#c-max').value),
          filters: {
            include_keywords: split(container.querySelector('#c-inc').value),
            exclude_keywords: split(container.querySelector('#c-exc').value),
            categories: split(container.querySelector('#c-cats').value),
            budget_min: container.querySelector('#c-bmin').value ? Number(container.querySelector('#c-bmin').value) : null,
            budget_max: container.querySelector('#c-bmax').value ? Number(container.querySelector('#c-bmax').value) : null,
          },
          min_recommendation_score: Number(container.querySelector('#c-score').value),
          quality_threshold: Number(container.querySelector('#c-quality').value),
          max_generation_attempts: Number(container.querySelector('#c-attempts').value),
        });
        toast('تنظیمات ذخیره شد', 'success');
      } catch (e) { toast(e.message, 'error'); }
    };
    bindSettingsSubTabs(container);
  },
};

// ------------------------------ profile ---------------------------------- //
export const profile = {
  title: () => 'پروفایل توسعه‌دهنده',
  async render(container) {
    container.innerHTML = spinner();
    const p = await api.get('/developer-profile');
    const isEn = currentLang() === 'en';

    container.innerHTML = `
      ${settingsSubTabs('profile')}
      <div class="grid lg:grid-cols-12 gap-5 items-start">
        
        <!-- RIGHT COLUMN: Streamlined Profile Credentials (8 cols) -->
        <div class="lg:col-span-8 card p-5 space-y-4 border border-slate-200/80 dark:border-slate-800">
          <div class="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-white/10">
            <div>
              <h3 class="font-bold text-sm text-slate-800 dark:text-white flex items-center gap-2">
                ${icon('user', 'w-4 h-4 text-teal-600 dark:text-teal-400')}
                <span>${isEn ? 'Professional Profile' : 'اطلاعات حرفه‌ای توسعه‌دهنده'}</span>
              </h3>
              <p class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                ${isEn ? 'Used by AI agents for project evaluation and proposal generation.' : 'مبنای استدلال هوش مصنوعی برای امتیازدهی به پروژه‌ها و نگارش پیشنهادهای اختصاصی'}
              </p>
            </div>
            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold bg-teal-500/10 text-teal-700 dark:text-teal-300 border border-teal-500/20">
              <span class="w-1.5 h-1.5 rounded-full bg-teal-500"></span>
              <span>Verified AI Context</span>
            </span>
          </div>

          <!-- Row 1: Name, Experience, Budget -->
          <div class="grid sm:grid-cols-3 gap-3">
            <div>
              <label class="lbl text-[11px]" for="p-name"><span>نام و عنوان شغلی</span></label>
              <input id="p-name" class="inp text-xs" placeholder="مثال: پرهام حسینی — فول‌استک" value="${esc(p.full_name || '')}">
            </div>
            <div>
              <label class="lbl text-[11px]" for="p-years"><span>سابقه کاری (سال)</span></label>
              <input id="p-years" type="number" step="0.5" class="inp text-xs" placeholder="مثال: 4" value="${p.experience_years ?? ''}">
            </div>
            <div>
              <label class="lbl text-[11px]" for="p-minbudget">
                <span>حداقل بودجه (تومان)</span>
              </label>
              <div style="direction: ltr;">
                <input id="p-minbudget" type="number" step="100000" class="inp text-xs font-mono" dir="ltr" placeholder="0" value="${p.min_acceptable_budget ?? ''}" style="text-align: left; direction: ltr;">
              </div>
            </div>
          </div>

          <!-- Row 2: Comprehensive Professional Bio & Summary -->
          <div>
            <div class="flex items-center justify-between mb-1.5">
              <label class="lbl mb-0" for="p-summary">
                <span>درباره من و خلاصه سوابق حرفه‌ای</span>
              </label>
              <span class="text-[10px] text-slate-400">استفاده مستقیم در پاراگراف اول پروپوزال</span>
            </div>
            <textarea id="p-summary" class="inp-area text-xs leading-relaxed" style="min-height:90px" placeholder="شرح تخصص‌های کلیدی، سبک کاری، فناوری‌های مسلط و سوابقی که مایلید هوش مصنوعی در پیشنهادها به آن‌ها استناد کند...">${esc(p.summary || '')}</textarea>
          </div>

          <!-- Row 3: Portfolio & GitHub URLs -->
          <div class="grid sm:grid-cols-2 gap-3">
            <div>
              <label class="lbl text-[11px]" for="p-github"><span>لینک گیت‌هاب / گیت‌لب</span></label>
              <div style="direction: ltr;">
                <input id="p-github" class="inp text-xs font-mono" dir="ltr" placeholder="https://github.com/username" value="${esc(p.github_url || '')}" style="text-align: left; direction: ltr;">
              </div>
            </div>
            <div>
              <label class="lbl text-[11px]" for="p-portfolio"><span>نمونه‌کارها یا وب‌سایت شخصی</span></label>
              <div style="direction: ltr;">
                <input id="p-portfolio" class="inp text-xs font-mono" dir="ltr" placeholder="https://portfolio.com (با کاما یا خط جدا کنید)" value="${esc((p.portfolio_urls || []).join(', '))}" style="text-align: left; direction: ltr;">
              </div>
            </div>
          </div>

          <!-- Optional Collapsible Details: Past Companies & Completed Projects -->
          <details class="p-3 rounded-2xl bg-slate-50 dark:bg-white/[0.02] border border-slate-100 dark:border-white/5 text-xs group transition">
            <summary class="font-bold cursor-pointer text-slate-700 dark:text-slate-300 flex items-center justify-between select-none list-none">
              <span class="flex items-center gap-1.5">
                <span class="text-teal-600 dark:text-teal-400">⚙️</span>
                <span>سوابق کاری تفصیلی و پروژه‌های شاخص (اختیاری)</span>
              </span>
              <span class="text-slate-400 text-[10px] group-open:rotate-180 transition-transform duration-200">▼</span>
            </summary>
            <div class="space-y-3 pt-3 mt-2 border-t border-slate-200/50 dark:border-white/5">
              <div>
                <label class="lbl text-[11px]" for="p-work">سابقه شرکت‌ها یا موقعیت‌های شغلی گذشته</label>
                <textarea id="p-work" class="inp-area text-xs" style="min-height:60px" placeholder="مثال: توسعه‌دهنده فرانت‌اند در شرکت X (۱۴۰۱ تا ۱۴۰۳)">${esc(p.work_experience || '')}</textarea>
              </div>
              <div>
                <label class="lbl text-[11px]" for="p-done">پروژه‌های برجسته‌ای که قبلاً تحویل داده‌اید</label>
                <textarea id="p-done" class="inp-area text-xs" style="min-height:60px" placeholder="مثال: سامانه رزرواسیون هتل با ری‌اکت و نود؛ پنل مدیریت اختصاصی">${esc(p.completed_projects || '')}</textarea>
              </div>
            </div>
          </details>

          <!-- Bottom Actions -->
          <div class="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-white/10">
            <span class="text-[11px] text-slate-400">تغییرات بلافاصله در تحلیل پروژه‌های جدید اعمال می‌شوند</span>
            <button class="btn-action-primary px-6" id="p-save">
              ${icon('check', 'w-4 h-4')}
              <span>ذخیره تغییرات</span>
            </button>
          </div>
        </div>

        <!-- LEFT COLUMN: Skills Manager (4 cols) -->
        <div class="lg:col-span-4 card p-5 space-y-4 border border-slate-200/80 dark:border-slate-800">
          <div class="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-white/10">
            <div>
              <h3 class="font-bold text-sm text-slate-800 dark:text-white flex items-center gap-1.5">
                ${icon('sparkles', 'w-4 h-4 text-teal-600 dark:text-teal-400')}
                <span>مهارت‌های فنی</span>
              </h3>
              <div class="text-[10px] text-slate-400 mt-0.5">${p.skills?.length || 0} مهارت ثبت‌شده</div>
            </div>
            <button class="btn-action text-xs py-1 px-2.5 flex items-center gap-1 text-teal-600 dark:text-teal-400" id="s-add">
              <span>+ مهارت</span>
            </button>
          </div>

          <!-- Quick Skill Add Input -->
          <div class="flex gap-1.5">
            <input id="sk-quick-input" class="inp text-xs flex-1" placeholder="افزودن سریع (مثلاً Python)">
            <button id="sk-quick-btn" type="button" class="btn-action-primary text-xs px-3">
              <span>ثبت</span>
            </button>
          </div>

          <!-- 1-Click Common Skills Chips -->
          <div>
            <div class="text-[10px] font-bold text-slate-400 mb-1.5">پیشنهادهای پرکاربرد (۱ کلیک):</div>
            <div class="flex flex-wrap gap-1" id="preset-skills">
              ${['پایتون', 'FastAPI', 'React', 'فتوشاپ', 'وردپرس', 'Node.js', 'UI/UX', 'سئو'].map(sk => `
                <button type="button" class="preset-chip text-[10px] py-0.5 px-2" data-add-chip="${esc(sk)}">
                  + ${esc(sk)}
                </button>
              `).join('')}
            </div>
          </div>

          <!-- Skills List -->
          <div id="skills-list" class="space-y-1.5 max-h-[360px] overflow-y-auto pt-1">
            ${p.skills && p.skills.length ? p.skills.map(s => `
              <div class="p-2.5 rounded-xl bg-slate-50 dark:bg-white/[0.03] border border-slate-100 dark:border-white/5 flex items-center justify-between gap-2 text-xs" data-skill="${s.id}">
                <div class="flex-1 min-w-0">
                  <div class="font-bold text-slate-800 dark:text-slate-100 flex items-center gap-1.5 truncate">
                    <span>${esc(s.name)}</span>
                    ${s.is_core ? `<span class="px-1.5 py-0.2 rounded text-[9px] bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 font-sans">اصلی</span>` : ''}
                  </div>
                  <div class="text-[10px] text-amber-500 tracking-wider mt-0.5">
                    ${'★'.repeat(s.level || 3)}${'☆'.repeat(5 - (s.level || 3))}
                  </div>
                </div>
                <button class="w-6 h-6 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-500/10 transition flex items-center justify-center cursor-pointer shrink-0" data-del title="حذف مهارت">
                  ✕
                </button>
              </div>
            `).join('') : emptyState('هنوز مهارتی اضافه نشده است')}
          </div>
        </div>

      </div>
    `;

    bindSettingsSubTabs(container);

    // Save Profile
    container.querySelector('#p-save').onclick = async () => {
      const splitUrls = v => v.split(/[،,\n]/).map(s => s.trim()).filter(Boolean);
      try {
        await api.put('/developer-profile', {
          full_name: container.querySelector('#p-name').value.trim(),
          experience_years: container.querySelector('#p-years').value ? Number(container.querySelector('#p-years').value) : null,
          min_acceptable_budget: container.querySelector('#p-minbudget').value ? Number(container.querySelector('#p-minbudget').value) : null,
          summary: container.querySelector('#p-summary').value.trim(),
          github_url: container.querySelector('#p-github').value.trim() || null,
          portfolio_urls: splitUrls(container.querySelector('#p-portfolio').value),
          work_experience: container.querySelector('#p-work')?.value?.trim() || '',
          completed_projects: container.querySelector('#p-done')?.value?.trim() || '',
          preferred_technologies: [],
          preferred_categories: [],
        });
        toast('پروفایل با موفقیت بروزرسانی شد', 'success');
      } catch (e) {
        toast(e.message || 'خطا در ذخیره‌سازی', 'error');
      }
    };

    // Quick Add Skill helper
    async function addSkillByName(name, level = 4) {
      if (!name) return;
      try {
        await api.post('/developer-profile/skills', {
          name,
          level,
          category: null,
          is_core: true,
        });
        toast(`مهارت «${name}» افزوده شد`, 'success');
        profile.render(container);
      } catch (e) {
        toast(e.message || 'خطا در افزودن مهارت', 'error');
      }
    }

    const quickInput = container.querySelector('#sk-quick-input');
    const quickBtn = container.querySelector('#sk-quick-btn');
    if (quickInput && quickBtn) {
      quickBtn.onclick = () => {
        const val = quickInput.value.trim();
        if (val) addSkillByName(val);
      };
      quickInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') {
          const val = quickInput.value.trim();
          if (val) addSkillByName(val);
        }
      });
    }

    // Preset chips click
    container.querySelectorAll('[data-add-chip]').forEach(chip => {
      chip.onclick = () => addSkillByName(chip.dataset.addChip);
    });

    // Modal Add Skill
    container.querySelector('#s-add').onclick = () => {
      const m = modal('افزودن مهارت تخصصی', `
        <div class="space-y-3.5 text-sm" dir="rtl">
          <div>
            <label class="lbl" for="sk-name">نام مهارت یا ابزار</label>
            <input id="sk-name" class="inp text-xs" placeholder="مثال: Python, React, Photoshop">
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="lbl" for="sk-level">سطح تسلط (۱ تا ۵ ستاره)</label>
              <select id="sk-level" class="inp text-xs">
                <option value="5">۵ ستاره — تسلط کامل (Senior)</option>
                <option value="4" selected>۴ ستاره — پیشرفته (Advanced)</option>
                <option value="3">۳ ستاره — متوسط (Intermediate)</option>
                <option value="2">۲ ستاره — آشنا (Junior)</option>
                <option value="1">۱ ستاره — مبتدی (Beginner)</option>
              </select>
            </div>
            <div>
              <label class="lbl" for="sk-cat">دسته‌بندی (اختیاری)</label>
              <input id="sk-cat" class="inp text-xs" placeholder="مثال: Backend, Design">
            </div>
          </div>
          <label class="flex items-center gap-2 text-xs cursor-pointer select-none">
            <input type="checkbox" id="sk-core" checked class="rounded border-slate-300">
            <span>مهارت اصلی (اولویت در انطباق با پروژه‌ها)</span>
          </label>
          <div class="flex justify-end gap-2 pt-2 border-t border-slate-100 dark:border-white/10">
            <button class="btn-action" data-x>انصراف</button>
            <button class="btn-action-primary px-5" data-s>افزودن مهارت</button>
          </div>
        </div>`);

      m.body.querySelector('[data-x]').onclick = m.close;
      m.body.querySelector('[data-s]').onclick = async () => {
        const name = m.body.querySelector('#sk-name').value.trim();
        if (!name) {
          toast('نام مهارت الزامی است', 'error');
          return;
        }
        try {
          await api.post('/developer-profile/skills', {
            name,
            level: Number(m.body.querySelector('#sk-level').value),
            category: m.body.querySelector('#sk-cat').value.trim() || null,
            is_core: m.body.querySelector('#sk-core').checked,
          });
          m.close();
          toast('مهارت با موفقیت ثبت شد', 'success');
          profile.render(container);
        } catch (e) {
          toast(e.message, 'error');
        }
      };
    };

    // Delete skill buttons
    container.querySelectorAll('[data-skill]').forEach(row => {
      row.querySelector('[data-del]').onclick = async () => {
        await api.del(`/developer-profile/skills/${row.dataset.skill}`);
        profile.render(container);
      };
    });
  },
};

// ------------------------------ notifications ----------------------------- //
export const notifications = {
  title: () => 'اعلان‌ها',
  async render(container) {
    container.innerHTML = spinner();
    const [data, prefs] = await Promise.all([api.get('/notifications?limit=60'), api.get('/notifications/preferences')]);
    container.innerHTML = `
      <div class="grid lg:grid-cols-3 gap-4">
        <div class="card p-4 lg:col-span-2">
          <div class="flex items-center justify-between mb-3"><h3 class="font-bold text-sm">تاریخچه اعلان‌ها</h3>
            <button class="btn text-[11px]" id="read-all">خواندن همه</button></div>
          <div class="space-y-1.5 max-h-[70vh] overflow-y-auto">
            ${data.items.length ? data.items.map(n => `
              <div class="surface p-3 ${n.is_read ? 'opacity-60' : 'border-s-2 border-s-gold-500'}">
                <div class="text-xs font-semibold">${esc(n.title)}</div>
                ${n.body ? `<div class="text-[11px] text-neutral-500 mt-1">${esc(n.body)}</div>` : ''}
                <div class="text-[10px] text-neutral-400 mt-1">${fa.datetime(n.created_at)} · ${n.type}</div>
              </div>`).join('') : emptyState('اعلانی وجود ندارد')}
          </div>
        </div>
        <div class="card p-4 space-y-3">
          <h3 class="font-bold text-sm">⚙️ تنظیمات اعلان</h3>
          ${[
            ['web_enabled', 'اعلان داشبورد (توست + زنگ)'], ['telegram_enabled', 'ارسال به تلگرام'],
            ['sound_enabled', 'صدای چایم'], ['browser_notifications', 'Notification مرورگر'],
            ['push_enabled', 'Web Push (خودکارسازی پس از فعال‌سازی)'],
          ].map(([k, label]) => `<label class="flex items-center gap-2 text-xs"><input type="checkbox" data-pref="${k}" ${prefs[k] ? 'checked' : ''}> ${label}</label>`).join('')}
          <div><label class="lbl">بلندی صدا: ${Math.round(prefs.volume * 100)}%</label>
            <input id="vol" type="range" min="0" max="100" value="${Math.round(prefs.volume * 100)}" class="w-full accent-gold-500">
            <button class="btn text-[11px] mt-1" id="test-sound">پخش چایم نمونه</button></div>
          <div><label class="lbl">حداقل امتیاز برای اعلان (۰ = همه)</label><input id="minscore" type="number" min="0" max="100" class="inp" value="${prefs.min_score_to_notify}"></div>
          <div class="flex justify-end"><button class="btn btn-primary" id="save-prefs">ذخیره</button></div>
        </div>
      </div>`;
    container.querySelector('#read-all').onclick = async () => { await api.post('/notifications/read-all'); notifications.render(container); };
    container.querySelector('#test-sound').onclick = () => { setSoundPrefs(true, container.querySelector('#vol').value / 100); playChime(); };
    container.querySelector('#save-prefs').onclick = async () => {
      const body = {};
      container.querySelectorAll('[data-pref]').forEach(c => body[c.dataset.pref] = c.checked);
      body.volume = Number(container.querySelector('#vol').value) / 100;
      body.min_score_to_notify = Number(container.querySelector('#minscore').value);
      await api.put('/notifications/preferences', body);
      setSoundPrefs(body.sound_enabled, body.volume);
      toast('ذخیره شد', 'success');
    };
  },
};

// ------------------------------ prompt studio ----------------------------- //
export const prompts = {
  title: () => 'استودیو پرامپت',
  async render(container) {
    container.innerHTML = spinner();
    const data = await api.get('/prompts');
    const faName = { analyzer: 'تحلیلگر پروژه', proposal: 'تولیدکننده پیشنهاد', quality: 'بازبین کیفیت' };
    container.innerHTML = `
      ${settingsSubTabs('prompts')}
      <div class="space-y-4">
      <div class="text-xs text-neutral-500 leading-6">قالب سیستم‌پرامپت هر ایجنت هوش مصنوعی. هر ویرایش یک نسخه جدید می‌سازد؛ نسخه‌های قبلی حفظ و قابل فعال‌سازی مجدد هستند.</div>
      ${data.items.map(pr => `
        <div class="card p-5 border border-slate-200/80 dark:border-slate-800" data-prompt="${pr.key}">
          <div class="flex items-center justify-between mb-2">
            <h3 class="font-bold text-sm flex items-center gap-2">
              ${icon('reports', 'w-4 h-4 text-teal-600')}
              <span>${faName[pr.key] || pr.key}</span>
              <span class="text-[10px] text-neutral-400">(${pr.key})</span>
            </h3>
            <button class="btn text-xs flex items-center gap-1" data-new>
              ${icon('sparkles', 'w-3 h-3 text-amber-500')}
              <span>ویرایش / نسخه جدید</span>
            </button>
          </div>
          <div class="text-[11px] text-neutral-500 mb-2">${esc(pr.description)}</div>
          <div class="space-y-1.5">
            ${pr.versions.map(v => `
              <div class="surface p-2.5 flex items-center gap-2 text-xs" data-ver="${v.id}">
                ${badge(v.is_active ? `نسخه ${v.version_no} فعال` : `نسخه ${v.version_no}`, v.is_active ? 'green' : 'neutral')}
                <span class="text-neutral-400 flex-1 truncate">${esc(v.template.slice(0, 90))}…</span>
                ${!v.is_active ? '<button class="btn text-[10px]" data-activate>فعال‌سازی</button>' : ''}
              </div>`).join('')}
          </div>
        </div>`).join('')}
    </div>`;

    container.querySelectorAll('[data-prompt]').forEach(card => {
      const key = card.dataset.prompt;
      const pr = data.items.find(x => x.key === key);
      card.querySelector('[data-new]').onclick = () => {
        const active = pr.versions.find(v => v.is_active);
        const m = modal(`ویرایش پرامپت — ${faName[key] || key}`, `
          <textarea id="tpl" class="inp-area" style="min-height:320px" dir="rtl">${esc(active?.template || '')}</textarea>
          <div class="flex justify-end gap-2 mt-3"><button class="btn" data-x>انصراف</button><button class="btn btn-primary" data-s>ذخیره نسخه جدید</button></div>`);
        m.body.querySelector('[data-x]').onclick = m.close;
        m.body.querySelector('[data-s]').onclick = async () => {
          await api.post(`/prompts/${key}/versions`, { template: m.body.querySelector('#tpl').value });
          toast('نسخه جدید فعال شد', 'success'); m.close(); prompts.render(container);
        };
      };
      card.querySelectorAll('[data-ver]').forEach(row => {
        row.querySelector('[data-activate]')?.addEventListener('click', async () => {
          await api.put(`/prompts/${key}/activate/${row.dataset.ver}`);
          toast('نسخه فعال شد', 'success'); prompts.render(container);
        });
      });
    });
    bindSettingsSubTabs(container);
  },
};

// ------------------------------ analytics / insights --------------------- //
export const analytics = {
  title: () => currentLang() === 'en' ? 'Performance Insights' : 'بینش و آمار عملکرد',
  async render(container) {
    container.innerHTML = spinner();
    const isEn = currentLang() === 'en';
    let s;
    try {
      s = await api.get('/analytics/summary');
    } catch (err) {
      container.innerHTML = `<div class="card p-6 text-sm text-red-500">${err.message || 'Error loading analytics'}</div>`;
      return;
    }

    const totalProj = s.projects?.total || 0;
    const recommendedProj = s.projects?.recommended || 0;
    const submittedProps = s.proposals?.submitted || 0;
    const generatedProps = s.proposals?.generated || 0;
    const wonProps = s.proposals?.won || 0;
    const convRate = s.proposals?.conversion_rate_percent ?? 0;
    const totalBidVal = s.proposals?.total_bid_value || 0;
    const avgBidVal = s.proposals?.avg_bid || 0;
    const timeSaved = s.time_saved_hours || 0;
    const totalTokens = s.ai?.total_tokens || 0;
    const promptTokens = s.ai?.prompt_tokens || 0;
    const compTokens = s.ai?.completion_tokens || 0;
    const estCost = s.ai?.estimated_cost || 0;

    container.innerHTML = `
      <!-- Executive Header Banner -->
      <div class="flex flex-wrap items-center justify-between gap-4 mb-6 pb-4 border-b border-slate-200/60 dark:border-slate-800">
        <div>
          <div class="flex items-center gap-2.5">
            <h2 class="text-xl md:text-2xl font-black text-slate-900 dark:text-white tracking-tight">
              ${isEn ? 'Executive Intelligence & Performance' : 'تحلیل جامع و عملکرد سیستم'}
            </h2>
            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-teal-500/10 text-teal-700 dark:text-teal-300 border border-teal-500/20">
              <span class="w-1.5 h-1.5 rounded-full bg-teal-500 animate-pulse"></span>
              <span>${isEn ? 'Live Telemetry' : 'رصد زنده'}</span>
            </span>
          </div>
          <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">
            ${isEn ? 'Holistic analytics covering opportunity discovery, proposal conversions, channel breakdown, and AI token economics.' : 'نمای تحلیلی یکپارچه از پروژه‌های کشف‌شده، نرخ پذیرش پیشنهادها، سهم پلتفرم‌ها و هزینه هوش مصنوعی.'}
          </p>
        </div>

        <div class="flex items-center gap-2">
          <button id="btn-refresh-analytics" class="pill-btn text-xs font-semibold" title="${isEn ? 'Refresh Data' : 'بروزرسانی داده‌ها'}">
            ${icon('refresh', 'w-3.5 h-3.5')}
            <span>${isEn ? 'Refresh' : 'بروزرسانی'}</span>
          </button>
        </div>
      </div>

      <!-- 4 Top Executive Stat Cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <!-- Card 1: Projects Analyzed -->
        <div class="card p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm relative overflow-hidden group hover:shadow-md transition">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">${isEn ? 'Discovered Projects' : 'پروژه‌های کشف‌شده'}</span>
            <div class="w-9 h-9 rounded-xl bg-teal-50 dark:bg-teal-950/40 text-teal-600 dark:text-teal-400 flex items-center justify-center">
              ${icon('folder', 'w-4 h-4')}
            </div>
          </div>
          <div class="text-2xl md:text-3xl font-black text-slate-900 dark:text-white mb-2 font-sans">${totalProj}</div>
          <div class="flex items-center justify-between text-[11px]">
            <span class="text-slate-500 dark:text-slate-400">${isEn ? 'AI Match Rate:' : 'توصیه هوشمند:'}</span>
            <span class="font-bold text-teal-600 dark:text-teal-400">${recommendedProj} ${isEn ? 'projects' : 'مورد'}</span>
          </div>
        </div>

        <!-- Card 2: Proposals Pipeline -->
        <div class="card p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm relative overflow-hidden group hover:shadow-md transition">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">${isEn ? 'Active Proposals' : 'پیشنهادهای ارسالی'}</span>
            <div class="w-9 h-9 rounded-xl bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
              ${icon('plane', 'w-4 h-4')}
            </div>
          </div>
          <div class="text-2xl md:text-3xl font-black text-slate-900 dark:text-white mb-2 font-sans">${submittedProps}</div>
          <div class="flex items-center justify-between text-[11px]">
            <span class="text-slate-500 dark:text-slate-400">${isEn ? 'Conversion Rate:' : 'نرخ تبدیل:'}</span>
            <span class="font-bold text-indigo-600 dark:text-indigo-400">${convRate}%</span>
          </div>
        </div>

        <!-- Card 3: Time Saved -->
        <div class="card p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm relative overflow-hidden group hover:shadow-md transition">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">${isEn ? 'Time Saved' : 'زمان صرفه‌جویی‌شده'}</span>
            <div class="w-9 h-9 rounded-xl bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 flex items-center justify-center">
              ${icon('clock', 'w-4 h-4')}
            </div>
          </div>
          <div class="text-2xl md:text-3xl font-black text-amber-600 dark:text-amber-400 mb-2 font-sans">
            ${timeSaved} <span class="text-sm font-bold text-slate-600 dark:text-slate-300">${isEn ? 'hrs' : 'ساعت'}</span>
          </div>
          <div class="flex items-center justify-between text-[11px]">
            <span class="text-slate-500 dark:text-slate-400">${isEn ? 'Per Proposal:' : 'به ازای هر پیشنهاد:'}</span>
            <span class="font-bold text-slate-700 dark:text-slate-200">~۴۵ ${isEn ? 'mins' : 'دقیقه'}</span>
          </div>
        </div>

        <!-- Card 4: AI Model Tokens -->
        <div class="card p-5 border border-slate-200/80 dark:border-slate-800 shadow-sm relative overflow-hidden group hover:shadow-md transition">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">${isEn ? 'AI Token Usage' : 'توکن‌های هوش مصنوعی'}</span>
            <div class="w-9 h-9 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
              ${icon('cpu', 'w-4 h-4')}
            </div>
          </div>
          <div class="text-2xl md:text-3xl font-black text-slate-900 dark:text-white mb-2 font-sans">${totalTokens.toLocaleString(isEn ? 'en-US' : 'fa-IR')}</div>
          <div class="flex items-center justify-between text-[11px]">
            <span class="text-slate-500 dark:text-slate-400">${isEn ? 'Est. Cost:' : 'هزینه تخمینی:'}</span>
            <span class="font-bold text-emerald-600 dark:text-emerald-400 font-sans">$${estCost}</span>
          </div>
        </div>
      </div>

      <!-- Second Row: 2 Visual Grid Columns -->
      <div class="grid lg:grid-cols-2 gap-5 mb-6">
        <!-- Platform Market Share & Volume -->
        <div class="card p-6 border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <div class="flex items-center justify-between mb-4">
            <div>
              <h3 class="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2">
                ${icon('channels', 'w-4 h-4 text-teal-600 dark:text-teal-400')}
                <span>${isEn ? 'Freelance Channels Share' : 'پروژه‌ها به تفکیک پلتفرم'}</span>
              </h3>
              <p class="text-[11px] text-slate-400 mt-0.5">${isEn ? 'Live distribution of incoming opportunities' : 'توزیع زنده فرصت‌های کاری ورودی'}</p>
            </div>
            <span class="text-xs font-bold text-slate-500 dark:text-slate-400">${s.projects?.by_platform?.length || 0} ${isEn ? 'Platforms' : 'پلتفرم'}</span>
          </div>

          <div class="space-y-4">
            ${(s.projects?.by_platform || []).length ? s.projects.by_platform.map(p => {
              const pct = totalProj ? Math.round((p.count / totalProj) * 100) : 0;
              return `
                <div>
                  <div class="flex items-center justify-between text-xs mb-1.5">
                    <span class="font-semibold text-slate-700 dark:text-slate-200">${esc(p.name)}</span>
                    <div class="flex items-center gap-2">
                      <span class="font-bold text-slate-900 dark:text-white font-sans">${p.count}</span>
                      <span class="text-[10px] text-slate-400 font-sans">(${pct}%)</span>
                    </div>
                  </div>
                  <div class="w-full h-2.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                    <div class="h-full rounded-full bg-teal-600 transition-all duration-500" style="width: ${Math.max(pct, 3)}%"></div>
                  </div>
                </div>
              `;
            }).join('') : emptyState(isEn ? 'No platforms connected' : 'پلتفرمی متصل نیست')}
          </div>
        </div>

        <!-- Project Pipeline Status Breakdown -->
        <div class="card p-6 border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <div class="flex items-center justify-between mb-4">
            <div>
              <h3 class="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2">
                ${icon('chart', 'w-4 h-4 text-teal-600 dark:text-teal-400')}
                <span>${isEn ? 'Project Lifecycle Status' : 'توزیع مراحل و وضعیت پروژه‌ها'}</span>
              </h3>
              <p class="text-[11px] text-slate-400 mt-0.5">${isEn ? 'From initial scraping to proposal submission' : 'از زمان کشف اولیه تا ارسال پروپوزال'}</p>
            </div>
            <span class="text-xs font-bold text-slate-500 dark:text-slate-400">${Object.keys(s.projects?.by_status || {}).length} ${isEn ? 'Stages' : 'مرحله'}</span>
          </div>

          <div class="space-y-2.5">
            ${Object.entries(s.projects?.by_status || {}).map(([k, v]) => {
              const label = STATUS_FA[k] || k;
              const pct = totalProj ? Math.round((v / totalProj) * 100) : 0;
              return `
                <div class="flex items-center justify-between p-2.5 rounded-xl bg-slate-50/70 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800">
                  <div class="flex items-center gap-2 text-xs font-medium text-slate-700 dark:text-slate-200">
                    <span class="w-2 h-2 rounded-full bg-teal-500"></span>
                    <span>${label}</span>
                  </div>
                  <div class="flex items-center gap-3">
                    <span class="text-xs font-bold text-slate-900 dark:text-white font-sans">${v}</span>
                    <span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 font-sans">${pct}%</span>
                  </div>
                </div>
              `;
            }).join('') || emptyState()}
          </div>
        </div>
      </div>

      <!-- Third Row: AI Economics & Financial Pipeline -->
      <div class="grid lg:grid-cols-2 gap-5">
        <!-- AI Intelligence Economics Card -->
        <div class="card p-6 border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <div class="flex items-center justify-between mb-4">
            <h3 class="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2">
              ${icon('cpu', 'w-4 h-4 text-emerald-600 dark:text-emerald-400')}
              <span>${isEn ? 'AI Intelligence Economics' : 'اقتصاد هوش مصنوعی و مدل‌ها'}</span>
            </h3>
            <button class="text-xs font-bold text-teal-600 dark:text-teal-400 hover:underline" id="btn-goto-ai">${isEn ? 'Manage AI Providers' : 'مدیریت ارائه‌دهندگان'}</button>
          </div>

          <div class="grid grid-cols-2 gap-3 mb-4">
            <div class="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
              <div class="text-[11px] text-slate-400 mb-1">${isEn ? 'Prompt / Input Tokens' : 'توکن‌های ورودی'}</div>
              <div class="text-base font-bold text-slate-800 dark:text-slate-100 font-sans">${promptTokens.toLocaleString(isEn ? 'en-US' : 'fa-IR')}</div>
            </div>
            <div class="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
              <div class="text-[11px] text-slate-400 mb-1">${isEn ? 'Completion / Output Tokens' : 'توکن‌های خروجی'}</div>
              <div class="text-base font-bold text-slate-800 dark:text-slate-100 font-sans">${compTokens.toLocaleString(isEn ? 'en-US' : 'fa-IR')}</div>
            </div>
          </div>

          <div class="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-800 dark:text-emerald-300 leading-relaxed">
            <div class="font-bold mb-1">${isEn ? 'Transparent Cost Calculation' : 'محاسبه شفاف هزینه'}</div>
            <p class="text-[11px] opacity-90">${esc(s.ai?.note || '')}</p>
          </div>
        </div>

        <!-- Financial Pipeline & Bid Strategy -->
        <div class="card p-6 border border-slate-200/80 dark:border-slate-800 shadow-sm">
          <div class="flex items-center justify-between mb-4">
            <h3 class="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2">
              ${icon('dollar', 'w-4 h-4 text-amber-600 dark:text-amber-400')}
              <span>${isEn ? 'Financial Volume & Bid Pipeline' : 'ارزش مالی مناقصات و پیشنهادات'}</span>
            </h3>
            <button class="text-xs font-bold text-teal-600 dark:text-teal-400 hover:underline" id="btn-goto-proposals">${isEn ? 'View Proposals' : 'مشاهده پیشنهادها'}</button>
          </div>

          <div class="grid grid-cols-2 gap-3 mb-4">
            <div class="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
              <div class="text-[11px] text-slate-400 mb-1">${isEn ? 'Total Bid Volume' : 'ارزش کل پیشنهادات'}</div>
              <div class="text-base font-bold text-slate-800 dark:text-slate-100 font-sans">${fa.toman(totalBidVal)}</div>
            </div>
            <div class="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800">
              <div class="text-[11px] text-slate-400 mb-1">${isEn ? 'Average Bid Value' : 'میانگین قیمت پیشنهاد'}</div>
              <div class="text-base font-bold text-slate-800 dark:text-slate-100 font-sans">${fa.toman(avgBidVal)}</div>
            </div>
          </div>

          <div class="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800 text-xs">
            <span class="text-slate-500 dark:text-slate-400">${isEn ? 'Won Submissions:' : 'مناقصات برنده (با شواهد):'}</span>
            <span class="font-bold text-emerald-600 dark:text-emerald-400 font-sans">${wonProps} ${isEn ? 'won' : 'پروژه'}</span>
          </div>
        </div>
      </div>
    `;

    // Event handlers
    container.querySelector('#btn-refresh-analytics')?.addEventListener('click', () => {
      analytics.render(container);
    });
    container.querySelector('#btn-goto-ai')?.addEventListener('click', () => {
      navigate('ai');
    });
    container.querySelector('#btn-goto-proposals')?.addEventListener('click', () => {
      navigate('proposals');
    });
  },
};

// ------------------------------ logs -------------------------------------- //
export const logs = {
  title: () => 'لاگ‌های اجرا',
  async render(container) {
    container.innerHTML = spinner();
    const data = await api.get('/logs?limit=150');
    const lvlColor = { info: 'sky', warning: 'amber', error: 'red', debug: 'neutral' };
    container.innerHTML = `
      ${settingsSubTabs('logs')}
      <div class="flex flex-wrap gap-2 mb-3">
        <select id="log-level" class="inp max-w-36 text-xs"><option value="">همه سطوح</option>
          ${['info', 'warning', 'error'].map(l => `<option value="${l}">${l}</option>`).join('')}</select>
        <input id="log-comp" class="inp max-w-44 text-xs" placeholder="کامپوننت (analyzer, discovery…)">
        <button class="btn text-xs" id="log-filter">فیلتر</button>
      </div>
      <div class="card p-2 overflow-x-auto"><table class="tbl"><thead><tr><th>زمان</th><th>سطح</th><th>کامپوننت</th><th>پیام</th></tr></thead>
      <tbody>${data.items.length ? data.items.map(l => `<tr>
        <td class="text-[10px] whitespace-nowrap">${fa.datetime(l.created_at)}</td>
        <td>${badge(l.level, lvlColor[l.level] || 'neutral')}</td>
        <td class="text-[11px]">${esc(l.component)}</td>
        <td class="text-[11px]">${esc(l.message)}${l.project_id ? ` <span class="text-neutral-400">(پروژه ${l.project_id})</span>` : ''}</td>
      </tr>`).join('') : `<tr><td colspan="4">${emptyState('لاگی نیست')}</td></tr>`}</tbody></table></div>`;
    container.querySelector('#log-filter').onclick = async () => {
      const level = container.querySelector('#log-level').value;
      const comp = container.querySelector('#log-comp').value.trim();
      const d = await api.get(`/logs?limit=150${level ? `&level=${level}` : ''}${comp ? `&component=${encodeURIComponent(comp)}` : ''}`);
      container.querySelector('tbody').innerHTML = d.items.length ? d.items.map(l => `<tr>
        <td class="text-[10px] whitespace-nowrap">${fa.datetime(l.created_at)}</td>
        <td>${badge(l.level, lvlColor[l.level] || 'neutral')}</td>
        <td class="text-[11px]">${esc(l.component)}</td>
        <td class="text-[11px]">${esc(l.message)}</td></tr>`).join('') : `<tr><td colspan="4">${emptyState('لاگی نیست')}</td></tr>`;
    };
    bindSettingsSubTabs(container);
  },
};

// ------------------------------ settings ---------------------------------- //
export const settings = {
  title: () => 'تنظیمات',
  async render(container) {
    container.innerHTML = `
      ${settingsSubTabs('settings')}
      <div class="grid lg:grid-cols-2 gap-4">
        <div class="card p-5 space-y-3 border border-slate-200/80 dark:border-slate-800">
          <h3 class="font-bold text-sm flex items-center gap-2">
            ${icon('sun', 'w-4 h-4 text-teal-600')}
            <span>ظاهر و زبان / Appearance & Language</span>
          </h3>
          <div class="flex items-center gap-2 text-xs"><span>حالت:</span>
            <button class="btn" id="s-dark">تیره / Dark</button><button class="btn" id="s-light">روشن / Light</button></div>
          <div class="flex items-center gap-2 text-xs"><span>زبان:</span>
            <button class="btn" id="s-fa">فارسی (RTL)</button><button class="btn" id="s-en">English (LTR)</button></div>
        </div>
        <div class="card p-5 space-y-3 border border-slate-200/80 dark:border-slate-800">
          <h3 class="font-bold text-sm flex items-center gap-2">
            ${icon('settings', 'w-4 h-4 text-teal-600')}
            <span>تغییر رمز عبور / Security</span>
          </h3>
          <div><label class="lbl">رمز فعلی</label><input id="cur-pass" type="password" class="inp"></div>
          <div><label class="lbl">رمز جدید (حداقل ۸ کاراکتر)</label><input id="new-pass" type="password" class="inp"></div>
          <div class="flex justify-end"><button class="btn btn-primary" id="change-pass">تغییر رمز</button></div>
        </div>
      </div>`;
    bindSettingsSubTabs(container);
    container.querySelector('#s-dark').onclick = () => { localStorage.setItem('fa_theme', 'dark'); applyTheme(); };
    container.querySelector('#s-light').onclick = () => { localStorage.setItem('fa_theme', 'light'); applyTheme(); };
    container.querySelector('#s-fa').onclick = () => location.reload();
    container.querySelector('#s-en').onclick = async () => {
      await api.put('/settings/user', { language: 'en' });
      localStorage.setItem('fa_lang', 'en'); location.reload();
    };
    container.querySelector('#change-pass').onclick = async () => {
      try {
        await api.post('/auth/change-password', {
          current_password: container.querySelector('#cur-pass').value,
          new_password: container.querySelector('#new-pass').value,
        });
        toast('رمز عبور تغییر کرد', 'success');
      } catch (e) { toast(e.message, 'error'); }
    };
  },
};
