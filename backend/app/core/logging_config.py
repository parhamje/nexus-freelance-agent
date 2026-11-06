"""Logging setup + in-process execution log helper."""
from __future__ import annotations

import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


async def log_execution(session, component: str, message: str, level: str = "info",
                        data: dict | None = None, project_id: int | None = None) -> None:
    """Persist an execution log row (audit trail). Commit is the caller's job."""
    from app.models import ExecutionLog

    session.add(
        ExecutionLog(level=level, component=component, message=message,
                     data=data or {}, project_id=project_id)
    )
