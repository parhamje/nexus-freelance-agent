"""Offline connector tests: normalization and capability honesty (no network)."""
import json

from app.integrations.base.connector import ensure_connectors_loaded
from app.integrations.platforms.demo_connector import DemoConnector

ensure_connectors_loaded()


def _karlancer_row():
    return {
        "id": 338539, "user_id": 1616700,
        "title": "تولید محتوای آموزشی درباره آشنایی با انواع میوه‌ها",
        "description": "<p>به تولید محتوا مسلط باشید</p>",
        "status": "pending", "job_duration": "3",
        "min_budget": "1800000", "max_budget": "3,500,000",
        "country": "تهران", "category_id": "3", "rate": "4.5", "rate_num": "12",
        "is_expired": "False", "ladder_at": "2026-11-04T10:17:45.000000+03:30",
        "url": "تولید-محتوای-آموزشی-درباره-آشنایی-انواع-میوهها-2m6m2wr3r850",
        "skills": [{"name": "تولید محتوا", "id": 1437}],
        "successful_projects_percentage": "80",
    }


def test_karlancer_normalization():
    from app.integrations.platforms.karlancer.connector import KarlancerConnector

    item = KarlancerConnector()._normalize(_karlancer_row())
    assert item.external_id == "338539"
    assert item.url.startswith("https://www.karlancer.com/projects/")
    assert item.budget_min == 1800000.0 and item.budget_max == 3500000.0
    assert item.currency == "IRT"
    assert item.deadline is not None and item.published_at is not None
    assert "تولید محتوا" in item.skills
    assert item.description == "به تولید محتوا مسلط باشید"
    assert item.client_info.get("rate") == 4.5


def test_karlancer_availability_from_raw():
    import asyncio
    from app.integrations.platforms.karlancer.connector import KarlancerConnector

    c = KarlancerConnector()
    row = _karlancer_row()
    check = asyncio.run(c.check_availability("1", row))
    assert check.available is True
    row["is_expired"] = "True"
    check = asyncio.run(c.check_availability("1", row))
    assert check.available is False


def _ponisha_html():
    project = {
        "id": "763226", "title": "تدوین ویدیوهای یوتیوب", "slug": "تدوین-ویدیو",
        "description": "ادیت ویدیو با After Effects", "priority": None,
        "billboarded_at": "2026-11-04T09:00:00", "bidding_closed_at": None,
        "project_bids_count": 3, "bidders": [], "skills": [{"title": "تدوین ویدیو"}],
        "promotions": [], "amount_min": "3000000", "amount_max": "6000000",
        "approved_at": "2026-11-04T08:30:00",
    }
    state = {"props": {"pageProps": {"dehydratedState": {"queries": [
        {"queryKey": ["skills"], "state": {"data": []}},
        {"queryKey": ["search", "projects", {"query": "", "page": 1}],
         "state": {"data": {"data": [project], "meta": {"pagination": {"total_items": 1}}}}},
    ]}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(state)}</script></html>'


def test_ponisha_extracts_and_normalizes():
    import asyncio
    from app.integrations.platforms.ponisha.connector import PonishaConnector

    c = PonishaConnector()
    rows = c._extract_projects(_ponisha_html())
    assert len(rows) == 1
    item = c._normalize(rows[0])
    assert item.external_id == "763226"
    assert item.url == "https://ponisha.ir/project/763226/%D8%AA%D8%AF%D9%88%DB%8C%D9%86-%D9%88%DB%8C%D8%AF%DB%8C%D9%88"
    assert item.budget_max == 6000000.0
    assert item.deadline is None  # bidding still open
    assert "تدوین ویدیو" in item.skills
    check = asyncio.run(c.check_availability("763226", rows[0]))
    assert check.available is True
    rows[0]["bidding_closed_at"] = "2026-11-03T00:00:00"
    check = asyncio.run(c.check_availability("763226", rows[0]))
    assert check.available is False


SITEMAP = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://parscoders.com/project/622162/ترجمه-پروپوزال-119716</loc><lastmod>2026-11-04</lastmod></url>
<url><loc>https://parscoders.com/project/622160/ساخت-بازی-119714</loc><lastmod>2026-11-04</lastmod></url>
</urlset>"""

PC_DETAIL = """
<html><head><title>ترجمه پروپوزال - 119716 | پارس کدرز</title>
<meta name="description" content="کد پروژه: 119716 ترجمه فارسی به انگلیسی برای پروپوزال"></head>
<body><div>بودجه 25,000 تومان تا 500,000 تومان</div><div>مهلت برای انجام 2روز</div></body></html>
"""


def test_parscoders_url_and_detail_parsing():
    from app.integrations.platforms.parscoders.connector import ParsCodersConnector

    c = ParsCodersConnector()
    item = c._normalize_from_url(
        "https://parscoders.com/project/622162/ترجمه-پروپوزال-119716", "2026-11-04")
    assert item.external_id == "622162"
    assert "ترجمه پروپوزال" in item.title

    detail = c._parse_detail_page(PC_DETAIL, "622162", item.url, {})
    assert "ترجمه پروپوزال" in detail.title
    assert detail.budget_min == 25000.0 and detail.budget_max == 500000.0
    assert detail.client_info["duration_days"] == 2
    assert detail.client_info["deadline_approximate"] is True


def test_capability_honesty_all_platforms_assisted():
    """No current platform may claim programmatic submission."""
    from app.integrations.platforms.karlancer.connector import KarlancerConnector
    from app.integrations.platforms.ponisha.connector import PonishaConnector
    from app.integrations.platforms.parscoders.connector import ParsCodersConnector

    for cls in (KarlancerConnector, PonishaConnector, ParsCodersConnector):
        caps = cls().capabilities()
        assert caps.submit_proposal is False, cls.slug
        assert caps.submit_method == "assisted", cls.slug
        assert caps.fetch_projects is True


def test_demo_connector_offline():
    import asyncio

    demo = DemoConnector()
    items = asyncio.run(demo.fetch_projects(page=1, max_items=10))
    assert len(items) == 5
    assert all(i.external_id.startswith("demo-") for i in items)
    check = asyncio.run(demo.check_availability(items[0].external_id, items[0].raw))
    assert check.available is True
