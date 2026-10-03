from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
from fastapi import HTTPException, status

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - production dependency is pinned, tests may isolate it.
    genai = None
    genai_types = None

from app.config import get_settings

LOGGER = logging.getLogger("placeai.roadmap.market")
settings = get_settings()

_RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_AUTH_HTTP_STATUS = {401, 403}
_REQUEST_REJECTED_HTTP_STATUS = {400, 404, 422}
_GATEWAY_ERROR_TYPES = frozenset({
    "customer_verification_required", "quota_for_entity_exceeded",
    "authentication_error", "invalid_api_key", "invalid_token",
    "permission_denied", "invalid_request_error", "rate_limit_exceeded", "other",
})
_GATEWAY_CREDENTIAL_SOURCES = frozenset({"runtime_oidc", "env_oidc", "api_key"})
_RETRYABLE_NETWORK_ERRORS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)

ROADMAP_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "market_snapshot": {
            "type": "object",
            "properties": {
                "region": {"type": "string"},
                "target_roles": {"type": "array", "items": {"type": "string"}},
                "demand_signals": {"type": "array", "items": {"type": "string"}},
                "in_demand_skills": {"type": "array", "items": {"type": "string"}},
                "tools_and_technologies": {"type": "array", "items": {"type": "string"}},
                "entry_level_expectations": {"type": "array", "items": {"type": "string"}},
                "market_notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "region",
                "target_roles",
                "demand_signals",
                "in_demand_skills",
                "tools_and_technologies",
                "entry_level_expectations",
                "market_notes",
            ],
            "additionalProperties": False,
        },
        "estimated_days": {"type": "integer", "minimum": 14, "maximum": 730},
        "weekly_hours": {"type": "integer", "minimum": 1, "maximum": 80},
        "learning_pattern": {
            "type": "object",
            "properties": {
                "recommended_style": {"type": "string"},
                "weekly_cycle": {"type": "string"},
                "daily_session": {"type": "string"},
                "revision_strategy": {"type": "string"},
            },
            "required": [
                "recommended_style",
                "weekly_cycle",
                "daily_session",
                "revision_strategy",
            ],
            "additionalProperties": False,
        },
        "phases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "phase": {"type": "integer"},
                    "name": {"type": "string"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 180},
                    "outcomes": {"type": "array", "items": {"type": "string"}},
                    "skills": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "level": {"type": "string"},
                                "why": {"type": "string"},
                            },
                            "required": ["name", "level", "why"],
                            "additionalProperties": False,
                        },
                    },
                    "projects": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "scope": {"type": "string"},
                                "deliverables": {"type": "array", "items": {"type": "string"}},
                                "portfolio_proof": {"type": "string"},
                            },
                            "required": ["title", "scope", "deliverables", "portfolio_proof"],
                            "additionalProperties": False,
                        },
                    },
                    "practice": {"type": "array", "items": {"type": "string"}},
                    "milestone": {"type": "string"},
                },
                "required": [
                    "phase",
                    "name",
                    "days",
                    "outcomes",
                    "skills",
                    "projects",
                    "practice",
                    "milestone",
                ],
                "additionalProperties": False,
            },
        },
        "advanced_next_steps": {"type": "array", "items": {"type": "string"}},
        "portfolio_plan": {"type": "array", "items": {"type": "string"}},
        "interview_preparation": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "market_snapshot",
        "estimated_days",
        "weekly_hours",
        "learning_pattern",
        "phases",
        "advanced_next_steps",
        "portfolio_plan",
        "interview_preparation",
    ],
    "additionalProperties": False,
}


def safe_gateway_diagnostics(value: Any) -> dict[str, Any]:
    """Allow only fixed operational labels, never provider bodies or credentials."""
    if not isinstance(value, dict):
        return {}
    safe: dict[str, Any] = {}
    http_status = value.get("gateway_http_status")
    if type(http_status) is int and 100 <= http_status <= 599:
        safe["gateway_http_status"] = http_status
    error_type = value.get("gateway_error_type")
    if isinstance(error_type, str) and error_type in _GATEWAY_ERROR_TYPES:
        safe["gateway_error_type"] = error_type
    source = value.get("gateway_credential_source")
    if isinstance(source, str) and source in _GATEWAY_CREDENTIAL_SOURCES:
        safe["gateway_credential_source"] = source
    return safe


class _MarketSearchFailure(RuntimeError):
    def __init__(self, code: str, *, diagnostics: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.diagnostics = safe_gateway_diagnostics(diagnostics)


def _usable_key(value: str | None) -> str:
    key = (value or "").strip()
    if not key or key.startswith("your-") or key.lower() in {"replace-me", "changeme", "none", "null"}:
        return ""
    return key


def _keys() -> list[str]:
    candidates = [
        _usable_key(os.getenv("OPENAI_API_KEY") or getattr(settings, "openai_api_key", "")),
        _usable_key(os.getenv("OPENAI_BACKUP_API_KEY") or getattr(settings, "openai_backup_api_key", "")),
    ]
    return list(dict.fromkeys(key for key in candidates if key))


def _gemini_key() -> str:
    return _usable_key(os.getenv("GEMINI_API_KEY") or getattr(settings, "gemini_api_key", ""))


def _gateway_token(runtime_token: str | None = None) -> str:
    # Vercel Functions receive a fresh request-scoped OIDC token. Prefer it
    # over build-time or static credentials so stale keys cannot poison auth.
    return _usable_key(
        runtime_token
        or os.getenv("VERCEL_OIDC_TOKEN")
        or os.getenv("AI_GATEWAY_API_KEY")
    )


def _gateway_models() -> list[str]:
    candidates = [
        (os.getenv("VERCEL_AI_GATEWAY_ROADMAP_MODEL") or "").strip(),
        "xai/grok-4.5",
        "xai/grok-4.3",
    ]
    return list(dict.fromkeys(model for model in candidates if model))


def _gemini_models() -> list[str]:
    candidates = [
        (os.getenv("GEMINI_WEB_SEARCH_MODEL") or "").strip(),
        str(getattr(settings, "gemini_model", "") or "").strip(),
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.5-flash",
    ]
    return list(dict.fromkeys(model for model in candidates if model))


def _models() -> list[str]:
    candidates = [
        (os.getenv("OPENAI_WEB_SEARCH_MODEL") or "").strip(),
        str(getattr(settings, "openai_model", "") or "").strip(),
        "gpt-6.1-sol",
        "gpt-6-luna",
        "gpt-5.6-terra",
        "gpt-5.5",
        "gpt-5.4-mini",
        "gpt-5.4",
    ]
    return list(dict.fromkeys(model for model in candidates if model))


def _extract_text(payload: dict[str, Any]) -> str:
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
                value = content["text"].strip()
                if value:
                    parts.append(value)
    return "\n".join(parts).strip()


def _clean_source(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    url = str(value.get("url") or "").strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        return None
    title = str(value.get("title") or value.get("name") or "").strip()[:300]
    return {"title": title or url, "url": url[:2000]}


def _extract_sources(payload: dict[str, Any]) -> list[dict[str, str]]:
    candidates: list[Any] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        action = item.get("action")
        if isinstance(action, dict):
            candidates.extend(action.get("sources") or [])
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            candidates.extend(content.get("annotations") or [])
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        source = _clean_source(candidate)
        if source is None and isinstance(candidate, dict):
            nested = candidate.get("url_citation")
            source = _clean_source(nested)
        if source is None or source["url"] in seen:
            continue
        seen.add(source["url"])
        output.append(source)
        if len(output) >= 20:
            break
    return output


def _status_code(exc: Exception) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return exc.response.status_code
    return None


def _openai_rate_limit_code(exc: Exception) -> str:
    if not isinstance(exc, httpx.HTTPStatusError) or exc.response is None:
        return "CURRENT_MARKET_PROVIDER_BUSY"
    try:
        payload = exc.response.json()
    except Exception:
        return "CURRENT_MARKET_PROVIDER_BUSY"
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return "CURRENT_MARKET_PROVIDER_BUSY"
    signature = " ".join(str(error.get(key) or "") for key in ("code", "type")).lower()
    if any(token in signature for token in ("insufficient_quota", "quota", "billing", "usage_limit")):
        return "CURRENT_MARKET_PROVIDER_QUOTA"
    return "CURRENT_MARKET_PROVIDER_BUSY"


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, _MarketSearchFailure):
        return exc.code
    code = _status_code(exc)
    if code in _AUTH_HTTP_STATUS:
        return "CURRENT_MARKET_PROVIDER_AUTH"
    if code == 429:
        return _openai_rate_limit_code(exc)
    if code in _REQUEST_REJECTED_HTTP_STATUS:
        return "CURRENT_MARKET_PROVIDER_REJECTED"
    if isinstance(exc, httpx.TimeoutException):
        return "CURRENT_MARKET_PROVIDER_TIMEOUT"
    if isinstance(exc, _RETRYABLE_NETWORK_ERRORS):
        return "CURRENT_MARKET_PROVIDER_NETWORK"
    return "CURRENT_MARKET_SEARCH_UNAVAILABLE"


def _is_retryable(exc: Exception) -> bool:
    code = _status_code(exc)
    return code in _RETRYABLE_HTTP_STATUS or isinstance(exc, _RETRYABLE_NETWORK_ERRORS)


def _retry_delay(attempt: int) -> float:
    return min(0.25 * (2 ** attempt), 0.75)


def _request_payload(prompt: str, model: str, *, structured: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "input": prompt,
        "tools": [{"type": "web_search", "search_context_size": "medium"}],
        "tool_choice": "required",
        "include": ["web_search_call.action.sources"],
        "max_output_tokens": 6500,
        "store": False,
    }
    payload["text"] = {
        "format": {
            "type": "json_schema",
            "name": "placeai_career_roadmap",
            "strict": True,
            "schema": ROADMAP_OUTPUT_SCHEMA,
        }
    } if structured else {"format": {"type": "json_object"}}
    return payload


def _object_value(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _extract_gemini_sources(response: Any) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in _object_value(response, "candidates") or []:
        metadata = _object_value(candidate, "grounding_metadata")
        for chunk in _object_value(metadata, "grounding_chunks") or []:
            web = _object_value(chunk, "web")
            if web is None:
                continue
            source = _clean_source({
                "title": _object_value(web, "title"),
                "url": _object_value(web, "uri"),
            })
            if source is None or source["url"] in seen:
                continue
            seen.add(source["url"])
            output.append(source)
            if len(output) >= 20:
                return output
    return output


def _gemini_status_code(exc: Exception) -> int | None:
    for name in ("status_code", "code"):
        value = getattr(exc, name, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _gemini_failure_code(exc: Exception) -> str:
    if isinstance(exc, _MarketSearchFailure):
        return exc.code
    code = _gemini_status_code(exc)
    if code in _AUTH_HTTP_STATUS:
        return "CURRENT_MARKET_FALLBACK_AUTH"
    if code == 429:
        signature = str(exc).lower()
        if any(token in signature for token in ("quota", "resource_exhausted", "billing", "usage limit")):
            return "CURRENT_MARKET_FALLBACK_QUOTA"
        return "CURRENT_MARKET_FALLBACK_BUSY"
    if code in _REQUEST_REJECTED_HTTP_STATUS:
        return "CURRENT_MARKET_FALLBACK_REJECTED"
    if isinstance(exc, _RETRYABLE_NETWORK_ERRORS):
        return "CURRENT_MARKET_FALLBACK_NETWORK"
    return "CURRENT_MARKET_FALLBACK_UNAVAILABLE"


def _search_current_market_gemini(prompt: str) -> tuple[str, list[dict[str, str]], str]:
    """Run grounded research first, then structure it in a separate call.

    Grounding metadata is most reliable when search is not simultaneously
    constrained by a strict JSON schema. Separating the stages preserves
    verifiable sources and prevents successful live research being discarded.
    """
    api_key = _gemini_key()
    if not api_key or genai is None or genai_types is None:
        raise _MarketSearchFailure("CURRENT_MARKET_FALLBACK_UNAVAILABLE")

    last_error: Exception | None = None
    for model in _gemini_models():
        try:
            timeout_ms = int(
                max(5.0, min(float(getattr(settings, "ai_request_timeout_seconds", 45) or 45), 55.0)) * 1000
            )
            client = genai.Client(
                api_key=api_key,
                http_options={"timeout": timeout_ms, "retry_options": {"attempts": 1}},
            )

            research_response = client.models.generate_content(
                model=model,
                contents=(
                    prompt
                    + "\n\nRESEARCH STAGE ONLY: Use Google Search now. "
                    "Return a concise evidence memo covering current demand, required skills, "
                    "tools/technologies, entry-level expectations and market caveats. "
                    "Do not return the final JSON roadmap yet."
                ),
                config=genai_types.GenerateContentConfig(
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                ),
            )
            research_text = str(getattr(research_response, "text", "") or "").strip()
            if not research_text:
                raise _MarketSearchFailure("CURRENT_MARKET_EMPTY_RESPONSE")
            sources = _extract_gemini_sources(research_response)
            if not sources:
                raise _MarketSearchFailure("CURRENT_MARKET_SOURCES_MISSING")

            structured_response = client.models.generate_content(
                model=model,
                contents=(
                    "The live-market research has already been completed in a separate grounded-search stage. "
                    "Do not perform another web search. Use ONLY the grounded evidence below for current-market claims. "
                    "Follow the planning brief and return the requested Career Roadmap JSON.\n\n"
                    f"PLANNING BRIEF:\n{prompt}\n\n"
                    f"GROUNDED LIVE-MARKET EVIDENCE:\n{research_text}"
                ),
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=ROADMAP_OUTPUT_SCHEMA,
                ),
            )
            text = str(getattr(structured_response, "text", "") or "").strip()
            if not text:
                raise _MarketSearchFailure("CURRENT_MARKET_EMPTY_RESPONSE")
            try:
                parsed = json.loads(text)
            except (TypeError, json.JSONDecodeError) as exc:
                raise _MarketSearchFailure("CURRENT_MARKET_RESPONSE_INVALID") from exc
            if not isinstance(parsed, dict):
                raise _MarketSearchFailure("CURRENT_MARKET_RESPONSE_INVALID")

            LOGGER.warning(
                "Career roadmap market search recovered with two-stage grounded fallback "
                "provider=gemini model=%s source_count=%s",
                model,
                len(sources),
            )
            return text, sources, model
        except Exception as exc:
            last_error = exc
            safe_code = _gemini_failure_code(exc)
            LOGGER.warning(
                "Career roadmap two-stage grounded fallback failed provider=gemini model=%s "
                "error_code=%s error_type=%s status_code=%s",
                model,
                safe_code,
                type(exc).__name__,
                _gemini_status_code(exc),
            )
            continue

    if last_error is not None:
        raise _MarketSearchFailure(_gemini_failure_code(last_error)) from last_error
    raise _MarketSearchFailure("CURRENT_MARKET_FALLBACK_UNAVAILABLE")

def _gateway_error_type(exc: Exception) -> str:
    if not isinstance(exc, httpx.HTTPStatusError) or exc.response is None:
        return "other"
    try:
        payload = exc.response.json()
    except (ValueError, UnicodeError):
        return "other"
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        for specific in ("customer_verification_required", "quota_for_entity_exceeded"):
            if any(error.get(name) == specific for name in ("type", "code")):
                return specific
        for name in ("type", "code"):
            value = error.get(name)
            if isinstance(value, str) and value in _GATEWAY_ERROR_TYPES:
                return value
    return "other"


def _gateway_failure_code(exc: Exception) -> str:
    if isinstance(exc, _MarketSearchFailure):
        return exc.code
    code = _status_code(exc)
    if code == 401:
        return "CURRENT_MARKET_GATEWAY_AUTH"
    if code == 403:
        if _gateway_error_type(exc) == "customer_verification_required":
            return "CURRENT_MARKET_GATEWAY_VERIFICATION_REQUIRED"
        return "CURRENT_MARKET_GATEWAY_ACCESS_DENIED"
    if code == 402:
        return "CURRENT_MARKET_GATEWAY_BUDGET"
    if code == 429:
        return "CURRENT_MARKET_GATEWAY_BUSY"
    if code in _REQUEST_REJECTED_HTTP_STATUS:
        return "CURRENT_MARKET_GATEWAY_REJECTED"
    if isinstance(exc, httpx.TimeoutException):
        return "CURRENT_MARKET_GATEWAY_TIMEOUT"
    if isinstance(exc, _RETRYABLE_NETWORK_ERRORS):
        return "CURRENT_MARKET_GATEWAY_NETWORK"
    return "CURRENT_MARKET_GATEWAY_UNAVAILABLE"


def _gateway_request_payload(prompt: str, model: str) -> dict[str, Any]:
    return {
        "model": model,
        "input": prompt,
        "tools": [{"type": "web_search"}],
        "tool_choice": "required",
        "include": ["web_search_call.action.sources"],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "placeai_career_roadmap",
                "strict": True,
                "schema": ROADMAP_OUTPUT_SCHEMA,
            }
        },
        "max_output_tokens": 6500,
        "store": False,
    }


def _gateway_auth(runtime_token: str | None = None) -> tuple[str, str]:
    runtime_oidc = _usable_key(runtime_token)
    if runtime_oidc:
        return runtime_oidc, "oidc"
    build_oidc = _usable_key(os.getenv("VERCEL_OIDC_TOKEN"))
    if build_oidc:
        return build_oidc, "oidc"
    api_key = _usable_key(os.getenv("AI_GATEWAY_API_KEY"))
    if api_key:
        return api_key, "api-key"
    return "", ""


def _search_current_market_gateway(
    prompt: str,
    *,
    gateway_token: str | None = None,
) -> tuple[str, list[dict[str, str]], str]:
    token, auth_method = _gateway_auth(gateway_token)
    if not token:
        raise _MarketSearchFailure("CURRENT_MARKET_GATEWAY_UNAVAILABLE")
    credential_source = (
        "runtime_oidc" if _usable_key(gateway_token)
        else "env_oidc" if _usable_key(os.getenv("VERCEL_OIDC_TOKEN"))
        else "api_key"
    )

    last_error: Exception | None = None
    for model in _gateway_models():
        try:
            response = httpx.post(
                "https://ai-gateway.vercel.sh/v1/responses",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "ai-gateway-auth-method": auth_method,
                },
                json=_gateway_request_payload(prompt, model),
                timeout=httpx.Timeout(55.0, connect=5.0, read=55.0, write=8.0, pool=5.0),
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") == "incomplete":
                raise _MarketSearchFailure("CURRENT_MARKET_RESPONSE_INCOMPLETE")
            text = _extract_text(payload)
            if not text:
                raise _MarketSearchFailure("CURRENT_MARKET_EMPTY_RESPONSE")
            try:
                parsed = json.loads(text)
            except (TypeError, json.JSONDecodeError) as exc:
                raise _MarketSearchFailure("CURRENT_MARKET_RESPONSE_INVALID") from exc
            if not isinstance(parsed, dict):
                raise _MarketSearchFailure("CURRENT_MARKET_RESPONSE_INVALID")
            sources = _extract_sources(payload)
            if not sources:
                raise _MarketSearchFailure("CURRENT_MARKET_SOURCES_MISSING")
            LOGGER.warning(
                "Career roadmap market search recovered provider=vercel_ai_gateway model=%s source_count=%s",
                model,
                len(sources),
            )
            return text, sources, f"gateway:{model}"
        except Exception as exc:
            last_error = exc
            code = _gateway_failure_code(exc)
            LOGGER.warning(
                "Career roadmap AI Gateway fallback failed model=%s error_code=%s error_type=%s "
                "status_code=%s gateway_error_type=%s credential_source=%s",
                model,
                code,
                type(exc).__name__,
                _status_code(exc),
                _gateway_error_type(exc),
                credential_source,
            )
            if _status_code(exc) in _AUTH_HTTP_STATUS or _status_code(exc) == 402:
                break
            continue

    if last_error is not None:
        raise _MarketSearchFailure(
            _gateway_failure_code(last_error),
            diagnostics={
                "gateway_http_status": _status_code(last_error),
                "gateway_error_type": _gateway_error_type(last_error),
                "gateway_credential_source": credential_source,
            },
        ) from last_error
    raise _MarketSearchFailure("CURRENT_MARKET_GATEWAY_UNAVAILABLE")


def search_current_market(
    prompt: str,
    *,
    gateway_token: str | None = None,
) -> tuple[str, list[dict[str, str]], str]:
    keys = _keys()
    gemini_available = bool(_gemini_key() and genai is not None and genai_types is not None)
    gateway_available = bool(_gateway_auth(gateway_token)[0])
    if not keys and not gemini_available and not gateway_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CURRENT_MARKET_SEARCH_UNAVAILABLE",
                "message": "Current-market web research is not configured for Career Roadmap.",
            },
        )

    last_error: Exception | None = None
    last_code = "CURRENT_MARKET_SEARCH_UNAVAILABLE"

    for key_slot, api_key in enumerate(keys, start=1):
        key_rejected = False
        provider_unstable = False
        for model in _models():
            model_limited = False
            for structured in (True, False):
                for attempt in range(2):
                    try:
                        response = httpx.post(
                            "https://api.openai.com/v1/responses",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                            },
                            json=_request_payload(prompt, model, structured=structured),
                            timeout=httpx.Timeout(55.0, connect=5.0, read=55.0, write=8.0, pool=5.0),
                        )
                        response.raise_for_status()
                        payload = response.json()
                        if payload.get("status") == "incomplete":
                            raise _MarketSearchFailure("CURRENT_MARKET_RESPONSE_INCOMPLETE")
                        text = _extract_text(payload)
                        if not text:
                            raise _MarketSearchFailure("CURRENT_MARKET_EMPTY_RESPONSE")
                        try:
                            parsed = json.loads(text)
                        except (TypeError, json.JSONDecodeError) as exc:
                            raise _MarketSearchFailure("CURRENT_MARKET_RESPONSE_INVALID") from exc
                        if not isinstance(parsed, dict):
                            raise _MarketSearchFailure("CURRENT_MARKET_RESPONSE_INVALID")
                        sources = _extract_sources(payload)
                        if not sources:
                            raise _MarketSearchFailure("CURRENT_MARKET_SOURCES_MISSING")
                        if not structured:
                            LOGGER.warning(
                                "Career roadmap market search recovered with JSON mode model=%s key_slot=%s",
                                model,
                                key_slot,
                            )
                        return text, sources, model
                    except Exception as exc:
                        last_error = exc
                        last_code = _failure_code(exc)
                        http_status = _status_code(exc)
                        LOGGER.warning(
                            "Career roadmap market search attempt failed model=%s key_slot=%s "
                            "format=%s attempt=%s error_code=%s error_type=%s status_code=%s",
                            model,
                            key_slot,
                            "json_schema" if structured else "json_object",
                            attempt + 1,
                            last_code,
                            type(exc).__name__,
                            http_status,
                        )

                        if http_status in _AUTH_HTTP_STATUS:
                            key_rejected = True
                            break
                        if isinstance(exc, _RETRYABLE_NETWORK_ERRORS):
                            provider_unstable = True
                            break
                        if http_status == 429:
                            if attempt == 0 and last_code == "CURRENT_MARKET_PROVIDER_BUSY":
                                time.sleep(_retry_delay(attempt))
                                continue
                            model_limited = True
                            break
                        if http_status in _RETRYABLE_HTTP_STATUS:
                            if attempt == 0:
                                time.sleep(_retry_delay(attempt))
                                continue
                            provider_unstable = True
                            break
                        break

                if key_rejected or provider_unstable or model_limited:
                    break
                # Compatibility/content failures may recover by falling back from
                # strict Structured Outputs to JSON mode on the same model.
            if key_rejected or provider_unstable:
                break
            if model_limited:
                continue

    primary_code = last_code
    fallback_code: str | None = None
    if gemini_available:
        try:
            return _search_current_market_gemini(prompt)
        except Exception as exc:
            last_error = exc
            if isinstance(exc, _MarketSearchFailure):
                fallback_code = exc.code
                last_code = exc.code
            else:
                fallback_code = _gemini_failure_code(exc)
                last_code = fallback_code

    gateway_code: str | None = None
    gateway_diagnostics: dict[str, Any] = {}
    if gateway_available:
        try:
            return _search_current_market_gateway(prompt, gateway_token=gateway_token)
        except Exception as exc:
            last_error = exc
            if isinstance(exc, _MarketSearchFailure):
                gateway_code = exc.code
                last_code = exc.code
                gateway_diagnostics = safe_gateway_diagnostics(exc.diagnostics)
            else:
                gateway_code = _gateway_failure_code(exc)
                last_code = gateway_code

    message = "Current-market research is temporarily unavailable. Please try again shortly."
    if last_code in {
        "CURRENT_MARKET_PROVIDER_BUSY",
        "CURRENT_MARKET_PROVIDER_QUOTA",
        "CURRENT_MARKET_FALLBACK_BUSY",
        "CURRENT_MARKET_FALLBACK_QUOTA",
        "CURRENT_MARKET_GATEWAY_BUSY",
        "CURRENT_MARKET_GATEWAY_BUDGET",
    }:
        message = "Current-market research providers are temporarily at capacity. Please try again shortly."
    elif last_code in {"CURRENT_MARKET_PROVIDER_AUTH", "CURRENT_MARKET_GATEWAY_AUTH"}:
        message = "Current-market research is temporarily unavailable while its provider connection is restored."

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": last_code,
            "message": message,
            "diagnostics": {
                "primary_code": primary_code,
                "fallback_code": fallback_code,
                "gateway_code": gateway_code,
                **gateway_diagnostics,
            },
        },
    ) from last_error
