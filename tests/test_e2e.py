"""End-to-end workflow test with a mock AI:
discovery -> analysis -> owner approval -> proposal generation -> quality review
-> final approval -> ASSISTED submission -> confirmation -> analytics.
The demo platform (enabled only in debug) stands in for a real platform.
"""
import asyncio
import json

import httpx


def test_full_owner_controlled_workflow():
    from conftest import fresh_db
    fresh_db()  # tests share one SQLite file; start from a clean slate
    result = asyncio.run(_run())
    assert result["analysis"]["match_score"] >= 70
    assert result["proposal"]["status"] == "ready"
    assert result["submission"]["status"] == "submitted"          # only after owner confirm
    assert result["submission"]["method"] == "assisted"
    assert result["analytics"]["proposals"]["submitted"] >= 1


async def _run() -> dict:
    from app.main import app
    from app.core.db import init_models, get_session_factory
    from app.core.seed import seed
    from app.core.security import encrypt_value
    from app.models import AIProvider, AgentConfiguration, Platform, Project, Proposal, ProposalSubmission
    from sqlalchemy import select

    await init_models()
    factory = get_session_factory()

    async with factory() as session:
        await seed(session)
        from app.services.discovery import sync_platform_rows, get_agent_config
        await sync_platform_rows(session)

        provider = AIProvider(name="mock", provider_type="openai_compatible",
                              base_url="http://mock.local/v1",
                              api_key_encrypted=encrypt_value("k"), default_model="mock-1")
        session.add(provider)
        await session.flush()
        cfg = await get_agent_config(session)
        cfg.model_assignments = {
            "analyzer": {"provider_id": provider.id, "model": "mock-1"},
            "proposal": {"provider_id": provider.id, "model": "mock-1"},
            "quality": {"provider_id": provider.id, "model": "mock-1"},
        }
        demo = (await session.execute(select(Platform).where(Platform.slug == "demo"))).scalar_one()
        demo.enabled = True
        await session.commit()

    # ---- patch the AI layer with a deterministic fake (cautious Persian outputs) ----
    import app.services.analyzer as analyzer_mod
    import app.services.proposals as proposals_mod

    async def fake_chat(provider, model, system, user, **kwargs):
        usage = {"prompt_tokens": 120, "completion_tokens": 200, "total_tokens": 320,
                 "provider_id": provider.id, "model": model}
        # NOTE: order matters - the analyzer schema also contains the substring
        # '"score"' (inside client_quality), so match_score is checked first.
        if '"match_score"' in system:
            analysis = {
            "match_score": 82, "recommendation": "BID",
            "summary": "پروژه با مهارت‌های ثبت‌شده شما هم‌پوشانی قابل توجهی دارد.",
            "reasoning": "بر اساس مهارت‌های پایتون و API در پروفایل شما.",
            "aggressive_bid": {"price": 10000000, "delivery_days": 5, "rationale": "قیمت رقابتی"},
            "balanced_bid": {"price": 12000000, "delivery_days": 7, "rationale": "تعادل قیمت و کیفیت"},
            "premium_bid": {"price": 15000000, "delivery_days": 10, "rationale": "تحویل کامل‌تر"},
            "estimated_hours": 40, "estimated_delivery_days": 7,
            "matching_skills": ["Python"], "missing_required_skills": [],
            "missing_optional_skills": ["Docker"],
            "technical_complexity": "medium", "scope_complexity": "medium",
            "technical_risks": ["عدم شفافیت کامل نیازمندی‌ها"], "scope_risks": [],
            "budget_feasibility": "high", "deadline_feasibility": "high",
            "client_quality": {"score": None, "evidence": "شواهد کافی نیست"},
            "clarification_questions": ["آیا طراحی آماده وجود دارد؟"],
        }
        if '"content"' in system:
            content = ("سلام، متن پروژه شما را با دقت خواندم. " * 20)
            return {"text": json.dumps({"content": content.strip()}), "usage": usage}
        if '"issues"' in system:  # quality reviewer (analyzer has no "issues" key)
            return {"text": json.dumps({"score": 85, "issues": [], "strengths": ["متناسب با پروژه"],
                                        "word_count_ok": True}), "usage": usage}
        return {"text": json.dumps(analysis), "usage": usage}

    analyzer_mod.chat_completion = fake_chat
    proposals_mod.chat_completion = fake_chat

    # ---- discovery scan (demo platform) ----
    from app.services.discovery import scan_platform
    from app.services.outbox import process_pending
    counts = await scan_platform("demo", trigger="manual")
    assert counts["new"] >= 3, counts
    # rescan -> all duplicates, never duplicate records
    counts2 = await scan_platform("demo", trigger="manual")
    assert counts2["new"] == 0 and counts2["duplicates"] >= 3, counts2

    await process_pending(factory)   # analyze.project -> recommended

    async with factory() as session:
        project = (await session.execute(
            select(Project).order_by(Project.id.desc()).limit(1))).scalar_one()
        project_id = project.id
        assert project.status == "recommended", project.status
        assert project.analysis is not None if hasattr(project, "analysis") else True

    # ---- API workflow with real auth ----
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/v1/auth/login",
                              json={"username": "admin", "password": "change-me-please"})
        assert r.status_code == 200, r.text
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # unauthenticated access is rejected
        r = await client.get("/api/v1/projects")
        assert r.status_code == 401

        r = await client.get("/api/v1/projects?status=recommended", headers=headers)
        assert any(i["id"] == project_id for i in r.json()["items"])

        # generate BEFORE approval must fail (owner control)
        r = await client.post(f"/api/v1/projects/{project_id}/proposals/generate",
                              json={"strategy": "balanced"}, headers=headers)
        assert r.status_code == 409

        r = await client.post(f"/api/v1/projects/{project_id}/approve", headers=headers)
        assert r.status_code == 200

        r = await client.post(f"/api/v1/projects/{project_id}/proposals/generate",
                              json={"strategy": "balanced"}, headers=headers)
        assert r.status_code == 202, r.text
        for _ in range(4):
            await process_pending(factory)

        r = await client.get("/api/v1/proposals", headers=headers)
        proposals = r.json()["items"]
        assert proposals, "no proposal generated"
        proposal_id = proposals[0]["id"]
        r = await client.get(f"/api/v1/proposals/{proposal_id}", headers=headers)
        detail = r.json()
        assert detail["status"] == "ready"
        assert detail["quality_score"] == 85
        assert detail["analysis"] is not None
        out = {"analysis": {"match_score": detail["analysis"]["match_score"]},
               "proposal": {"status": detail["status"]}}

        # ---- final approval + assisted submission ----
        r = await client.post(f"/api/v1/proposals/{proposal_id}/submit", headers=headers)
        assert r.status_code == 200, r.text
        submission = r.json()
        assert submission["method"] == "assisted"
        assert submission["status"] == "assisted_pending"
        assert submission["assisted"]["url"].startswith("http")

        # double submit blocked (duplicate-action protection)
        r = await client.post(f"/api/v1/proposals/{proposal_id}/submit", headers=headers)
        assert r.status_code == 409

        r = await client.post(f"/api/v1/submissions/{submission['id']}/confirm-assisted",
                              headers=headers)
        assert r.status_code == 200, r.text
        out["submission"] = r.json()
        assert out["submission"]["status"] == "submitted"

        async with factory() as session:
            project = (await session.execute(
                select(Project).where(Project.id == project_id))).scalar_one()
            assert project.status == "proposal_submitted"

        # ---- analytics ----
        r = await client.get("/api/v1/analytics/summary", headers=headers)
        s = r.json()
        out["analytics"] = s
        assert s["projects"]["total"] >= 3
        assert s["proposals"]["submitted"] >= 1
        assert s["ai"]["total_tokens"] > 0

        # notifications were recorded
        r = await client.get("/api/v1/notifications", headers=headers)
        assert r.json()["total"] >= 3

    from app.core import db as app_db
    await app_db.dispose_engine()
    return out
