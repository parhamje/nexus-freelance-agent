// Projects pages: discovered / recommended / skipped / approved + detail modal
import { api, fa, esc, platformBadge, STATUS_FA, STATUS_COLOR, scoreClass } from '../api.js';
import { badge, modal, confirmModal, spinner, emptyState, toast, renderPagination, bindPagination } from '../ui.js';
import { navigate, render } from '../app.js';
import { currentLang } from '../i18n.js';
import { icon } from '../icons.js';

const STATUS_BY_PAGE = { discovered: null, recommended: 'recommended', skipped: 'skipped', approved: 'approved_for_proposal,proposal_ready,proposal_generating,proposal_submitted' };

let lastParams = { page: 'discovered', params: {} };

export function projectListPage(pageKey) {
  return {
    title: () => ({ discovered: 'پروژه‌های کشف‌شده', recommended: 'پیشنهادشده توسط هوش مصنوعی', skipped: 'صرف‌نظرشده‌ها', approved: 'پروژه‌های تأییدشده' }[pageKey]),
    async render(container, params, isCurrent) {
      lastParams = { page: pageKey, params };
      container.innerHTML = spinner();
      const statusFilter = STATUS_BY_PAGE[pageKey];
      const q = params.q || '';
      const platform = params.platform || '';
      const limit = Math.max(1, Number(params.limit) || 6);
      const offset = Math.max(0, Number(params.offset) || 0);

      const queryParts = [
        `limit=${limit}`,
        `offset=${offset}`,
        statusFilter ? `status=${encodeURIComponent(statusFilter)}` : '',
        pageKey === 'recommended' ? 'min_score=70' : '',
        q ? `q=${encodeURIComponent(q)}` : '',
        platform ? `platform=${encodeURIComponent(platform)}` : '',
      ].filter(Boolean).join('&');

      const data = await api.get(`/projects?${queryParts}`);
      if (!isCurrent()) return;
      const isEn = currentLang() === 'en';
      container.innerHTML = `
        <!-- Sub-page Workflow Pills -->
        <div class="sub-tabs-scroll gap-2 mb-5">
          <button class="sub-tab-pill ${pageKey === 'discovered' ? 'active' : ''}" data-nav="discovered">
            ${icon('folder', 'w-3.5 h-3.5 inline me-1.5')}${isEn ? 'All Projects' : 'همه پروژه‌ها'}
          </button>
          <button class="sub-tab-pill ${pageKey === 'recommended' ? 'active' : ''}" data-nav="recommended">
            ${icon('star', 'w-3.5 h-3.5 inline me-1.5')}${isEn ? 'AI Recommended' : 'پیشنهاد هوش مصنوعی'}
          </button>
          <button class="sub-tab-pill ${pageKey === 'approved' ? 'active' : ''}" data-nav="approved">
            ${icon('check', 'w-3.5 h-3.5 inline me-1.5')}${isEn ? 'Approved' : 'تأییدشده‌ها'}
          </button>
          <button class="sub-tab-pill ${pageKey === 'skipped' ? 'active' : ''}" data-nav="skipped">
            ${icon('close', 'w-3.5 h-3.5 inline me-1.5')}${isEn ? 'Skipped' : 'صرف‌نظرشده‌ها'}
          </button>
        </div>

        <div class="flex flex-col sm:flex-row sm:items-center gap-2.5 sm:gap-3 mb-5 bg-slate-50 dark:bg-slate-800/50 p-2.5 sm:p-3 rounded-2xl border border-slate-200/70 dark:border-slate-700/60">
          <div class="relative flex-1 min-w-0 sm:min-w-[220px]">
            <span class="absolute inset-y-0 start-3 flex items-center text-slate-400 pointer-events-none">
              ${icon('search', 'w-4 h-4')}
            </span>
            <input id="proj-q" class="inp ps-9 text-xs w-full" placeholder="${isEn ? 'Search title, skills or summary…' : 'جستجو در عنوان، مهارت‌ها یا توضیحات…'}" value="${esc(q)}">
          </div>
          <select id="proj-platform" class="inp w-full sm:max-w-[160px] text-xs">
            <option value="">${isEn ? 'All Platforms' : 'همه پلتفرم‌ها'}</option>
          </select>
          <div class="text-xs font-medium text-slate-500 dark:text-slate-400 px-1 sm:px-2 flex items-center gap-1.5 whitespace-nowrap justify-between sm:justify-start">
            <span class="inline-flex items-center gap-1.5">
              <span class="inline-block w-2 h-2 rounded-full bg-teal-500"></span>
              <span>${isEn ? `Total: <b class="font-bold text-slate-700 dark:text-slate-200">${data.total}</b> projects` : `مجموع: <b class="font-bold text-slate-700 dark:text-slate-200">${data.total.toLocaleString('fa-IR')}</b> پروژه`}</span>
            </span>
          </div>
        </div>

        <div id="proj-list" class="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
          ${data.items.length ? data.items.map(projectCard).join('') : emptyState(isEn ? 'No projects in this category' : 'پروژه‌ای در این دسته نیست')}
        </div>

        ${renderPagination({ total: data.total, limit, offset, isEn, label: isEn ? 'project' : 'پروژه' })}
      `;

      container.querySelectorAll('[data-nav]').forEach(btn => {
        btn.onclick = () => navigate(btn.dataset.nav, { limit });
      });

      // platform filter options
      const plats = (await api.get('/platforms')).items;
      const sel = container.querySelector('#proj-platform');
      plats.forEach(p => sel.add(new Option(p.name, p.slug)));
      sel.value = params.platform || '';
      sel.onchange = () => navigate(pageKey, { ...params, platform: sel.value, offset: 0, limit });

      const qInput = container.querySelector('#proj-q');
      if (qInput) {
        qInput.addEventListener('keydown', e => {
          if (e.key === 'Enter') navigate(pageKey, { ...params, q: e.target.value.trim(), offset: 0, limit });
        });
      }

      // Bind executive pagination events
      bindPagination(container, {
        onPageChange: (newPage) => {
          const newOffset = (newPage - 1) * limit;
          navigate(pageKey, { ...params, offset: newOffset, limit });
          window.scrollTo({ top: 0, behavior: 'smooth' });
        },
        onLimitChange: (newLimit) => {
          navigate(pageKey, { ...params, offset: 0, limit: newLimit });
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
      });

      container.querySelectorAll('[data-project]').forEach(el => {
        el.querySelector('[data-view]').onclick = () => openProjectDetail(Number(el.dataset.project));
        const approveBtn = el.querySelector('[data-approve]');
        if (approveBtn) approveBtn.onclick = () => doApprove(Number(el.dataset.project));
        const rejectBtn = el.querySelector('[data-reject]');
        if (rejectBtn) rejectBtn.onclick = () => doReject(Number(el.dataset.project));
      });
      if (params.detail) { openProjectDetail(Number(params.detail)); }
    },
  };
}

function projectCard(p) {
  const actionable = ['recommended', 'analyzed', 'skipped'].includes(p.status);
  const skills = (p.skills || []).slice(0, 3);
  return `<div class="card p-5 flex flex-col justify-between gap-4 transition hover:shadow-lg hover:-translate-y-0.5 border border-slate-200/80 dark:border-slate-800" data-project="${p.id}">
    <div>
      <div class="flex items-start gap-3">
        ${platformBadge(p.platform, p.platform_name)}
        <div class="flex-1 min-w-0">
          <div class="text-xs font-bold leading-5 line-clamp-2 text-slate-800 dark:text-white" title="${esc(p.title)}">${esc(p.title)}</div>
          <div class="text-[10px] text-slate-400 mt-1 flex items-center gap-1.5">
            <span>${p.platform_name}</span>
            <span>•</span>
            <span>${fa.ago(p.first_discovered_at)}</span>
          </div>
        </div>
        <span class="score-ring ${scoreClass(p.match_score)} shadow-sm">${p.match_score ?? '—'}</span>
      </div>

      <div class="text-xs text-slate-600 dark:text-slate-300 space-y-1.5 mt-3 pt-3 border-t border-slate-100 dark:border-slate-800">
        <div class="flex items-center gap-2">
          <span class="text-teal-600">${icon('chart', 'w-3.5 h-3.5')}</span>
          <span class="font-semibold">${fa.toman(p.budget_min)} ${p.budget_max ? ' تا ' + fa.toman(p.budget_max) : ''}</span>
        </div>
        <div class="flex items-center gap-2 text-slate-400">
          <span>${icon('calendar', 'w-3.5 h-3.5')}</span>
          <span class="text-[11px]">${fa.date(p.deadline)}</span>
        </div>
        ${p.summary ? `<div class="line-clamp-2 text-slate-500 text-[11px] bg-slate-50 dark:bg-slate-900/50 p-2 rounded-xl mt-2 flex items-start gap-1.5">
          <span class="text-teal-600 flex-none">${icon('sparkles', 'w-3.5 h-3.5')}</span>
          <span>${esc(p.summary)}</span>
        </div>` : ''}
      </div>

      ${skills.length ? `
        <div class="flex flex-wrap gap-1 mt-3">
          ${skills.map(s => `<span class="text-[10px] px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">${esc(s)}</span>`).join('')}
        </div>
      ` : ''}
    </div>

    <div class="flex items-center gap-2 flex-wrap pt-2 border-t border-slate-100 dark:border-slate-800">
      ${badge(STATUS_FA[p.status] || p.status, STATUS_COLOR[p.status] || 'neutral')}
      <div class="flex-1"></div>
      ${actionable ? `
        <button class="btn-action text-emerald-600 dark:text-emerald-400 hover:border-emerald-500/40" data-approve title="تأیید برای ارسال پیشنهاد">
          ${icon('check', 'w-3.5 h-3.5 text-emerald-600')} <span>تأیید</span>
        </button>
        <button class="btn-action text-rose-600 dark:text-rose-400 hover:border-rose-500/40" data-reject title="صرف‌نظر از پروژه">
          ${icon('close', 'w-3.5 h-3.5 text-rose-500')} <span>رد</span>
        </button>
      ` : ''}
      <button class="btn-action-primary" data-view title="مشاهده جزئیات">
        <span>جزئیات</span> ${icon('chevronLeft', 'w-3.5 h-3.5')}
      </button>
    </div>
  </div>`;
}

// ---------------- actions ----------------
export async function doApprove(projectId) {
  confirmModal('با تأیید، فقط اجازه <b>تولید پیشنهاد</b> داده می‌شود. ارسال نهایی نیاز به تأیید جداگانه دارد. ادامه؟', async () => {
    try {
      await api.post(`/projects/${projectId}/approve`);
      toast('پروژه تأیید شد — اکنون می‌توانید پیشنهاد تولید کنید', 'success');
      render();
    } catch (e) { toast(e.message, 'error'); }
  }, { danger: false, yesLabel: 'تأیید پروژه' });
}

export async function doReject(projectId) {
  confirmModal('پروژه رد شود؟ برای آن پیشنهادی ساخته نمی‌شود.', async () => {
    try {
      await api.post(`/projects/${projectId}/reject`);
      toast('پروژه رد شد');
      render();
    } catch (e) { toast(e.message, 'error'); }
  });
}

// ---------------- detail modal ----------------
export async function openProjectDetail(projectId) {
  const p = await api.get(`/projects/${projectId}`);
  const a = p.analysis;
  const canApprove = ['recommended', 'analyzed', 'skipped'].includes(p.status);
  const canGenerate = ['approved_for_proposal', 'proposal_ready'].includes(p.status);

  const strategies = a ? [
    ['aggressive', 'تهاجمی', a.aggressive_bid],
    ['balanced', 'متوازن', a.balanced_bid],
    ['premium', 'پرمیوم', a.premium_bid],
  ] : [];

  const m = modal(`🗂 ${esc(p.title)}`, `
    <div class="space-y-4 text-sm">
      <div class="flex flex-wrap items-center gap-2">
        ${platformBadge(p.platform, p.platform_name)}
        <span class="text-xs text-neutral-500">${p.platform_name} · ${fa.datetime(p.first_discovered_at)}</span>
        ${badge(STATUS_FA[p.status] || p.status, STATUS_COLOR[p.status] || 'neutral')}
        <div class="flex-1"></div>
        <a href="${esc(p.url)}" target="_blank" rel="noopener" class="text-xs link">🔗 مشاهده در ${p.platform_name} ↗</a>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        ${kv('بودجه', `${fa.toman(p.budget_min)}${p.budget_max ? ' تا ' + fa.toman(p.budget_max) : ''}`)}
        ${kv('مهلت', fa.date(p.deadline))}
        ${kv('امتیاز تطابق', a ? `${a.match_score}/100` : '—')}
        ${kv('پیشنهاد AI', a ? (a.recommendation === 'BID' ? 'ارسال پیشنهاد ✅' : 'صرف‌نظر ⛔') : '—')}
      </div>

      <details class="surface p-3" ${p.description ? '' : 'hidden'}>
        <summary class="cursor-pointer text-xs font-bold">توضیحات پروژه</summary>
        <p class="text-xs leading-6 mt-2 whitespace-pre-wrap text-neutral-600 dark:text-neutral-300">${esc(p.description)}</p>
      </details>

      ${a ? analysisBlock(a) : `<div class="surface p-4 text-xs text-neutral-500">هنوز تحلیل نشده است.</div>`}

      ${a ? `<div>
        <div class="text-xs font-bold mb-2">سطح‌بندی پیشنهاد قیمت</div>
        <div class="grid md:grid-cols-3 gap-2">
          ${strategies.map(([key, label, bid]) => `
            <div class="surface p-3">
              <div class="text-xs font-bold mb-1">${label}</div>
              <div class="text-xs">${fa.toman(bid?.price)}</div>
              <div class="text-[10px] text-neutral-400 mt-1">${bid?.delivery_days ? bid.delivery_days + ' روز تحویل' : ''}</div>
              <div class="text-[10px] text-neutral-500 mt-1 leading-4">${esc(bid?.rationale || '')}</div>
              ${canGenerate ? `<button class="btn btn-primary w-full mt-2 text-[11px]" data-gen="${key}">تولید با ${label}</button>` : ''}
            </div>`).join('')}
        </div>
      </div>` : ''}

      ${a?.clarification_questions?.length ? `<div class="surface p-3"><div class="text-xs font-bold mb-1">❓ پرسش‌های شفاف‌سازی</div>
        <ul class="text-xs list-disc ps-5 space-y-1">${a.clarification_questions.map(q => `<li>${esc(q)}</li>`).join('')}</ul></div>` : ''}

      <div class="flex flex-wrap gap-2 justify-end pt-2">
        ${canApprove ? `<button class="btn btn-success" data-approve>✅ تأیید پروژه</button>
        <button class="btn btn-danger" data-reject>❌ رد پروژه</button>` : ''}
        ${canApprove || ['rejected_by_owner', 'analysis_failed'].includes(p.status) ? `<button class="btn" data-reanalyze>🔄 تحلیل مجدد</button>` : ''}
        ${canGenerate && p.proposal_id ? `<a class="btn btn-primary" href="#/proposals?detail=${p.proposal_id}">📝 مشاهده پیشنهاد</a>` : ''}
      </div>
    </div>`, { wide: true });

  m.body.querySelector('[data-approve]')?.addEventListener('click', () => doApprove(projectId));
  m.body.querySelector('[data-reject]')?.addEventListener('click', () => doReject(projectId));
  m.body.querySelector('[data-reanalyze]')?.addEventListener('click', async () => {
    await api.post(`/projects/${projectId}/reanalyze`);
    toast('تحلیل مجدد در صف قرار گرفت', 'success');
    m.close(); render();
  });
  m.body.querySelectorAll('[data-gen]').forEach(btn => {
    btn.onclick = async () => {
      try {
        await api.post(`/projects/${projectId}/proposals/generate`, { strategy: btn.dataset.gen });
        toast('تولید پیشنهاد آغاز شد؛ پس از آماده شدن اعلان می‌گیرید', 'success');
        m.close();
      } catch (e) { toast(e.message, 'error'); }
    };
  });
}

function kv(label, value) {
  return `<div class="surface p-2.5"><div class="text-[10px] text-neutral-400">${label}</div><div class="font-semibold mt-0.5">${value}</div></div>`;
}

function analysisBlock(a) {
  const lvl = v => ({ low: 'کم', medium: 'متوسط', high: 'زیاد', unknown: 'نامشخص' }[v] || v);
  return `<div class="space-y-3">
    <div class="surface p-3">
      <div class="text-xs font-bold mb-1">🤖 خلاصه تحلیل</div>
      <p class="text-xs leading-6 text-neutral-600 dark:text-neutral-300">${esc(a.summary)}</p>
      ${a.reasoning ? `<p class="text-[11px] leading-5 text-neutral-500 mt-2">${esc(a.reasoning)}</p>` : ''}
    </div>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
      ${kv('پیچیدگی فنی', lvl(a.technical_complexity))}
      ${kv('پیچیدگی محدوده', lvl(a.scope_complexity))}
      ${kv('تخمین ساعت', a.estimated_hours ?? '—')}
      ${kv('روزهای تحویل', a.estimated_delivery_days ?? '—')}
      ${kv('تناسب بودجه', lvl(a.budget_feasibility))}
      ${kv('تناسب مهلت', lvl(a.deadline_feasibility))}
      ${kv('کیفیت کارفرما', a.client_quality?.score != null ? `${a.client_quality.score}/100` : 'شواهد کافی نیست')}
      ${kv('مدل تحلیل', esc(a.model_name || '—'))}
    </div>
    ${a.matching_skills?.length ? `<div class="surface p-3"><div class="text-xs font-bold mb-1">✅ مهارت‌های منطبق</div><div class="text-xs">${a.matching_skills.map(esc).join('، ')}</div></div>` : ''}
    ${a.missing_required_skills?.length ? `<div class="surface p-3"><div class="text-xs font-bold mb-1 text-red-500">⛔ مهارت‌های الزامی غایب</div><div class="text-xs">${a.missing_required_skills.map(esc).join('، ')}</div></div>` : ''}
    ${a.missing_optional_skills?.length ? `<div class="surface p-3"><div class="text-xs font-bold mb-1">➕ مهارت‌های مکمل غایب</div><div class="text-xs">${a.missing_optional_skills.map(esc).join('، ')}</div></div>` : ''}
    ${(a.technical_risks?.length || a.scope_risks?.length) ? `<div class="surface p-3"><div class="text-xs font-bold mb-1">⚠️ ریسک‌ها</div>
      <ul class="text-xs list-disc ps-5 space-y-1">${[...(a.technical_risks || []).map(x => [x, 'فنی']), ...(a.scope_risks || []).map(x => [x, 'محدوده'])].map(([r, kind]) => `<li><b class="text-[10px] text-neutral-400">[${kind}]</b> ${esc(r)}</li>`).join('')}</ul></div>` : ''}
  </div>`;
}

// listen for open-project events from other pages
window.addEventListener('fa:open-project', e => openProjectDetail(e.detail));
