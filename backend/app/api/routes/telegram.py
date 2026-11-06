"""Telegram configuration and chat management routes."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.security import encrypt_value, mask_secret
from app.models import AuthorizedChatID, TelegramSetting, User
from app.telegram import bot as bot_service

router = APIRouter(prefix="/telegram", tags=["telegram"], dependencies=[Depends(get_current_user)])


class TelegramSettingsIn(BaseModel):
    bot_token: str | None = None      # empty/None = keep existing
    enabled: bool | None = None
    mode: str | None = None           # polling | webhook
    webhook_url: str | None = None
    notify_enabled: bool | None = None
    notify_min_score: int | None = None


async def _settings(db: AsyncSession) -> TelegramSetting:
    row = (await db.execute(select(TelegramSetting).limit(1))).scalar_one_or_none()
    if row is None:
        row = TelegramSetting()
        db.add(row)
        await db.flush()
    return row


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    s = await _settings(db)
    return {
        "bot_token_masked": mask_secret(bot_service.decrypt_token(s)) if s.bot_token_encrypted else "",
        "has_token": bool(s.bot_token_encrypted),
        "bot_username": s.bot_username,
        "enabled": s.enabled,
        "mode": s.mode,
        "webhook_url": s.webhook_url,
        "pairing_code": s.pairing_code,
        "connection_status": s.connection_status,
        "notify_enabled": s.notify_enabled,
        "notify_min_score": s.notify_min_score,
        "last_check_at": s.last_check_at.isoformat() if s.last_check_at else None,
    }


@router.put("/settings")
async def update_settings(body: TelegramSettingsIn, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    s = await _settings(db)
    if body.bot_token:  # only overwrite when a new token is provided
        s.bot_token_encrypted = encrypt_value(body.bot_token.strip())
        s.connection_status = "disconnected"
        await bot_service.reset_bot()
    if body.enabled is not None:
        s.enabled = body.enabled
    if body.mode is not None:
        if body.mode not in ("polling", "webhook"):
            raise HTTPException(400, "حالت باید polling یا webhook باشد.")
        s.mode = body.mode
    if body.webhook_url is not None:
        s.webhook_url = body.webhook_url.strip() or None
    if body.notify_enabled is not None:
        s.notify_enabled = body.notify_enabled
    if body.notify_min_score is not None:
        s.notify_min_score = max(0, min(100, body.notify_min_score))
    await db.commit()
    return await get_settings(db=db, user=user)


@router.post("/test")
async def test_connection(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    s = await _settings(db)
    if not s.bot_token_encrypted:
        raise HTTPException(400, "ابتدا توکن ربات را ذخیره کنید.")
    result = await bot_service.test_token(bot_service.decrypt_token(s))
    s.connection_status = "connected" if result["ok"] else "error"
    if result["ok"] and result.get("bot_username"):
        s.bot_username = result["bot_username"]
    s.last_check_at = datetime.now(timezone.utc)
    await db.commit()
    return result


@router.post("/send-test")
async def send_test(body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    s = await _settings(db)
    if not s.bot_token_encrypted:
        raise HTTPException(400, "ابتدا توکن ربات را ذخیره کنید.")
    chats = (await db.execute(
        select(AuthorizedChatID).where(AuthorizedChatID.authorized == True)  # noqa: E712
    )).scalars().all()
    chat_id = body.get("chat_id")
    targets = [str(chat_id)] if chat_id else [c.chat_id for c in chats]
    if not targets:
        raise HTTPException(400, "هیچ چت تأییدشده‌ای وجود ندارد؛ ابتدا با کد جفت‌سازی ربات را متصل کنید.")
    ok, message = await bot_service.send_text(bot_service.decrypt_token(s), targets[0],
                                              "✅ پیام آزمایشی از Freelance Agent\nاتصال ربات برقرار است.")
    return {"ok": ok, "message": message, "sent_to": targets[0]}


@router.post("/disconnect")
async def disconnect(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    s = await _settings(db)
    s.enabled = False
    s.connection_status = "disconnected"
    await bot_service.reset_bot()
    await db.commit()
    return {"ok": True}


@router.post("/pairing-code")
async def regenerate_pairing(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    s = await _settings(db)
    s.pairing_code = bot_service.new_pairing_code()
    await db.commit()
    return {"pairing_code": s.pairing_code}


@router.get("/chats")
async def list_chats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(AuthorizedChatID).order_by(AuthorizedChatID.id))).scalars().all()
    return {"items": [{
        "id": c.id, "chat_id": c.chat_id, "username": c.username,
        "display_name": c.display_name, "authorized": c.authorized,
        "added_at": c.added_at.isoformat() if c.added_at else None,
    } for c in rows]}


@router.post("/chats/{chat_id}/toggle")
async def toggle_chat(chat_id: str, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    row = (await db.execute(
        select(AuthorizedChatID).where(AuthorizedChatID.chat_id == str(chat_id))
    )).scalar_one_or_none()
    if row is None:
        row = AuthorizedChatID(chat_id=str(chat_id))
        db.add(row)
    row.authorized = not row.authorized
    await db.commit()
    return {"ok": True, "authorized": row.authorized}


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    row = (await db.execute(
        select(AuthorizedChatID).where(AuthorizedChatID.chat_id == str(chat_id))
    )).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
    return {"ok": True}
