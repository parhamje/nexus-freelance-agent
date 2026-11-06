"""Proposal routes: generation (only for approved projects), versions, review,
strategy selection, final approve-and-submit and assisted submissions."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.routes.projects import _dt, serialize_analysis
from app.core.db import get_db
from app.models import (Platform, Project, Proposal, ProposalSubmission,
                        ProposalVersion, User)
from app.services import outbox, proposals as proposal_service, submissions as submission_service
from app.services.discovery import get_agent_config

router = APIRouter(tags=["proposals"], dependencies=[Depends(get_current_user)])


class GenerateIn(BaseModel):
    strategy: str = "balanced"


class EditIn(BaseModel):
    content: str
    price: float | None = None
    delivery_days: int | None = None


class StrategyIn(BaseModel):
    strategy: str


class PricingIn(BaseModel):
    price: float | None = None
    delivery_days: int | None = None


def serialize_version(v: ProposalVersion) -> dict:
    return {
        "id": v.id, "version_no": v.version_no, "attempt_no": v.attempt_no,
        "source": v.source, "content": v.content, "word_count": v.word_count,
        "strategy": v.strategy, "price": v.price, "delivery_days": v.delivery_days,
        "quality_score": v.quality_score, "quality_report": v.quality_report,
        "model_provider": v.model_provider, "model_name": v.model_name,
        "created_at": _dt(v.created_at),
    }


async def _bundle(db: AsyncSession, proposal_id: int) -> dict:
    row = (await db.execute(
        select(Proposal, Project, Platform)
        .join(Project, Proposal.project_id == Project.id)
        .join(Platform, Project.platform_id == Platform.id)
        .where(Proposal.id == proposal_id)
    )).first()
    if row is None:
        raise HTTPException(404, "پیشنهاد یافت نشد.")
    proposal, project, platform = row
    versions = (await db.execute(
        select(ProposalVersion).where(ProposalVersion.proposal_id == proposal.id)
        .order_by(ProposalVersion.version_no)
    )).scalars().all()
    submission = (await db.execute(
        select(ProposalSubmission).where(ProposalSubmission.proposal_id == proposal.id).limit(1)
    )).scalar_one_or_none()
    cfg = await get_agent_config(db)
    return {
        "id": proposal.id,
        "status": proposal.status,
        "selected_strategy": proposal.selected_strategy,
        "quality_score": proposal.quality_score,
        "current_version_id": proposal.current_version_id,
        "quality_threshold": cfg.quality_threshold,
        "max_generation_attempts": cfg.max_generation_attempts,
        "project": {
            "id": project.id, "title": project.title, "url": project.canonical_url,
            "platform": platform.slug, "platform_name": platform.name,
            "status": project.status, "budget_min": project.budget_min,
            "budget_max": project.budget_max, "currency": project.currency,
            "external_id": project.external_id,
        },
        "versions": [serialize_version(v) for v in versions],
        "submission": {
            "id": submission.id, "status": submission.status, "method": submission.method,
            "submitted_at": _dt(submission.submitted_at), "error": submission.error,
            "outcome": submission.outcome,
        } if submission else None,
        "created_at": _dt(proposal.created_at),
    }


@router.get("/proposals")
async def list_proposals(status: str | None = None, limit: int = 50, offset: int = 0,
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Proposal, Project, Platform).join(
        Project, Proposal.project_id == Project.id
    ).join(Platform, Project.platform_id == Platform.id)
    if status:
        stmt = stmt.where(Proposal.status == status)
    rows = (await db.execute(stmt.order_by(Proposal.updated_at.desc()).offset(offset).limit(limit))).all()
    items = [{
        "id": p.id, "status": p.status, "selected_strategy": p.selected_strategy,
        "quality_score": p.quality_score,
        "project_id": pr.id, "project_title": pr.title, "platform": pl.slug,
        "platform_name": pl.name, "updated_at": _dt(p.updated_at),
    } for p, pr, pl in rows]
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    data = await _bundle(db, proposal_id)
    project_id = data["project"]["id"]
    from app.models import ProjectAnalysis
    analysis = (await db.execute(
        select(ProjectAnalysis).where(ProjectAnalysis.project_id == project_id)
        .order_by(ProjectAnalysis.id.desc()).limit(1)
    )).scalar_one_or_none()
    data["analysis"] = serialize_analysis(analysis)
    return data


@router.post("/projects/{project_id}/proposals/generate", status_code=202)
async def generate_proposal(project_id: int, body: GenerateIn,
                            db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    from app.models import Project
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "پروژه یافت نشد.")
    if project.status not in ("approved_for_proposal", "proposal_ready", "proposal_generating"):
        raise HTTPException(409, "تولید پیشنهاد فقط برای پروژه‌های تأییدشده مجاز است.")
    await outbox.enqueue(db, "proposal.generate",
                         {"project_id": project_id, "strategy": body.strategy})
    await db.commit()
    return {"accepted": True,
            "note": "تولید پیشنهاد در پس‌زمینه آغاز شد؛ نتیجه از طریق اعلان و همین صفحه اعلام می‌شود."}


@router.post("/proposals/{proposal_id}/regenerate", status_code=202)
async def regenerate(proposal_id: int, body: StrategyIn | None = None,
                     db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    data = await _bundle(db, proposal_id)
    strategy = body.strategy if body else data["selected_strategy"]
    await outbox.enqueue(db, "proposal.generate",
                         {"project_id": data["project"]["id"], "strategy": strategy})
    await db.commit()
    return {"accepted": True}


@router.post("/proposals/{proposal_id}/edit")
async def edit_proposal(proposal_id: int, body: EditIn, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    try:
        version = await proposal_service.edit_proposal(db, proposal_id, body.content,
                                                       body.price, body.delivery_days)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "version": serialize_version(version)}


@router.post("/proposals/{proposal_id}/strategy")
async def set_strategy(proposal_id: int, body: StrategyIn, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    try:
        await proposal_service.set_strategy(db, proposal_id, body.strategy)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return await _bundle(db, proposal_id)


@router.post("/proposals/{proposal_id}/pricing")
async def update_pricing(proposal_id: int, body: PricingIn, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    data = await _bundle(db, proposal_id)
    version_id = data["current_version_id"]
    if not version_id:
        raise HTTPException(400, "نسخه فعالی وجود ندارد.")
    try:
        await proposal_service.update_version_pricing(db, proposal_id, version_id,
                                                      body.price, body.delivery_days)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return await _bundle(db, proposal_id)


@router.post("/proposals/{proposal_id}/submit")
async def approve_and_submit(proposal_id: int, db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    """The ONLY endpoint that initiates submission - explicit final approval."""
    try:
        result = await submission_service.request_submission(db, proposal_id, actor="web")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return result


@router.post("/submissions/{submission_id}/confirm-assisted")
async def confirm_assisted(submission_id: int, db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user)):
    try:
        return await submission_service.confirm_assisted(db, submission_id, actor="web")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.post("/submissions/{submission_id}/outcome")
async def set_outcome(submission_id: int, body: dict, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    try:
        sub = await submission_service.mark_outcome(db, submission_id,
                                                    body.get("outcome", "unknown"),
                                                    body.get("note"))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "outcome": sub.outcome}


@router.get("/submissions")
async def list_submissions(limit: int = 50, offset: int = 0,
                           db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(ProposalSubmission, Project, Platform)
        .join(Project, ProposalSubmission.project_id == Project.id)
        .join(Platform, ProposalSubmission.platform_id == Platform.id)
        .order_by(ProposalSubmission.created_at.desc()).offset(offset).limit(limit)
    )).all()
    items = [{
        "id": s.id, "proposal_id": s.proposal_id, "project_title": pr.title,
        "platform": pl.slug, "platform_name": pl.name, "status": s.status,
        "method": s.method, "price": s.price, "delivery_days": s.delivery_days,
        "outcome": s.outcome, "error": s.error,
        "submitted_at": _dt(s.submitted_at), "created_at": _dt(s.created_at),
        "project_url": pr.canonical_url,
    } for s, pr, pl in rows]
    return {"items": items, "limit": limit, "offset": offset}
