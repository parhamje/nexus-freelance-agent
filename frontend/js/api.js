// API client (ES module)
const TOKEN_KEY = 'fa_token';

export function getToken() { return localStorage.getItem(TOKEN_KEY) || ''; }
export function setToken(t) { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); }

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function request(method, path, body, opts = {}) {
  const headers = { 'Accept': 'application/json' };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let resp;
  try {
    resp = await fetch(`/api/v1${path}`, {
      method, headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: opts.signal,
    });
  } catch (e) {
    throw new ApiError(0, 'ارتباط با سرور برقرار نشد');
  }
  if (resp.status === 401 && !opts.noAuthRedirect) {
    setToken('');
    window.dispatchEvent(new CustomEvent('fa:logout'));
    throw new ApiError(401, 'نشست شما منقضی شد');
  }
  let data = null;
  try { data = await resp.json(); } catch { /* empty body */ }
  if (!resp.ok) {
    const msg = (data && (data.detail || data.message)) || `خطا ${resp.status}`;
    throw new ApiError(resp.status, typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return data;
}

export const api = {
  get: (p, o) => request('GET', p, undefined, o),
  post: (p, b, o) => request('POST', p, b ?? {}, o),
  put: (p, b, o) => request('PUT', p, b ?? {}, o),
  del: (p, o) => request('DELETE', p, undefined, o),
};

// ---------- formatting helpers ----------
export const fa = {
  toman(v) {
    if (v === null || v === undefined) return 'نامشخص';
    return Number(v).toLocaleString('fa-IR') + ' تومان';
  },
  date(s) {
    if (!s) return '—';
    try { return new Date(s).toLocaleDateString('fa-IR', { year: 'numeric', month: 'short', day: 'numeric' }); }
    catch { return s.slice(0, 10); }
  },
  datetime(s) {
    if (!s) return '—';
    try { return new Date(s).toLocaleString('fa-IR', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
    catch { return s.slice(0, 16); }
  },
  ago(s) {
    if (!s) return '—';
    const diff = (Date.now() - new Date(s).getTime()) / 1000;
    if (diff < 60) return 'لحظاتی پیش';
    if (diff < 3600) return `${Math.floor(diff / 60)} دقیقه پیش`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} ساعت پیش`;
    return `${Math.floor(diff / 86400)} روز پیش`;
  },
};

export const STATUS_FA = {
  discovered: 'کشف شد', pending_analysis: 'در انتظار تحلیل', analyzing: 'در حال تحلیل',
  analyzed: 'تحلیل شد', recommended: 'پیشنهاد ارسال', skipped: 'صرف‌نظر',
  approved_for_proposal: 'تأییدشده', rejected_by_owner: 'ردشده',
  proposal_generating: 'در حال تولید پیشنهاد', proposal_ready: 'پیشنهاد آماده',
  proposal_submitted: 'ارسال شد', analysis_failed: 'تحلیل ناموفق', unavailable: 'ناموجود',
};

export const STATUS_COLOR = {
  discovered: 'neutral', pending_analysis: 'neutral', analyzing: 'amber',
  analyzed: 'sky', recommended: 'gold', skipped: 'zinc', approved_for_proposal: 'green',
  rejected_by_owner: 'red', proposal_generating: 'amber', proposal_ready: 'green',
  proposal_submitted: 'emerald', analysis_failed: 'red',
};

export const PLATFORM_COLORS = { karlancer: '#2563eb', ponisha: '#00843d', parscoders: '#7c3aed', demo: '#6b7280' };

export function platformBadge(slug, name) {
  const color = PLATFORM_COLORS[slug] || '#6b7280';
  const letter = (name || slug || '?').charAt(0).toUpperCase();
  return `<span class="plat-logo" style="background:${color}" title="${name || slug}">${letter}</span>`;
}

export function scoreClass(score) {
  if (score === null || score === undefined) return 'bg-neutral-200 text-neutral-600 dark:bg-slate-700 dark:text-neutral-300';
  if (score >= 70) return 'bg-emerald-600/15 text-emerald-600 dark:text-emerald-400 border border-emerald-600/40';
  if (score >= 50) return 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/40';
  return 'bg-red-500/10 text-red-500 dark:text-red-400 border border-red-500/40';
}

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
