// i18n: Persian (default, RTL) + English
const DICT = {
  fa: {
    overview: 'داشبورد', discovered: 'پروژه‌ها', recommended: 'پیشنهادهای هوش مصنوعی',
    skipped: 'صرف‌نظرشده‌ها', approved: 'پروژه‌های تأییدشده', proposals: 'پیشنهادها',
    submitted: 'پیشنهادهای ارسال‌شده', platforms: 'کانال‌ها', ai: 'تأمین‌کنندگان هوش مصنوعی',
    agentconfig: 'تنظیمات ایجنت', profile: 'پروفایل من', telegram: 'ربات تلگرام',
    notifications: 'اعلان‌ها', prompts: 'استودیو پرامپت', analytics: 'آمار',
    logs: 'لاگ‌های سیستم', settings: 'تنظیمات',
    dashboard: 'داشبورد', insights: 'بینش‌ها', channels: 'کانال‌ها', back: 'بازگشت',
    visits_today: 'پروژه‌های پایش‌شده امروز', view_full_stat: 'مشاهده جریان پروژه‌ها',
    popularity_rate: 'نرخ شانس برد در مناقصات',
    popularity_insight: 'امتیاز شما به دلیل تطابق دقیق کلمات کلیدی، استراتژی بهینه قیمت و سرعت پاسخ ایجنت افزایش یافته است.',
    learn_insights: 'تنظیم استراتژی قیمت‌گذاری و پرامپت‌ها',
    finance_performance: 'ارزش مالی مناقصات و قراردادها', monthly_income: 'حجم پیشنهادات ارسالی',
    top_performers: 'برترین فرصت‌های همخوان', targeting_region: 'رادار پلتفرم‌ها و کانال‌ها',
    members_count: '۳ پلتفرم فعال', rate: 'آمار', reports: 'پیشنهادها',
    approve: 'تأیید پروژه', reject: 'رد پروژه', details: 'مشاهده جزئیات', generate: 'تولید پیشنهاد',
    save: 'ذخیره', cancel: 'انصراف', close: 'بستن', delete: 'حذف', edit: 'ویرایش',
    regenerate: 'تولید مجدد', submit_final: 'تأیید و ارسال', strategy: 'استراتژی قیمت',
    aggressive: 'تهاجمی', balanced: 'متوازن', premium: 'پرمیوم', quality: 'کیفیت',
    score: 'امتیاز تطابق', budget: 'بودجه', deadline: 'مهلت', status: 'وضعیت',
    platform: 'پلتفرم', discovered_at: 'زمان کشف', source: 'منبع', none: 'موردی نیست',
    loading: 'در حال بارگذاری…', search: 'جستجو…', test: 'تست اتصال', scan_now: 'اسکن فوری',
    enabled: 'فعال', disabled: 'غیرفعال', connected: 'متصل', error: 'خطا', unknown: 'نامشخص',
  },
  en: {
    overview: 'Overview', discovered: 'Projects', recommended: 'AI Recommended',
    skipped: 'Skipped', approved: 'Approved', proposals: 'Proposals',
    submitted: 'Submitted', platforms: 'Channels', ai: 'AI Providers',
    agentconfig: 'Agent Config', profile: 'Profile', telegram: 'Telegram Bot',
    notifications: 'Notifications', prompts: 'Prompt Studio', analytics: 'Rate',
    logs: 'System Logs', settings: 'Settings',
    dashboard: 'Dashboard', insights: 'Insights', channels: 'Channels', back: 'Back',
    visits_today: 'Projects Monitored Today', view_full_stat: 'VIEW ALL PROJECTS',
    popularity_rate: 'Proposal Win Probability',
    popularity_insight: 'Your score increased due to tight keyword matching, balanced pricing and fast response time.',
    learn_insights: 'Bidding Strategy & Prompt Studio',
    finance_performance: 'Financial & Bid Pipeline', monthly_income: 'Active Proposals Volume',
    top_performers: 'Top Matched Projects', targeting_region: 'Platform Channels Radar',
    members_count: '3 Channels Active', rate: 'Rate', reports: 'Reports',
    approve: 'Approve Project', reject: 'Reject Project', details: 'View Details', generate: 'Generate Proposal',
    save: 'Save', cancel: 'Cancel', close: 'Close', delete: 'Delete', edit: 'Edit',
    regenerate: 'Regenerate', submit_final: 'Approve & Submit', strategy: 'Pricing Strategy',
    aggressive: 'Aggressive', balanced: 'Balanced', premium: 'Premium', quality: 'Quality',
    score: 'Match Score', budget: 'Budget', deadline: 'Deadline', status: 'Status',
    platform: 'Platform', discovered_at: 'Discovered', source: 'Source', none: 'Nothing here yet',
    loading: 'Loading…', search: 'Search…', test: 'Test Connection', scan_now: 'Scan Now',
    enabled: 'Enabled', disabled: 'Disabled', connected: 'Connected', error: 'Error', unknown: 'Unknown',
  },
};

let lang = localStorage.getItem('fa_lang') || 'fa';

export function t(key) { return DICT[lang][key] ?? DICT.fa[key] ?? key; }
export function currentLang() { return lang; }

export function applyLang() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'fa' ? 'rtl' : 'ltr';
  localStorage.setItem('fa_lang', lang);
}

export function setLang(l) { lang = l; applyLang(); }
