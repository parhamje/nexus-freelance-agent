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


class ChatAddIn(BaseModel):
    chat_id: str
    display_name: str | None = None
    username: str | None = None


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
    # Migrate to modern URL-safe NX-XXXXX pairing code if missing or legacy Persian
    if not s.pairing_code or not s.pairing_code.startswith("NX-"):
        s.pairing_code = bot_service.new_pairing_code()
        await db.commit()
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
        raw_token = body.bot_token.strip()
        s.bot_token_encrypted = encrypt_value(raw_token)
        await bot_service.reset_bot()
        # Verify token automatically upon save
        test_res = await bot_service.test_token(raw_token)
        if test_res["ok"]:
            s.connection_status = "connected"
            s.enabled = True
            s.notify_enabled = True
            if test_res.get("bot_username"):
                s.bot_username = test_res["bot_username"]
        else:
            s.connection_status = "error"
        s.last_check_at = datetime.now(timezone.utc)
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
    bot_service.wakeup_supervisor()
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
        raise HTTPException(400, "هیچ چت فعالی متصل نشده است؛ ابتدا در تلگرام وارد ربات خود شوید و دکمه Start را بزنید تا چت شما به‌صورت خودکار متصل شود.")
    
    token = bot_service.decrypt_token(s)
    text = body.get("message") or (
        "⚡ <b>سامانه هوشمند فریلنسری NEXUS</b>\n\n"
        "✅ <b>تست اتصال ربات تلگرام:</b> ارتباط سیستم با تلگرام برقرار و فعال است.\n"
        "تمامی اعلان‌های پروژه‌ها و پیشنهادهای جدید به این چت ارسال خواهند شد.\n"
        f"⏱ زمان تست: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
    )

    results = []
    for t in targets:
        ok, msg = await bot_service.send_text(token, t, text)
        results.append({"chat_id": t, "ok": ok, "message": msg})

    any_ok = any(r["ok"] for r in results)
    if not any_ok:
        err = results[0]["message"] if results else "خطای نامشخص"
        return {"ok": False, "message": f"ارسال ناموفق بود: {err}", "results": results}

    success_count = sum(1 for r in results if r["ok"])
    return {
        "ok": True,
        "message": f"پیام آزمایشی به {success_count} چت با موفقیت ارسال شد.",
        "sent_to": targets[0] if len(targets) == 1 else "all",
        "results": results
    }


@router.post("/disconnect")
async def disconnect(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    s = await _settings(db)
    s.enabled = False
    s.connection_status = "disconnected"
    await bot_service.reset_bot()
    await db.commit()
    bot_service.wakeup_supervisor()
    return {"ok": True}


@router.post("/pairing-code")
async def regenerate_pairing(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    s = await _settings(db)
    s.pairing_code = bot_service.new_pairing_code()
    await db.commit()
    return {"pairing_code": s.pairing_code}


@router.post("/chats")
async def add_chat(body: ChatAddIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    cid = body.chat_id.strip()
    if not cid:
        raise HTTPException(400, "شناسه چت (Chat ID) الزامی است.")
    row = (await db.execute(
        select(AuthorizedChatID).where(AuthorizedChatID.chat_id == cid)
    )).scalar_one_or_none()
    if row is None:
        row = AuthorizedChatID(chat_id=cid)
        db.add(row)
    row.authorized = True
    if body.display_name:
        row.display_name = body.display_name.strip()
    if body.username:
        row.username = body.username.strip().lstrip("@")
    
    # Automatically enable telegram service and notifications
    s = await _settings(db)
    s.enabled = True
    s.notify_enabled = True
    await db.commit()
    bot_service.wakeup_supervisor()
    return {"ok": True, "chat_id": row.chat_id}


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
