"""Offline unit tests for text utilities, security, dedup and connector parsing."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.text import (canonicalize_url, content_hash, count_words,
                               extract_json, normalize_text, strip_html,
                               token_similarity)
from app.core.security import (decrypt_value, encrypt_value, hash_password,
                               verify_password, create_access_token,
                               decode_access_token, mask_secret)


# ------------------------------------------------------------------ text
def test_normalize_unifies_arabic_and_persian():
    assert normalize_text("کتاب‌هاي خوب") == normalize_text("کتاب‌های خوب")
    assert "۱۲" not in normalize_text("سال ۱۲")


def test_content_hash_stable_and_sensitive():
    a = content_hash("توسعه سایت فروشگاهی", "با پایتون و جنگو")
    b = content_hash("توسعه  سایت   فروشگاهی", "با پایتون و جنگو")
    c = content_hash("طراحی لوگو", "با پایتون و جنگو")
    assert a == b and a != c


def test_canonical_url_strips_utm_and_fragment():
    u = canonicalize_url("https://X.com/project/1/?utm_source=tg&utm_medium=x#top")
    assert u == "https://x.com/project/1"


def test_similarity_and_word_count():
    assert token_similarity("طراحی سایت فروشگاهی", "طراحی  سایت فروشگاهی") > 0.9
    assert token_similarity("طراحی سایت", "ترجمه مقاله") < 0.4
    assert count_words("سلام این یک متن آزمایشی است") == 6


def test_strip_html_and_extract_json():
    assert strip_html("<p>سلام</p><script>x()</script> دنیا") == "سلام دنیا"
    obj = extract_json('متن اضافه\n```json\n{"a": {"b": 1}, "c": "x{y}"}\n```')
    assert obj == {"a": {"b": 1}, "c": "x{y}"}


# ------------------------------------------------------------------ security
def test_encrypt_roundtrip_and_mask():
    secret = "bot-token-123456"
    enc = encrypt_value(secret)
    assert enc != secret and decrypt_value(enc) == secret
    assert mask_secret(secret).endswith("3456")
    assert decrypt_value("garbage") == ""


def test_password_and_token():
    h = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", h) and not verify_password("wrong", h)
    token = create_access_token("admin")
    assert decode_access_token(token)["sub"] == "admin"
    assert decode_access_token(token + "x") is None


# ------------------------------------------------------------------ connectors (offline parsing)
def test_karlancer_normalize():
    from datetime import datetime, timezone
    from app.integrations.platforms.karlancer.connector import KarlancerConnector

    row = {
        "id": 338539, "title": "تولید محتوا", "description": "<p>توضیح</p>",
        "min_budget": "1800000", "max_budget": "3,500,000", "job_duration": "3",
        "ladder_at": "2026-11-04T10:17:45.000000+03:30", "is_expired": "False",
        "status": "pending", "url": "tolid-mohtava-2m6m",
        "skills": [{"name": "تولید محتوا", "id": 1437}], "rate": "4.5", "rate_num": "10",
    }
    c = KarlancerConnector()
    p = c._normalize(row)
    assert p.external_id == "338539"
    assert p.url == "https://www.karlancer.com/projects/tolid-mohtava-2m6m"
    assert p.budget_min == 1800000 and p.budget_max == 3500000
    assert p.deadline is not None and p.deadline > p.published_at
    assert p.skills == ["تولید محتوا"]
    assert p.client_info["rate"] == 4.5


def test_ponisha_extraction():
    from app.integrations.platforms.ponisha.connector import PonishaConnector

    html = """<html><head><script id="__NEXT_DATA__" type="application/json">{
      "props": {"pageProps": {"dehydratedState": {"queries": [
        {"queryKey": ["skills"], "state": {"data": []}},
        {"queryKey": ["search", "projects", {"page": 1}], "state": {"data": {"data": [
          {"id": "763226", "title": "تدوین ویدیو", "slug": "تدوین-ویدیو",
           "description": "برای تولید ویدیو", "amount_min": 2000000, "amount_max": "5,000,000",
           "approved_at": "2026-11-04T09:00:00", "bidding_closed_at": null,
           "project_bids_count": 3, "skills": [{"title": "Editing"}]}
        ], "meta": {"pagination": {}}}}}
      ]}}}
    }</script></head><body></body></html>"""
    rows = PonishaConnector._extract_projects(html)
    assert len(rows) == 1
    p = PonishaConnector()._normalize(rows[0])
    assert p.external_id == "763226"
    assert "/project/763226/" in p.url
    assert p.budget_max == 5000000
    avail = PonishaConnector()
    import asyncio
    check = asyncio.run(avail.check_availability("1", rows[0]))
    assert check.available is True


def test_parscoders_url_and_detail_parsing():
    import asyncio
    from app.integrations.platforms.parscoders.connector import ParsCodersConnector

    c = ParsCodersConnector()
    item = c._normalize_from_url(
        "https://parscoders.com/project/622162/ترجمه-پروپوزال-119716", "2026-11-04")
    assert item.external_id == "622162"
    assert "ترجمه پروپوزال" in item.title

    html = """<html><head><title>ترجمه پروپوزال - 119716 | پارس کدرز</title>
      <meta name="description" content="ترجمه فارسی به انگلیسی برای پروپوزال">
      </head><body><div>بودجه 25,000 تومان تا 500,000 تومان</div>
      <div>مهلت برای انجام 2روز</div></body></html>"""
    detail = c._parse_detail_page(html, "622162", "https://parscoders.com/project/622162/x", {})
    assert detail.title.startswith("ترجمه پروپوزال")
    assert detail.budget_min == 25000 and detail.budget_max == 500000
    assert detail.client_info["duration_days"] == 2


def test_demo_connector():
    import asyncio
    from app.integrations.platforms.demo_connector import DemoConnector

    items = asyncio.run(DemoConnector().fetch_projects())
    assert len(items) == 5 and all(i.external_id.startswith("demo-") for i in items)


# ------------------------------------------------------------------ dedup
def _seed_db():
    import asyncio
    from app.core.db import get_session_factory, init_models
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.core.db import Base
    from app import models  # noqa

    engine = create_async_engine("sqlite+aiosqlite://")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def make():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(make())
    return engine, factory


def test_find_duplicate_all_layers():
    import asyncio
    from sqlalchemy import select
    from app.core.db import Base
    from app import models  # noqa
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.models import Platform, Project
    from app.services.discovery import find_duplicate
    from app.integrations.base.schemas import NormalizedProject

    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite://")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as s:
            s.add(Platform(slug="karlancer", name="Karlancer"))
            await s.flush()
            s.add(Project(platform_id=1, external_id="A1", canonical_url="https://x.com/projects/a",
                          title="توسعه فروشگاه آنلاین با پایتون", content_hash="h1"))
            await s.commit()
            # same external id
            item = NormalizedProject(external_id="A1", title="other", url="https://x.com/projects/b")
            assert await find_duplicate(s, 1, item) is not None
            # same canonical url
            item = NormalizedProject(external_id="A2", title="other",
                                     url="https://X.com/projects/a/?utm_source=t")
            assert await find_duplicate(s, 1, item) is not None
            # same content hash
            item = NormalizedProject(external_id="A3", title="other", url="https://x.com/projects/c")
            ch = (await s.execute(select(Project).where(Project.id == 1))).scalar_one()
            item2 = type(item)(external_id="A3", title="other", url="https://x.com/projects/c")
            # direct hash match
            from app.services.text import content_hash
            item3 = type(item)(external_id="A4", title="پایتون آنلاین با توسعه فروشگاه",
                               url="https://x.com/projects/d", description="")
            item3_hash = content_hash(ch.title, "")
            s.add(Project(platform_id=1, external_id="A9", canonical_url="https://x.com/projects/z",
                          title=ch.title, content_hash=item3_hash))
            await s.commit()
            assert await find_duplicate(s, 1, item3) is not None
        await engine.dispose()

    asyncio.run(scenario())


def test_ai_message_builders_are_cautious():
    """Prompts must forbid invented facts (Persian guardrails present)."""
    from app.ai.agents import ANALYZER_SYSTEM, PROPOSAL_SYSTEM
    assert "فرض نکن" in ANALYZER_SYSTEM or "ادعا نکن" in ANALYZER_SYSTEM
    assert "JSON" in ANALYZER_SYSTEM and "JSON" in PROPOSAL_SYSTEM
    assert "۱۰۰ تا ۱۸۰" in PROPOSAL_SYSTEM or "100 تا 180" in PROPOSAL_SYSTEM
