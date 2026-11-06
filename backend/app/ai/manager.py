"""AI provider manager: OpenAI-compatible, Anthropic and Ollama adapters.

All calls are plain HTTP (httpx) so any OpenAI-compatible endpoint (OpenAI,
Azure OpenAI gateways, OpenRouter, LM Studio, vLLM, ...) works. API keys are
decrypted only in memory and never logged or returned by the API layer.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.logging_config import get_logger
from app.core.security import decrypt_value
from app.models import AIProvider

log = get_logger("ai")

PROVIDER_TYPES = ("openai_compatible", "anthropic", "ollama")


class AIError(Exception):
    pass


def _base(provider: AIProvider) -> str:
    return (provider.base_url or "").rstrip("/")


def _headers(provider: AIProvider) -> dict[str, str]:
    api_key = decrypt_value(provider.api_key_encrypted)
    if provider.provider_type == "anthropic":
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    return {}


async def chat_completion(
    session_provider: AIProvider,
    model: str,
    system: str,
    user: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 8192,
    json_mode: bool = True,
    timeout: float = 180.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Returns {"text": str, "usage": {prompt_tokens, completion_tokens, total_tokens, provider_id}}."""
    provider = session_provider
    base = _base(provider)
    if not base:
        raise AIError(f"provider '{provider.name}' has no base URL")
    if not model:
        raise AIError(f"provider '{provider.name}' has no model configured")

    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        try:
            if provider.provider_type == "anthropic":
                resp = await client.post(
                    f"{base}/v1/messages",
                    headers=_headers(provider),
                    json={
                        "model": model,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "system": system,
                        "messages": [{"role": "user", "content": user}],
                    },
                )
            elif provider.provider_type == "ollama":
                resp = await client.post(
                    f"{base}/api/chat",
                    json={
                        "model": model,
                        "messages": [{"role": "system", "content": system},
                                     {"role": "user", "content": user}],
                        "stream": False,
                        "format": "json" if json_mode else None,
                        "options": {"temperature": temperature, "num_predict": max_tokens},
                    },
                )
            else:  # openai_compatible
                payload: dict[str, Any] = {
                    "model": model,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}
                resp = await client.post(f"{base}/chat/completions",
                                         headers=_headers(provider), json=payload)
        except httpx.HTTPError as exc:
            raise AIError(f"provider '{provider.name}' unreachable: {exc}") from exc

    if resp.status_code >= 400:
        raise AIError(f"provider '{provider.name}' HTTP {resp.status_code}: {resp.text[:400]}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise AIError(f"provider '{provider.name}' returned non-JSON response") from exc

    if provider.provider_type == "anthropic":
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
        usage_raw = data.get("usage") or {}
        usage = {
            "prompt_tokens": usage_raw.get("input_tokens", 0),
            "completion_tokens": usage_raw.get("output_tokens", 0),
        }
    elif provider.provider_type == "ollama":
        text = ((data.get("message") or {}).get("content") or "")
        usage = {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
        }
    else:
        choices = data.get("choices") or []
        if not choices:
            raise AIError(f"provider '{provider.name}' returned no choices: {str(data)[:300]}")
        message = choices[0].get("message") or {}
        text = message.get("content") or ""
        usage_raw = data.get("usage") or {}
        usage = {
            "prompt_tokens": usage_raw.get("prompt_tokens", 0),
            "completion_tokens": usage_raw.get("completion_tokens", 0),
        }
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    usage["provider_id"] = provider.id
    usage["model"] = model
    return {"text": text, "usage": usage}


async def list_models(provider: AIProvider, transport: httpx.AsyncBaseTransport | None = None) -> list[str]:
    base = _base(provider)
    async with httpx.AsyncClient(timeout=30.0, transport=transport) as client:
        try:
            if provider.provider_type == "ollama":
                resp = await client.get(f"{base}/api/tags")
            elif provider.provider_type == "anthropic":
                resp = await client.get(f"{base}/v1/models", headers=_headers(provider))
            else:
                resp = await client.get(f"{base}/models", headers=_headers(provider))
        except httpx.HTTPError as exc:
            raise AIError(f"provider '{provider.name}' unreachable: {exc}") from exc
    if resp.status_code >= 400:
        raise AIError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if provider.provider_type == "ollama":
        return [m.get("name") for m in data.get("models", []) if m.get("name")]
    items = data.get("data") or data.get("models") or []
    return [m.get("id") or m.get("name") for m in items if isinstance(m, dict) and (m.get("id") or m.get("name"))]


async def test_provider(provider: AIProvider, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    try:
        models = await list_models(provider, transport=transport)
        return {"ok": True, "message": f"OK - {len(models)} model(s) listed",
                "models": models[:50]}
    except AIError as exc:
        return {"ok": False, "message": str(exc), "models": []}
