"""ParsCoders connector (parscoders.com).

Verification status (checked against the live platform on 2026-11-04):
- robots.txt allows public project pages and DISALLOWS /api/ -> the REST API
  is never touched. Discovery uses the public sitemap
  ``https://parscoders.com/sitemap.xml`` (project index) and the server-rendered
  listing ``https://parscoders.com/project``; details come from the public
  project page HTML ``/project/{id}/{slug}``.
- Proposal submission requires a logged-in account -> assisted mode.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

from app.integrations.base.connector import (BaseConnector, PlatformUnavailable,
                                             register)
from app.integrations.base.schemas import (AvailabilityCheck, Capabilities,
                                           NormalizedProject)
from app.services.text import strip_html

SITEMAP_URL = "https://parscoders.com/sitemap/project.xml"
LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.S)
LASTMOD_RE = re.compile(r"<lastmod>\s*(.*?)\s*</lastmod>", re.S)
PROJECT_URL_RE = re.compile(r"^/project/(\d+)/(.+)$")

CLOSED_MARKERS = ["پروژه بسته شده", "پروژه انجام شده", "پایان یافته", "برنده انتخاب شد", "متوقف شده"]


def _parse_date(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.strip()).replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


@register
class ParsCodersConnector(BaseConnector):
    slug = "parscoders"
    name = "ParsCoders"
    base_url = "https://parscoders.com"
    verified = True  # discovery verified against live sitemap + HTML

    def capabilities(self) -> Capabilities:
        return Capabilities(
            fetch_projects=True,
            fetch_details=True,
            check_availability=True,
            submit_proposal=False,
            submit_method="assisted",
            verified=self.verified,
            notes=(
                "Discovery uses the public sitemap and public project pages "
                "(robots.txt of parscoders.com disallows /api/, which is respected). "
                "Submission requires an authenticated account -> assisted workflow."
            ),
        )

    # ------------------------------ discovery ------------------------------ #
    async def fetch_projects(self, page: int = 1, max_items: int = 50) -> list[NormalizedProject]:
        xml = await self.get_text(SITEMAP_URL)
        locs = [(m.group(1), None) for m in LOC_RE.finditer(xml)]
        rows: list[tuple[str, str | None]] = []
        for loc, _ in locs:
            path = loc.split("parscoders.com", 1)[-1]
            m = PROJECT_URL_RE.match(path)
            if not m:
                continue
            lastmod = None
            lm = re.search(re.escape(loc) + r".*?<lastmod>\s*(.*?)\s*</lastmod>", xml, re.S)
            if lm:
                lastmod = lm.group(1)
            rows.append((loc, lastmod))

        def sort_key(item: tuple[str, str | None]):
            external = PROJECT_URL_RE.match(item[0].split("parscoders.com", 1)[-1])
            return int(external.group(1)) if external else 0

        rows.sort(key=sort_key, reverse=True)  # newest (highest ids) first
        start = (max(page, 1) - 1) * max_items
        out = []
        for loc, lastmod in rows[start:start + max_items]:
            out.append(self._normalize_from_url(loc, lastmod))
        return out

    def _normalize_from_url(self, url: str, lastmod: str | None) -> NormalizedProject:
        path = url.split("parscoders.com", 1)[-1]
        m = PROJECT_URL_RE.match(path)
        external_id = m.group(1) if m else path
        raw = {"url": url}
        published = _parse_date(lastmod) if lastmod else None
        if published:
            raw["lastmod"] = lastmod
        title = ""
        if m:
            slug = unquote(m.group(2))
            title = re.sub(r"[-\s]*\d{5,}\s*$", "", slug).replace("-", " ").strip()
        return NormalizedProject(
            external_id=external_id,
            title=title or f"ParsCoders #{external_id}",
            url=url,
            published_at=published,
            raw=raw,
        )

    # ------------------------------- details ------------------------------- #
    async def fetch_project_details(self, external_id: str, raw: dict | None = None) -> NormalizedProject | None:
        raw = raw or {}
        url = raw.get("url") or f"{self.base_url}/project/{external_id}"
        html = await self.get_text(url)
        return self._parse_detail_page(html, external_id, url, raw)

    def _parse_detail_page(self, html: str, external_id: str, url: str, raw: dict) -> NormalizedProject | None:
        text = strip_html(html)
        m = re.search(r"<title>(.*?)</title>", html, re.S)
        title = strip_html(m.group(1)) if m else ""
        title = re.sub(r"\s*\|\s*پارس کدرز.*$", "", title).strip()
        desc = ""
        md = re.search(r'name="description"\s+content="([^"]*)"', html)
        if md:
            desc = md.group(1)

        budget_min = budget_max = None
        mb = re.search(r"بودجه\s*([\d,]+)\s*تومان\s*تا\s*([\d,]+)\s*تومان", text)
        if mb:
            budget_min = float(mb.group(1).replace(",", ""))
            budget_max = float(mb.group(2).replace(",", ""))
        else:
            ms = re.search(r"بودجه\s*([\d,]+)\s*تومان", text)
            if ms:
                v = float(ms.group(1).replace(",", ""))
                budget_min = budget_max = v

        deadline = None
        duration_days = None
        mdur = re.search(r"مهلت برای انجام\s*([\d۰-۹]+)\s*روز", text)
        if mdur:
            digits = mdur.group(1).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
            try:
                duration_days = int(digits)
            except ValueError:
                duration_days = None
            base = raw.get("_published_hint")
            if isinstance(base, datetime):
                deadline = base + timedelta(days=duration_days)

        return NormalizedProject(
            external_id=external_id,
            title=title or f"ParsCoders #{external_id}",
            description=desc,
            url=url,
            budget_min=budget_min,
            budget_max=budget_max,
            currency="IRT",
            deadline=deadline,
            client_info={"duration_days": duration_days, "deadline_approximate": duration_days is not None},
            raw={**raw, "page_text_snippet": text[:4000]},
        )

    async def check_availability(self, external_id: str, raw: dict | None = None) -> AvailabilityCheck:
        raw = raw or {}
        url = raw.get("url") or f"{self.base_url}/project/{external_id}"
        try:
            html = await self.get_text(url)
        except PlatformUnavailable as exc:
            if "HTTP 404" in str(exc):
                return AvailabilityCheck(available=False, reason="project page not found (404)")
            raise
        text = strip_html(html)
        for marker in CLOSED_MARKERS:
            if marker in text:
                return AvailabilityCheck(available=False, reason=f"page marker: {marker}")
        return AvailabilityCheck(available=None,
                                 reason="no explicit closed marker found; verify manually before posting")
