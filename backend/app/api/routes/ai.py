"""AI providers, agent configuration and Prompt Studio routes."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import agents
from app.ai.manager import PROVIDER_TYPES, list_models, test_provider
from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.security import decrypt_value, encrypt_value, mask_secret
from app.models import AIProvider, AgentConfiguration, Prompt, PromptVersion, User
from app.services.discovery import get_agent_config

router = APIRouter(tags=["ai"], dependencies=[Depends(get_current_user)])


# ------------------------------- providers -------------------------------- #
class ProviderIn(BaseModel):
    name: str
    provider_type: str
    base_url: str
    api_key: str | None = None
    default_model: str | None = None
    models: list[str] | None = None
    is_active: bool = True
    cost_per_1k_input: float | None = None
    cost_per_1k_output: float | None = None


class FetchModelsIn(BaseModel):
    provider_type: str = "openai_compatible"
    base_url: str
    api_key: str | None = None
    existing_provider_id: int | None = None


def _serialize_provider(p: AIProvider, with_models: bool = True) -> dict:
    data = {
        "id": p.id, "name": p.name, "provider_type": p.provider_type,
        "base_url": p.base_url, "default_model": p.default_model,
        "is_active": p.is_active, "connection_status": p.connection_status,
        "api_key_masked": mask_secret(decrypt_value(p.api_key_encrypted)) if p.api_key_encrypted else "",
        "cost_per_1k_input": p.cost_per_1k_input, "cost_per_1k_output": p.cost_per_1k_output,
        "last_test_at": p.last_test_at.isoformat() if p.last_test_at else None,
        "last_test_message": p.last_test_message,
    }
    if with_models:
        data["models"] = p.models or []
    return data


async def _provider(db: AsyncSession, provider_id: int) -> AIProvider:
    p = (await db.execute(select(AIProvider).where(AIProvider.id == provider_id))).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "تأمین‌کننده یافت نشد.")
    return p


@router.get("/ai/providers")
async def list_providers(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(AIProvider).order_by(AIProvider.id))).scalars().all()
    return {"items": [_serialize_provider(p) for p in rows], "provider_types": list(PROVIDER_TYPES)}


@router.post("/ai/providers")
async def create_provider(body: ProviderIn, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    if body.provider_type not in PROVIDER_TYPES:
        raise HTTPException(400, f"نوع تأمین‌کننده باید یکی از {PROVIDER_TYPES} باشد.")
    models_list = body.models or []
    p = AIProvider(
        name=body.name.strip(), provider_type=body.provider_type,
        base_url=body.base_url.strip().rstrip("/"),
        api_key_encrypted=encrypt_value(body.api_key) if body.api_key else "",
        models=models_list,
        connection_status="connected" if models_list else "unknown",
        default_model=body.default_model, is_active=body.is_active,
        cost_per_1k_input=body.cost_per_1k_input, cost_per_1k_output=body.cost_per_1k_output,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _serialize_provider(p)


@router.put("/ai/providers/{provider_id}")
async def update_provider(provider_id: int, body: ProviderIn,
                          db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    p = await _provider(db, provider_id)
    p.name = body.name.strip()
    if body.provider_type not in PROVIDER_TYPES:
        raise HTTPException(400, f"نوع تأمین‌کننده باید یکی از {PROVIDER_TYPES} باشد.")
    p.provider_type = body.provider_type
    p.base_url = body.base_url.strip().rstrip("/")
    if body.api_key is not None and body.api_key != "":
        p.api_key_encrypted = encrypt_value(body.api_key)
    if body.models is not None:
        p.models = body.models
        if body.models:
            p.connection_status = "connected"
    p.default_model = body.default_model
    p.is_active = body.is_active
    p.cost_per_1k_input = body.cost_per_1k_input
    p.cost_per_1k_output = body.cost_per_1k_output
    await db.commit()
    return _serialize_provider(p)


@router.post("/ai/providers/fetch-models")
async def fetch_models_preview(body: FetchModelsIn, db: AsyncSession = Depends(get_db),
                               user: User = Depends(get_current_user)):
    url = body.base_url.strip().rstrip("/")
    key = body.api_key.strip() if body.api_key else ""
    if not key and body.existing_provider_id:
        p = await _provider(db, body.existing_provider_id)
        key = decrypt_value(p.api_key_encrypted) if p.api_key_encrypted else ""

    temp = AIProvider(
        name="preview",
        provider_type=body.provider_type,
        base_url=url,
        api_key_encrypted=encrypt_value(key) if key else "",
        is_active=True,
    )
    try:
        models = await list_models(temp)
        return {"ok": True, "models": models, "count": len(models)}
    except Exception as exc:
        raise HTTPException(400, f"دریافت فهرست مدل‌ها ناموفق بود: {exc}")


@router.delete("/ai/providers/{provider_id}")
async def delete_provider(provider_id: int, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    p = await _provider(db, provider_id)
    cfg = await get_agent_config(db)
    assignments = cfg.model_assignments or {}
    used = [role for role, a in assignments.items() if isinstance(a, dict) and a.get("provider_id") == provider_id]
    if used:
        raise HTTPException(409, f"این تأمین‌کننده برای نقش‌های {used} در حال استفاده است؛ ابتدا نقش را تغییر دهید.")
    await db.delete(p)
    await db.commit()
    return {"ok": True}


@router.post("/ai/providers/{provider_id}/test")
async def test(provider_id: int, db: AsyncSession = Depends(get_db),
               user: User = Depends(get_current_user)):
    p = await _provider(db, provider_id)
    result = await test_provider(p)
    p.connection_status = "connected" if result["ok"] else "error"
    p.last_test_at = datetime.now(timezone.utc)
    p.last_test_message = result["message"]
    if result["ok"] and result["models"]:
        p.models = result["models"]
        if not p.default_model:
            p.default_model = result["models"][0]
    await db.commit()
    return result


@router.post("/ai/providers/{provider_id}/refresh-models")
async def refresh_models(provider_id: int, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    p = await _provider(db, provider_id)
    try:
        models = await list_models(p)
    except Exception as exc:  # noqa: BLE001
        p.connection_status = "error"
        p.last_test_message = str(exc)
        await db.commit()
        raise HTTPException(502, f"دریافت فهرست مدل‌ها ناموفق بود: {exc}")
    p.models = models
    p.connection_status = "connected"
    await db.commit()
    return {"models": models,
            "note": "اگر مدل شما در فهرست نیست، می‌توانید شناسه مدل را دستی وارد کنید."}


# ----------------------------- agent configuration ------------------------- #
class AgentConfigIn(BaseModel):
    scan_interval_minutes: int | None = None
    max_projects_per_scan: int | None = None
    filters: dict | None = None
    min_recommendation_score: int | None = None
    quality_threshold: int | None = None
    max_generation_attempts: int | None = None
    pricing_strategies: dict | None = None
    copilot_enabled: bool | None = None


@router.get("/agent-config")
async def get_config(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    cfg = await get_agent_config(db)
    return {
        "scan_interval_minutes": cfg.scan_interval_minutes,
        "max_projects_per_scan": cfg.max_projects_per_scan,
        "filters": cfg.filters,
        "min_recommendation_score": cfg.min_recommendation_score,
        "quality_threshold": cfg.quality_threshold,
        "max_generation_attempts": cfg.max_generation_attempts,
        "pricing_strategies": cfg.pricing_strategies,
        "model_assignments": cfg.model_assignments,
        "copilot_enabled": cfg.copilot_enabled,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


@router.put("/agent-config")
async def update_config(body: AgentConfigIn, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    cfg = await get_agent_config(db)
    if body.scan_interval_minutes is not None:
        if body.scan_interval_minutes < 5:
            raise HTTPException(400, "فاصله اسکن سراسری نباید کمتر از ۵ دقیقه باشد.")
        cfg.scan_interval_minutes = body.scan_interval_minutes
    if body.max_projects_per_scan is not None:
        cfg.max_projects_per_scan = max(1, min(100, body.max_projects_per_scan))
    if body.filters is not None:
        cfg.filters = body.filters
    if body.min_recommendation_score is not None:
        cfg.min_recommendation_score = max(0, min(100, body.min_recommendation_score))
    if body.quality_threshold is not None:
        cfg.quality_threshold = max(0, min(100, body.quality_threshold))
    if body.max_generation_attempts is not None:
        cfg.max_generation_attempts = max(1, min(5, body.max_generation_attempts))
    if body.pricing_strategies is not None:
        cfg.pricing_strategies = body.pricing_strategies
    if body.copilot_enabled is not None:
        cfg.copilot_enabled = body.copilot_enabled
    await db.commit()
    return await get_config(db=db, user=user)


class AssignmentsIn(BaseModel):
    analyzer: dict | None = None
    proposal: dict | None = None
    quality: dict | None = None
    copilot: dict | None = None


@router.put("/agent-config/model-assignments")
async def set_assignments(body: AssignmentsIn, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    cfg = await get_agent_config(db)
    assignments = dict(cfg.model_assignments or {})
    for role in ("analyzer", "proposal", "quality", "copilot"):
        value = getattr(body, role)
        if value is None:
            continue
        if not value.get("provider_id"):
            assignments.pop(role, None)
            continue
        assignments[role] = {"provider_id": value.get("provider_id"), "model": value.get("model")}
    cfg.model_assignments = assignments
    await db.commit()
    return {"model_assignments": cfg.model_assignments}


# -------------------------------- prompts ---------------------------------- #
@router.get("/prompts")
async def list_prompts(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(Prompt))).scalars().all()
    all_versions = (await db.execute(
        select(PromptVersion).order_by(PromptVersion.version_no.desc())
    )).scalars().all()
    items = []
    for prompt in rows:
        versions = [v for v in all_versions if v.prompt_id == prompt.id]
        items.append({
            "key": prompt.key, "name": prompt.name, "description": prompt.description,
            "versions": [{
                "id": v.id, "version_no": v.version_no, "is_active": v.is_active,
                "template": v.template, "created_at": v.created_at.isoformat() if v.created_at else None,
            } for v in versions],
        })
    return {"items": items}


class PromptVersionIn(BaseModel):
    template: str


@router.post("/prompts/{key}/versions")
async def add_prompt_version(key: str, body: PromptVersionIn,
                             db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    prompt = (await db.execute(select(Prompt).where(Prompt.key == key))).scalar_one_or_none()
    if prompt is None:
        raise HTTPException(404, "پرامپت یافت نشد.")
    if not body.template.strip():
        raise HTTPException(400, "متن پرامپت خالی است.")
    existing = (await db.execute(
        select(PromptVersion).where(PromptVersion.prompt_id == prompt.id)
        .order_by(PromptVersion.version_no.desc())
    )).scalars().all()
    max_no = max((v.version_no for v in existing), default=0)
    for v in existing:
        v.is_active = False
    version = PromptVersion(prompt_id=prompt.id, version_no=max_no + 1,
                            template=body.template, is_active=True)
    db.add(version)
    await db.commit()
    return {"ok": True, "version_no": version.version_no}


@router.put("/prompts/{key}/activate/{version_id}")
async def activate_version(key: str, version_id: int, db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user)):
    prompt = (await db.execute(select(Prompt).where(Prompt.key == key))).scalar_one_or_none()
    if prompt is None:
        raise HTTPException(404, "پرامپت یافت نشد.")
    versions = (await db.execute(
        select(PromptVersion).where(PromptVersion.prompt_id == prompt.id)
    )).scalars().all()
    target = None
    for v in versions:
        v.is_active = (v.id == version_id)
        if v.is_active:
            target = v
    if target is None:
        raise HTTPException(404, "نسخه یافت نشد.")
    await db.commit()
    return {"ok": True, "activated": version_id}
