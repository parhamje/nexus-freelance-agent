"""Misc routes: analytics, execution logs, health and the WebSocket endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.logging_config import get_logger
from app.core.security import decode_access_token
from app.models import ExecutionLog, User
from app.services import analytics
from app.services.ws import manager as ws_manager

log = get_logger("api")
router = APIRouter(tags=["misc"])


@router.get("/analytics/summary")
async def analytics_summary(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await analytics.summary(db)


@router.get("/logs")
async def list_logs(level: str | None = None, component: str | None = None,
                    project_id: int | None = None, limit: int = Query(50, le=300),
                    offset: int = 0, db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    stmt = select(ExecutionLog).order_by(ExecutionLog.id.desc())
    if level:
        stmt = stmt.where(ExecutionLog.level == level)
    if component:
        stmt = stmt.where(ExecutionLog.component == component)
    if project_id:
        stmt = stmt.where(ExecutionLog.project_id == project_id)
    rows = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    return {"items": [{
        "id": r.id, "level": r.level, "component": r.component, "message": r.message,
        "data": r.data, "project_id": r.project_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


@router.get("/health")
async def health():
    return {"status": "ok", "ws_clients": ws_manager.client_count}


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = ""):
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        await ws.close(code=4401)
        return
    await ws_manager.connect(ws)
    log.info("dashboard client connected (%s open)", ws_manager.client_count)
    try:
        while True:
            message = await ws.receive_text()  # keepalive pings are ignored
            if message == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        ws_manager.disconnect(ws)
