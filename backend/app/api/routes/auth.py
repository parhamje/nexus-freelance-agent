"""Authentication routes for the dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/login")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username.strip()))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "نام کاربری یا رمز عبور اشتباه است.")
    token = create_access_token(user.username)
    return {"access_token": token, "token_type": "bearer", "username": user.username}


@router.post("/register")
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    username = body.username.strip()
    if len(username) < 3:
        raise HTTPException(400, "نام کاربری باید حداقل ۳ کاراکتر باشد.")
    if len(body.password) < 6:
        raise HTTPException(400, "رمز عبور باید حداقل ۶ کاراکتر باشد.")
    if " " in username:
        raise HTTPException(400, "نام کاربری نباید شامل فاصله باشد.")

    result = await db.execute(select(User).where(User.username == username))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(400, "این نام کاربری قبلاً ثبت شده است.")

    user = User(
        username=username,
        password_hash=hash_password(body.password),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.username)
    return {"access_token": token, "token_type": "bearer", "username": user.username}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"username": user.username, "created_at": user.created_at.isoformat() if user.created_at else None}


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "رمز عبور فعلی اشتباه است.")
    if len(body.new_password) < 8:
        raise HTTPException(400, "رمز عبور جدید باید حداقل ۸ کاراکتر باشد.")
    user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"ok": True}
