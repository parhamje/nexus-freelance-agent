"""Demo platform connector - ONLY for local development and pipeline testing.

Registered exclusively when FREELANCE_DEBUG=true. It fabricates deterministic
sample projects so the full workflow (discovery -> analysis -> proposal ->
assisted submission) can be exercised end-to-end without touching any real
platform. It is never enabled in production.
"""
from __future__ import annotations

import time

from app.integrations.base.connector import BaseConnector, register
from app.integrations.base.schemas import (AvailabilityCheck, Capabilities,
                                           NormalizedProject)

_TITLES = [
    "توسعه داشبورد تحلیل فروش با پایتون و React",
    "طراحی ربات تلگرام مدیریت سفارش‌ها",
    "پیاده‌سازی API پرداخت و گزارش‌گیری",
    "سایت وردپرس شرکتی + سئو",
    "اپلیکیشن موبایل فروشگاهی با فلاتر",
    "مهاجرت دیتابیس MySQL به PostgreSQL",
    "اسکرپینگ و پاک‌سازی داده‌های عمومی",
    "توسعه افزونه_chrome مدیریت وظایف",
]
_SKILLS = [
    ["Python", "FastAPI", "SQL"], ["Python", "Telegram Bot"], ["Node.js", "REST API"],
    ["WordPress", "SEO"], ["Flutter", "Mobile"], ["PostgreSQL", "SQL"],
    ["Python", "Scraping"], ["JavaScript", "Chrome Extension"],
]


@register
class DemoConnector(BaseConnector):
    slug = "demo"
    name = "Demo (Testing Only)"
    base_url = "https://example.org/demo"
    verified = True

    def capabilities(self) -> Capabilities:
        return Capabilities(
            fetch_projects=True, fetch_details=True, check_availability=True,
            submit_proposal=False, submit_method="assisted", verified=True,
            notes="Synthetic projects for testing the pipeline. Never use in production.",
        )

    async def fetch_projects(self, page: int = 1, max_items: int = 50) -> list[NormalizedProject]:
        bucket = int(time.time() // 3600)  # a fresh batch every hour
        out = []
        for i in range(min(max_items, 5)):
            idx = (bucket * 7 + i + page * 100) % len(_TITLES)
            n = bucket * 100 + i
            out.append(NormalizedProject(
                external_id=f"demo-{n}",
                title=_TITLES[idx],
                description=f"پروژه نمونه شماره {n}: {_TITLES[idx]}",
                url=f"{self.base_url}/{n}",
                budget_min=15_000_000 + i * 3_000_000,
                budget_max=40_000_000 + i * 5_000_000,
                currency="IRT",
                skills=_SKILLS[idx],
                client_info={"demo": True},
                raw={"demo": True, "n": n},
            ))
        return out

    async def check_availability(self, external_id: str, raw: dict | None = None) -> AvailabilityCheck:
        return AvailabilityCheck(available=True, reason="demo project")
