from __future__ import annotations

import logging
import os
import time
from contextvars import ContextVar

import httpx
from fastapi import HTTPException, status

try:
    from google import genai
except Exception:
    genai = None

from app.config import get_settings

settings = get_settings()
LOGGER = logging.getLogger("placeai.ai")
_LAST_AI_MODEL: ContextVar[str] = ContextVar("placeai_last_ai_model", default="")
_LAST_AI_PROVIDER: ContextVar[str] = ContextVar("placeai_last_ai_provider", default="")
_RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_RETRYABLE_HTTP_ERRORS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)
_ALLOWED_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}


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


def _request_timeout(total_seconds: float | None = None) -> httpx.Timeout:
    configured = float(getattr(settings, "ai_request_timeout_seconds", 45) or 45)
    requested = configured if total_seconds is None else float(total_seconds)
    total = max(5.0, min(requested, 55.0))
    return httpx.Timeout(total, connect=min(5.0, total), read=total, write=min(8.0, total), pool=min(5.0, total))


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        raw = (response.headers.get("retry-after") or "").strip()
        try:
            return max(0.1, min(float(raw), 2.0))
        except (TypeError, ValueError):
            pass
    return min(0.35 * (2 ** attempt), 1.25)


def _call_openai(
    api_key: str,
    prompt: str,
    *,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
    model_override: str | None = None,
    timeout_seconds: float | None = None,
    retry_count: int = 1,
) -> str:
    model = (model_override or getattr(settings, "openai_model", "gpt-5.6-terra")).strip()
    output_limit = int(max_output_tokens or getattr(settings, "ai_max_output_tokens", 5000) or 5000)
    output_limit = max(256, min(output_limit, 8000))
    payload: dict[str, object] = {
        "model": model,
        "input": prompt,
        "max_output_tokens": output_limit,
        "store": False,
    }
    if reasoning_effort in _ALLOWED_REASONING_EFFORTS:
        payload["reasoning"] = {"effort": reasoning_effort}

    last_error: Exception | None = None
    retries = max(0, min(int(retry_count), 2))
    for attempt in range(retries + 1):
        response: httpx.Response | None = None
        try:
            response = httpx.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=_request_timeout(timeout_seconds),
            )
            if response.status_code in _RETRYABLE_HTTP_STATUS and attempt < retries:
                LOGGER.warning(
                    "AI provider transient response provider=openai status_code=%s retry=1",
                    response.status_code,
                )
                time.sleep(_retry_delay(response, attempt))
                continue
            response.raise_for_status()
            text = _extract_openai_text(response.json())
            if not text:
                raise RuntimeError("OpenAI returned an empty response")
            _LAST_AI_MODEL.set(model)
            _LAST_AI_PROVIDER.set("openai")
            return text
        except _RETRYABLE_HTTP_ERRORS as exc:
            last_error = exc
            if attempt < retries:
                LOGGER.warning("AI provider network retry provider=openai error_type=%s", type(exc).__name__)
                time.sleep(_retry_delay(response, attempt))
                continue
            raise
        except Exception as exc:
            last_error = exc
            raise
    if last_error:
        raise last_error
    raise RuntimeError("OpenAI request did not complete")


def _call_gemini(api_key: str, prompt: str, *, retry_count: int = 1) -> str:
    if genai is None:
        raise RuntimeError("Gemini SDK unavailable")
    last_error: Exception | None = None
    retries = max(0, min(int(retry_count), 2))
    for attempt in range(retries + 1):
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(model=settings.gemini_model, contents=prompt)
            text = getattr(response, "text", None)
            if not isinstance(text, str) or not text.strip():
                raise RuntimeError("Gemini returned an empty response")
            _LAST_AI_MODEL.set(settings.gemini_model)
            _LAST_AI_PROVIDER.set("gemini")
            return text.strip()
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                LOGGER.warning("AI provider retry provider=gemini error_type=%s", type(exc).__name__)
                time.sleep(0.35)
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError("Gemini request did not complete")


def _safe_failure_metadata(exc: Exception) -> tuple[str, int | None]:
    status_code = None
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        status_code = exc.response.status_code
    return type(exc).__name__, status_code


def ai_status_payload() -> dict[str, object]:
    openai_ready = bool(_openai_keys())
    gemini_ready = bool(_gemini_key())
    if openai_ready:
        return {"configured": True, "sdk_available": True, "model": getattr(settings, "openai_model", "gpt-5.6-terra")}
    if gemini_ready:
        return {"configured": True, "sdk_available": genai is not None, "model": settings.gemini_model}
    return {"configured": False, "sdk_available": True, "model": getattr(settings, "openai_model", "gpt-5.6-terra")}


def current_ai_model() -> str:
    model = _LAST_AI_MODEL.get().strip()
    return model or str(ai_status_payload()["model"])


def current_ai_provider() -> str:
    provider = _LAST_AI_PROVIDER.get().strip()
    if provider:
        return provider
    if _openai_keys():
        return "openai"
    if _gemini_key():
        return "gemini"
    return "unavailable"


def call_ai_text(
    prompt: str,
    *,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
    model_override: str | None = None,
    timeout_seconds: float | None = None,
    retry_count_per_provider: int | None = None,
) -> str:
    """OpenAI primary -> OpenAI backup -> Gemini fallback with bounded transient retries.

    Interactive callers can supply a task-specific model, timeout, and retry count so a
    temporary provider problem cannot stall a user-facing workflow for tens of seconds.
    """
    attempted = False
    for slot, api_key in enumerate(_openai_keys(), start=1):
        attempted = True
        try:
            # Preserve the original two-argument private-call contract for legacy tests/callers
            # when no task-specific controls are requested.
            no_controls = (
                reasoning_effort is None
                and max_output_tokens is None
                and model_override is None
                and timeout_seconds is None
                and retry_count_per_provider is None
            )
            if no_controls:
                result = _call_openai(api_key, prompt)
            else:
                result = _call_openai(
                    api_key,
                    prompt,
                    reasoning_effort=reasoning_effort,
                    max_output_tokens=max_output_tokens,
                    model_override=model_override,
                    timeout_seconds=timeout_seconds,
                    retry_count=1 if retry_count_per_provider is None else retry_count_per_provider,
                )
            if slot > 1:
                LOGGER.warning("AI fallback succeeded provider=openai slot=%s", slot)
            return result
        except Exception as exc:
            error_type, status_code = _safe_failure_metadata(exc)
            LOGGER.warning(
                "AI provider attempt failed provider=openai slot=%s error_type=%s status_code=%s",
                slot, error_type, status_code,
            )

    gemini_api_key = _gemini_key()
    if gemini_api_key:
        attempted = True
        try:
            if retry_count_per_provider is None:
                result = _call_gemini(gemini_api_key, prompt)
            else:
                result = _call_gemini(gemini_api_key, prompt, retry_count=retry_count_per_provider)
            LOGGER.warning("AI fallback succeeded provider=gemini")
            return result
        except Exception as exc:
            error_type, status_code = _safe_failure_metadata(exc)
            LOGGER.warning(
                "AI provider attempt failed provider=gemini error_type=%s status_code=%s",
                error_type, status_code,
            )

    detail = (
        "AI service is temporarily unavailable. Please try again in a moment."
        if attempted
        else "AI service is not configured yet. Please contact the PlaceAI administrator."
    )
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
