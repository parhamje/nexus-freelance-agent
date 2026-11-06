"""Analytics: discovery/approval funnel, proposals, AI usage and cost estimates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func as safunc
from sqlalchemy import select

from app.models import (AIProvider, ExecutionLog, Notification, Project,
                        ProjectAnalysis, Proposal, ProposalSubmission,
                        ProposalVersion, PlatformScanLog)
from app.services.discovery import get_agent_config


def _utcnow():
    return datetime.now(timezone.utc)


async def summary(session) -> dict:
    cfg = await get_agent_config(session)

    async def count(model, *conditions):
        stmt = select(safunc.count(model.id))
        for c in conditions:
            stmt = stmt.where(c)
        return int((await session.execute(stmt)).scalar() or 0)

    total_projects = await count(Project)
    by_status = dict((await session.execute(
        select(Project.status, safunc.count(Project.id)).group_by(Project.status)
    )).all())
    by_platform_rows = (await session.execute(
        select(Project.platform_id, safunc.count(Project.id)).group_by(Project.platform_id)
    )).all()

    from app.models import Platform
    platforms = {p.id: p.name for p in (await session.execute(select(Platform))).scalars()}
    by_platform = [{"platform_id": pid, "name": platforms.get(pid, str(pid)), "count": n}
                   for pid, n in by_platform_rows]

    proposals_generated = await count(Proposal)
    submissions_total = await count(ProposalSubmission)
    submissions_ok = await count(ProposalSubmission, ProposalSubmission.status.in_(["submitted"]))
    won = await count(ProposalSubmission, ProposalSubmission.outcome == "won")
    lost = await count(ProposalSubmission, ProposalSubmission.outcome == "lost")
    conversion = round(100.0 * won / submissions_ok, 1) if submissions_ok else None

    bid_stats = (await session.execute(
        select(safunc.avg(ProposalSubmission.price), safunc.sum(ProposalSubmission.price))
        .where(ProposalSubmission.status == "submitted")
    )).one()
    avg_bid = round(float(bid_stats[0]), 0) if bid_stats[0] else None
    total_bid_value = float(bid_stats[1]) if bid_stats[1] else 0.0

    from app.core.config import settings as app_settings
    time_saved_hours = round(
        (submissions_ok * (app_settings.time_saved_per_proposal_minutes or 45)) / 60.0, 1)

    # AI usage + cost estimate (cost only when the provider rate is configured)
    providers = {p.id: p for p in (await session.execute(select(AIProvider))).scalars()}
    usage_rows = []
    analysis_usage = (await session.execute(select(ProjectAnalysis.usage, ProjectAnalysis.model_provider))).all()
    version_usage = (await session.execute(select(ProposalVersion.usage, ProposalVersion.model_provider))).all()
    usage_rows = [u for u, _ in analysis_usage if u] + [u for u, _ in version_usage if u]
    prompt_tokens = sum(int(u.get("prompt_tokens") or 0) for u in usage_rows)
    completion_tokens = sum(int(u.get("completion_tokens") or 0) for u in usage_rows)
    cost = 0.0
    for u in usage_rows:
        p = providers.get(u.get("provider_id"))
        if p is None or p.cost_per_1k_input is None and p.cost_per_1k_output is None:
            continue
        ci = p.cost_per_1k_input if p.cost_per_1k_input is not None else 0.0
        co = p.cost_per_1k_output if p.cost_per_1k_output is not None else 0.0
        cost += (int(u.get("prompt_tokens") or 0) / 1000.0) * ci
        cost += (int(u.get("completion_tokens") or 0) / 1000.0) * co

    week_ago = _utcnow() - timedelta(days=7)
    projects_week = await count(Project, Project.first_discovered_at >= week_ago)
    scans_week = await count(PlatformScanLog, PlatformScanLog.started_at >= week_ago)
    scan_fail_week = await count(PlatformScanLog, PlatformScanLog.started_at >= week_ago,
                                 PlatformScanLog.status == "failed")
    errors_week = await count(ExecutionLog, ExecutionLog.level == "error",
                              ExecutionLog.created_at >= week_ago)
    unread = await count(Notification, Notification.is_read == False)  # noqa: E712

    return {
        "projects": {
            "total": total_projects,
            "last_7_days": projects_week,
            "by_status": by_status,
            "by_platform": by_platform,
            "recommended": by_status.get("recommended", 0),
            "skipped": by_status.get("skipped", 0),
            "approved": by_status.get("approved_for_proposal", 0) + by_status.get("proposal_ready", 0)
                        + by_status.get("proposal_submitted", 0),
            "rejected": by_status.get("rejected_by_owner", 0),
        },
        "proposals": {
            "generated": proposals_generated,
            "submitted": submissions_ok,
            "submission_attempts": submissions_total,
            "won": won,
            "lost": lost,
            "outcome_unknown": submissions_ok - won - lost if submissions_ok > won + lost else 0,
            "conversion_rate_percent": conversion,
            "avg_bid": avg_bid,
            "total_bid_value": total_bid_value,
        },
        "time_saved_hours": time_saved_hours,
        "ai": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "estimated_cost": round(cost, 4),
            "note": "هزینه بر اساس نرخ‌های اختیاری ثبت‌شده در هر تأمین‌کننده تخمین زده می‌شود.",
        },
        "health": {
            "scans_last_7_days": scans_week,
            "scan_failures_last_7_days": scan_fail_week,
            "errors_last_7_days": errors_week,
            "unread_notifications": unread,
        },
    }
