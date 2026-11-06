"""Ponisha connector (ponisha.ir).

Verification status (checked against the live platform on 2026-11-04):
- The public project search page ``https://ponisha.ir/search/projects`` is
  server-side rendered and embeds the project list as JSON inside
  ``<script id="__NEXT_DATA__">`` (React-Query dehydrated state). That public
  page content is what this connector reads - the same data any browser sees.
- Canonical project URLs are ``https://ponisha.ir/project/{id}/{slug}``.
- The separate API host (api.ponisha.ir) requires authenticated requests;
  it is NOT used. Proposal submission requires an account -> assisted mode.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.integrations.base.connector import (BaseConnector, PlatformUnavailable,
                                             register)
from app.integrations.base.schemas import (AvailabilityCheck, Capabilities,
                                           NormalizedProject)
from app.services.text import strip_html

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@register
class PonishaConnector(BaseConnector):
    slug = "ponisha"
    name = "Ponisha"
    base_url = "https://ponisha.ir"
    verified = True  # discovery verified against live SSR page

    def capabilities(self) -> Capabilities:
        return Capabilities(
            fetch_projects=True,
            fetch_details=True,
            check_availability=True,
            submit_proposal=False,
            submit_method="assisted",
            verified=self.verified,
            notes=(
                "Discovery reads the public SSR search page of ponisha.ir. "
                "Bidding requires an authenticated account, so proposals are "
                "prepared here and posted by the owner (assisted)."
            ),
        )

    # ------------------------------ discovery ------------------------------ #
    async def fetch_projects(self, page: int = 1, max_items: int = 50) -> list[NormalizedProject]:
        url = f"{self.base_url}/search/projects"
        if page and page > 1:
            url += f"?page={page}"
        html = await self.get_text(url)
        rows = self._extract_projects(html)
        if not rows:
            raise PlatformUnavailable(f"{self.name}: could not find project data in the public page")
        return [self._normalize(r) for r in rows[:max_items] if isinstance(r, dict)]

    @staticmethod
    def _extract_projects(html: str) -> list[dict]:
        match = NEXT_DATA_RE.search(html)
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
        except ValueError:
            return []
        queries = (
            data.get("props", {}).get("pageProps", {})
            .get("dehydratedState", {}).get("queries", [])
        )
        for q in queries:
            key = q.get("queryKey") or []
            if len(key) >= 2 and key[0] == "search" and key[1] == "projects":
                payload = (q.get("state") or {}).get("data") or {}
                rows = payload.get("data")
                if isinstance(rows, list):
                    return rows
        return []

    def _normalize(self, row: dict) -> NormalizedProject:
        external_id = str(row.get("id"))
        slug = str(row.get("slug") or "").strip()
        from urllib.parse import quote
        url = f"{self.base_url}/project/{external_id}/{quote(slug)}" if slug else f"{self.base_url}/search/projects"
        skills = []
        for s in row.get("skills") or []:
            if isinstance(s, dict):
                label = s.get("title") or s.get("name")
                if label:
                    skills.append(str(label))
        closed = _parse_dt(row.get("bidding_closed_at"))
        return NormalizedProject(
            external_id=external_id,
            title=str(row.get("title") or "").strip(),
            description=strip_html(str(row.get("description") or "")),
            url=url,
            budget_min=self._to_float(row.get("amount_min")),
            budget_max=self._to_float(row.get("amount_max")),
            currency="IRT",
            deadline=closed,  # bidding close time doubles as the response deadline
            published_at=_parse_dt(row.get("approved_at")) or _parse_dt(row.get("billboarded_at")),
            client_name=None,
            client_info={
                "bids_count": row.get("project_bids_count"),
            },
            skills=skills,
            raw=row,
        )

    # ------------------------------- details ------------------------------- #
    async def fetch_project_details(self, external_id: str, raw: dict | None = None) -> NormalizedProject | None:
        if not raw:
            return None
        return self._normalize(raw)

    async def check_availability(self, external_id: str, raw: dict | None = None) -> AvailabilityCheck:
        raw = raw or {}
        closed = _parse_dt(raw.get("bidding_closed_at"))
        if closed is not None:
            return AvailabilityCheck(available=False, reason=f"bidding closed at {closed.isoformat()}")
        return AvailabilityCheck(available=True, reason="bidding still open")

    # ------------------------------- helpers ------------------------------- #
    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(re.sub(r"[,\s]", "", str(value)))
        except (TypeError, ValueError):
            return None
