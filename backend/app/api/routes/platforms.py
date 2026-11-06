"""Platform integration routes: enable/disable, credentials, scan control, logs."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db, get_session_factory
from app.core.logging_config import get_logger
from app.core.security import encrypt_value, mask_secret
from app.integrations.base.connector import CONNECTORS, ConnectorError, get_connector
from app.models import Platform, PlatformCredential, PlatformScanLog, User
from app.services.discovery import scan_platform

log = get_logger("platforms")
router = APIRouter(prefix="/platforms", tags=["platforms"], dependencies=[Depends(get_current_user)])


class PlatformUpdate(BaseModel):
    enabled: bool | None = None
    scan_interval_minutes: int | None = None
    max_projects_per_scan: int | None = None
    settings: dict | None = None


class CredentialsIn(BaseModel):
    credentials: dict


def _serialize_platform(p: Platform) -> dict:
    return {
        "slug": p.slug, "name": p.name, "base_url": p.base_url,
        "enabled": p.enabled, "capabilities": p.capabilities or {},
        "scan_interval_minutes": p.scan_interval_minutes,
        "max_projects_per_scan": p.max_projects_per_scan,
        "connection_status": p.connection_status,
        "last_scan_at": p.last_scan_at.isoformat() if p.last_scan_at else None,
        "last_success_scan_at": p.last_success_scan_at.isoformat() if p.last_success_scan_at else None,
        "last_error": p.last_error, "last_error_at": p.last_error_at.isoformat() if p.last_error_at else None,
        "settings": p.settings or {},
        "has_credentials": p.credentials is not None and bool(p.credentials.encrypted_payload),
    }


async def _get_platform(db: AsyncSession, slug: str) -> Platform:
    p = (await db.execute(select(Platform).where(Platform.slug == slug))).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "پلتفرم یافت نشد.")
    return p


@router.get("")
async def list_platforms(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(Platform).order_by(Platform.id))).scalars().all()
    return {"items": [_serialize_platform(p) for p in rows]}


@router.get("/{slug}")
async def get_platform(slug: str, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    return _serialize_platform(await _get_platform(db, slug))


@router.put("/{slug}")
async def update_platform(slug: str, body: PlatformUpdate, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    platform = await _get_platform(db, slug)
    if slug == "demo" and body.enabled:
        from app.core.config import settings
        if not settings.debug:
            raise HTTPException(400, "پلتفرم demo فقط در حالت دیباگ قابل فعال‌سازی است.")
    if body.enabled is not None:
        platform.enabled = body.enabled
    if body.scan_interval_minutes is not None:
        if body.scan_interval_minutes < 5:
            raise HTTPException(400, "فاصله اسکن نباید کمتر از ۵ دقیقه باشد (احترام به پلتفرم).")
        platform.scan_interval_minutes = body.scan_interval_minutes
    if body.max_projects_per_scan is not None:
        platform.max_projects_per_scan = max(1, min(100, body.max_projects_per_scan))
    if body.settings is not None:
        platform.settings = body.settings
    await db.commit()
    return _serialize_platform(platform)


@router.put("/{slug}/credentials")
async def set_credentials(slug: str, body: CredentialsIn, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    platform = await _get_platform(db, slug)
    payload = encrypt_value(json.dumps(body.credentials))
    row = (await db.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == platform.id)
    )).scalar_one_or_none()
    if row is None:
        row = PlatformCredential(platform_id=platform.id)
        db.add(row)
    row.encrypted_payload = payload
    await db.commit()
    return {"ok": True, "keys": sorted(body.credentials.keys())}


@router.delete("/{slug}/credentials")
async def clear_credentials(slug: str, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    platform = await _get_platform(db, slug)
    row = (await db.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == platform.id)
    )).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()
    return {"ok": True}


@router.post("/{slug}/test")
async def test_connection(slug: str, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    platform = await _get_platform(db, slug)
    cred_row = (await db.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == platform.id)
    )).scalar_one_or_none()
    credentials = {}
    if cred_row and cred_row.encrypted_payload:
        try:
            credentials = json.loads(_decrypt(cred_row.encrypted_payload))
        except ValueError:
            credentials = {}
    try:
        connector = get_connector(slug, credentials=credentials, config=platform.settings or {})
    except ConnectorError as exc:
        raise HTTPException(400, str(exc))
    result = await connector.test_connection()
    platform.connection_status = "connected" if result["ok"] else "error"
    platform.last_error = None if result["ok"] else result["message"]
    platform.last_error_at = None if result["ok"] else datetime.now(timezone.utc)
    await db.commit()
    return result


def _decrypt(value: str) -> str:
    from app.core.security import decrypt_value
    return decrypt_value(value)


@router.post("/{slug}/scan-now")
async def scan_now(slug: str, db: AsyncSession = Depends(get_db),
                   user: User = Depends(get_current_user)):
    platform = await _get_platform(db, slug)
    if not platform.enabled:
        raise HTTPException(400, "ابتدا پلتفرم را فعال کنید.")
    asyncio.create_task(_run_scan(slug))
    return {"started": True, "note": "اسکن در پس‌زمینه آغاز شد؛ نتیجه در لاگ اسکن‌ها و اعلان‌ها دیده می‌شود."}


async def _run_scan(slug: str) -> None:
    try:
        counts = await scan_platform(slug, trigger="manual")
        log.info("manual scan %s: %s", slug, counts)
    except Exception as exc:  # noqa: BLE001
        log.warning("manual scan %s failed: %s", slug, exc)


@router.get("/{slug}/scan-logs")
async def scan_logs(slug: str, limit: int = 20, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    platform = await _get_platform(db, slug)
    rows = (await db.execute(
        select(PlatformScanLog).where(PlatformScanLog.platform_id == platform.id)
        .order_by(PlatformScanLog.id.desc()).limit(min(limit, 100))
    )).scalars().all()
    return {"items": [{
        "id": s.id, "status": s.status, "trigger": s.trigger,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "finished_at": s.finished_at.isoformat() if s.finished_at else None,
        "projects_found": s.projects_found, "projects_new": s.projects_new,
        "duplicates": s.duplicates, "filtered": s.filtered, "error": s.error,
    } for s in rows]}
