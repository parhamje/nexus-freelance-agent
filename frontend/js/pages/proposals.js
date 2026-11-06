// Proposals pages: list + detail (versions, quality, edit, submit flow) + submissions
import { api, fa, esc, platformBadge } from '../api.js';
import { badge, modal, confirmModal, spinner, emptyState, toast, copyText } from '../ui.js';
import { navigate, render } from '../app.js';
import { currentLang } from '../i18n.js';
import { icon } from '../icons.js';

export function proposalSubTabs(activeKey) {
  const isEn = currentLang() === 'en';
  return `
    <div class="flex items-center gap-2 mb-6 overflow-x-auto pb-1">
      <button class="sub-tab-pill ${activeKey === 'proposals' ? 'active' : ''}" data-prop-nav="proposals">
        ${icon('reports', 'w-3.5 h-3.5 inline me-1.5')}${isEn ? 'All Proposals' : 'همه پیشنهادها'}
      </button>
      <button class="sub-tab-pill ${activeKey === 'submitted' ? 'active' : ''}" data-prop-nav="submitted">
        ${icon('plane', 'w-3.5 h-3.5 inline me-1.5')}${isEn ? 'Submitted Proposals' : 'پیشنهادهای ارسال‌شده'}
      </button>
    </div>
  `;
}

export const proposals = {
  title: () => 'پیشنهادها',
  async render(container, params, isCurrent) {
    container.innerHTML = spinner();
    const data = await api.get('/proposals?limit=100');
    if (!isCurrent()) return;
    container.innerHTML = `
      ${proposalSubTabs('proposals')}
      <div class="flex items-center mb-4"><h3 class="font-bold text-sm">پیشنهادهای تولیدشده</h3>
        <span class="text-xs text-neutral-500 ms-2">${data.items.length} مورد</span></div>
      <div class="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
        ${data.items.length ? data.items.map(row).join('') : emptyState('پیشنهادی تولید نشده است. ابتدا یک پروژه را تأیید کنید.')}
      </div>`;
    container.querySelectorAll('[data-prop-nav]').forEach(b => {
      b.onclick = () => navigate(b.dataset.propNav);
    });
    container.querySelectorAll('[data-prop]').forEach(el => {
      el.onclick = () => openProposalDetail(Number(el.dataset.prop));
    });
    if (params.detail) openProposalDetail(Number(params.detail));
  },
};

function row(p) {
  const warn = p.quality_score !== null && p.quality_score !== undefined && p.quality_score < 75;
  return `<div class="card p-4 cursor-pointer hover:border-gold-500/50 transition" data-prop="${p.id}">
    <div class="flex items-start gap-2">
      <div class="flex-1 min-w-0">
        <div class="text-sm font-bold line-clamp-1">${esc(p.project_title)}</div>
        <div class="text-[11px] text-neutral-400 mt-1">${p.platform_name} · ${fa.ago(p.updated_at)}</div>
      </div>
      ${badge(p.status === 'ready' ? 'آماده' : p.status === 'submitted' ? 'ارسال شد' : p.status, p.status === 'submitted' ? 'emerald' : 'gold')}
    </div>
    <div class="flex items-center gap-3 mt-3 text-xs text-neutral-500">
      <span>🏁 کیفیت: <b class="${warn ? 'text-red-500' : 'text-green-600'}">${p.quality_score ?? '—'}/100</b></span>
      <span>🎯 ${p.selected_strategy === 'aggressive' ? 'تهاجمی' : p.selected_strategy === 'premium' ? 'پرمیوم' : 'متوازن'}</span>
    </div>
  </div>`;
}

export async function openProposalDetail(proposalId) {
  const d = await api.get(`/proposals/${proposalId}`);
  const current = d.versions.find(v => v.id === d.current_version_id) || d.versions[d.versions.length - 1];
  const canSubmit = d.status === 'ready' && !d.submission;
  const attemptInfo = `تلاش‌های AI: ${d.versions.filter(v => v.source === 'ai').length}/${d.max_generation_attempts}`;

  const m = modal(`📝 پیشنهاد — ${esc(d.project.title)}`, `
    <div class="space-y-4 text-sm" id="prop-detail">
      <div class="flex flex-wrap items-center gap-2 text-xs">
        ${platformBadge(d.project.platform, d.project.platform_name)}
        <span class="text-neutral-500">${d.project.platform_name} · ${fa.toman(d.project.budget_max)}</span>
        ${badge(d.status === 'ready' ? 'آماده' : d.status === 'submitted' ? 'ارسال شد' : d.status, d.status === 'submitted' ? 'emerald' : 'gold')}
        <div class="flex-1"></div>
        <a href="${esc(d.project.url)}" target="_blank" rel="noopener" class="link">🔗 پروژه ↗</a>
      </div>

      <div class="surface p-3 text-xs space-y-1">
        <div class="flex justify-between"><span>کیفیت نسخه فعلی</span><b class="${current && d.quality_score < d.quality_threshold ? 'text-red-500' : 'text-green-600'}">${d.quality_score ?? '—'}/100 (حد آستانه ${d.quality_threshold})</b></div>
        <div class="flex justify-between"><span>تعداد کلمات</span><b>${current?.word_count ?? '—'} ${current && (current.word_count < 100 || current.word_count > 180) ? '(خارج از بازه ۱۰۰-۱۸۰ ⚠️)' : ''}</b></div>
        <div class="flex justify-between"><span>${attemptInfo}</span><b>استراتژی: ${({ aggressive: 'تهاجمی', balanced: 'متوازن', premium: 'پرمیوم' })[d.selected_strategy]}</b></div>
        <div class="flex justify-between"><span>قیمت / تحویل</span><b>${fa.toman(current?.price)} / ${current?.delivery_days ?? '—'} روز</b></div>
      </div>

      ${d.quality_score < d.quality_threshold ? `<div class="text-xs p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-500">⚠️ کیفیت این نسخه زیر حد آستانه است. می‌توانید تولید مجدد بزنید (تا سقف ${d.max_generation_attempts} تلاش) یا متن را دستی ویرایش کنید.</div>` : ''}

      <div>
        <div class="flex items-center gap-2 mb-2 overflow-x-auto pb-1" id="version-tabs">
          ${d.versions.map(v => `<button class="btn ${v.id === current?.id ? 'btn-primary' : ''} text-[11px]" data-ver="${v.id}">نسخه ${v.version_no}${v.source === 'edited' ? ' ✍️' : ''}</button>`).join('')}
        </div>
        <div class="surface p-3">
          <pre class="text-xs leading-7 whitespace-pre-wrap font-vazir" id="prop-content">${esc(current?.content || '')}</pre>
          <div class="flex gap-2 mt-3">
            <button class="btn text-[11px]" id="copy-prop">📋 کپی متن</button>
          </div>
        </div>
      </div>

      ${current?.quality_report?.issues?.length ? `<div class="surface p-3 text-xs"><b>نقد بازبین:</b><ul class="list-disc ps-5 mt-1 space-y-0.5">${current.quality_report.issues.map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>` : ''}

      <div class="flex flex-wrap gap-2 justify-end pt-1 border-t border-neutral-200 dark:border-ink-700">
        ${d.status === 'ready' ? `
          <select id="strategy-sel" class="inp max-w-36 text-xs">
            <option value="aggressive" ${d.selected_strategy === 'aggressive' ? 'selected' : ''}>تهاجمی</option>
            <option value="balanced" ${d.selected_strategy === 'balanced' ? 'selected' : ''}>متوازن</option>
            <option value="premium" ${d.selected_strategy === 'premium' ? 'selected' : ''}>پرمیوم</option>
          </select>
          <button class="btn" id="set-strategy">اعمال استراتژی</button>
          <button class="btn" id="edit-prop">✍️ ویرایش</button>
          <button class="btn" id="regen-prop">🔄 تولید مجدد</button>
          <button class="btn btn-primary" id="price-prop">💵 قیمت/تحویل</button>
          <button class="btn btn-success" id="submit-prop">🚀 تأیید و ارسال</button>` : ''}
        ${d.submission && d.submission.status === 'assisted_pending' ? `<button class="btn btn-success" id="confirm-assisted">✔️ ارسال دستی را تأیید می‌کنم</button>` : ''}
        ${d.submission && d.submission.status === 'submitted' ? `
          <span class="text-xs text-green-600 self-center">ارسال‌شده ✓ ${fa.date(d.submission.submitted_at)}</span>
          ${d.submission.outcome !== 'won' ? `<button class="btn text-[11px]" id="outcome-won">🏆 برنده شدم</button>` : ''}
          ${d.submission.outcome !== 'lost' ? `<button class="btn text-[11px]" id="outcome-lost">برنده نشدم</button>` : ''}` : ''}
      </div>
    </div>`, { wide: true });

  // version tabs
  m.body.querySelectorAll('[data-ver]').forEach(btn => {
    btn.onclick = () => {
      const v = d.versions.find(x => x.id === Number(btn.dataset.ver));
      m.body.querySelector('#prop-content').textContent = v.content;
      m.body.querySelectorAll('[data-ver]').forEach(b => b.classList.toggle('btn-primary', b === btn));
    };
  });
  m.body.querySelector('#copy-prop').onclick = (e) => copyText(current?.content || '', e.target);

  const setStrategy = m.body.querySelector('#set-strategy');
  if (setStrategy) setStrategy.onclick = async () => {
    await api.post(`/proposals/${proposalId}/strategy`, { strategy: m.body.querySelector('#strategy-sel').value });
    toast('استراتژی اعمال شد', 'success'); m.close(); openProposalDetail(proposalId);
  };
  m.body.querySelector('#edit-prop')?.addEventListener('click', () => {
    const em = modal('✍️ ویرایش پیشنهاد', `
      <textarea id="edit-content" class="inp-area text-xs leading-7">${esc(current.content)}</textarea>
      <div class="flex gap-2 justify-end mt-3">
        <button class="btn" data-x>انصراف</button>
        <button class="btn btn-primary" data-s>ذخیره نسخه جدید</button>
      </div>`);
    em.body.querySelector('[data-x]').onclick = em.close;
    em.body.querySelector('[data-s]').onclick = async () => {
      try {
        await api.post(`/proposals/${proposalId}/edit`, { content: em.body.querySelector('#edit-content').value });
        toast('نسخه ویرایش‌شده ذخیره شد (بازبین کیفیت اجرا شد)', 'success');
        em.close(); m.close(); openProposalDetail(proposalId);
      } catch (e) { toast(e.message, 'error'); }
    };
  });
  m.body.querySelector('#regen-prop')?.addEventListener('click', async () => {
    confirmModal('نسخه جدید با استراتژی انتخابی تولید شود؟ (هر تلاش AI شمرده می‌شود)', async () => {
      await api.post(`/proposals/${proposalId}/regenerate`, { strategy: m.body.querySelector('#strategy-sel')?.value || d.selected_strategy });
      toast('تولید مجدد آغاز شد؛ اعلان می‌گیرید', 'success'); m.close();
    }, { danger: false });
  });
  m.body.querySelector('#price-prop')?.addEventListener('click', () => {
    const pm = modal('💵 قیمت و زمان تحویل', `
      <div class="grid grid-cols-2 gap-3">
        <div><label class="lbl">قیمت (تومان)</label><input id="p-price" type="number" class="inp" value="${current?.price || ''}"></div>
        <div><label class="lbl">روزهای تحویل</label><input id="p-days" type="number" class="inp" value="${current?.delivery_days || ''}"></div>
      </div>
      <div class="flex gap-2 justify-end mt-4"><button class="btn" data-x>انصراف</button><button class="btn btn-primary" data-s>ذخیره</button></div>`);
    pm.body.querySelector('[data-x]').onclick = pm.close;
    pm.body.querySelector('[data-s]').onclick = async () => {
      await api.post(`/proposals/${proposalId}/pricing`, {
        price: Number(pm.body.querySelector('#p-price').value),
        delivery_days: Number(pm.body.querySelector('#p-days').value),
      });
      toast('قیمت و زمان به‌روزرسانی شد', 'success'); pm.close(); m.close(); openProposalDetail(proposalId);
    };
  });

  // FINAL APPROVAL - the only path to submission
  m.body.querySelector('#submit-prop')?.addEventListener('click', () => {
    const sm = modal('🚀 تأیید نهایی و ارسال', `
      <div class="text-sm space-y-3">
        <div class="p-3 rounded-lg bg-amber-500/10 border border-amber-500/40 text-xs leading-6">
          با تأیید نهایی، پیشنهاد برای ارسال به <b>${esc(d.project.platform_name)}</b> آماده می‌شود.<br>
          این <b>مرحله دوم تأیید</b> است؛ تأیید پروژه به‌تنهایی مجوز ارسال نیست.
        </div>
        <div class="grid grid-cols-2 gap-2 text-xs">
          ${kv('پلتفرم', d.project.platform_name)}${kv('قیمت', fa.toman(current?.price))}
          ${kv('تحویل', `${current?.delivery_days} روز`)}${kv('کیفیت', `${d.quality_score}/100`)}
        </div>
        <div class="flex gap-2 justify-end">
          <button class="btn" data-x>بازگشت</button>
          <button class="btn btn-success" data-go>🚀 تأیید و ارسال</button>
        </div>
      </div>`);
    sm.body.querySelector('[data-x]').onclick = sm.close;
    sm.body.querySelector('[data-go]').onclick = async () => {
      try {
        const result = await api.post(`/proposals/${proposalId}/submit`);
        sm.close(); m.close();
        if (result.method === 'assisted') showAssistedFlow(result);
        else toast(result.status === 'submitted' ? 'پیشنهاد ارسال شد ✅' : `ارسال ناموفق: ${result.error}`, result.status === 'submitted' ? 'success' : 'error');
        render();
      } catch (e) { toast(e.message, 'error'); }
    };
  });

  m.body.querySelector('#confirm-assisted')?.addEventListener('click', async () => {
    try {
      await api.post(`/submissions/${d.submission.id}/confirm-assisted`);
      toast('ارسال دستی تأیید و ثبت شد', 'success');
      m.close(); render();
    } catch (e) { toast(e.message, 'error'); }
  });
  m.body.querySelector('#outcome-won')?.addEventListener('click', () => setOutcome(d.submission.id, 'won'));
  m.body.querySelector('#outcome-lost')?.addEventListener('click', () => setOutcome(d.submission.id, 'lost'));
}

function showAssistedFlow(result) {
  const a = result.assisted;
  const m = modal('📤 ارسال دستی (Assisted Submission)', `
    <div class="text-sm space-y-4">
      <div class="p-3 rounded-lg bg-sky-500/10 border border-sky-500/40 text-xs leading-6">
        ${esc(a.instructions)}
      </div>
      <div class="grid grid-cols-2 gap-2 text-xs">
        ${kv('قیمت', a.price_display)}${kv('تحویل', `${a.delivery_days} روز`)}
      </div>
      <div class="surface p-3">
        <div class="flex items-center justify-between mb-2">
          <b class="text-xs">متن پیشنهاد آماده</b>
          <button class="btn text-[11px]" id="a-copy">📋 کپی</button>
        </div>
        <pre class="text-xs leading-7 whitespace-pre-wrap font-vazir">${esc(a.proposal_text)}</pre>
      </div>
      <a href="${esc(a.url)}" target="_blank" rel="noopener" class="btn btn-primary w-full block text-center">🔗 باز کردن صفحه پروژه در ${esc(result.platform_name)} ↗</a>
      <div class="text-[11px] text-neutral-500 leading-5">پس از ارسال در پلتفرم، دکمه زیر را بزنید تا در تاریخچه ثبت شود. تا قبل از تأیید شما، هیچ رکورد «ارسال‌شده» ثبت نمی‌شود.</div>
      <div class="flex gap-2 justify-end">
        <button class="btn" id="a-later">بعداً</button>
        <button class="btn btn-success" id="a-confirm">✔️ ارسال کردم</button>
      </div>
    </div>`, { wide: true });
  m.body.querySelector('#a-copy').onclick = (e) => copyText(a.proposal_text, e.target);
  m.body.querySelector('#a-later').onclick = m.close;
  m.body.querySelector('#a-confirm').onclick = async () => {
    try {
      await api.post(`/submissions/${result.id}/confirm-assisted`);
      toast('ارسال دستی تأیید و ثبت شد ✅', 'success');
      m.close(); render();
    } catch (e) { toast(e.message, 'error'); }
  };
}

async function setOutcome(submissionId, outcome) {
  await api.post(`/submissions/${submissionId}/outcome`, { outcome });
  toast(outcome === 'won' ? '🏆 تبریک! نتیجه ثبت شد' : 'نتیجه ثبت شد');
  render();
}

function kv(label, value) {
  return `<div class="surface p-2.5"><div class="text-[10px] text-neutral-400">${label}</div><div class="font-semibold mt-0.5">${value}</div></div>`;
}

// ---------------- submitted proposals page ----------------
export const submitted = {
  title: () => 'پیشنهادهای ارسال‌شده',
  async render(container, params, isCurrent) {
    container.innerHTML = spinner();
    const data = await api.get('/submissions?limit=100');
    if (!isCurrent()) return;
    const statusFa = { assisted_pending: 'در انتظار ارسال دستی', submitted: 'ارسال‌شده', failed: 'ناموفق' };
    container.innerHTML = `
      ${proposalSubTabs('submitted')}
      <div class="card p-4 overflow-x-auto">
        <div class="text-xs text-neutral-500 mb-3">تفاوت مهم: «ارسال‌شده» به معنای برنده‌شدن نیست؛ نتیجه واقعی فقط وقتی ثبت می‌شود که خودتان آن را اعلام کنید.</div>
        <table class="tbl"><thead><tr>
          <th>پروژه</th><th>پلتفرم</th><th>روش</th><th>قیمت</th><th>تحویل</th><th>وضعیت</th><th>نتیجه</th><th>زمان</th><th></th>
        </tr></thead><tbody>
        ${data.items.length ? data.items.map(s => `<tr>
          <td class="max-w-56"><a class="link" href="${esc(s.project_url)}" target="_blank" rel="noopener">${esc(s.project_title.slice(0, 60))}</a></td>
          <td>${s.platform_name}</td>
          <td>${s.method === 'assisted' ? 'دستی' : 'API'}</td>
          <td>${fa.toman(s.price)}</td>
          <td>${s.delivery_days ?? '—'} روز</td>
          <td>${badge(statusFa[s.status] || s.status, s.status === 'submitted' ? 'emerald' : s.status === 'failed' ? 'red' : 'amber')}</td>
          <td>${s.outcome === 'won' ? '🏆 برنده' : s.outcome === 'lost' ? 'برنده نشد' : 'نامشخص'}</td>
          <td class="text-[11px]">${fa.datetime(s.submitted_at || s.created_at)}</td>
          <td>${s.status === 'submitted' && !s.outcome ? `<button class="btn text-[11px]" data-outcome="${s.id}">ثبت نتیجه</button>` : ''}</td>
        </tr>`).join('') : `<tr><td colspan="9">${emptyState('هنوز پیشنهادی ارسال نشده است')}</td></tr>`}
        </tbody></table>
      </div>`;
    container.querySelectorAll('[data-prop-nav]').forEach(b => {
      b.onclick = () => navigate(b.dataset.propNav);
    });
    container.querySelectorAll('[data-outcome]').forEach(btn => {
      btn.onclick = () => {
        const om = modal('ثبت نتیجه واقعی', `
          <div class="flex gap-2 justify-center">
            <button class="btn btn-success" data-o="won">🏆 برنده شدم</button>
            <button class="btn btn-danger" data-o="lost">برنده نشدم</button>
          </div>`);
        om.body.querySelectorAll('[data-o]').forEach(b => {
          b.onclick = async () => { await setOutcome(Number(btn.dataset.outcome), b.dataset.o); om.close(); };
        });
      };
    });
  },
};
