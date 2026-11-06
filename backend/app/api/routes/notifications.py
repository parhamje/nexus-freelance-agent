"""Notification history, read states and preferences."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func as safunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import Notification, User
from app.services.notifications import _serialize, get_preferences

router = APIRouter(prefix="/notifications", tags=["notifications"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_notifications(unread_only: bool = False, limit: int = Query(30, le=200),
                             offset: int = 0, db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    stmt = select(Notification).order_by(Notification.id.desc())
    count_stmt = select(safunc.count(Notification.id))
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)  # noqa: E712
        count_stmt = count_stmt.where(Notification.is_read == False)  # noqa: E712
    total = int((await db.execute(count_stmt)).scalar() or 0)
    rows = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    unread = int((await db.execute(
        select(safunc.count(Notification.id)).where(Notification.is_read == False)  # noqa: E712
    )).scalar() or 0)
    return {"total": total, "unread": unread, "items": [_serialize(n) for n in rows]}


@router.get("/unread-count")
async def unread_count(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    unread = int((await db.execute(
        select(safunc.count(Notification.id)).where(Notification.is_read == False)  # noqa: E712
    )).scalar() or 0)
    return {"unread": unread}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: int, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    row = (await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )).scalar_one_or_none()
    if row and not row.is_read:
        row.is_read = True
        row.read_at = datetime.now(timezone.utc)
        await db.commit()
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(Notification).where(Notification.is_read == False)  # noqa: E712
    )).scalars().all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.is_read = True
        row.read_at = now
    await db.commit()
    return {"ok": True, "marked": len(rows)}


class PrefsIn(BaseModel):
    web_enabled: bool | None = None
    telegram_enabled: bool | None = None
    sound_enabled: bool | None = None
    volume: float | None = None
    browser_notifications: bool | None = None
    push_enabled: bool | None = None
    min_score_to_notify: int | None = None


@router.get("/preferences")
async def get_prefs(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    p = await get_preferences(db)
    return {
        "web_enabled": p.web_enabled, "telegram_enabled": p.telegram_enabled,
        "sound_enabled": p.sound_enabled, "volume": p.volume,
        "browser_notifications": p.browser_notifications, "push_enabled": p.push_enabled,
        "min_score_to_notify": p.min_score_to_notify,
    }


@router.put("/preferences")
async def update_prefs(body: PrefsIn, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    p = await get_preferences(db)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if "volume" in data:
        data["volume"] = max(0.0, min(1.0, float(data["volume"])))
    if "min_score_to_notify" in data:
        data["min_score_to_notify"] = max(0, min(100, int(data["min_score_to_notify"])))
    for key, value in data.items():
        setattr(p, key, value)
    await db.commit()
    return await get_prefs(db=db, user=user)
