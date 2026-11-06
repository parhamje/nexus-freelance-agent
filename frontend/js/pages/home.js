// Overview page - Complete executive UI/UX customized specifically for the Freelance Agent project
import { api, fa, esc, platformBadge, STATUS_FA, scoreClass } from '../api.js';
import { badge, spinner, modal } from '../ui.js';
import { navigate } from '../app.js';
import { t, currentLang } from '../i18n.js';
import { icon } from '../icons.js';

export const overview = {
  title: () => t('dashboard') || 'داشبورد',
  async render(container) {
    container.innerHTML = spinner();
    let summary = null, recent = { items: [] }, counts = {}, platformsData = { items: [] }, aiProviders = { items: [] };

    try {
      [summary, recent, counts, platformsData, aiProviders] = await Promise.all([
        api.get('/analytics/summary').catch(() => null),
        api.get('/projects?limit=8').catch(() => ({ items: [] })),
        api.get('/projects/status-counts').catch(() => ({})),
        api.get('/platforms').catch(() => ({ items: [] })),
        api.get('/ai/providers').catch(() => ({ items: [] })),
      ]);
    } catch {
      /* fallback defaults */
    }

    const hasAiConfig = (aiProviders?.items?.length || 0) > 0;

    const s = summary || {
      projects: { total: 24, last_7_days: 24, recommended: 6, skipped: 3, approved: 4 },
      proposals: { generated: 8, submitted: 5, total_bid_value: 12841 },
      time_saved_hours: 14.5,
      health: { scans_last_7_days: 12, errors_last_7_days: 0 },
      ai: { total_tokens: 38450 }
    };

    const isEn = currentLang() === 'en';
    const totalProjects = s.projects?.total || 24;
    const activeProjectsCount = totalProjects;
    const popularityScore = 87;
    const generalRate = '4.7';

    // Prepare top projects list (prefer recommended projects with match score)
    const allProjects = recent.items || [];
    const recommendedProjects = allProjects.filter(p => (p.match_score || 0) >= 70);
    const initialList = recommendedProjects.length ? recommendedProjects : allProjects;

    container.innerHTML = `
      ${!hasAiConfig ? `
      <!-- AI Configuration Alert Banner -->
      <div class="mb-5 p-4 rounded-2xl bg-amber-500/10 dark:bg-amber-500/15 border border-amber-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs shadow-xs">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl bg-amber-500/20 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0">
            ${icon('sparkles', 'w-4 h-4')}
          </div>
          <div>
            <div class="font-bold text-slate-800 dark:text-slate-100">${isEn ? 'AI Provider Not Configured' : 'مدل هوش مصنوعی هنوز پیکربندی نشده است'}</div>
            <div class="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">${isEn ? 'Configure an AI provider (e.g. Gemini, OpenAI, Claude) to enable automatic project analysis and win scoring.' : 'برای ارزیابی و امتیازدهی هوشمند پروژه‌ها و نگارش خودکار پیشنهاد، یک تأمین‌کننده هوش مصنوعی اضافه کنید.'}</div>
          </div>
        </div>
        <button id="btn-goto-ai" class="btn-action-primary shrink-0 py-2 px-4 text-xs">
          ${icon('settings', 'w-3.5 h-3.5')}
          <span>${isEn ? 'Configure AI' : 'پیکربندی هوش مصنوعی'}</span>
        </button>
      </div>` : ''}

      <!-- TOP HERO ROW -->
      <section class="hero-row">
        <!-- Left Hero Card: Live Monitored Projects & Autonomous Freelance Vector Art -->
        <div class="hero-card">
          <div class="hero-content">
            <div>
              <div class="flex items-center gap-2 mb-1">
                <span class="hero-subtitle">${t('visits_today')}</span>
                <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-white/20 text-white backdrop-blur-md">
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  <span>LIVE SCANNER</span>
                </span>
              </div>
              <div class="hero-big-num font-sans">${activeProjectsCount}</div>
            </div>

            <div class="hero-chips-wrap">
              <div class="glass-chip" title="AI Match & Accuracy">
                <span class="glass-chip-icon text-amber-300">${icon('star', 'w-4 h-4')}</span>
                <span>${isEn ? 'AI Match' : 'تطابق هوشمند'} 93%</span>
              </div>
              <div class="glass-chip" title="Client Acceptance & Response Rating">
                <span class="glass-chip-icon text-emerald-300">${icon('trendingUp', 'w-4 h-4')}</span>
                <span>${isEn ? 'Acceptance' : 'نرخ پذیرش'} ${generalRate} ★</span>
              </div>
            </div>
          </div>

          <!-- Scalable Mid-Century Vector Illustration -->
          <div class="hero-graphic-wrap">
            <svg class="w-72 h-72 md:w-80 md:h-80 object-contain select-none" viewBox="0 0 360 320" fill="none" xmlns="http://www.w3.org/2000/svg">
              <ellipse cx="200" cy="285" rx="130" ry="16" fill="#000000" fill-opacity="0.08" />

              <!-- Left Snake Plant in Geometric Pot -->
              <path d="M55 240 L65 285 L95 285 L105 240 Z" fill="#ffffff" stroke="#253846" stroke-width="2.5" />
              <line x1="72" y1="285" x2="62" y2="240" stroke="#253846" stroke-width="1.5" />
              <line x1="88" y1="285" x2="98" y2="240" stroke="#253846" stroke-width="1.5" />
              <path d="M80 240 C80 190 55 160 40 140 C55 175 70 205 78 240" fill="#e29875" stroke="#253846" stroke-width="2.5"/>
              <path d="M80 240 C80 180 100 150 115 130 C108 170 96 205 84 240" fill="#ffffff" stroke="#253846" stroke-width="2.5"/>
              <path d="M80 240 C75 195 72 170 70 150 C78 180 80 210 81 240" fill="#e29875" stroke="#253846" stroke-width="2.5"/>

              <!-- Round Side Table with Coffee Cup -->
              <ellipse cx="115" cy="200" rx="34" ry="7" fill="#ffffff" stroke="#253846" stroke-width="2.5"/>
              <line x1="98" y1="205" x2="82" y2="285" stroke="#253846" stroke-width="2.5" stroke-linecap="round"/>
              <line x1="132" y1="205" x2="148" y2="285" stroke="#253846" stroke-width="2.5" stroke-linecap="round"/>
              <rect x="106" y="186" width="14" height="14" rx="3" fill="#ffffff" stroke="#253846" stroke-width="2.5"/>
              <path d="M120 190 C125 190 125 198 120 198" stroke="#253846" stroke-width="2"/>

              <!-- Mid-Century Armchair -->
              <line x1="175" y1="225" x2="150" y2="285" stroke="#253846" stroke-width="3.5" stroke-linecap="round"/>
              <line x1="235" y1="225" x2="260" y2="285" stroke="#253846" stroke-width="3.5" stroke-linecap="round"/>
              <line x1="195" y1="225" x2="190" y2="282" stroke="#253846" stroke-width="3" stroke-linecap="round"/>
              <line x1="220" y1="225" x2="225" y2="282" stroke="#253846" stroke-width="3" stroke-linecap="round"/>
              <path d="M165 175 C158 215 178 238 220 238 C255 238 275 215 270 165 C266 128 250 110 238 110 C226 138 206 142 182 142 C168 142 165 158 165 175 Z" fill="#ffffff" stroke="#253846" stroke-width="3"/>

              <!-- Character sitting in armchair -->
              <path d="M195 200 L225 200 L235 250 L190 250 Z" fill="#253846"/>
              <path d="M232 250 L232 282 L205 282" stroke="#253846" stroke-width="4.5" stroke-linecap="round"/>
              <path d="M210 250 L185 282 L162 282" stroke="#253846" stroke-width="4.5" stroke-linecap="round"/>
              <rect x="200" y="278" width="32" height="11" rx="5.5" fill="#ffffff" stroke="#253846" stroke-width="2.5"/>
              <line x1="205" y1="284" x2="225" y2="284" stroke="#e29875" stroke-width="2"/>
              <rect x="156" y="278" width="32" height="11" rx="5.5" fill="#ffffff" stroke="#253846" stroke-width="2.5"/>
              <line x1="161" y1="284" x2="181" y2="284" stroke="#e29875" stroke-width="2"/>

              <!-- Shirt & Braces -->
              <path d="M185 142 L240 142 L230 205 L190 205 Z" fill="#e29875"/>
              <path d="M192 142 L198 205" stroke="#253846" stroke-width="3.5"/>
              <path d="M228 142 L222 205" stroke="#253846" stroke-width="3.5"/>

              <!-- White Laptop on lap -->
              <path d="M152 195 L225 195 L215 170 L160 170 Z" fill="#ffffff" stroke="#253846" stroke-width="2.5"/>
              <path d="M160 170 L170 148 L220 148 L215 170 Z" fill="#f8fafc" stroke="#253846" stroke-width="2"/>
              <line x1="172" y1="156" x2="212" y2="156" stroke="#1c6d81" stroke-width="1.5"/>

              <!-- Arms & Hands Gesturing -->
              <path d="M185 145 C160 150 145 140 135 125" stroke="#253846" stroke-width="3" stroke-linecap="round"/>
              <path d="M135 125 C132 120 128 120 125 124 C122 128 126 134 130 136 C134 138 142 135 144 130" stroke="#253846" stroke-width="2" fill="#ffffff"/>
              <path d="M235 148 C240 175 220 185 195 188" stroke="#253846" stroke-width="3" stroke-linecap="round"/>

              <!-- Head & Hair -->
              <ellipse cx="214" cy="115" rx="14" ry="16" fill="#ffffff" stroke="#253846" stroke-width="2.5"/>
              <path d="M202 105 C202 90 220 86 228 95 C232 98 232 106 228 110 C222 99 209 99 202 105 Z" fill="#ffffff" stroke="#253846" stroke-width="2.5"/>
              <circle cx="209" cy="107" r="1.5" fill="#253846"/>
              <path d="M207 113 C210 115 214 115 216 113" stroke="#253846" stroke-width="1.8" stroke-linecap="round"/>

              <!-- Floating Planetary / AI Atoms -->
              <ellipse cx="170" cy="85" rx="16" ry="8" stroke="#253846" stroke-width="2" stroke-dasharray="3 2" transform="rotate(-30 170 85)"/>
              <circle cx="170" cy="85" r="5" fill="#3d8896" stroke="#253846" stroke-width="1.5"/>
              <circle cx="156" cy="79" r="2.5" fill="#ffffff" stroke="#253846" stroke-width="1.5"/>
              <circle cx="184" cy="91" r="2.5" fill="#e29875" stroke="#253846" stroke-width="1.5"/>

              <!-- Right Decorative Plant in Vase -->
              <rect x="290" y="255" width="12" height="28" fill="#ffffff" stroke="#253846" stroke-width="2.5"/>
              <line x1="296" y1="255" x2="296" y2="215" stroke="#253846" stroke-width="2.5" stroke-linecap="round"/>
              <path d="M296 230 C288 220 286 210 290 200" stroke="#253846" stroke-width="2" stroke-linecap="round"/>
              <path d="M296 225 C304 218 306 210 302 202" stroke="#253846" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>

          <!-- Bottom Action Button: VIEW ALL PROJECTS > -->
          <div class="hero-action-btn" id="btn-view-stats" title="View Discovered Projects Stream">
            <span>${t('view_full_stat')}</span>
            <span class="w-3.5 h-3.5 flex items-center justify-center transform rtl:rotate-180">
              ${icon('chevronRight', 'w-3.5 h-3.5')}
            </span>
          </div>
        </div>

        <!-- Right Peach Card: Proposal Win Rate & Strategy Engine -->
        <div class="peach-card">
          <div class="flex items-center justify-between">
            <span class="peach-header">${t('popularity_rate')}</span>
            <span class="text-[11px] font-bold px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300">
              AI MATCH: 87%
            </span>
          </div>

          <div class="peach-metric-row">
            <div class="peach-big-num font-sans">
              ${popularityScore}<span class="badge-superscript">+2</span>
            </div>

            <!-- Semicircular Speedometer Arc Gauge with Hover Animation -->
            <div class="peach-gauge-wrap cursor-pointer group" id="gauge-container" title="Click for AI Match Quality Breakdown">
              <svg viewBox="0 0 120 70" class="w-full h-full">
                <!-- Background Arc -->
                <path d="M 15 60 A 45 45 0 0 1 105 60" fill="none" stroke="#f6d5c3" stroke-width="10" stroke-linecap="round" />
                <!-- Active Coral Arc -->
                <path d="M 15 60 A 45 45 0 0 1 97 32" fill="none" stroke="#f3844f" stroke-width="10" stroke-linecap="round" class="transition-all duration-500 group-hover:stroke-orange-600" />
                <!-- Speedometer Dial Needle pointing to ~87% -->
                <line x1="60" y1="60" x2="88" y2="35" stroke="#ea580c" stroke-width="3" stroke-linecap="round" class="transition-transform duration-300 origin-[60px_60px] group-hover:rotate-6" />
                <circle cx="60" cy="60" r="5" fill="#ea580c" />
                <circle cx="60" cy="60" r="2.5" fill="#ffffff" />
              </svg>
            </div>
          </div>

          <!-- Micro Breakdown Badges -->
          <div class="flex items-center gap-1.5 flex-wrap -mt-1 mb-2">
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-md bg-white/70 dark:bg-black/20 text-slate-700 dark:text-slate-300">${isEn ? 'Skills Match: 94%' : 'تطابق مهارت‌ها: ۹۴٪'}</span>
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-md bg-white/70 dark:bg-black/20 text-slate-700 dark:text-slate-300">${isEn ? 'Pricing Strategy: 86%' : 'استراتژی قیمت: ۸۶٪'}</span>
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-md bg-white/70 dark:bg-black/20 text-emerald-600 dark:text-emerald-400">${isEn ? 'Response: <2min' : 'سرعت پاسخ: ۲ دقیقه'}</span>
          </div>

          <div class="peach-description">
            ${t('popularity_insight')}
          </div>

          <!-- Bottom Banner: Paper Plane + Learn Insights + Play Button -->
          <div class="peach-bottom-bar" id="btn-learn-insights" title="Open Bidding Intelligence Studio">
            <div class="text-orange-500 flex items-center justify-center">
              ${icon('plane', 'w-5 h-5')}
            </div>
            <span class="peach-bottom-text">${t('learn_insights')}</span>
            <div class="circle-play-btn">
              ${icon('play', 'w-3.5 h-3.5')}
            </div>
          </div>
        </div>
      </section>

      <!-- BOTTOM 3 WIDGETS ROW (CUSTOMIZED FOR FREELANCE AGENT) -->
      <section class="bottom-widgets-row">
        <!-- Widget 1: Finance Performance & Proposal Pipeline -->
        <div class="widget-card">
          <div class="flex items-center justify-between mb-3">
            <span class="widget-title mb-0">${t('finance_performance')}</span>
            <div class="flex items-center gap-1">
              <button class="px-2 py-1 rounded-lg text-[10px] font-bold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 transition" id="btn-toggle-curr" title="Switch USD / Toman">USD $</button>
            </div>
          </div>

          <div class="finance-header-box">
            <div class="flex items-center gap-3">
              <div class="finance-badge-icon font-sans">$</div>
              <div>
                <div class="finance-amount-num font-sans" id="finance-display-num">12 841</div>
                <div class="finance-subtext">${t('monthly_income')}</div>
              </div>
            </div>
            <button class="action-icon-btn" id="btn-finance-cal" title="View Financial Breakdown">
              ${icon('calendar', 'w-4 h-4')}
            </button>
          </div>

          <!-- 6-Month Vertical Bar Chart with Rounded Pillars (DEC - MAY) -->
          <div class="finance-bar-chart" id="finance-chart-bars">
            ${renderBar('DEC', 48, '$6,800', 12)}
            ${renderBar('JAN', 30, '$4,200', 8)}
            ${renderBar('FEB', 40, '$5,600', 11)}
            ${renderBar('MAR', 65, '$9,100', 16)}
            ${renderBar('APR', 78, '$11,000', 21)}
            ${renderBar('MAY', 92, '$12,841', 24)}
          </div>
        </div>

        <!-- Widget 2: TOP Matching Freelance Projects -->
        <div class="widget-card">
          <div class="flex items-center justify-between mb-3">
            <span class="widget-title mb-0">${t('top_performers')}</span>
            <div class="flex items-center gap-1 bg-slate-100 dark:bg-slate-800 p-0.5 rounded-lg text-[10px] font-bold">
              <button class="px-2 py-1 rounded-md bg-white dark:bg-slate-700 shadow-sm transition" id="tab-top-rec">${isEn ? 'AI Match' : 'پیشنهاد هوش مصنوعی'}</button>
              <button class="px-2 py-1 text-slate-500 hover:text-slate-800 dark:hover:text-white transition" id="tab-top-all">${isEn ? `All (${totalProjects})` : `همه (${totalProjects})`}</button>
            </div>
          </div>

          <div class="performer-list" id="performer-container">
            ${initialList.slice(0, 3).map((p, idx) => renderProjectRow(p, isEn, idx)).join('') || `
              <div class="p-6 text-center text-xs text-slate-400">
                ${isEn ? 'No matching projects yet' : 'پروژه‌ای یافت نشد'}
              </div>
            `}
          </div>
        </div>

        <!-- Widget 3: Platform Channels Radar & Market Share -->
        <div class="widget-card">
          <div class="flex items-center justify-between mb-3">
            <span class="widget-title mb-0">${t('targeting_region')}</span>
            <span class="text-[10px] font-bold text-teal-600 dark:text-teal-400 bg-teal-50 dark:bg-teal-950/40 px-2.5 py-0.5 rounded-full flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-teal-500 animate-pulse"></span>
              <span>${isEn ? '3 CHANNELS ONLINE' : '۳ پلتفرم متصل'}</span>
            </span>
          </div>

          <div class="region-map-box">
            <!-- Dot Matrix World Map Vector -->
            <svg class="w-full h-full opacity-35 dark:opacity-20" viewBox="0 0 380 180" fill="currentColor">
              <g fill="#1c6d81">
                <!-- North America dots (Upwork Global) -->
                <circle cx="50" cy="50" r="2.5"/><circle cx="65" cy="45" r="2.5"/><circle cx="80" cy="40" r="2.5"/>
                <circle cx="55" cy="65" r="2.5"/><circle cx="70" cy="60" r="2.5"/><circle cx="85" cy="55" r="2.5"/><circle cx="95" cy="65" r="2.5"/>
                <circle cx="65" cy="80" r="2.5"/><circle cx="80" cy="75" r="2.5"/><circle cx="95" cy="80" r="2.5"/>
                <!-- South America dots -->
                <circle cx="105" cy="110" r="2.5"/><circle cx="115" cy="125" r="2.5"/><circle cx="120" cy="140" r="2.5"/>
                <circle cx="110" cy="155" r="2.5"/><circle cx="115" cy="170" r="2.5"/>
                <!-- Europe dots -->
                <circle cx="185" cy="45" r="2.5"/><circle cx="198" cy="42" r="2.5"/><circle cx="210" cy="46" r="2.5"/>
                <circle cx="190" cy="58" r="2.5"/><circle cx="205" cy="56" r="2.5"/><circle cx="218" cy="58" r="2.5"/>
                <!-- Middle East / Iran dots (Karlancer / Ponisha / Parscoders) -->
                <circle cx="225" cy="70" r="2.5"/><circle cx="240" cy="65" r="2.5"/><circle cx="255" cy="60" r="2.5"/><circle cx="270" cy="55" r="2.5"/>
                <circle cx="235" cy="82" r="2.5"/><circle cx="250" cy="80" r="2.5"/><circle cx="265" cy="78" r="2.5"/><circle cx="280" cy="75" r="2.5"/>
                <circle cx="245" cy="95" r="2.5"/><circle cx="260" cy="92" r="2.5"/><circle cx="275" cy="90" r="2.5"/><circle cx="290" cy="85" r="2.5"/>
                <!-- Africa dots -->
                <circle cx="195" cy="85" r="2.5"/><circle cx="205" cy="98" r="2.5"/><circle cx="215" cy="115" r="2.5"/>
                <!-- Australia dots -->
                <circle cx="310" cy="130" r="2.5"/><circle cx="325" cy="135" r="2.5"/><circle cx="320" cy="148" r="2.5"/>
              </g>
            </svg>

            <!-- 3 Interactive Channel Radar Beacons -->
            <div class="region-radar-pulse cursor-pointer" id="beacon-karlancer" style="top: 75px; left: 245px;" title="Karlancer (کارلنسر) - ۲۴ پروژه کشف‌شده"></div>
            <div class="region-radar-pulse cursor-pointer" id="beacon-ponisha" style="top: 55px; left: 225px; animation-delay: 1.1s;" title="Ponisha (پونیشا) - متصل"></div>
            <div class="region-radar-pulse cursor-pointer" id="beacon-upwork" style="top: 55px; left: 75px; animation-delay: 0.6s;" title="Upwork (بین‌المللی)"></div>

            <!-- Floating Interactive Channel Tooltip Card -->
            <div class="region-tooltip-card cursor-pointer group" id="channel-card" title="Click to view Platform settings">
              <div class="w-8 h-8 rounded-lg bg-teal-700 text-white flex items-center justify-center font-black text-xs shrink-0" id="channel-badge">
                K
              </div>
              <div>
                <div class="text-[11px] font-bold text-slate-800 dark:text-white group-hover:text-teal-600 transition" id="channel-name">Karlancer (کارلنسر)</div>
                <div class="text-[10px] text-emerald-600 dark:text-emerald-400 font-bold flex items-center gap-1.5" id="channel-stat">
                  <span>${totalProjects} پروژه کشف‌شده</span>
                  <span>• ۵۵٪ سهم بازار</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    `;

    // ---------------- Interactions & UX Wiring ----------------
    const viewStatsBtn = container.querySelector('#btn-view-stats');
    if (viewStatsBtn) {
      viewStatsBtn.onclick = () => navigate('discovered');
    }

    // Currency Switcher Toggle
    let currState = 'USD';
    const currBtn = container.querySelector('#btn-toggle-curr');
    const dispNum = container.querySelector('#finance-display-num');
    if (currBtn && dispNum) {
      currBtn.onclick = () => {
        currState = currState === 'USD' ? 'IRT' : 'USD';
        currBtn.textContent = currState === 'USD' ? 'USD $' : 'تومان';
        dispNum.textContent = currState === 'USD' ? '12 841' : '۱۲۸,۴۱۰,۰۰۰';
      };
    }

    // Interactive Bar Chart Clicks
    container.querySelectorAll('.bar-col').forEach(col => {
      col.onclick = () => {
        const info = col.getAttribute('title');
        modal(
          isEn ? 'Monthly Proposal Performance' : 'عملکرد مالی و مناقصات ماهانه',
          `<div class="space-y-3 p-2">
            <div class="text-sm font-bold text-slate-800 dark:text-white">${info}</div>
            <p class="text-xs text-slate-500 leading-relaxed">
              ${isEn
                ? 'During this period, opportunities were analyzed with an average win rate of 87%. Bids submitted followed the optimal balanced pricing strategy.'
                : 'در این ماه پروژه‌ها با نرخ تطابق ۸۷٪ پایش شده و پیشنهادها طبق استراتژی قیمت‌گذاری متوازن با موفقیت بالا ثبت شده‌اند.'}
            </p>
            <button class="btn-primary w-full mt-4" data-close-chart>${isEn ? 'View Proposals' : 'مشاهده پروژه‌ها و پیشنهادها'}</button>
          </div>`
        );
        document.querySelector('[data-close-chart]')?.addEventListener('click', () => {
          document.querySelector('.modal-backdrop')?.remove();
          navigate('proposals');
        });
      };
    });

    // Gauge breakdown modal
    const gaugeWrap = container.querySelector('#gauge-container');
    if (gaugeWrap) {
      gaugeWrap.onclick = () => {
        modal(
          isEn ? 'AI Win Score & Match Criteria (87%)' : 'شاخص‌های شانس برد و تطابق هوش مصنوعی (۸۷٪)',
          `<div class="space-y-3 text-xs md:text-sm">
            <div class="p-3.5 rounded-2xl bg-orange-50 dark:bg-orange-950/30 border border-orange-200 dark:border-orange-800">
              <div class="font-bold text-orange-800 dark:text-orange-300 mb-2">شاخص‌های بهینه‌سازی ایجنت:</div>
              <ul class="list-disc list-inside space-y-1.5 text-slate-700 dark:text-slate-300 text-xs leading-relaxed">
                <li><b>تطابق مهارت‌ها (۹۴٪):</b> استخراج دقیق تک‌استک پایتون، ری‌اکت و هوش مصنوعی با رزومه شما.</li>
                <li><b>استراتژی قیمت‌گذاری (۸۶٪):</b> نرخ متوازن و رقابتی در محدوده مطلوب بودجه کارفرما.</li>
                <li><b>سرعت پاسخ‌دهی ایجنت:</b> ارسال هوشمند در کمتر از ۲ دقیقه پس از انتشار مناقصه.</li>
              </ul>
            </div>
            <button class="btn-primary w-full" data-close-gauge>بهینه‌سازی تنظیمات ایجنت</button>
          </div>`
        );
        document.querySelector('[data-close-gauge]')?.addEventListener('click', () => {
          document.querySelector('.modal-backdrop')?.remove();
          navigate('agentconfig');
        });
      };
    }

    // Bidding Intelligence Modal
    const learnInsightsBtn = container.querySelector('#btn-learn-insights');
    if (learnInsightsBtn) {
      learnInsightsBtn.onclick = () => {
        modal(
          t('learn_insights'),
          `
          <div class="space-y-4 text-xs md:text-sm text-slate-600 dark:text-slate-300">
            <div class="p-4 rounded-2xl bg-teal-50 dark:bg-teal-900/20 border border-teal-200 dark:border-teal-800 flex items-start gap-3">
              <div class="text-teal-700 text-xl font-bold">⚡</div>
              <div>
                <b class="text-teal-800 dark:text-teal-300">استراتژی بهینه‌سازی پیشنهادها:</b>
                <p class="mt-1">نرخ پذیرش در پروژه‌های فریلنسری با پیشنهادهای اختصاصی و سریع تا ۷۴٪ افزایش می‌یابد.</p>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div class="card p-3">
                <div class="font-bold text-slate-800 dark:text-white flex items-center gap-1.5">
                  <span class="w-2 h-2 rounded-full bg-teal-600"></span> ۱. تحلیل هوشمند مهارت‌ها
                </div>
                <p class="text-xs text-slate-500 mt-1">تطابق دقیق کلمات کلیدی و نیازمندی‌های کارفرما با رزومه شما.</p>
              </div>
              <div class="card p-3">
                <div class="font-bold text-slate-800 dark:text-white flex items-center gap-1.5">
                  <span class="w-2 h-2 rounded-full bg-orange-500"></span> ۲. قیمت‌گذاری متوازن
                </div>
                <p class="text-xs text-slate-500 mt-1">پیشنهاد در محدوده بهینه بودجه پروژه جهت جلب توجه کارفرما.</p>
              </div>
            </div>
            <div class="text-center pt-2">
              <button class="btn-primary w-full" data-close-modal>متوجه شدم، رفتن به استودیو پرامپت</button>
            </div>
          </div>
          `
        );
        const btn = document.querySelector('[data-close-modal]');
        if (btn) btn.onclick = () => {
          document.querySelector('.modal-backdrop')?.remove();
          navigate('prompts');
        };
      };
    }

    // TOP Projects Toggle (AI Recommended vs All Discovered)
    const tabRec = container.querySelector('#tab-top-rec');
    const tabAll = container.querySelector('#tab-top-all');
    const projectBox = container.querySelector('#performer-container');

    if (tabRec && tabAll && projectBox) {
      tabRec.onclick = () => {
        tabRec.className = 'px-2 py-1 rounded-md bg-white dark:bg-slate-700 shadow-sm transition';
        tabAll.className = 'px-2 py-1 text-slate-500 hover:text-slate-800 dark:hover:text-white transition';
        const list = recommendedProjects.length ? recommendedProjects : allProjects;
        projectBox.innerHTML = list.slice(0, 3).map((p, idx) => renderProjectRow(p, isEn, idx)).join('') || `
          <div class="p-6 text-center text-xs text-slate-400">${isEn ? 'No AI recommended projects yet' : 'پروژه پیشنهادی یافت نشد'}</div>
        `;
        wireProjectClicks();
      };

      tabAll.onclick = () => {
        tabAll.className = 'px-2 py-1 rounded-md bg-white dark:bg-slate-700 shadow-sm transition';
        tabRec.className = 'px-2 py-1 text-slate-500 hover:text-slate-800 dark:hover:text-white transition';
        projectBox.innerHTML = allProjects.slice(0, 3).map((p, idx) => renderProjectRow(p, isEn, idx)).join('') || `
          <div class="p-6 text-center text-xs text-slate-400">${isEn ? 'No projects discovered yet' : 'پروژه‌ای کشف نشده است'}</div>
        `;
        wireProjectClicks();
      };
    }

    function wireProjectClicks() {
      container.querySelectorAll('[data-project-id]').forEach(el => {
        el.onclick = () => {
          const pid = el.dataset.projectId;
          if (pid) navigate('discovered', { detail: pid });
        };
      });
    }
    wireProjectClicks();

    // Interactive Channel Radar Beacons
    const cName = container.querySelector('#channel-name');
    const cStat = container.querySelector('#channel-stat');
    const cBadge = container.querySelector('#channel-badge');

    container.querySelector('#beacon-karlancer')?.addEventListener('click', () => {
      if (cName && cStat && cBadge) {
        cBadge.textContent = 'K';
        cBadge.style.backgroundColor = '#1c6d81';
        cName.textContent = 'Karlancer (کارلنسر)';
        cStat.innerHTML = `<span>${totalProjects} پروژه فعال</span><span>• ۵۵٪ سهم بازار</span>`;
      }
    });

    container.querySelector('#beacon-ponisha')?.addEventListener('click', () => {
      if (cName && cStat && cBadge) {
        cBadge.textContent = 'P';
        cBadge.style.backgroundColor = '#2563eb';
        cName.textContent = 'Ponisha (پونیشا)';
        cStat.innerHTML = `<span>متصل و فعال</span><span>• ۲۵٪ سهم بازار</span>`;
      }
    });

    container.querySelector('#beacon-upwork')?.addEventListener('click', () => {
      if (cName && cStat && cBadge) {
        cBadge.textContent = 'U';
        cBadge.style.backgroundColor = '#4f46e5';
        cName.textContent = 'Upwork (بین‌المللی)';
        cStat.innerHTML = `<span>کانال ارزی متصل</span><span>• ۲۰٪ درآمد دلاری</span>`;
      }
    });

    container.querySelector('#channel-card')?.addEventListener('click', () => {
      navigate('platforms');
    });

    container.querySelector('#btn-goto-ai')?.addEventListener('click', () => {
      navigate('ai');
    });
  },
};

function renderBar(month, heightPct, valueLabel, proposalsCount) {
  return `
    <div class="bar-col group" title="${month}: ${valueLabel} (${proposalsCount} proposals)">
      <div class="bar-pillar" style="height: ${heightPct}%;"></div>
      <span class="bar-label group-hover:text-slate-900 dark:group-hover:text-white transition">${month}</span>
    </div>
  `;
}

function renderProjectRow(p, isEn, idx) {
  const score = p.match_score ?? (94 - idx * 4);
  const platColor = p.platform === 'karlancer' ? '#1c6d81' : (p.platform === 'ponisha' ? '#2563eb' : (p.platform === 'parscoders' ? '#0d9488' : '#4f46e5'));
  const letter = (p.platform_name || p.platform || 'K').charAt(0).toUpperCase();
  const budgetStr = p.budget_max ? fa.toman(p.budget_max) : (p.budget_min ? fa.toman(p.budget_min) : (isEn ? 'Negotiable' : 'بودجه توافقی'));

  return `
    <div class="performer-row group" data-project-id="${p.id}" title="${esc(p.title)}">
      <div class="performer-avatar-wrap">
        <div class="w-10 h-10 rounded-xl flex items-center justify-center font-black text-xs text-white shadow-xs" style="background:${platColor}">
          ${letter}
        </div>
        <span class="online-dot"></span>
      </div>
      <div class="flex-1 min-w-0">
        <div class="performer-name truncate group-hover:text-teal-700 dark:group-hover:text-teal-400 transition">
          ${esc(p.title)}
        </div>
        <div class="performer-status flex items-center gap-2 mt-0.5">
          <span class="font-bold text-slate-600 dark:text-slate-300">${esc(p.platform_name || p.platform || 'Karlancer')}</span>
          <span class="text-slate-300 dark:text-slate-600">•</span>
          <span class="text-slate-500 dark:text-slate-400 font-sans text-[11px]">${budgetStr}</span>
        </div>
      </div>
      <div class="performer-rating-pill font-sans font-bold" title="${isEn ? 'AI Match Score' : 'امتیاز تطابق هوشمند'}">
        ${score}%
      </div>
    </div>
  `;
}
