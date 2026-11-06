"""Project routes: discovery listing, details, owner approval decisions."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func as safunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import (Platform, Project, ProjectAnalysis, ProjectStatus,
                        Proposal, User)
from app.services import outbox
from app.services.discovery import get_agent_config

router = APIRouter(prefix="/projects", tags=["projects"], dependencies=[Depends(get_current_user)])


def _dt(v):
    return v.isoformat() if isinstance(v, datetime) else None


def serialize_project(p: Project, platform: Platform | None, analysis: ProjectAnalysis | None = None) -> dict:
    data = {
        "id": p.id,
        "platform": platform.slug if platform else None,
        "platform_name": platform.name if platform else None,
        "external_id": p.external_id,
        "title": p.title,
        "budget_min": p.budget_min,
        "budget_max": p.budget_max,
        "currency": p.currency,
        "deadline": _dt(p.deadline),
        "published_at": _dt(p.published_at),
        "first_discovered_at": _dt(p.first_discovered_at),
        "status": p.status,
        "url": p.canonical_url,
        "client_name": p.client_name,
        "skills": (p.skills or [])[:8],
        "approved_at": _dt(p.approved_at),
        "rejected_at": _dt(p.rejected_at),
    }
    if analysis is not None:
        data.update({
            "match_score": analysis.match_score,
            "recommendation": analysis.recommendation,
            "summary": analysis.summary,
        })
    return data


def serialize_analysis(a: ProjectAnalysis | None) -> dict | None:
    if a is None:
        return None
    return {
        "id": a.id,
        "match_score": a.match_score,
        "recommendation": a.recommendation,
        "summary": a.summary,
        "reasoning": a.reasoning,
        "aggressive_bid": a.aggressive_bid,
        "balanced_bid": a.balanced_bid,
        "premium_bid": a.premium_bid,
        "estimated_hours": a.estimated_hours,
        "estimated_delivery_days": a.estimated_delivery_days,
        "matching_skills": a.matching_skills,
        "missing_required_skills": a.missing_required_skills,
        "missing_optional_skills": a.missing_optional_skills,
        "technical_complexity": a.technical_complexity,
        "scope_complexity": a.scope_complexity,
        "technical_risks": a.technical_risks,
        "scope_risks": a.scope_risks,
        "budget_feasibility": a.budget_feasibility,
        "deadline_feasibility": a.deadline_feasibility,
        "client_quality": a.client_quality,
        "clarification_questions": a.clarification_questions,
        "model_provider": a.model_provider,
        "model_name": a.model_name,
        "created_at": _dt(a.created_at),
    }


async def _latest_analyses(db: AsyncSession, project_ids: list[int]) -> dict[int, ProjectAnalysis]:
    if not project_ids:
        return {}
    max_ids = select(safunc.max(ProjectAnalysis.id)).where(
        ProjectAnalysis.project_id.in_(project_ids)
    ).group_by(ProjectAnalysis.project_id)
    rows = (await db.execute(
        select(ProjectAnalysis).where(ProjectAnalysis.id.in_(max_ids))
    )).scalars().all()
    return {a.project_id: a for a in rows}


async def _project_with_platform(db: AsyncSession, project_id: int):
    row = (await db.execute(
        select(Project, Platform).join(Platform, Project.platform_id == Platform.id)
        .where(Project.id == project_id)
    )).first()
    return row


@router.get("")
async def list_projects(
    status: str | None = Query(None, description="comma separated statuses"),
    platform: str | None = None,
    min_score: int | None = None,
    q: str | None = None,
    limit: int = Query(25, le=100),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Project, Platform).join(Platform, Project.platform_id == Platform.id)
    count_stmt = select(safunc.count(Project.id)).join(Platform, Project.platform_id == Platform.id)
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        stmt = stmt.where(Project.status.in_(statuses))
        count_stmt = count_stmt.where(Project.status.in_(statuses))
    if platform:
        stmt = stmt.where(Platform.slug == platform)
        count_stmt = count_stmt.where(Platform.slug == platform)
    if q:
        like = f"%{q.strip()}%"
        cond = Project.title.ilike(like) | Project.description.ilike(like)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = int((await db.execute(count_stmt)).scalar() or 0)
    rows = (await db.execute(
        stmt.order_by(Project.first_discovered_at.desc()).offset(offset).limit(limit)
    )).all()
    analyses = await _latest_analyses(db, [p.id for p, _ in rows])
    items = []
    for p, plat in rows:
        a = analyses.get(p.id)
        if min_score is not None and min_score > 0:
            if a is None or a.match_score < min_score:
                total -= 1
                continue
        items.append(serialize_project(p, plat, a))
    return {"total": total, "items": items, "limit": limit, "offset": offset}


@router.get("/status-counts")
async def status_counts(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(Project.status, safunc.count(Project.id)).group_by(Project.status)
    )).all()
    return {s: n for s, n in rows}


@router.get("/{project_id}")
async def project_detail(project_id: int, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    row = await _project_with_platform(db, project_id)
    if row is None:
        raise HTTPException(404, "پروژه یافت نشد.")
    project, platform = row
    analysis = (await db.execute(
        select(ProjectAnalysis).where(ProjectAnalysis.project_id == project_id)
        .order_by(ProjectAnalysis.id.desc()).limit(1)
    )).scalar_one_or_none()
    proposal = (await db.execute(
        select(Proposal).where(Proposal.project_id == project_id).limit(1)
    )).scalar_one_or_none()
    data = serialize_project(project, platform, analysis)
    data.update({
        "description": project.description,
        "client_info": project.client_info,
        "category": project.category,
        "all_skills": project.skills,
        "raw_budget_hint": (project.raw_data or {}).get("determined_budget"),
        "analysis": serialize_analysis(analysis),
        "proposal_id": proposal.id if proposal else None,
        "proposal_status": proposal.status if proposal else None,
    })
    return data


def _transition_ok(current: str, target: str) -> bool:
    return current != target


@router.post("/{project_id}/approve")
async def approve_project(project_id: int, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "پروژه یافت نشد.")
    allowed = {ProjectStatus.RECOMMENDED.value, ProjectStatus.ANALYZED.value,
               ProjectStatus.SKIPPED.value}
    if project.status not in allowed:
        raise HTTPException(409, f"تأیید از وضعیت «{project.status}» مجاز نیست.")
    project.status = ProjectStatus.APPROVED_FOR_PROPOSAL.value
    project.approved_at = datetime.now(timezone.utc)
    project.rejected_at = None
    await db.commit()
    return {"ok": True, "status": project.status,
            "note": "پروژه تأیید شد؛ فقط تولید پیشنهاد مجاز است، ارسال نیاز به تأیید جداگانه دارد."}


@router.post("/{project_id}/reject")
async def reject_project(project_id: int, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "پروژه یافت نشد.")
    if project.status in (ProjectStatus.PROPOSAL_SUBMITTED.value,):
        raise HTTPException(409, "برای پروژه پیشنهادی ارسال شده است؛ رد کردن مجاز نیست.")
    project.status = ProjectStatus.REJECTED_BY_OWNER.value
    project.rejected_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "status": project.status}


@router.post("/{project_id}/reanalyze")
async def reanalyze_project(project_id: int, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "پروژه یافت نشد.")
    cfg = await get_agent_config(db)
    project.status = ProjectStatus.PENDING_ANALYSIS.value
    await outbox.enqueue(db, "analyze.project", {"project_id": project.id})
    await db.commit()
    return {"ok": True, "status": project.status}
