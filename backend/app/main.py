"""Freelance Agent - FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging_config import get_logger, setup_logging
from app.core.security import decode_access_token

setup_logging()
log = get_logger("main")


# --------------------------------------------------------------------------- #
# Background tasks                                                            #
# --------------------------------------------------------------------------- #
_bg_tasks: dict[str, asyncio.Task] = {}


async def _startup() -> None:
    from app.core.db import get_session_factory, init_models
    from app.core.seed import seed
    from app.services.discovery import DiscoveryScheduler, sync_platform_rows
    from app.services.outbox import outbox_worker, recover_stale
    from app.telegram.bot import start_polling

    await init_models()
    session_factory = get_session_factory()
    async with session_factory() as session:
        await seed(session)
        await sync_platform_rows(session)
    await recover_stale(session_factory)

    # Import services so their @handler registrations are active
    import app.services.analyzer  # noqa: F401
    import app.services.proposals  # noqa: F401
    import app.services.submissions  # noqa: F401
    import app.telegram.bot  # noqa: F401  (registers notify.telegram handler)

    scheduler = DiscoveryScheduler()
    _bg_tasks["scheduler"] = asyncio.create_task(scheduler._run(), name="discovery-scheduler")
    _bg_tasks["outbox"] = asyncio.create_task(outbox_worker(session_factory), name="outbox-worker")
    _bg_tasks["telegram"] = asyncio.create_task(start_polling(session_factory), name="telegram-supervisor")
    log.info("startup complete - discovery, outbox and telegram tasks running")


async def _shutdown() -> None:
    for name, task in _bg_tasks.items():
        task.cancel()
    for name, task in _bg_tasks.items():
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    _bg_tasks.clear()
    from app.core.db import dispose_engine
    await dispose_engine()
    log.info("shutdown complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _startup()
    yield
    await _shutdown()


app = FastAPI(title=settings.app_name, version=settings.app_version,
              docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)


# --------------------------------------------------------------------------- #
# Middleware: CORS + simple rate limiting                                     #
# --------------------------------------------------------------------------- #
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

_hits: dict[str, deque] = defaultdict(lambda: deque(maxlen=400))


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    import time
    t0 = time.perf_counter()
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/v1/health"):
        client = request.client.host if request.client else "?"
        now = time.time()
        window = _hits[client]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            return JSONResponse({"detail": "تعداد درخواست‌ها بیش از حد مجاز است."}, status_code=429)
        window.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    elapsed = (time.perf_counter() - t0) * 1000
    if path.startswith("/api/"):
        log.info("[PERF] %s: %.2f ms", path, elapsed)
    return response


# --------------------------------------------------------------------------- #
# Routers                                                                     #
# --------------------------------------------------------------------------- #
from app.api.routes.ai import router as ai_router  # noqa: E402
from app.api.routes.auth import router as auth_router  # noqa: E402
from app.api.routes.misc import router as misc_router  # noqa: E402
from app.api.routes.notifications import router as notifications_router  # noqa: E402
from app.api.routes.platforms import router as platforms_router  # noqa: E402
from app.api.routes.profile import router as profile_router  # noqa: E402
from app.api.routes.projects import router as projects_router  # noqa: E402
from app.api.routes.proposal_routes import router as proposals_router  # noqa: E402
from app.api.routes.telegram import router as telegram_router  # noqa: E402

API = "/api/v1"
app.include_router(auth_router, prefix=API)
app.include_router(projects_router, prefix=API)
app.include_router(proposals_router, prefix=API)
app.include_router(platforms_router, prefix=API)
app.include_router(ai_router, prefix=API)
app.include_router(profile_router, prefix=API)
app.include_router(telegram_router, prefix=API)
app.include_router(notifications_router, prefix=API)
app.include_router(misc_router, prefix=API)


# --------------------------------------------------------------------------- #
# Telegram webhook mode (optional)                                            #
# --------------------------------------------------------------------------- #
@app.post("/telegram/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    from sqlalchemy import select
    from app.core.db import get_session_factory
    from app.models import TelegramSetting

    if settings.telegram_webhook_secret and secret != settings.telegram_webhook_secret:
        raise HTTPException(403, "invalid webhook secret")
    session_factory = get_session_factory()
    async with session_factory() as session:
        setting = (await session.execute(select(TelegramSetting).limit(1))).scalar_one_or_none()
        token = decrypt_setting_token(setting)
        mode_ok = bool(setting and setting.enabled and setting.mode == "webhook")
    if not mode_ok or not token:
        raise HTTPException(400, "webhook mode is not enabled")
    from aiogram import Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Update
    from app.telegram.bot import _bot_for, build_router

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_router())
    payload = await request.json()
    update = Update.model_validate(payload)
    await dp.feed_update(_bot_for(token), update)
    return {"ok": True}


def decrypt_setting_token(setting):
    from app.telegram.bot import decrypt_token
    return decrypt_token(setting) if setting else ""


# --------------------------------------------------------------------------- #
# Frontend (vanilla JS SPA)                                                   #
# --------------------------------------------------------------------------- #
_frontend = settings.frontend_path
if (_frontend / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
else:
    @app.get("/")
    async def frontend_missing():
        return JSONResponse({"detail": "frontend not built - see frontend/ directory"}, status_code=404)
