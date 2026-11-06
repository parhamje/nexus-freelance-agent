"""End-to-end pipeline test with a MOCK AI provider and the offline demo platform.

Validates the full, safety-critical workflow:
  discover -> analyze -> owner approval -> proposal generation -> quality review
  -> final approval -> ASSISTED submission -> owner confirmation -> analytics
and the guards that make automatic submission impossible.
"""
import asyncio
import json

from conftest import fresh_db


def _run(coro):
    return asyncio.run(coro)


ANALYSIS_JSON = json.dumps({
    "match_score": 85, "recommendation": "BID",
    "summary": "پروژه نمونه مناسب مهارت‌های ثبت‌شده به نظر می‌رسد.",
    "reasoning": "تطابق مهارت‌ها بالا و بودجه در محدوده قابل قبول است؛ ارزیابی صرفاً بر اساس اطلاعات ارائه‌شده.",
    "aggressive_bid": {"price": 16000000, "delivery_days": 5, "rationale": "قیمت رقابتی"},
    "balanced_bid": {"price": 20000000, "delivery_days": 7, "rationale": "تعادل قیمت و کیفیت"},
    "premium_bid": {"price": 28000000, "delivery_days": 10, "rationale": "کیفیت بالاتر"},
    "estimated_hours": 30, "estimated_delivery_days": 7,
    "matching_skills": ["Python", "FastAPI"],
    "missing_required_skills": [], "missing_optional_skills": ["Docker"],
    "technical_complexity": "medium", "scope_complexity": "medium",
    "technical_risks": ["عدم شفافیت کامل نیازمندی‌ها"], "scope_risks": [],
    "budget_feasibility": "high", "deadline_feasibility": "medium",
    "client_quality": {"score": None, "evidence": "شواهد کافی در اطلاعات پروژه نیست."},
    "clarification_questions": ["خروجی مورد انتظار دقیقاً چیست؟"],
}, ensure_ascii=False)

PROPOSAL_CONTENT = (
    "سلام وقت بخیر. توضیحات پروژه را با دقت خواندم و مسیر پیشنهادی من این است: ابتدا در یک جلسه کوتاه نیازمندی‌ها را دقیق می‌کنیم "
    "و فهرست ویژگی‌ها را نهایی می‌کنیم تا محدوده کار شفاف شود. سپس ساختار اصلی را پیاده‌سازی می‌کنم و پیشرفت کار را مرحله‌به‌مرحله "
    "برای شما می‌فرستم تا در مسیر درست حرکت کنیم. بر اساس مهارت‌های ثبت‌شده در پروفایل من، این پروژه در تخصص من قرار می‌گیرد و "
    "برای کیفیت خروجی برنامه تست و بازبینی در نظر گرفته‌ام. قیمت پیشنهادی بر اساس برآورد ساعت کار و پیچیدگی اعلام‌شده محاسبه شده و "
    "زمان تحویل با احتیاط تعیین شده است. اگر جزئیات بیشتری از نمونه‌های مشابه موردنظرتان هست، لطفاً بفرمایید. آیا می‌توانیم برای "
    "هم‌راستایی دقیق‌تر گفت‌وگوی کوتاهی داشته باشیم؟"
)


async def _mock_ai(provider, model, system, user, **kwargs):
    """Route by prompt fingerprint, like the real router would."""
    if '"match_score"' in system:
        text = ANALYSIS_JSON
    elif '"content"' in system:
        text = json.dumps({"content": PROPOSAL_CONTENT}, ensure_ascii=False)
    elif '"score"' in system:
        text = json.dumps({"score": 82, "issues": [], "strengths": ["متناسب با پروژه"],
                           "word_count_ok": True}, ensure_ascii=False)
    else:
        raise AssertionError("unknown prompt fingerprint")
    return {"text": text, "usage": {"prompt_tokens": 120, "completion_tokens": 300,
                                    "total_tokens": 420, "provider_id": provider.id, "model": model}}


def test_full_pipeline_with_mock_ai():
    fresh_db()

    async def flow():
        # --- bootstrap (mirrors app startup without background loops) ---
        from app.core.db import dispose_engine, get_session_factory, init_models
        from app.core.seed import seed
        from app.services.discovery import scan_platform, sync_platform_rows
        from app.services.outbox import process_pending

        import app.services.analyzer  # noqa: F401 (registers analyze handler)
        import app.services.proposals  # noqa: F401 (proposal.generate handler)
        import app.services.submissions  # noqa: F401
        import app.telegram.bot  # noqa: F401 (notify.telegram handler)

        # mock the AI inside the service modules
        import app.services.analyzer as analyzer_mod
        import app.services.proposals as proposals_mod
        analyzer_mod.chat_completion = _mock_ai
        proposals_mod.chat_completion = _mock_ai

        from httpx import ASGITransport, AsyncClient
        from app.main import app

        await init_models()
        factory = get_session_factory()
        async with factory() as session:
            await seed(session)
            await sync_platform_rows(session)

        async def drain(rounds=40):
            for _ in range(rounds):
                if await process_pending(factory) == 0:
                    break

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                # ---------------- auth ----------------
                r = await c.post("/api/v1/auth/login",
                                 json={"username": "admin", "password": "change-me-please"})
                assert r.status_code == 200, r.text
                tok = r.json()["access_token"]
                H = {"Authorization": f"Bearer {tok}"}
                r = await c.get("/api/v1/auth/me", headers=H)
                assert r.status_code == 200

                # unauthorized access rejected
                r = await c.get("/api/v1/projects")
                assert r.status_code == 401

                # ---------------- AI provider + role assignment ----------------
                r = await c.post("/api/v1/ai/providers", headers=H, json={
                    "name": "MockAI", "provider_type": "openai_compatible",
                    "base_url": "http://mock.local/v1", "api_key": "sk-test-123"})
                assert r.status_code == 200, r.text
                provider_id = r.json()["id"]
                assert r.json()["api_key_masked"].endswith("123") and "sk-test" not in r.json()["api_key_masked"]

                r = await c.put("/api/v1/agent-config/model-assignments", headers=H, json={
                    "analyzer": {"provider_id": provider_id, "model": "mock-model"},
                    "proposal": {"provider_id": provider_id, "model": "mock-model"},
                    "quality": {"provider_id": provider_id, "model": "mock-model"},
                })
                assert r.status_code == 200

                # ---------------- discovery (demo platform) ----------------
                r = await c.get("/api/v1/platforms", headers=H)
                slugs = {p["slug"]: p for p in r.json()["items"]}
                assert {"karlancer", "ponisha", "parscoders"} <= set(slugs), slugs.keys()
                caps = slugs["parscoders"]["capabilities"]
                assert caps["submit_method"] == "assisted" and caps["verified"] is True

                r = await c.put("/api/v1/platforms/demo", headers=H, json={"enabled": True})
                assert r.status_code == 200

                counts = await scan_platform("demo", trigger="manual")
                assert counts["new"] == 5 and counts["duplicates"] == 0, counts

                # scan log persisted with counters
                r = await c.get("/api/v1/platforms/demo/scan-logs", headers=H)
                log0 = r.json()["items"][0]
                assert log0["status"] == "success" and log0["projects_new"] == 5

                # ---------------- analysis via outbox ----------------
                await drain()
                r = await c.get("/api/v1/projects?limit=50", headers=H)
                projects = r.json()["items"]
                assert len(projects) == 5
                assert all(p["status"] == "recommended" for p in projects), \
                    [ (p["id"], p["status"], p.get("match_score")) for p in projects ]
                assert all(p["match_score"] == 85 for p in projects)

                # notifications created (web) and delivered to outbox (telegram noop)
                r = await c.get("/api/v1/notifications?limit=50", headers=H)
                assert r.json()["total"] >= 5
                unread0 = r.json()["unread"]

                # ---------------- guards: no proposal before approval ----------------
                pid = projects[0]["id"]
                r = await c.post(f"/api/v1/projects/{pid}/proposals/generate", headers=H,
                                 json={"strategy": "balanced"})
                assert r.status_code == 409  # project not approved yet

                # ---------------- reject flow ----------------
                pid2 = projects[1]["id"]
                r = await c.post(f"/api/v1/projects/{pid2}/reject", headers=H)
                assert r.status_code == 200
                r = await c.post(f"/api/v1/projects/{pid2}/proposals/generate", headers=H,
                                 json={"strategy": "balanced"})
                assert r.status_code == 409

                # ---------------- approve (stage 1) ----------------
                r = await c.post(f"/api/v1/projects/{pid}/approve", headers=H)
                assert r.status_code == 200 and r.json()["status"] == "approved_for_proposal"
                assert "تأیید جداگانه" in r.json()["note"]

                # ---------------- proposal generation + quality review ----------------
                r = await c.post(f"/api/v1/projects/{pid}/proposals/generate", headers=H,
                                 json={"strategy": "balanced"})
                assert r.status_code == 202
                await drain()
                r = await c.get("/api/v1/proposals", headers=H)
                assert len(r.json()["items"]) == 1
                proposal_id = r.json()["items"][0]["id"]

                r = await c.get(f"/api/v1/proposals/{proposal_id}", headers=H)
                prop = r.json()
                assert prop["status"] == "ready"
                assert prop["quality_score"] == 82
                assert prop["versions"][0]["word_count"] > 100
                assert prop["versions"][0]["price"] == 20000000
                assert prop["analysis"]["match_score"] == 85

                # max attempts guard: regenerate twice -> second must fail (cap=2)
                await drain()
                r = await c.post(f"/api/v1/proposals/{proposal_id}/regenerate", headers=H,
                                 json={"strategy": "aggressive"})
                assert r.status_code == 202
                await drain()
                r = await c.get(f"/api/v1/proposals/{proposal_id}", headers=H)
                assert len(r.json()["versions"]) == 2
                r = await c.post(f"/api/v1/proposals/{proposal_id}/regenerate", headers=H,
                                 json={"strategy": "aggressive"})
                assert r.status_code == 202
                await drain()
                r = await c.get(f"/api/v1/proposals/{proposal_id}", headers=H)
                assert len(r.json()["versions"]) == 2  # still 2 - cap enforced

                # ---------------- manual edit (no AI attempt consumed) ----------------
                r = await c.post(f"/api/v1/proposals/{proposal_id}/edit", headers=H,
                                 json={"content": PROPOSAL_CONTENT, "price": 19000000,
                                       "delivery_days": 6})
                assert r.status_code == 200
                assert r.json()["version"]["source"] == "edited"

                # ---------------- final approval + ASSISTED submission ----------------
                r = await c.post(f"/api/v1/proposals/{proposal_id}/submit", headers=H)
                assert r.status_code == 200, r.text
                sub = r.json()
                assert sub["method"] == "assisted"
                assert sub["status"] == "assisted_pending"   # NEVER fake success
                assert sub["assisted"]["proposal_text"]
                assert sub["assisted"]["url"].startswith("https://example.org/demo/")

                # duplicate submit rejected
                r = await c.post(f"/api/v1/proposals/{proposal_id}/submit", headers=H)
                assert r.status_code == 409

                # owner confirms the manual post - only NOW it is "submitted"
                r = await c.post(f"/api/v1/submissions/{sub['id']}/confirm-assisted", headers=H)
                assert r.status_code == 200 and r.json()["status"] == "submitted"

                r = await c.get(f"/api/v1/projects/{pid}", headers=H)
                assert r.json()["status"] == "proposal_submitted"

                # double confirm rejected
                r = await c.post(f"/api/v1/submissions/{sub['id']}/confirm-assisted", headers=H)
                assert r.status_code == 409

                # ---------------- outcome + analytics ----------------
                r = await c.post(f"/api/v1/submissions/{sub['id']}/outcome", headers=H,
                                 json={"outcome": "won", "note": "تماس شد"})
                assert r.status_code == 200

                r = await c.get("/api/v1/analytics/summary", headers=H)
                s = r.json()
                assert s["proposals"]["submitted"] == 1
                assert s["proposals"]["won"] == 1
                assert s["proposals"]["conversion_rate_percent"] == 100.0
                assert s["ai"]["total_tokens"] > 0
                assert s["projects"]["total"] == 5
                assert s["projects"]["rejected"] == 1

                # ---------------- dedup on second scan ----------------
                counts = await scan_platform("demo", trigger="manual")
                assert counts["new"] == 0 and counts["duplicates"] == 5, counts
                r = await c.get("/api/v1/projects?limit=50", headers=H)
                assert r.json()["total"] == 5

                # ---------------- notifications read state ----------------
                r = await c.post("/api/v1/notifications/read-all", headers=H)
                r = await c.get("/api/v1/notifications/unread-count", headers=H)
                assert r.json()["unread"] == 0

                # ---------------- prompt studio ----------------
                r = await c.get("/api/v1/prompts", headers=H)
                keys = {p["key"] for p in r.json()["items"]}
                assert {"analyzer", "proposal", "quality"} <= keys
                r = await c.post("/api/v1/prompts/analyzer/versions", headers=H,
                                 json={"template": "تحلیلگر نسخه آزمایشی \"match_score\""})
                assert r.status_code == 200
                r = await c.get("/api/v1/prompts", headers=H)
                analyzer = next(p for p in r.json()["items"] if p["key"] == "analyzer")
                assert len(analyzer["versions"]) == 2
                assert analyzer["versions"][0]["is_active"] is True

                # ---------------- developer profile ----------------
                r = await c.put("/api/v1/developer-profile", headers=H, json={
                    "full_name": "تستر", "summary": "توسعه‌دهنده بک‌اند",
                    "preferred_technologies": ["Python"]})
                assert r.status_code == 200
                r = await c.post("/api/v1/developer-profile/skills", headers=H,
                                 json={"name": "Python", "level": 5, "is_core": True})
                assert r.status_code == 200

                # ---------------- logs ----------------
                r = await c.get("/api/v1/logs?limit=20", headers=H)
                assert r.status_code == 200 and len(r.json()["items"]) > 0

                # frontend served
                r = await c.get("/")
                assert r.status_code == 200 and "Freelance Agent" in r.text
        finally:
            await dispose_engine()

    _run(flow())
