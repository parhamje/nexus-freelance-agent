"""Proposal generation (owner-approved projects only) + quality review loop."""
from __future__ import annotations

from sqlalchemy import select, func as safunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import agents
from app.ai.manager import AIError, chat_completion
from app.core.logging_config import get_logger, log_execution
from app.models import (DeveloperProfile, DeveloperSkill, Platform, Project,
                        ProjectAnalysis, ProjectStatus, Proposal,
                        ProposalStatus, ProposalVersion)
from app.services import notifications
from app.services.analyzer import _get_profile
from app.services.discovery import get_agent_config
from app.services.outbox import handler
from app.services.text import count_words, extract_json

log = get_logger("proposals")

RETRYABLE = (AIError, ConnectionError, TimeoutError)

WORD_MIN, WORD_MAX = 100, 180


async def get_or_create_proposal(session: AsyncSession, project_id: int) -> Proposal:
    result = await session.execute(select(Proposal).where(Proposal.project_id == project_id))
    proposal = result.scalar_one_or_none()
    if proposal is None:
        proposal = Proposal(project_id=project_id)
        session.add(proposal)
        await session.flush()
    return proposal


async def latest_analysis(session: AsyncSession, project_id: int) -> ProjectAnalysis | None:
    result = await session.execute(
        select(ProjectAnalysis).where(ProjectAnalysis.project_id == project_id)
        .order_by(ProjectAnalysis.id.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def ai_attempt_count(session: AsyncSession, proposal_id: int) -> int:
    result = await session.execute(
        select(safunc.count(ProposalVersion.id)).where(
            ProposalVersion.proposal_id == proposal_id,
            ProposalVersion.source == "ai",
        )
    )
    return int(result.scalar() or 0)


async def _next_version_no(session: AsyncSession, proposal_id: int) -> int:
    result = await session.execute(
        select(safunc.max(ProposalVersion.version_no)).where(ProposalVersion.proposal_id == proposal_id)
    )
    return int(result.scalar() or 0) + 1


async def review_quality(session: AsyncSession, project: Project, content: str,
                         word_count: int, profile, skills,
                         platform_name: str = "") -> agents.QualityOut:
    """Separate quality reviewer (own model assignment, threshold from config)."""
    cfg = await get_agent_config(session)
    try:
        provider, model = await agents.resolve_assignment(session, cfg, "quality")
        system_tpl = await agents.get_active_prompt(session, "quality", agents.QUALITY_SYSTEM)
        system = system_tpl if '"score"' in system_tpl else system_tpl + '\n\nخروجی فقط JSON با کلیدهای score، issues، strengths، word_count_ok باشد.'
        _, user = agents.build_quality_messages(project, content, profile, skills, word_count,
                                                platform_name=platform_name)
        result = await chat_completion(provider, model, system, user)
        return agents.QualityOut.model_validate(extract_json(result["text"]))
    except Exception as exc:  # noqa: BLE001 - reviewer failure must not block a good proposal
        log.warning("quality review failed: %s", exc)
        return agents.QualityOut(score=0, issues=[f"بازبین کیفیت در دسترس نبود: {exc}"], strengths=[])


async def generate_for_project(session: AsyncSession, project_id: int,
                               strategy: str = "balanced", actor: str = "web") -> Proposal:
    """Generate (or regenerate) a proposal. HARD RULES:
    - project must be owner-approved (approved_for_proposal / proposal_ready);
    - at most cfg.max_generation_attempts AI attempts per proposal;
    - every version passes through the separate quality reviewer."""
    row = (await session.execute(
        select(Project, Platform)
        .join(Platform, Project.platform_id == Platform.id)
        .where(Project.id == project_id)
    )).first()
    if row is None:
        raise ValueError("پروژه یافت نشد.")
    project, platform = row
    if project.status not in (ProjectStatus.APPROVED_FOR_PROPOSAL.value,
                              ProjectStatus.PROPOSAL_READY.value,
                              ProjectStatus.PROPOSAL_GENERATING.value):
        raise ValueError("تولید پیشنهاد فقط پس از تأیید صریح پروژه توسط شما مجاز است.")

    cfg = await get_agent_config(session)
    analysis = await latest_analysis(session, project_id)
    if analysis is None:
        raise ValueError("پروژه هنوز تحلیل نشده است؛ ابتدا تحلیل را اجرا کنید.")

    proposal = await get_or_create_proposal(session, project_id)
    attempts_used = await ai_attempt_count(session, proposal.id)
    max_attempts = max(1, int(cfg.max_generation_attempts or 2))
    if attempts_used >= max_attempts:
        raise ValueError(
            f"سقف تلاش‌های تولید ({max_attempts}) پر شده است. می‌توانید متن را ویرایش کنید یا نسخه‌ها را مقایسه کنید."
        )

    strategy = strategy or proposal.selected_strategy or "balanced"
    if strategy not in ("aggressive", "balanced", "premium"):
        strategy = "balanced"
    proposal.status = ProposalStatus.GENERATING.value
    if project.status == ProjectStatus.APPROVED_FOR_PROPOSAL.value:
        project.status = ProjectStatus.PROPOSAL_GENERATING.value
    await session.commit()

    profile, skills = await _get_profile(session)

    try:
        version = await _one_generation(session, project, proposal, analysis, profile, skills,
                                        cfg, strategy, attempts_used, platform_name=platform.name)
    except RETRYABLE:
        proposal.status = ProposalStatus.READY.value if proposal.current_version_id else ProposalStatus.GENERATING.value
        await session.commit()
        raise
    except Exception as exc:  # noqa: BLE001
        proposal.status = ProposalStatus.READY.value if proposal.current_version_id else ProposalStatus.GENERATING.value
        await log_execution(session, "proposal", f"generation failed for project {project_id}: {exc}",
                            level="error", project_id=project_id)
        await session.commit()
        raise ValueError(f"تولید پیشنهاد ناموفق بود: {exc}") from exc

    proposal.status = ProposalStatus.READY.value
    proposal.selected_strategy = strategy
    proposal.quality_score = version.quality_score
    proposal.current_version_id = version.id
    project.status = ProjectStatus.PROPOSAL_READY.value
    await log_execution(session, "proposal",
                        f"proposal v{version.version_no} ready for project {project_id} "
                        f"(quality={version.quality_score}, attempt={version.attempt_no})",
                        project_id=project_id)
    await session.commit()

    warning = version.quality_score is not None and version.quality_score < cfg.quality_threshold
    try:
        await notifications.notify_proposal_ready(session, project, proposal, warning=warning)
    except Exception as exc:  # noqa: BLE001
        log.warning("proposal notification failed: %s", exc)
    return proposal


async def _one_generation(session: AsyncSession, project, proposal, analysis,
                          profile, skills, cfg, strategy, attempts_used,
                          platform_name: str = "") -> ProposalVersion:
    provider, model = await agents.resolve_assignment(session, cfg, "proposal")
    system_tpl = await agents.get_active_prompt(session, "proposal", agents.PROPOSAL_SYSTEM)
    system = system_tpl if '"content"' in system_tpl else system_tpl + '\n\nخروجی فقط JSON: {"content": "متن"}'

    bid = getattr(analysis, f"{strategy}_bid") or {}
    price = bid.get("price")
    delivery_days = bid.get("delivery_days") or analysis.estimated_delivery_days
    _, user = agents.build_proposal_messages(project, analysis, profile, skills,
                                             strategy, price, delivery_days,
                                             platform_name=platform_name)
    result = await chat_completion(provider, model, system, user)
    out = agents.ProposalOut.model_validate(extract_json(result["text"]))
    content = out.content.strip()
    if not content:
        raise ValueError("پاسخ مدل خالی بود.")

    wc = count_words(content)
    quality = await review_quality(session, project, content, wc, profile, skills,
                                   platform_name=platform_name)

    next_no = await _next_version_no(session, proposal.id)
    version = ProposalVersion(
        proposal_id=proposal.id,
        version_no=next_no,
        attempt_no=attempts_used + 1,
        source="ai",
        content=content,
        word_count=wc,
        strategy=strategy,
        price=price,
        delivery_days=delivery_days,
        quality_score=quality.score,
        quality_report=quality.model_dump(),
        model_provider=provider.name,
        model_name=model,
        usage=result["usage"],
    )
    session.add(version)
    await session.flush()
    return version


async def regenerate(session: AsyncSession, proposal_id: int, strategy: str | None = None,
                     actor: str = "web") -> Proposal:
    result = await session.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise ValueError("پیشنهاد یافت نشد.")
    project = (await session.execute(select(Project).where(Project.id == proposal.project_id))).scalar_one()
    strategy = strategy or proposal.selected_strategy
    return await generate_for_project(session, project.id, strategy=strategy, actor=actor)


async def edit_proposal(session: AsyncSession, proposal_id: int, content: str,
                        price: float | None = None, delivery_days: int | None = None) -> ProposalVersion:
    """Owner manual edit - creates a new version (does not consume AI attempts)."""
    result = await session.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise ValueError("پیشنهاد یافت نشد.")
    content = (content or "").strip()
    if len(content) < 40:
        raise ValueError("متن پیشنهاد خیلی کوتاه است.")
    project, platform = (await session.execute(
        select(Project, Platform)
        .join(Platform, Project.platform_id == Platform.id)
        .where(Project.id == proposal.project_id)
    )).one()
    current = (await session.execute(
        select(ProposalVersion).where(ProposalVersion.id == proposal.current_version_id)
    )).scalar_one_or_none()

    wc = count_words(content)
    profile, skills = await _get_profile(session)
    quality = await review_quality(session, project, content, wc, profile, skills,
                                   platform_name=platform.name)

    next_no = await _next_version_no(session, proposal.id)
    version = ProposalVersion(
        proposal_id=proposal.id,
        version_no=next_no,
        attempt_no=current.attempt_no if current else 1,
        source="edited",
        content=content,
        word_count=wc,
        strategy=current.strategy if current else proposal.selected_strategy,
        price=price if price is not None else (current.price if current else None),
        delivery_days=delivery_days if delivery_days is not None else (current.delivery_days if current else None),
        quality_score=quality.score,
        quality_report=quality.model_dump(),
    )
    session.add(version)
    await session.flush()
    proposal.current_version_id = version.id
    proposal.quality_score = quality.score
    proposal.status = ProposalStatus.READY.value
    await session.commit()
    return version


async def set_strategy(session: AsyncSession, proposal_id: int, strategy: str) -> Proposal:
    if strategy not in ("aggressive", "balanced", "premium"):
        raise ValueError("استراتژی نامعتبر است.")
    result = await session.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise ValueError("پیشنهاد یافت نشد.")
    proposal.selected_strategy = strategy
    await session.commit()
    return proposal


async def update_version_pricing(session: AsyncSession, proposal_id: int, version_id: int,
                                 price: float | None, delivery_days: int | None) -> ProposalVersion:
    result = await session.execute(
        select(ProposalVersion).where(ProposalVersion.id == version_id,
                                      ProposalVersion.proposal_id == proposal_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise ValueError("نسخه یافت نشد.")
    if price is not None:
        if price <= 0:
            raise ValueError("قیمت باید بزرگ‌تر از صفر باشد.")
        version.price = price
    if delivery_days is not None:
        if delivery_days <= 0:
            raise ValueError("زمان تحویل باید بزرگ‌تر از صفر باشد.")
        version.delivery_days = int(delivery_days)
    await session.commit()
    return version


@handler("proposal.generate")
async def _handle_generate(session: AsyncSession, payload: dict) -> None:
    await generate_for_project(session, payload.get("project_id"),
                               strategy=payload.get("strategy", "balanced"),
                               actor="outbox")
