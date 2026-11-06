"""Transactional outbox: reliable background event processing with retries.

Events are persisted in ``outbox_events`` and processed by a background
worker, so a dashboard restart or a transient AI/Telegram outage never loses
work. Handlers are registered with the ``@handler`` decorator.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_logger, log_execution
from app.models import OutboxEvent

log = get_logger("outbox")

HANDLERS: dict[str, Callable[[AsyncSession, dict], Awaitable[None]]] = {}


def handler(event_type: str):
    def wrap(fn):
        HANDLERS[event_type] = fn
        return fn
    return wrap


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue(session: AsyncSession, event_type: str, payload: dict,
                  max_attempts: int = 8) -> OutboxEvent:
    event = OutboxEvent(event_type=event_type, payload=payload, max_attempts=max_attempts)
    session.add(event)
    await session.flush()
    return event


def _backoff(attempts: int) -> int:
    return min(1800, 15 * (2 ** max(attempts - 1, 0)))


async def process_pending(session_factory, batch_size: int = 20) -> int:
    """Process due events. Returns number of events handled."""
    processed = 0
    while processed < batch_size:
        async with session_factory() as session:
            now = _utcnow()
            result = await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status == "pending")
                .where((OutboxEvent.next_attempt_at.is_(None)) | (OutboxEvent.next_attempt_at <= now))
                .order_by(OutboxEvent.id)
                .limit(1)
            )
            event = result.scalar_one_or_none()
            if event is None:
                return processed

            # Optimistic claim: only the worker that flips pending->processing runs it.
            claim = await session.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == event.id, OutboxEvent.status == "pending")
                .values(status="processing")
            )
            if claim.rowcount == 0:
                continue
            await session.commit()
            await session.refresh(event)
            # Capture plain values BEFORE running the handler: after any
            # rollback the ORM object is expired and attribute access would
            # trigger synchronous IO (MissingGreenlet in async context).
            event_id = event.id
            event_type = event.event_type
            payload = dict(event.payload or {})
            attempts_before = int(event.attempts or 0)
            max_attempts = int(event.max_attempts or 8)

            fn = HANDLERS.get(event_type)
            try:
                if fn is None:
                    raise RuntimeError(f"no handler registered for {event_type}")
                await fn(session, payload)
                await session.execute(
                    update(OutboxEvent).where(OutboxEvent.id == event_id)
                    .values(status="done", processed_at=_utcnow(), error=None)
                )
                await session.commit()
            except Exception as exc:  # noqa: BLE001 - background worker must survive anything
                await session.rollback()
                attempts = attempts_before + 1
                error = f"{type(exc).__name__}: {exc}"[:2000]
                if attempts >= max_attempts:
                    await session.execute(
                        update(OutboxEvent).where(OutboxEvent.id == event_id)
                        .values(status="failed", attempts=attempts, error=error)
                    )
                    await log_execution(session, "outbox",
                                        f"event {event_id} ({event_type}) failed permanently: {error}",
                                        level="error")
                    await session.commit()
                    await _on_final_failure(session, event_type, payload)
                else:
                    await session.execute(
                        update(OutboxEvent).where(OutboxEvent.id == event_id)
                        .values(status="pending", attempts=attempts, error=error,
                                next_attempt_at=_utcnow() + timedelta(seconds=_backoff(attempts)))
                    )
                    await session.commit()
            processed += 1
    return processed


async def _on_final_failure(session: AsyncSession, event_type: str, payload: dict) -> None:
    """Domain-specific compensation when retries are exhausted."""
    if event_type == "analyze.project":
        from app.models import Project, ProjectStatus

        pid = payload.get("project_id")
        if not pid:
            return
        result = await session.execute(select(Project).where(Project.id == pid))
        project = result.scalar_one_or_none()
        if project and project.status == ProjectStatus.ANALYZING.value:
            project.status = ProjectStatus.ANALYSIS_FAILED.value
            await log_execution(session, "analyzer", f"analysis failed permanently for project {pid}", level="error", project_id=pid)
            await session.commit()


async def recover_stale(session_factory) -> None:
    """Reset events stuck in 'processing' (e.g. after a crash)."""
    async with session_factory() as session:
        await session.execute(
            update(OutboxEvent).where(OutboxEvent.status == "processing").values(status="pending")
        )
        await session.commit()


async def outbox_worker(session_factory) -> None:
    log.info("outbox worker started")
    while True:
        try:
            await process_pending(session_factory)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.error("outbox worker error: %s", exc)
        await asyncio.sleep(3)
