"""Developer profile (verified data used by all AI features) + user settings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import DeveloperProfile, DeveloperSkill, User, UserSetting

router = APIRouter(tags=["profile"], dependencies=[Depends(get_current_user)])


class ProfileIn(BaseModel):
    full_name: str | None = None
    summary: str | None = None
    github_url: str | None = None
    portfolio_urls: list[str] | None = None
    experience_years: float | None = None
    work_experience: str | None = None
    completed_projects: str | None = None
    preferred_categories: list[str] | None = None
    preferred_technologies: list[str] | None = None
    min_acceptable_budget: float | None = None
    currency: str | None = None


class SkillIn(BaseModel):
    name: str
    level: int = 3
    category: str | None = None
    is_core: bool = False


async def _get_profile(db: AsyncSession) -> DeveloperProfile:
    result = await db.execute(
        select(DeveloperProfile).where(DeveloperProfile.is_active == True).limit(1)  # noqa: E712
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = DeveloperProfile()
        db.add(profile)
        await db.flush()
    return profile


@router.get("/developer-profile")
async def get_profile(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    profile = await _get_profile(db)
    skills = (await db.execute(
        select(DeveloperSkill).where(DeveloperSkill.profile_id == profile.id)
        .order_by(DeveloperSkill.is_core.desc(), DeveloperSkill.level.desc())
    )).scalars().all()
    return {
        "full_name": profile.full_name, "summary": profile.summary,
        "github_url": profile.github_url, "portfolio_urls": profile.portfolio_urls,
        "experience_years": profile.experience_years,
        "work_experience": profile.work_experience,
        "completed_projects": profile.completed_projects,
        "preferred_categories": profile.preferred_categories,
        "preferred_technologies": profile.preferred_technologies,
        "min_acceptable_budget": profile.min_acceptable_budget,
        "currency": profile.currency,
        "skills": [{
            "id": s.id, "name": s.name, "level": s.level,
            "category": s.category, "is_core": s.is_core,
        } for s in skills],
    }


@router.put("/developer-profile")
async def update_profile(body: ProfileIn, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    profile = await _get_profile(db)
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(profile, field, value)
    await db.commit()
    return await get_profile(db=db, user=user)


@router.post("/developer-profile/skills")
async def add_skill(body: SkillIn, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    profile = await _get_profile(db)
    exists = (await db.execute(
        select(DeveloperSkill).where(DeveloperSkill.profile_id == profile.id,
                                     DeveloperSkill.name == body.name.strip())
    )).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "این مهارت قبلاً ثبت شده است.")
    skill = DeveloperSkill(profile_id=profile.id, name=body.name.strip(),
                           level=max(1, min(5, body.level)), category=body.category,
                           is_core=body.is_core)
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return {"id": skill.id, "name": skill.name, "level": skill.level,
            "category": skill.category, "is_core": skill.is_core}


@router.put("/developer-profile/skills/{skill_id}")
async def update_skill(skill_id: int, body: SkillIn, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    skill = (await db.execute(
        select(DeveloperSkill).where(DeveloperSkill.id == skill_id)
    )).scalar_one_or_none()
    if skill is None:
        raise HTTPException(404, "مهارت یافت نشد.")
    skill.name = body.name.strip()
    skill.level = max(1, min(5, body.level))
    skill.category = body.category
    skill.is_core = body.is_core
    await db.commit()
    return {"ok": True}


@router.delete("/developer-profile/skills/{skill_id}")
async def delete_skill(skill_id: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    skill = (await db.execute(
        select(DeveloperSkill).where(DeveloperSkill.id == skill_id)
    )).scalar_one_or_none()
    if skill is None:
        raise HTTPException(404, "مهارت یافت نشد.")
    await db.delete(skill)
    await db.commit()
    return {"ok": True}


# ------------------------------ user settings ------------------------------ #
@router.get("/settings/user")
async def get_user_settings(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(UserSetting))).scalars().all()
    return {r.key: r.value for r in rows}


@router.put("/settings/user")
async def put_user_setting(body: dict, db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user)):
    updated = {}
    for key, value in body.items():
        if not key or len(key) > 64:
            continue
        row = (await db.execute(select(UserSetting).where(UserSetting.key == key))).scalar_one_or_none()
        if row is None:
            row = UserSetting(key=key, value={"value": value})
            db.add(row)
        else:
            row.value = {"value": value}
        updated[key] = value
    await db.commit()
    return {"ok": True, "values": updated}
