from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import get_settings

LOGGER = logging.getLogger("placeai.roadmap.market")
settings = get_settings()

_RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_AUTH_HTTP_STATUS = {401, 403}
_REQUEST_REJECTED_HTTP_STATUS = {400, 404, 422}
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


class _MarketSearchFailure(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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


def _models() -> list[str]:
    candidates = [
        (os.getenv("OPENAI_WEB_SEARCH_MODEL") or "").strip(),
        str(getattr(settings, "openai_model", "") or "").strip(),
        "gpt-5.6-terra",
        "gpt-5.6",
        "gpt-5.6-luna",
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


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, _MarketSearchFailure):
        return exc.code
    code = _status_code(exc)
    if code in _AUTH_HTTP_STATUS:
        return "CURRENT_MARKET_PROVIDER_AUTH"
    if code == 429:
        return "CURRENT_MARKET_PROVIDER_BUSY"
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


def search_current_market(prompt: str) -> tuple[str, list[dict[str, str]], str]:
    keys = _keys()
    if not keys:
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
        for model in _models():
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
                        text = _extract_text(payload)
                        if not text:
                            raise _MarketSearchFailure("CURRENT_MARKET_EMPTY_RESPONSE")
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
                        if _is_retryable(exc) and attempt == 0:
                            time.sleep(_retry_delay(attempt))
                            continue
                        break

                if key_rejected:
                    break
                # A format-specific 4xx can be recovered by falling back from strict
                # Structured Outputs to JSON mode on the same model. For all other
                # failures, trying the second format is harmless and bounded.
            if key_rejected:
                break

    message = "Current-market research is temporarily unavailable. Please try again shortly."
    if last_code == "CURRENT_MARKET_PROVIDER_BUSY":
        message = "Current-market research is busy right now. Please wait a moment and try again."
    elif last_code == "CURRENT_MARKET_PROVIDER_AUTH":
        message = "Current-market research is temporarily unavailable while its provider connection is restored."

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": last_code, "message": message},
    ) from last_error
