from __future__ import annotations

import os
from contextvars import ContextVar

import httpx
from fastapi import HTTPException, status

try:
    from google import genai
except Exception:
    genai = None

from app.config import get_settings

settings = get_settings()
_LAST_AI_MODEL: ContextVar[str] = ContextVar("placeai_last_ai_model", default="")
_LAST_AI_PROVIDER: ContextVar[str] = ContextVar("placeai_last_ai_provider", default="")


def _usable_key(value: str | None) -> str:
    key = (value or "").strip()
    if not key or key.startswith("your-") or key.lower() in {"replace-me", "changeme", "none", "null"}:
        return ""
    return key


def _openai_keys() -> list[str]:
    candidates = [
        _usable_key(os.getenv("OPENAI_API_KEY") or getattr(settings, "openai_api_key", "")),
        _usable_key(os.getenv("OPENAI_BACKUP_API_KEY") or getattr(settings, "openai_backup_api_key", "")),
    ]
    result: list[str] = []
    for key in candidates:
        if key and key not in result:
            result.append(key)
    return result


def _gemini_key() -> str:
    return _usable_key(os.getenv("GEMINI_API_KEY") or settings.gemini_api_key)


def _extract_openai_text(payload: dict) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                text = content["text"].strip()
                if text:
                    parts.append(text)
    return "\n".join(parts).strip()


def _call_openai(api_key: str, prompt: str) -> str:
    model = getattr(settings, "openai_model", "gpt-5.6-terra")
    max_output_tokens = getattr(settings, "ai_max_output_tokens", 5000)
    timeout_seconds = getattr(settings, "ai_request_timeout_seconds", 45)
    response = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    text = _extract_openai_text(response.json())
    if not text:
        raise RuntimeError("OpenAI returned an empty response")
    _LAST_AI_MODEL.set(model)
    _LAST_AI_PROVIDER.set("openai")
    return text


def _call_gemini(api_key: str, prompt: str) -> str:
    if genai is None:
        raise RuntimeError("Gemini SDK unavailable")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=settings.gemini_model, contents=prompt)
    text = getattr(response, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Gemini returned an empty response")
    _LAST_AI_MODEL.set(settings.gemini_model)
    _LAST_AI_PROVIDER.set("gemini")
    return text.strip()


def ai_status_payload() -> dict[str, object]:
    openai_ready = bool(_openai_keys())
    gemini_ready = bool(_gemini_key())
    if openai_ready:
        return {
            "configured": True,
            "sdk_available": True,
            "model": getattr(settings, "openai_model", "gpt-5.6-terra"),
        }
    if gemini_ready:
        return {
            "configured": True,
            "sdk_available": genai is not None,
            "model": settings.gemini_model,
        }
    return {
        "configured": False,
        "sdk_available": True,
        "model": getattr(settings, "openai_model", "gpt-5.6-terra"),
    }


def current_ai_model() -> str:
    model = _LAST_AI_MODEL.get().strip()
    if model:
        return model
    return str(ai_status_payload()["model"])


def current_ai_provider() -> str:
    provider = _LAST_AI_PROVIDER.get().strip()
    if provider:
        return provider
    if _openai_keys():
        return "openai"
    if _gemini_key():
        return "gemini"
    return "unavailable"


def call_ai_text(prompt: str) -> str:
    """Use OpenAI primary, then a second OpenAI key, then Gemini fallback."""
    attempted = False
    for api_key in _openai_keys():
        attempted = True
        try:
            return _call_openai(api_key, prompt)
        except Exception:
            continue

    gemini_api_key = _gemini_key()
    if gemini_api_key:
        attempted = True
        try:
            return _call_gemini(gemini_api_key, prompt)
        except Exception:
            pass

    detail = (
        "AI service is temporarily unavailable. Please try again later."
        if attempted
        else "AI service is not configured yet. Please contact the PlaceAI administrator."
    )
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
