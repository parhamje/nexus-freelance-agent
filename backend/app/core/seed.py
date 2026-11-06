"""Database seeds: admin user, agent configuration, prompts, preferences."""
from __future__ import annotations

import secrets

from sqlalchemy import select

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.security import hash_password
from app.models import (AgentConfiguration, DeveloperProfile, NotificationPreference,
                        Prompt, PromptVersion, TelegramSetting, User)
from app.telegram.bot import new_pairing_code

log = get_logger("seed")


async def seed(session) -> None:
    # Admin user
    result = await session.execute(select(User).where(User.username == settings.admin_username))
    if result.scalar_one_or_none() is None:
        session.add(User(username=settings.admin_username,
                         password_hash=hash_password(settings.admin_password)))
        log.info("seeded admin user '%s'", settings.admin_username)

    # Agent configuration singleton
    result = await session.execute(select(AgentConfiguration).limit(1))
    if result.scalar_one_or_none() is None:
        session.add(AgentConfiguration(
            scan_interval_minutes=settings.default_scan_interval_minutes,
            max_projects_per_scan=30,
            filters={"include_keywords": [], "exclude_keywords": [], "categories": [],
                     "budget_min": None, "budget_max": None},
            min_recommendation_score=70,
            quality_threshold=75,
            max_generation_attempts=2,
            pricing_strategies={"aggressive": {"factor": 0.8}, "balanced": {"factor": 1.0},
                                "premium": {"factor": 1.25}},
            model_assignments={},
        ))

    # Notification preferences singleton
    result = await session.execute(select(NotificationPreference).limit(1))
    if result.scalar_one_or_none() is None:
        session.add(NotificationPreference())

    # Telegram settings singleton with a fresh pairing code
    result = await session.execute(select(TelegramSetting).limit(1))
    tg = result.scalar_one_or_none()
    if tg is None:
        session.add(TelegramSetting(pairing_code=new_pairing_code()))

    # Prompts (analyzer / proposal / quality) with active v1
    from app.ai.agents import DEFAULT_PROMPTS
    for key, meta in DEFAULT_PROMPTS.items():
        prompt = (await session.execute(select(Prompt).where(Prompt.key == key))).scalar_one_or_none()
        if prompt is None:
            prompt = Prompt(key=key, name=meta["name"], description=meta["description"])
            session.add(prompt)
            await session.flush()
            session.add(PromptVersion(prompt_id=prompt.id, version_no=1,
                                      template=meta["template"], is_active=True))

    # Empty developer profile placeholder
    result = await session.execute(select(DeveloperProfile).limit(1))
    if result.scalar_one_or_none() is None:
        session.add(DeveloperProfile())

    await session.commit()
    log.info("seed complete")
