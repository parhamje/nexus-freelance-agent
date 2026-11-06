"""Proposal submission - the safety-critical stage.

HARD RULES:
- Submission only starts from the explicit "Approve and Submit" action.
- Preflight checks run first: proposal ready, no prior submission, price and
  delivery valid, project still open (when the platform allows checking).
- If the platform offers no submission API (true for all current platforms),
  the result is an ASSISTED workflow: the owner posts the proposal manually
  on the platform, then confirms it here. The app NEVER reports success that
  did not happen.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger, log_execution
from app.integrations.base.connector import get_connector
from app.integrations.base.schemas import SubmissionPayload
from app.models import (Platform, PlatformCredential, Project, ProjectStatus,
                        Proposal, ProposalStatus, ProposalSubmission,
                        ProposalVersion, SubmissionMethod, SubmissionStatus)
from app.core.security import decrypt_value
from app.core.db import get_session_factory
from app.services import notifications
from app.services.outbox import handler
from app.services.text import format_toman

log = get_logger("submission")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _load_credentials(platform_id: int) -> dict:
    import json

    session_factory = get_session_factory()
    async with session_factory() as session:
        row = (await session.execute(
            select(PlatformCredential).where(PlatformCredential.platform_id == platform_id)
        )).scalar_one_or_none()
    if not row or not row.encrypted_payload:
        return {}
    try:
        return json.loads(decrypt_value(row.encrypted_payload))
    except ValueError:
        return {}


async def request_submission(session: AsyncSession, proposal_id: int, actor: str = "web") -> dict:
    proposal = (await session.execute(select(Proposal).where(Proposal.id == proposal_id))).scalar_one_or_none()
    if proposal is None:
        raise ValueError("پیشنهاد یافت نشد.")
    if proposal.status not in (ProposalStatus.READY.value, ProposalStatus.SUBMIT_FAILED.value):
        raise ValueError("پیشنهاد در وضعیت آماده ارسال نیست.")

    existing = (await session.execute(
        select(ProposalSubmission).where(ProposalSubmission.proposal_id == proposal_id)
    )).scalar_one_or_none()
    if existing is not None and existing.status not in (SubmissionStatus.FAILED.value,):
        raise ValueError("برای این پیشنهاد قبلاً ثبت درخواست ارسال شده است؛ ارسال تکراری مجاز نیست.")

    project, platform = (await session.execute(
        select(Project, Platform)
        .join(Platform, Project.platform_id == Platform.id)
        .where(Project.id == proposal.project_id)
    )).one()
    if project.status not in (ProjectStatus.PROPOSAL_READY.value, ProjectStatus.PROPOSAL_SUBMITTED.value):
        raise ValueError("پروژه در وضعیت مجاز برای ارسال نیست.")

    version = None
    if proposal.current_version_id:
        version = (await session.execute(
            select(ProposalVersion).where(ProposalVersion.id == proposal.current_version_id)
        )).scalar_one_or_none()
    if version is None:
        raise ValueError("نسخه فعالی برای ارسال وجود ندارد.")

    price = version.price
    delivery_days = version.delivery_days
    if not price or price <= 0:
        raise ValueError("قیمت پیشنهاد نامعتبر است؛ ابتدا قیمت را تعیین کنید.")
    if not delivery_days or delivery_days <= 0:
        raise ValueError("زمان تحویل نامعتبر است؛ ابتدا آن را تعیین کنید.")

    preflight: dict = {
        "proposal_status": proposal.status,
        "project_status": project.status,
        "price": price,
        "delivery_days": delivery_days,
        "checks": {
            "proposal_ready": True,
            "not_submitted_before": existing is None,
            "price_valid": True,
            "deadline_valid": True,
            "owner_approval": project.approved_at is not None,
        },
    }

    connector = get_connector(platform.slug,
                              credentials=await _load_credentials(project.platform_id),
                              config=platform.settings or {})
    caps = connector.capabilities()
    try:
        if caps.submit_proposal and caps.submit_method == "api":
            # Platform-supported programmatic submission (none of the current
            # platforms qualify; kept for future authorized integrations).
            avail = await connector.check_availability(project.external_id, project.raw_data)
            preflight["availability"] = {"available": avail.available, "reason": avail.reason}
            if avail.available is False:
                submission = ProposalSubmission(
                    proposal_id=proposal.id, project_id=project.id, platform_id=project.platform_id,
                    version_id=version.id, price=price, delivery_days=delivery_days,
                    currency="IRT",
                    method=SubmissionMethod.API.value, status=SubmissionStatus.FAILED.value,
                    error=f"پروژه دیگر در حال دریافت پیشنهاد نیست: {avail.reason}",
                    preflight_report=preflight,
                )
                session.add(submission)
                await session.commit()
                await notifications.notify_submission(
                    session, project, submission,
                    "ارسال انجام نشد: پروژه بسته شده است", platform_name=platform.name)
                return _serialize(submission, project, platform, version)

            payload = SubmissionPayload(
                external_id=project.external_id, url=project.canonical_url, title=project.title,
                content=version.content, price=price, delivery_days=delivery_days)
            result = await connector.submit_proposal(payload)
            submission = ProposalSubmission(
                proposal_id=proposal.id, project_id=project.id, platform_id=project.platform_id,
                version_id=version.id, price=price, delivery_days=delivery_days, currency="IRT",
                method=SubmissionMethod.API.value,
                status=SubmissionStatus.SUBMITTED.value if result.success else SubmissionStatus.FAILED.value,
                external_submission_id=result.external_submission_id,
                error=None if result.success else result.message,
                preflight_report=preflight,
                submitted_at=_utcnow() if result.success else None,
                verified_at=_utcnow() if result.success else None,
            )
            session.add(submission)
            await session.flush()
            if result.success:
                proposal.status = ProposalStatus.SUBMITTED.value
                project.status = ProjectStatus.PROPOSAL_SUBMITTED.value
            else:
                proposal.status = ProposalStatus.SUBMIT_FAILED.value
            await log_execution(session, "submission",
                                f"API submission for proposal {proposal.id}: {submission.status}",
                                project_id=project.id, data={"message": result.message})
            await session.commit()
            await notifications.notify_submission(
                session, project, submission,
                "پیشنهاد با موفقیت ارسال شد" if result.success else f"ارسال ناموفق: {result.message}",
                platform_name=platform.name)
            return _serialize(submission, project, platform, version)

        # --- Assisted submission (all current platforms) ---
        submission = ProposalSubmission(
            proposal_id=proposal.id, project_id=project.id, platform_id=project.platform_id,
            version_id=version.id, price=price, delivery_days=delivery_days, currency="IRT",
            method=SubmissionMethod.ASSISTED.value,
            status=SubmissionStatus.ASSISTED_PENDING.value,
            preflight_report=preflight,
        )
        session.add(submission)
        await session.flush()
        await log_execution(session, "submission",
                            f"assisted submission prepared for proposal {proposal.id} "
                            f"(platform {platform.slug} has no submission API)",
                            project_id=project.id)
        await session.commit()
        await notifications.notify_submission(
            session, project, submission,
            "پیشنهاد برای ارسال دستی آماده شد (ارسال توسط خودتان در پلتفرم)",
            platform_name=platform.name)
        return _serialize(submission, project, platform, version)
    finally:
        await connector.aclose()


async def confirm_assisted(session: AsyncSession, submission_id: int, actor: str = "web") -> dict:
    """Owner confirms they posted the proposal on the platform themselves."""
    submission = (await session.execute(
        select(ProposalSubmission).where(ProposalSubmission.id == submission_id)
    )).scalar_one_or_none()
    if submission is None:
        raise ValueError("رکورد ارسال یافت نشد.")
    if submission.method != SubmissionMethod.ASSISTED.value:
        raise ValueError("این رکورد ارسال دستی نیست.")
    if submission.status != SubmissionStatus.ASSISTED_PENDING.value:
        raise ValueError("این ارسال قبلاً تأیید شده است.")
    submission.status = SubmissionStatus.SUBMITTED.value
    submission.submitted_at = _utcnow()
    submission.confirmed_at = _utcnow()
    proposal = (await session.execute(select(Proposal).where(Proposal.id == submission.proposal_id))).scalar_one()
    project, platform = (await session.execute(
        select(Project, Platform)
        .join(Platform, Project.platform_id == Platform.id)
        .where(Project.id == submission.project_id)
    )).one()
    proposal.status = ProposalStatus.SUBMITTED.value
    project.status = ProjectStatus.PROPOSAL_SUBMITTED.value
    await log_execution(session, "submission",
                        f"owner confirmed assisted submission #{submission.id}",
                        project_id=project.id, data={"actor": actor})
    await session.commit()
    await notifications.notify_submission(
        session, project, submission,
        "ارسال دستی پیشنهاد توسط شما تأیید شد", platform_name=platform.name)
    return _serialize(submission, project, platform, None)


async def mark_outcome(session: AsyncSession, submission_id: int,
                       outcome: str, note: str | None = None) -> ProposalSubmission:
    """Record a *known* outcome (won/lost). Only set with real evidence."""
    if outcome not in ("won", "lost", "unknown"):
        raise ValueError("نتیجه باید won، lost یا unknown باشد.")
    submission = (await session.execute(
        select(ProposalSubmission).where(ProposalSubmission.id == submission_id)
    )).scalar_one_or_none()
    if submission is None:
        raise ValueError("رکورد ارسال یافت نشد.")
    submission.outcome = None if outcome == "unknown" else outcome
    submission.outcome_note = note
    await session.commit()
    return submission


def _serialize(submission: ProposalSubmission, project: Project,
               platform, version: ProposalVersion | None) -> dict:
    data = {
        "id": submission.id,
        "proposal_id": submission.proposal_id,
        "project_id": submission.project_id,
        "platform": platform.slug,
        "platform_name": platform.name,
        "status": submission.status,
        "method": submission.method,
        "price": submission.price,
        "delivery_days": submission.delivery_days,
        "currency": submission.currency,
        "external_submission_id": submission.external_submission_id,
        "error": submission.error,
        "preflight_report": submission.preflight_report,
        "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
        "confirmed_at": submission.confirmed_at.isoformat() if submission.confirmed_at else None,
        "project_url": project.canonical_url,
        "project_title": project.title,
    }
    if submission.method == SubmissionMethod.ASSISTED.value and version is not None:
        data["assisted"] = {
            "url": project.canonical_url,
            "proposal_text": version.content,
            "price": version.price,
            "delivery_days": version.delivery_days,
            "currency": submission.currency,
            "price_display": format_toman(version.price),
            "instructions": (
                "این پلتفرم API عمومی برای ارسال پیشنهاد ندارد. متن و قیمت آماده شده را "
                "در صفحه پروژه پلتفرم خودتان ارسال کنید و سپس همین‌جا تأیید کنید. "
                "هیچ چیزی به‌جای شما ارسال نمی‌شود."
            ),
        }
    return data


@handler("submission.request")
async def _handle_submit(session: AsyncSession, payload: dict) -> None:
    await request_submission(session, payload.get("proposal_id"), actor="outbox")
