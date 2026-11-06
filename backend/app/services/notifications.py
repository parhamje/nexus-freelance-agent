"""Notification service: persistent records, WebSocket fan-out, Telegram delivery.

Every notification is stored once (dedupe_key prevents duplicates across
retries), pushed to open dashboards over WebSocket, and queued for Telegram
through the outbox so bot downtime never loses a notification.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger
from app.models import Notification, NotificationPreference
from app.services import outbox
from app.services.ws import manager as ws_manager

log = get_logger("notify")


async def get_preferences(session: AsyncSession) -> NotificationPreference:
    result = await session.execute(select(NotificationPreference).limit(1))
    pref = result.scalar_one_or_none()
    if pref is None:
        pref = NotificationPreference()
        session.add(pref)
        await session.flush()
    return pref


async def create(session: AsyncSession, *, type: str, title: str, body: str = "",
                 data: dict | None = None, project_id: int | None = None,
                 dedupe_key: str | None = None) -> Notification | None:
    if dedupe_key:
        existing = await session.execute(
            select(Notification).where(Notification.dedupe_key == dedupe_key)
        )
        if existing.scalar_one_or_none() is not None:
            return None  # already notified - never duplicate on retries

    notification = Notification(
        type=type, title=title, body=body, data=data or {},
        project_id=project_id, dedupe_key=dedupe_key,
    )
    session.add(notification)
    await session.flush()

    # Real-time push to connected dashboards (same process).
    await ws_manager.broadcast({
        "type": "notification",
        "notification": _serialize(notification),
        "event_kind": type,
        "data": data or {},
    })

    # Telegram delivery via the outbox (retried until the bot is reachable).
    pref = await get_preferences(session)
    if pref.telegram_enabled:
        await outbox.enqueue(session, "notify.telegram", {"notification_id": notification.id})
    await session.commit()
    return notification


def _serialize(n: Notification) -> dict:
    return {
        "id": n.id, "type": n.type, "title": n.title, "body": n.body,
        "data": n.data, "project_id": n.project_id, "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def serialize(n: Notification) -> dict:
    return _serialize(n)


# --------------------------------------------------------------------------- #
# Domain helpers                                                              #
# --------------------------------------------------------------------------- #
async def notify_new_project(session: AsyncSession, project, platform_name: str = "",
                             analysis_pref_min_score: int = 0) -> None:
    from app.services.text import format_toman

    budget = "نامشخص"
    if project.budget_min or project.budget_max:
        low = format_toman(project.budget_min)
        high = format_toman(project.budget_max)
        budget = f"{low} تا {high}" if project.budget_min and project.budget_max else (high if project.budget_max else low)
    await create(
        session,
        type="project.new",
        title=f"پروژه جدید در {platform_name or 'پلتفرم'}: {project.title[:80]}",
        body=f"بودجه: {budget}",
        data={"project_id": project.id, "url": project.canonical_url},
        project_id=project.id,
        dedupe_key=f"project.new:{project.id}",
    )


async def notify_analysis_done(session: AsyncSession, project, analysis, threshold: int) -> None:
    rec = "پیشنهاد ارسال پیشنهاد" if analysis.recommendation == "BID" else "پیشنهاد صرف‌نظر"
    await create(
        session,
        type="analysis.done",
        title=f"تحلیل انجام شد: {project.title[:70]} — امتیاز {analysis.match_score}",
        body=f"{rec} (حد آستانه: {threshold})",
        data={"project_id": project.id, "match_score": analysis.match_score,
              "recommendation": analysis.recommendation, "url": project.canonical_url},
        project_id=project.id,
        dedupe_key=f"analysis.done:{project.id}:{analysis.id}",
    )


async def notify_analysis_failed(session: AsyncSession, project, error: str) -> None:
    # If the failure is due to missing AI configuration, deduplicate globally so user isn't spammed for each scraped project
    is_config_err = "پیکربندی نشده است" in error or "یافت نشد یا غیرفعال است" in error or "هیچ مدل" in error
    title = "تنظیمات ایجنت: مدل تحلیلگر هوش مصنوعی پیکربندی نشده است" if is_config_err else f"تحلیل پروژه ناموفق بود: {project.title[:70]}"
    dedupe = "analysis.failed:missing_config" if is_config_err else f"analysis.failed:{project.id}"
    await create(
        session,
        type="analysis.failed",
        title=title,
        body=error[:300],
        data={"project_id": project.id},
        project_id=project.id,
        dedupe_key=dedupe,
    )


async def notify_proposal_ready(session: AsyncSession, project, proposal, warning: bool = False) -> None:
    suffix = " (هشدار: کیفیت زیر حد آستانه)" if warning else ""
    await create(
        session,
        type="proposal.ready",
        title=f"پیشنهاد آماده بررسی است: {project.title[:70]}{suffix}",
        body=f"کیفیت: {proposal.quality_score if proposal.quality_score is not None else '—'}/100",
        data={"project_id": project.id, "proposal_id": proposal.id,
              "quality_score": proposal.quality_score},
        project_id=project.id,
        dedupe_key=f"proposal.ready:{proposal.id}:{proposal.current_version_id}",
    )


async def notify_submission(session: AsyncSession, project, submission, message: str,
                            platform_name: str = "") -> None:
    await create(
        session,
        type="submission.update",
        title=message[:200],
        body=f"پلتفرم: {platform_name or project.platform_id} — وضعیت: {submission.status}",
        data={"project_id": project.id, "proposal_id": submission.proposal_id,
              "submission_id": submission.id, "status": submission.status},
        project_id=project.id,
        dedupe_key=f"submission:{submission.id}:{submission.status}:{submission.submitted_at is not None}",
    )
