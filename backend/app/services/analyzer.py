"""AI project analyzer: runs after discovery, produces a transparent match score."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import agents
from app.ai.manager import AIError, chat_completion
from app.core.logging_config import get_logger, log_execution
from app.models import (DeveloperProfile, DeveloperSkill, Platform, Project,
                        ProjectAnalysis, ProjectStatus)
from app.services import notifications
from app.services.discovery import get_agent_config
from app.services.outbox import handler
from app.services.text import extract_json

log = get_logger("analyzer")

RETRYABLE = (AIError, ConnectionError, TimeoutError)


async def _get_profile(session: AsyncSession):
    result = await session.execute(
        select(DeveloperProfile).where(DeveloperProfile.is_active == True).limit(1)  # noqa: E712
    )
    profile = result.scalar_one_or_none()
    skills = []
    if profile is not None:
        result = await session.execute(
            select(DeveloperSkill).where(DeveloperSkill.profile_id == profile.id)
            .order_by(DeveloperSkill.level.desc())
        )
        skills = result.scalars().all()
    return profile, skills


async def run_analysis(session: AsyncSession, project_id: int) -> ProjectAnalysis | None:
    row = (await session.execute(
        select(Project, Platform)
        .join(Platform, Project.platform_id == Platform.id)
        .where(Project.id == project_id)
    )).first()
    if row is None:
        return None
    project, platform = row

    allowed = {
        ProjectStatus.DISCOVERED.value, ProjectStatus.PENDING_ANALYSIS.value,
        ProjectStatus.ANALYSIS_FAILED.value, ProjectStatus.RECOMMENDED.value,
        ProjectStatus.SKIPPED.value, ProjectStatus.ANALYZED.value,
    }
    if project.status not in allowed:
        return None

    cfg = await get_agent_config(session)
    profile, skills = await _get_profile(session)

    project.status = ProjectStatus.ANALYZING.value
    await session.commit()

    try:
        provider, model = await agents.resolve_assignment(session, cfg, "analyzer")
        system_tpl = await agents.get_active_prompt(session, "analyzer", agents.ANALYZER_SYSTEM)
        # The stored template may be edited; keep the JSON contract from the default
        # when an edited template omits it, by always appending the schema reminder.
        system = system_tpl if '"match_score"' in system_tpl else (
            system_tpl + "\n\nخروجی فقط یک شیء JSON معتبر با همان ساختار پرامپت پیش‌فرض باشد."
        )
        _, user = agents.build_analysis_messages(project, profile, skills, cfg,
                                                 platform_name=platform.name)
        result = await chat_completion(provider, model, system, user)
        parsed = agents.AnalysisOut.model_validate(extract_json(result["text"]))
    except RETRYABLE as exc:
        project.status = ProjectStatus.PENDING_ANALYSIS.value
        await session.commit()
        raise  # outbox will retry with backoff
    except Exception as exc:  # noqa: BLE001 - permanent failure (config/parsing)
        is_ai_unconfigured = "پیکربندی نشده است" in str(exc) or "یافت نشد یا غیرفعال است" in str(exc)
        if is_ai_unconfigured:
            project.status = ProjectStatus.PENDING_ANALYSIS.value
            await log_execution(session, "analyzer",
                                f"پروژه {project_id} در انتظار تحلیل: مدل هوش مصنوعی هنوز پیکربندی نشده است.",
                                level="warn", project_id=project_id)
        else:
            project.status = ProjectStatus.ANALYSIS_FAILED.value
            await log_execution(session, "analyzer",
                                f"analysis of project {project_id} failed: {exc}",
                                level="error", project_id=project_id)
        await session.commit()
        try:
            await notifications.notify_analysis_failed(session, project, str(exc))
        except Exception:  # noqa: BLE001
            pass
        return None

    analysis = ProjectAnalysis(
        project_id=project.id,
        match_score=parsed.match_score,
        recommendation=parsed.recommendation,
        reasoning=parsed.reasoning,
        summary=parsed.summary,
        aggressive_bid=parsed.aggressive_bid.model_dump(),
        balanced_bid=parsed.balanced_bid.model_dump(),
        premium_bid=parsed.premium_bid.model_dump(),
        estimated_hours=parsed.estimated_hours,
        estimated_delivery_days=parsed.estimated_delivery_days,
        matching_skills=parsed.matching_skills,
        missing_required_skills=parsed.missing_required_skills,
        missing_optional_skills=parsed.missing_optional_skills,
        technical_complexity=parsed.technical_complexity,
        scope_complexity=parsed.scope_complexity,
        technical_risks=parsed.technical_risks,
        scope_risks=parsed.scope_risks,
        budget_feasibility=parsed.budget_feasibility,
        deadline_feasibility=parsed.deadline_feasibility,
        client_quality=parsed.client_quality.model_dump(),
        clarification_questions=parsed.clarification_questions,
        model_provider=provider.name,
        model_name=model,
        usage=result["usage"],
    )
    session.add(analysis)
    await session.flush()

    threshold = cfg.min_recommendation_score
    if parsed.recommendation == "BID" and parsed.match_score >= threshold:
        project.status = ProjectStatus.RECOMMENDED.value
    elif parsed.recommendation == "SKIP":
        project.status = ProjectStatus.SKIPPED.value
    else:
        project.status = ProjectStatus.ANALYZED.value

    await log_execution(session, "analyzer",
                        f"project {project_id} analyzed: score={parsed.match_score} rec={parsed.recommendation}",
                        project_id=project_id, data={"model": model, "provider": provider.name})
    await session.commit()

    try:
        await notifications.notify_analysis_done(session, project, analysis, threshold)
    except Exception as exc:  # noqa: BLE001
        log.warning("analysis notification failed: %s", exc)
    return analysis


@handler("analyze.project")
async def _handle_analyze(session: AsyncSession, payload: dict) -> None:
    await run_analysis(session, payload.get("project_id"))
