"""Karlancer connector (karlancer.com).

Verification status (checked against the live platform on 2026-11-04):
- Project discovery works through the website's own public search endpoint
  ``GET /api/publics/search/projects?page=N`` (no authentication, the same
  endpoint the public website calls).
- Canonical project URLs are ``https://www.karlancer.com/projects/{slug}``.
- Proposal submission requires an authenticated user panel -> assisted mode.
No login, CAPTCHA or security control is bypassed.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.integrations.base.connector import (BaseConnector, PlatformUnavailable,
                                             register)
from app.integrations.base.schemas import (AvailabilityCheck, Capabilities,
                                           NormalizedProject)
from app.services.text import strip_html

API_BASE = "https://www.karlancer.com/api/publics"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@register
class KarlancerConnector(BaseConnector):
    slug = "karlancer"
    name = "Karlancer"
    base_url = "https://www.karlancer.com"
    verified = True  # discovery verified against live API

    def capabilities(self) -> Capabilities:
        return Capabilities(
            fetch_projects=True,
            fetch_details=True,
            check_availability=True,
            submit_proposal=False,
            submit_method="assisted",
            verified=self.verified,
            notes=(
                "Discovery uses Karlancer's public website search API. "
                "Proposal submission requires an authenticated panel account, "
                "so proposals are prepared here and posted by the owner (assisted)."
            ),
        )

    # ------------------------------ discovery ------------------------------ #
    async def fetch_projects(self, page: int = 1, max_items: int = 50) -> list[NormalizedProject]:
        data = await self.get_json(f"{API_BASE}/search/projects", params={"page": max(page, 1)})
        if not isinstance(data, dict) or data.get("status") != "success":
            raise PlatformUnavailable(f"{self.name}: unexpected search response")
        rows = (data.get("data") or {}).get("data") or []
        return [self._normalize(row) for row in rows[:max_items] if isinstance(row, dict)]

    def _normalize(self, row: dict) -> NormalizedProject:
        slug = str(row.get("url") or "").strip()
        external_id = str(row.get("id"))
        duration_days = self._to_int(row.get("job_duration"))
        published = _parse_dt(row.get("ladder_at"))
        deadline = None
        if published and duration_days:
            deadline = published + timedelta(days=duration_days)
        skills = []
        for s in row.get("skills") or []:
            if isinstance(s, dict) and s.get("name"):
                skills.append(str(s["name"]))
        client_info = {
            "user_id": row.get("user_id"),
            "country": row.get("country"),
            "rate": self._to_float(row.get("rate")),
            "rate_num": self._to_int(row.get("rate_num")),
            "successful_projects_percentage": self._to_float(row.get("successful_projects_percentage")),
        }
        return NormalizedProject(
            external_id=external_id,
            title=str(row.get("title") or "").strip(),
            description=strip_html(str(row.get("description") or "")),
            url=f"{self.base_url}/projects/{slug}" if slug else f"{self.base_url}/search",
            budget_min=self._to_float(row.get("min_budget")),
            budget_max=self._to_float(row.get("max_budget")),
            currency="IRT",
            deadline=deadline,
            published_at=published,
            client_name=None,
            client_info={k: v for k, v in client_info.items() if v not in (None, "", 0)},
            skills=skills,
            raw=row,
        )

    # ------------------------------- details ------------------------------- #
    async def fetch_project_details(self, external_id: str, raw: dict | None = None) -> NormalizedProject | None:
        raw = raw or {}
        slug = str(raw.get("url") or "").strip()
        if not slug:
            return None
        data = await self.get_json(f"{API_BASE}/projects/{slug}")
        if isinstance(data, dict) and data.get("status") == "success" and isinstance(data.get("data"), dict):
            return self._normalize(data["data"])
        return None

    async def check_availability(self, external_id: str, raw: dict | None = None) -> AvailabilityCheck:
        raw = raw or {}
        expired = str(raw.get("is_expired", "")).lower() in ("true", "1")
        status = str(raw.get("status", "")).lower()
        if expired or status in ("expired", "closed", "finished"):
            return AvailabilityCheck(available=False, reason=f"status={status or 'expired'}")
        return AvailabilityCheck(available=True, reason=f"status={status or 'active'}")

    # ------------------------------- helpers ------------------------------- #
    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            cleaned = re.sub(r"[,\s]", "", str(value))
            if cleaned in ("", "None", "N/A"):
                return None
            return float(cleaned)
        except (TypeError, ValueError):
            return None
