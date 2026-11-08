"""Project discovery engine: platform scanning, filtering, dedup, scheduling.

The scheduler runs inside the same process as the API but fully independently
of any open browser tab; it keeps scanning while the dashboard is closed.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.core.logging_config import get_logger, log_execution
from app.integrations.base.connector import (CONNECTORS, ConnectorError,
                                              get_connector)
from app.models import (AgentConfiguration, DeveloperProfile, DeveloperSkill,
                        Platform, PlatformCredential, PlatformScanLog, Project, ProjectStatus)
from app.core.security import decrypt_value
from app.core.db import get_session_factory
from app.services import notifications, outbox
from app.services.text import canonicalize_url, content_hash, normalize_text, token_similarity

log = get_logger("discovery")

CHECK_INTERVAL_SECONDS = 30
SIMILARITY_THRESHOLD = 0.92


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Platform row sync                                                           #
# --------------------------------------------------------------------------- #
async def sync_platform_rows(session) -> None:
    """Ensure a platform row exists for every registered connector (new
    connectors appear automatically, disabled until the owner enables them)."""
    from app.core.config import settings
    from app.integrations.base.connector import ensure_connectors_loaded

    ensure_connectors_loaded()
    for slug, cls in CONNECTORS.items():
        if slug == "demo" and not settings.debug:
            continue
        existing = await session.execute(select(Platform).where(Platform.slug == slug))
        if existing.scalar_one_or_none() is None:
            caps = cls().capabilities()
            session.add(Platform(
                slug=slug, name=cls.name, base_url=cls.base_url,
                capabilities=caps.model_dump(), enabled=False,
            ))
    await session.commit()


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #
async def get_agent_config(session) -> AgentConfiguration:
    result = await session.execute(select(AgentConfiguration).limit(1))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = AgentConfiguration(
            filters={"include_keywords": [], "exclude_keywords": [], "categories": [],
                     "budget_min": None, "budget_max": None},
            pricing_strategies={"aggressive": {"factor": 0.8}, "balanced": {"factor": 1.0},
                                "premium": {"factor": 1.25}},
            model_assignments={},
        )
        session.add(cfg)
        await session.flush()
    return cfg


def _load_platform_credentials(raw_encrypted: str) -> dict:
    import json

    if not raw_encrypted:
        return {}
    try:
        return json.loads(decrypt_value(raw_encrypted))
    except ValueError:
        return {}


def _passes_filters(item, filters: dict, profile=None, skills=None) -> tuple[bool, str]:
    title_desc = normalize_text(f"{item.title} {item.description} {' '.join(item.skills or [])}").lower()
    include = [k.strip().lower() for k in (filters.get("include_keywords") or []) if k and k.strip()]
    if not include and profile and profile.preferred_technologies:
        include = [k.strip().lower() for k in profile.preferred_technologies if k and k.strip()]
    if not include and skills:
        include = [s.name.strip().lower() for s in skills if s.name and s.name.strip()]

    if include:
        item_skills_lower = [s.strip().lower() for s in (item.skills or []) if s]
        has_skill_match = any(k in item_skills_lower for k in include)
        has_text_match = any(k in title_desc for k in include)
        if not (has_skill_match or has_text_match):
            return False, "عدم تطابق با مهارت‌ها و حوزه‌های تخصصی شما"

    for k in (filters.get("exclude_keywords") or []):
        if k and normalize_text(k).lower() in title_desc:
            return False, f"کلمه کلیدی مستثنی‌شده: {k}"

    categories = [c for c in (filters.get("categories") or []) if c]
    if categories and (not item.category or not any(normalize_text(c) in normalize_text(item.category) for c in categories)):
        return False, "فیلتر دسته‌بندی"

    bmin = filters.get("budget_min")
    if bmin is None and profile and profile.min_acceptable_budget:
        bmin = profile.min_acceptable_budget
    bmax = filters.get("budget_max")

    if bmin and item.budget_max is not None and item.budget_max < float(bmin):
        return False, f"بودجه کمتر از حداقل مجاز ({item.budget_max} < {bmin})"
    if bmax and item.budget_min is not None and item.budget_min > float(bmax):
        return False, f"بودجه بیشتر از حداکثر مجاز ({item.budget_min} > {bmax})"

    return True, ""


# --------------------------------------------------------------------------- #
# Deduplication                                                               #
# --------------------------------------------------------------------------- #
async def find_duplicate(session, platform_id: int, item) -> Project | None:
    """Strong duplicate detection: external ID -> canonical URL -> content hash
    -> title similarity (reordered/reworded near-duplicates)."""
    result = await session.execute(
        select(Project).where(Project.platform_id == platform_id,
                              Project.external_id == str(item.external_id))
    )
    dup = result.scalar_one_or_none()
    if dup:
        return dup
    canon = canonicalize_url(item.url)
    result = await session.execute(
        select(Project).where(Project.canonical_url == canon)
    )
    dup = result.scalar_one_or_none()
    if dup:
        return dup
    chash = content_hash(item.title, item.description)
    result = await session.execute(
        select(Project).where(Project.content_hash == chash)
    )
    dup = result.scalar_one_or_none()
    if dup:
        return dup
    cutoff = _utcnow() - timedelta(days=14)
    rows = (await session.execute(
        select(Project.id, Project.title)
        .where(Project.platform_id == platform_id, Project.first_discovered_at >= cutoff)
        .order_by(Project.first_discovered_at.desc()).limit(500)
    )).all()
    near = _near_duplicate(item, [{"id": r[0], "title": r[1]} for r in rows])
    if near is not None:
        return await session.get(Project, near["id"])
    return None


def _near_duplicate(item, recent: list[dict]) -> dict | None:
    """Secondary check: very high title similarity against recently seen items."""
    for row in recent:
        if token_similarity(item.title, row["title"]) >= SIMILARITY_THRESHOLD:
            return row
    return None


# --------------------------------------------------------------------------- #
# Scanning                                                                    #
# --------------------------------------------------------------------------- #
async def scan_platform(slug: str, trigger: str = "scheduler") -> dict[str, Any]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        prow = (await session.execute(select(Platform).where(Platform.slug == slug))).scalar_one_or_none()
        if prow is None or not prow.enabled:
            return {"skipped": True, "reason": "platform disabled or unknown"}
        cfg = await get_agent_config(session)
        cred_row = (await session.execute(
            select(PlatformCredential).where(PlatformCredential.platform_id == prow.id)
        )).scalar_one_or_none()
        credentials = _load_platform_credentials(cred_row.encrypted_payload if cred_row else "")
        max_items = prow.max_projects_per_scan or cfg.max_projects_per_scan

    scan_log = PlatformScanLog(platform_id=prow.id, trigger=trigger)
    async with session_factory() as session:
        session.add(scan_log)
        await session.commit()
        await session.refresh(scan_log)

    counts = {"found": 0, "new": 0, "duplicates": 0, "filtered": 0}
    connector = None
    try:
        connector = get_connector(slug, credentials=credentials, config=prow.settings or {})
        items = await connector.fetch_projects(page=1, max_items=max_items)
        counts["found"] = len(items)

        async with session_factory() as session:
            prof_row = (await session.execute(
                select(DeveloperProfile).where(DeveloperProfile.is_active == True).limit(1)  # noqa: E712
            )).scalar_one_or_none()
            prof_skills = []
            if prof_row:
                prof_skills = (await session.execute(
                    select(DeveloperSkill).where(DeveloperSkill.profile_id == prof_row.id)
                )).scalars().all()

            cutoff = _utcnow() - timedelta(days=14)
            rows = (await session.execute(
                select(Project.id, Project.title)
                .where(Project.platform_id == prow.id, Project.first_discovered_at >= cutoff)
                .order_by(Project.first_discovered_at.desc()).limit(500)
            )).all()
            recent = [{"id": r[0], "title": r[1]} for r in rows]

            for item in items:
                ok, reason = _passes_filters(item, cfg.filters or {}, profile=prof_row, skills=prof_skills)
                if not ok:
                    counts["filtered"] += 1
                    continue
                dup = await find_duplicate(session, prow.id, item)
                if dup is not None:
                    counts["duplicates"] += 1
                    continue

                # Enrich new items with details when the connector supports it
                # (keeps sitemap-only platforms like ParsCoders useful).
                if not item.description and connector is not None:
                    try:
                        details = await connector.fetch_project_details(str(item.external_id), item.raw)
                        if details is not None:
                            if details.title and (not item.title or item.title.startswith("ParsCoders #")):
                                item.title = details.title
                            item.description = details.description or item.description
                            item.budget_min = item.budget_min or details.budget_min
                            item.budget_max = item.budget_max or details.budget_max
                            item.deadline = item.deadline or details.deadline
                            item.published_at = item.published_at or details.published_at
                            if details.client_info:
                                item.client_info = {**details.client_info, **item.client_info}
                            if details.skills:
                                item.skills = details.skills
                            await connector.polite_delay(0.5)
                    except ConnectorError as exc:
                        await log_execution(session, "discovery",
                                            f"detail enrichment failed for {item.external_id}: {exc}",
                                            level="warning")

                project = Project(
                    platform_id=prow.id,
                    external_id=str(item.external_id),
                    canonical_url=canonicalize_url(item.url),
                    title=item.title[:500],
                    description=item.description or "",
                    budget_min=item.budget_min, budget_max=item.budget_max,
                    currency=item.currency,
                    deadline=item.deadline,
                    client_name=item.client_name,
                    client_info=item.client_info or {},
                    category=item.category,
                    skills=item.skills or [],
                    published_at=item.published_at,
                    raw_data=item.raw or {},
                    content_hash=content_hash(item.title, item.description),
                    status=ProjectStatus.DISCOVERED.value,
                )
                project.platform_id = prow.id
                session.add(project)
                await session.flush()
                counts["new"] += 1
                recent.append({"id": project.id, "title": project.title})

                await notifications.notify_new_project(session, project, platform_name=prow.name)
                await outbox.enqueue(session, "analyze.project", {"project_id": project.id})
                await session.commit()

        async with session_factory() as session:
            prow_live = (await session.execute(select(Platform).where(Platform.id == prow.id))).scalar_one()
            log_row = (await session.execute(
                select(PlatformScanLog).where(PlatformScanLog.id == scan_log.id))).scalar_one()
            prow_live.last_scan_at = _utcnow()
            prow_live.last_success_scan_at = _utcnow()
            prow_live.connection_status = "connected"
            prow_live.last_error = None
            prow_live.last_error_at = None
            log_row.status = "success"
            log_row.finished_at = _utcnow()
            log_row.projects_found = counts["found"]
            log_row.projects_new = counts["new"]
            log_row.duplicates = counts["duplicates"]
            log_row.filtered = counts["filtered"]
            await log_execution(session, "discovery",
                                f"scan of {slug}: {counts['found']} found / {counts['new']} new / "
                                f"{counts['duplicates']} duplicates / {counts['filtered']} filtered")
            await session.commit()

    except Exception as exc:  # noqa: BLE001 - platform outages must never crash the scheduler
        async with session_factory() as session:
            prow_live = (await session.execute(select(Platform).where(Platform.id == prow.id))).scalar_one_or_none()
            log_row = (await session.execute(
                select(PlatformScanLog).where(PlatformScanLog.id == scan_log.id))).scalar_one_or_none()
            if prow_live:
                prow_live.last_scan_at = _utcnow()
                prow_live.connection_status = "error"
                prow_live.last_error = str(exc)[:1000]
                prow_live.last_error_at = _utcnow()
            if log_row:
                log_row.status = "failed"
                log_row.finished_at = _utcnow()
                log_row.error = str(exc)[:2000]
                log_row.projects_found = counts["found"]
                log_row.projects_new = counts["new"]
                log_row.duplicates = counts["duplicates"]
                log_row.filtered = counts["filtered"]
            await log_execution(session, "discovery", f"scan of {slug} failed: {exc}", level="error")
            await session.commit()
        raise
    finally:
        if connector is not None:
            await connector.aclose()
    return counts


# --------------------------------------------------------------------------- #
# Scheduler                                                                   #
# --------------------------------------------------------------------------- #
class DiscoveryScheduler:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="discovery-scheduler")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        log.info("discovery scheduler started (independent of the dashboard)")
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.error("scheduler tick failed: %s", exc)
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    async def tick(self) -> None:
        session_factory = get_session_factory()
        async with session_factory() as session:
            rows = (await session.execute(select(Platform).where(Platform.enabled == True))).scalars().all()  # noqa: E712
            cfg = await get_agent_config(session)
            default_interval = cfg.scan_interval_minutes or 20

        now = _utcnow()
        for platform in rows:
            interval = platform.scan_interval_minutes or default_interval
            last_scan = platform.last_success_scan_at
            if last_scan is not None and last_scan.tzinfo is None:
                last_scan = last_scan.replace(tzinfo=timezone.utc)
            due = (last_scan is None or
                   now >= last_scan + timedelta(minutes=interval))
            if not due:
                continue
            lock = self._locks.setdefault(platform.slug, asyncio.Lock())
            if lock.locked():
                continue
            asyncio.create_task(self._scan_locked(platform.slug, lock),
                                name=f"scan-{platform.slug}")

    async def _scan_locked(self, slug: str, lock: asyncio.Lock) -> None:
        async with lock:
            try:
                counts = await scan_platform(slug)
                log.info("scan %s: %s", slug, counts)
            except Exception as exc:  # noqa: BLE001
                log.warning("scan %s failed: %s", slug, exc)
