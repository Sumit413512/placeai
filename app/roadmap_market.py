from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import get_settings

LOGGER = logging.getLogger("placeai.roadmap.market")
settings = get_settings()


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
        "gpt-5.6",
        "gpt-5.5",
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
    for api_key in keys:
        for model in _models():
            try:
                response = httpx.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "input": prompt,
                        "tools": [{"type": "web_search", "search_context_size": "medium"}],
                        "tool_choice": "required",
                        "include": ["web_search_call.action.sources"],
                        "reasoning": {"effort": "low"},
                        "max_output_tokens": 6500,
                        "store": False,
                    },
                    timeout=httpx.Timeout(55.0, connect=5.0, read=55.0, write=8.0, pool=5.0),
                )
                response.raise_for_status()
                payload = response.json()
                text = _extract_text(payload)
                if not text:
                    raise RuntimeError("Current-market search returned an empty response")
                sources = _extract_sources(payload)
                if not sources:
                    raise RuntimeError("Current-market search returned no verifiable sources")
                return text, sources, model
            except Exception as exc:
                last_error = exc
                status_code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) and exc.response else None
                LOGGER.warning(
                    "Career roadmap market search failed model=%s error_type=%s status_code=%s",
                    model,
                    type(exc).__name__,
                    status_code,
                )

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "CURRENT_MARKET_SEARCH_UNAVAILABLE",
            "message": "Current-market research is temporarily unavailable. No roadmap was generated from stale assumptions.",
        },
    ) from last_error
