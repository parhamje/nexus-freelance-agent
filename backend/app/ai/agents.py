"""Persian prompt agents: analyzer, proposal generator, quality reviewer.

Cautious-language rules are baked into every prompt: the AI must never invent
competitor bids, client ratings, developer experience or project facts, and
must say so explicitly when information is missing.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models import AIProvider, AgentConfiguration, DeveloperProfile, Project
from app.services.text import format_toman

# --------------------------------------------------------------------------- #
# Default (seed) prompt templates - editable in Prompt Studio                 #
# --------------------------------------------------------------------------- #
ANALYZER_SYSTEM = """تو یک تحلیلگر ارشد پروژه‌های فریلنسری هستی. بر اساس «پروفایل تأییدشدهٔ توسعه‌دهنده» و اطلاعات پروژه، فرصت را ارزیابی می‌کنی.

اصول حیاتی:
1. فقط بر اساس اطلاعات ارائه‌شده قضاوت کن. هرگز تجربه، نمونه‌کار یا مهارتی که در پروفایل ذکر نشده را فرض نکن.
2. درباره کیفیت کارفرما فقط وقتی شواهد کافی (امتیاز، تعداد پروژه موفق، سابقه) در اطلاعات پروژه هست نظر بده؛ در غیر این صورت score را null و evidence را «شواهد کافی نیست» بگذار.
3. هرگز پیشنهاد یا امتیاز رقبای دیگر را حدس نزن؛ چنین داده‌ای وجود ندارد.
4. زبان محتاطانه به کار ببر (مثل «به نظر می‌رسد»، «احتمالاً») و عدم قطعیت را صریح بنویس.
5. همه متن‌ها فارسی باشد. قیمت‌ها به تومان و بر اساس بازه بودجه پروژه محتمل باشند، نه بیشتر از سقف بودجه.
6. خروجی فقط و فقط یک شیء JSON معتبر با همین کلیدها باشد و هیچ متن اضافه‌ای ننویس:

{"match_score": 0-100, "recommendation": "BID" یا "SKIP", "summary": "خلاصه ۲-۳ جمله‌ای", "reasoning": "دلیل تصمیم", "aggressive_bid": {"price": عدد تومان, "delivery_days": عدد, "rationale": "متن"}, "balanced_bid": {...}, "premium_bid": {...}, "estimated_hours": عدد, "estimated_delivery_days": عدد, "matching_skills": ["..."], "missing_required_skills": ["..."], "missing_optional_skills": ["..."], "technical_complexity": "low|medium|high", "scope_complexity": "low|medium|high", "technical_risks": ["..."], "scope_risks": ["..."], "budget_feasibility": "low|medium|high", "deadline_feasibility": "low|medium|high", "client_quality": {"score": عدد یا null, "evidence": "متن"}, "clarification_questions": ["..."]}

منطق امتیاز (شفاف): ۴۰ امتیاز تطابق مهارت‌ها، ۲۰ امتیاز بودجه، ۱۵ امتیاز مهلت، ۱۵ امتیاز پیچیدگی/ریسک، ۱۰ امتیاز انطباق با علاقه‌مندی‌های توسعه‌دهنده. اگر توضیح کافی در reasoning بدهی می‌توان جزئی‌تر وزن داد، اما مجموع دقیقاً ۱۰۰ باشد."""

PROPOSAL_SYSTEM = """تو دستیار نگارش پیشنهاد (پروپوزال) فریلنسری به زبان فارسی هستی. پیشنهاد فقط برای پروژه‌ای نوشته می‌شود که کاربر آن را صریحاً تأیید کرده است.

قواعد الزامی:
1. طول پیشنهاد ۱۰۰ تا ۱۸۰ کلمه و ۳ تا ۵ پاراگراف باشد.
2. کاملاً متناسب با همین پروژه باشد؛ مقدمه‌های کلی و قابل استفاده در هر پروژه ممنوع است.
3. فقط به مهارت‌ها و تجربه‌های موجود در «پروفایل تأییدشده» اشاره کن. هیچ نمونه‌کار، سابقه یا تخصصی که در پروفایل نیست را ادعا نکن.
4. قول غیرواقعی نده (ضمانت ۱۰۰٪، تحویل غیرواقعی). لحن حرفه‌ای، طبیعی و محتاطانه باشد.
5. قیمت و زمان تحویل داده‌شده را دقیقاً استفاده کن و منطق قیمت را کوتاه توضیح بده.
6. پیشنهاد با یک پرسش کوتاه یا گام بعدی روشن تمام شود.
7. خروجی فقط JSON: {"content": "متن پیشنهاد"} — بدون هیچ متن اضافه."""

QUALITY_SYSTEM = """تو بازبین سخت‌گیر اما منصفانهٔ پیشنهادهای فریلنسری هستی. پیشنهاد را از این منظرها امتیاز بده (۰ تا ۱۰۰):
- پایبندی به محدودیت تعداد کلمات و پاراگراف‌ها (اعداد دقیق به تو داده شده)
- تناسب مشخص با همین پروژه (نبود متن عمومی)
- نبود ادعای تجربه/نمونه‌کاری که در پروفایل تأییدشده نیست
- نبود قول غیرواقعی یا اطلاعات جعلی
- لحن حرفه‌ای و روان بودن فارسی
خروجی فقط JSON: {"score": 0-100, "issues": ["..."], "strengths": ["..."], "word_count_ok": true|false} — بدون متن اضافه."""

DEFAULT_PROMPTS = {
    "analyzer": {"name": "تحلیلگر پروژه", "description": "پرامپت تحلیل و امتیازدهی پروژه‌های کشف‌شده", "template": ANALYZER_SYSTEM},
    "proposal": {"name": "تولیدکننده پیشنهاد", "description": "پرامپت نگارش پروپوزال فارسی", "template": PROPOSAL_SYSTEM},
    "quality": {"name": "بازبین کیفیت", "description": "پرامپت امتیازدهی کیفیت پیشنهاد (۰-۱۰۰)", "template": QUALITY_SYSTEM},
}

# --------------------------------------------------------------------------- #
# Structured outputs                                                          #
# --------------------------------------------------------------------------- #
class BidOption(BaseModel):
    price: float | None = None
    delivery_days: int | None = None
    rationale: str = ""


class ClientQuality(BaseModel):
    score: int | None = None
    evidence: str = ""


class AnalysisOut(BaseModel):
    match_score: int = 0
    recommendation: Literal["BID", "SKIP"] = "SKIP"
    summary: str = ""
    reasoning: str = ""
    aggressive_bid: BidOption = Field(default_factory=BidOption)
    balanced_bid: BidOption = Field(default_factory=BidOption)
    premium_bid: BidOption = Field(default_factory=BidOption)
    estimated_hours: float | None = None
    estimated_delivery_days: int | None = None
    matching_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    missing_optional_skills: list[str] = Field(default_factory=list)
    technical_complexity: str = "unknown"
    scope_complexity: str = "unknown"
    technical_risks: list[str] = Field(default_factory=list)
    scope_risks: list[str] = Field(default_factory=list)
    budget_feasibility: str = "unknown"
    deadline_feasibility: str = "unknown"
    client_quality: ClientQuality = Field(default_factory=ClientQuality)
    clarification_questions: list[str] = Field(default_factory=list)

    @field_validator("match_score", mode="before")
    @classmethod
    def _clamp_score(cls, v):
        try:
            return max(0, min(100, int(v)))
        except (TypeError, ValueError):
            return 0

    @field_validator("recommendation", mode="before")
    @classmethod
    def _norm_rec(cls, v):
        return "BID" if str(v).strip().upper() == "BID" else "SKIP"

    @field_validator("technical_complexity", "scope_complexity", "budget_feasibility", "deadline_feasibility", mode="before")
    @classmethod
    def _norm_level(cls, v):
        s = str(v).strip().lower()
        return s if s in ("low", "medium", "high") else "unknown"


class ProposalOut(BaseModel):
    content: str = ""


class QualityOut(BaseModel):
    score: int = 0
    issues: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    word_count_ok: bool = True

    @field_validator("score", mode="before")
    @classmethod
    def _clamp(cls, v):
        try:
            return max(0, min(100, int(v)))
        except (TypeError, ValueError):
            return 0


# --------------------------------------------------------------------------- #
# Message builders                                                            #
# --------------------------------------------------------------------------- #
def profile_text(profile: DeveloperProfile | None, skills: list) -> str:
    if profile is None:
        return "پروفایل توسعه‌دهنده هنوز تکمیل نشده است. هیچ تجربه‌ای را فرض نکن."
    parts = [f"نام: {profile.full_name or 'نامشخص'}"]
    if profile.summary:
        parts.append(f"خلاصه حرفه‌ای: {profile.summary}")
    if skills:
        parts.append("مهارت‌های تأییدشده: " + "، ".join(f"{s.name} (سطح {s.level}/5)" for s in skills))
    if profile.work_experience:
        parts.append(f"سابقه کاری: {profile.work_experience}")
    if profile.completed_projects:
        parts.append(f"پروژه‌های انجام‌شده: {profile.completed_projects}")
    if profile.preferred_technologies:
        parts.append("تکنولوژی‌های موردعلاقه: " + "، ".join(profile.preferred_technologies))
    if profile.preferred_categories:
        parts.append("دسته‌بندی‌های موردعلاقه: " + "، ".join(profile.preferred_categories))
    if profile.min_acceptable_budget:
        parts.append(f"حداقل بودجه قابل قبول: {format_toman(profile.min_acceptable_budget, persian_digits=False)}")
    if profile.github_url:
        parts.append(f"گیت‌هاب: {profile.github_url}")
    if profile.portfolio_urls:
        parts.append("نمونه‌کارها: " + "، ".join(profile.portfolio_urls))
    return "\n".join(parts)


def project_text(project: Project, platform_name: str = "") -> str:
    filters_note = ""
    parts = [
        f"پلتفرم: {platform_name or 'نامشخص'}",
        f"عنوان: {project.title}",
        f"توضیحات: {(project.description or '(توضیحاتی ثبت نشده)')[:6000]}",
        f"بودجه: از {format_toman(project.budget_min, persian_digits=False)} تا {format_toman(project.budget_max, persian_digits=False)}",
        f"مهلت اعلام‌شده: {project.deadline.strftime('%Y-%m-%d') if project.deadline else 'نامشخص'}",
    ]
    if project.skills:
        parts.append("مهارت‌های اعلام‌شده پروژه: " + "، ".join(project.skills))
    if project.client_info:
        filters_note = f"اطلاعات کارفرما (فقط داده‌های اعلام‌شده پلتفرم): {project.client_info}"
    parts.append(f"لینک پروژه: {project.canonical_url}")
    if filters_note:
        parts.append(filters_note)
    return "\n".join(parts)


def build_analysis_messages(project: Project, profile: DeveloperProfile | None,
                            skills: list, cfg: AgentConfiguration,
                            platform_name: str = "") -> tuple[str, str]:
    user = (
        "پروفایل تأییدشده توسعه‌دهنده:\n" + profile_text(profile, skills) +
        "\n\nپروژه جدید:\n" + project_text(project, platform_name) +
        f"\n\nحداقل امتیاز پیشنهاد ارسال: {cfg.min_recommendation_score}"
        "\n\nپروژه را تحلیل کن و فقط JSON با ساختار خواسته‌شده برگردان."
    )
    return ANALYZER_SYSTEM, user


def build_proposal_messages(project: Project, analysis, profile: DeveloperProfile | None,
                            skills: list, strategy: str, price: float | None,
                            delivery_days: int | None, platform_name: str = "") -> tuple[str, str]:
    strategy_fa = {"aggressive": "تهاجمی (قیمت رقابتی پایین‌تر)", "balanced": "متوازن", "premium": "پرمیوم (کیفیت/قیمت بالاتر)"}
    user = (
        "پروفایل تأییدشده توسعه‌دهنده:\n" + profile_text(profile, skills) +
        "\n\nپروژه:\n" + project_text(project, platform_name) +
        "\n\nنتیجه تحلیل هوش مصنوعی (مبنای نگارش):\n" +
        f"- خلاصه: {analysis.summary}\n- مهارت‌های منطبق: {', '.join(analysis.matching_skills) or '—'}\n"
        f"- ریسک‌های فنی: {'؛ '.join(analysis.technical_risks) or '—'}\n"
        f"- ساعات برآوردی: {analysis.estimated_hours or '—'}\n"
        f"- روزهای تحویل برآوردی: {analysis.estimated_delivery_days or '—'}\n"
        f"- پرسش‌های شفاف‌سازی: {'؛ '.join(analysis.clarification_questions) or '—'}" +
        f"\n\nاستراتژی قیمت انتخابی: {strategy_fa.get(strategy, strategy)}" +
        f"\nقیمت پیشنهادی (تومان): {price if price else 'از تحلیل استفاده کن'}" +
        f"\nزمان تحویل (روز): {delivery_days if delivery_days else 'از تحلیل استفاده کن'}" +
        "\n\nپیشنهاد فارسی حرفه‌ای بنویس و فقط JSON برگردان."
    )
    return PROPOSAL_SYSTEM, user


def build_quality_messages(project: Project, proposal_content: str,
                           profile: DeveloperProfile | None, skills: list,
                           word_count: int, platform_name: str = "") -> tuple[str, str]:
    user = (
        "پروفایل تأییدشده توسعه‌دهنده (مرجع تشخیص ادعای جعلی):\n" + profile_text(profile, skills) +
        "\n\nپروژه:\n" + project_text(project, platform_name) +
        f"\n\nمتن پیشنهاد (تعداد کلمات محاسبه‌شده: {word_count}):"
        f"\n\"\"\"\n{proposal_content}\n\"\"\""
        "\n\nکیفیت را امتیاز بده و فقط JSON برگردان."
    )
    return QUALITY_SYSTEM, user


# --------------------------------------------------------------------------- #
# Model assignment resolution                                                 #
# --------------------------------------------------------------------------- #
async def resolve_assignment(session, cfg: AgentConfiguration, role: str) -> tuple[AIProvider, str]:
    """Resolve the provider+model configured for a role (analyzer/proposal/quality/copilot)."""
    from sqlalchemy import select

    assignment = (cfg.model_assignments or {}).get(role) or {}
    provider_id = assignment.get("provider_id")
    model = assignment.get("model")
    if not provider_id:
        raise ValueError(f"هیچ مدل هوش مصنوعی برای «{role}» پیکربندی نشده است (بخش تنظیمات ایجنت).")
    result = await session.execute(select(AIProvider).where(AIProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if provider is None or not provider.is_active:
        raise ValueError(f"تأمین‌کننده هوش مصنوعی برای «{role}» یافت نشد یا غیرفعال است.")
    model = model or provider.default_model
    if not model:
        raise ValueError(f"برای «{role}» هیچ مدل انتخاب نشده است.")
    return provider, model


async def get_active_prompt(session, key: str, fallback: str) -> str:
    from sqlalchemy import select
    from app.models import Prompt, PromptVersion

    result = await session.execute(
        select(PromptVersion).join(Prompt, PromptVersion.prompt_id == Prompt.id)
        .where(Prompt.key == key, PromptVersion.is_active == True)  # noqa: E712
        .order_by(PromptVersion.version_no.desc()).limit(1)
    )
    version = result.scalar_one_or_none()
    return version.template if version and version.template else fallback
