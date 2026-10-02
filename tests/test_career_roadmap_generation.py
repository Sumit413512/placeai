from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app import roadmap_market
from app.roadmap_market import _extract_sources
from app.roadmap_service import normalize_roadmap_payload


def test_normalize_roadmap_uses_phase_duration_as_canonical_total():
    request = {
        "target_roles": ["Data Engineer"],
        "target_fields": ["Data"],
        "market_region": "India",
        "hours_per_week": 12,
        "desired_timeline_days": 60,
    }
    payload = {
        "title": "Data Engineer Roadmap",
        "estimated_days": 999,
        "market_snapshot": {
            "region": "India",
            "target_roles": ["Data Engineer"],
            "in_demand_skills": ["SQL", "Python"],
        },
        "weekly_hours": 12,
        "learning_pattern": {"weekly_cycle": "Learn, build, review"},
        "phases": [
            {"phase": 1, "name": "Foundations", "days": 30, "skills": ["SQL"]},
            {"phase": 2, "name": "Build", "days": 45, "skills": [{"name": "Python", "level": "working"}]},
        ],
    }
    result = normalize_roadmap_payload(payload, request_data=request)
    assert result["estimated_days"] == 75
    assert result["market_snapshot"]["in_demand_skills"] == ["SQL", "Python"]
    assert len(result["phases"]) == 2


def test_web_search_source_extraction_deduplicates_and_rejects_unsafe_urls():
    payload = {
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "sources": [
                        {"title": "Employer careers", "url": "https://example.com/jobs"},
                        {"title": "Employer careers duplicate", "url": "https://example.com/jobs"},
                        {"title": "Unsafe", "url": "javascript:alert(1)"},
                    ]
                },
            },
            {
                "type": "message",
                "content": [{
                    "type": "output_text",
                    "text": "{}",
                    "annotations": [{"type": "url_citation", "title": "Report", "url": "https://example.org/report"}],
                }],
            },
        ]
    }
    sources = _extract_sources(payload)
    assert sources == [
        {"title": "Employer careers", "url": "https://example.com/jobs"},
        {"title": "Report", "url": "https://example.org/report"},
    ]



def _market_payload(text: str, *, with_sources: bool = True) -> dict:
    output = []
    if with_sources:
        output.append({
            "type": "web_search_call",
            "action": {"sources": [{"title": "Market source", "url": "https://example.com/market"}]},
        })
    output.append({
        "type": "message",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    })
    return {"output_text": text, "output": output}


def _response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )


def test_market_search_uses_web_search_and_strict_structured_output(monkeypatch):
    seen = []

    monkeypatch.setattr(roadmap_market, "_keys", lambda: ["test-key"])
    monkeypatch.setattr(roadmap_market, "_models", lambda: ["gpt-5.6-terra"])

    def fake_post(*args, **kwargs):
        seen.append(kwargs["json"])
        return _response(200, _market_payload(json.dumps({"phases": []})))

    monkeypatch.setattr(roadmap_market.httpx, "post", fake_post)
    text, sources, model = roadmap_market.search_current_market("research")

    assert json.loads(text) == {"phases": []}
    assert sources == [{"title": "Market source", "url": "https://example.com/market"}]
    assert model == "gpt-5.6-terra"
    assert seen[0]["tools"] == [{"type": "web_search", "search_context_size": "medium"}]
    assert seen[0]["tool_choice"] == "required"
    assert seen[0]["include"] == ["web_search_call.action.sources"]
    assert seen[0]["text"]["format"]["type"] == "json_schema"
    assert seen[0]["text"]["format"]["strict"] is True
    assert seen[0]["text"]["format"]["schema"]["additionalProperties"] is False


def test_market_search_falls_back_to_json_mode_on_non_retryable_format_rejection(monkeypatch):
    calls = []
    monkeypatch.setattr(roadmap_market, "_keys", lambda: ["test-key"])
    monkeypatch.setattr(roadmap_market, "_models", lambda: ["gpt-5.6-terra"])

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            return _response(400, {"error": {"message": "request rejected"}})
        return _response(200, _market_payload(json.dumps({"phases": []})))

    monkeypatch.setattr(roadmap_market.httpx, "post", fake_post)
    roadmap_market.search_current_market("research")

    assert len(calls) == 2
    assert calls[0]["text"]["format"]["type"] == "json_schema"
    assert calls[1]["text"]["format"]["type"] == "json_object"


def test_market_search_retries_transient_provider_failure_once(monkeypatch):
    calls = []
    monkeypatch.setattr(roadmap_market, "_keys", lambda: ["test-key"])
    monkeypatch.setattr(roadmap_market, "_models", lambda: ["gpt-5.6-terra"])
    monkeypatch.setattr(roadmap_market.time, "sleep", lambda *_: None)

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            return _response(429, {"error": {"message": "busy"}})
        return _response(200, _market_payload(json.dumps({"phases": []})))

    monkeypatch.setattr(roadmap_market.httpx, "post", fake_post)
    roadmap_market.search_current_market("research")

    assert len(calls) == 2
    assert all(call["text"]["format"]["type"] == "json_schema" for call in calls)


def test_market_search_classifies_provider_auth_failure_without_leaking_response(monkeypatch):
    monkeypatch.setattr(roadmap_market, "_keys", lambda: ["test-key"])
    monkeypatch.setattr(roadmap_market, "_models", lambda: ["gpt-5.6-terra"])
    monkeypatch.setattr(
        roadmap_market.httpx,
        "post",
        lambda *args, **kwargs: _response(401, {"error": {"message": "sensitive provider detail"}}),
    )

    with pytest.raises(HTTPException) as exc:
        roadmap_market.search_current_market("research")

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "CURRENT_MARKET_PROVIDER_AUTH"
    assert "sensitive provider detail" not in str(exc.value.detail)


def test_market_search_requires_verifiable_sources(monkeypatch):
    monkeypatch.setattr(roadmap_market, "_keys", lambda: ["test-key"])
    monkeypatch.setattr(roadmap_market, "_models", lambda: ["gpt-5.6-terra"])
    monkeypatch.setattr(
        roadmap_market.httpx,
        "post",
        lambda *args, **kwargs: _response(
            200,
            _market_payload(json.dumps({"phases": []}), with_sources=False),
        ),
    )

    with pytest.raises(HTTPException) as exc:
        roadmap_market.search_current_market("research")

    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "CURRENT_MARKET_SOURCES_MISSING"



def test_market_search_recovers_from_invalid_success_payload(monkeypatch):
    calls = []
    monkeypatch.setattr(roadmap_market, "_keys", lambda: ["test-key"])
    monkeypatch.setattr(roadmap_market, "_models", lambda: ["gpt-5.6-terra"])

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            return _response(200, _market_payload("not-json"))
        return _response(200, _market_payload(json.dumps({"phases": []})))

    monkeypatch.setattr(roadmap_market.httpx, "post", fake_post)
    text, _, _ = roadmap_market.search_current_market("research")

    assert json.loads(text) == {"phases": []}
    assert len(calls) == 2
    assert calls[0]["text"]["format"]["type"] == "json_schema"
    assert calls[1]["text"]["format"]["type"] == "json_object"


def test_market_search_recovers_from_incomplete_response(monkeypatch):
    calls = []
    monkeypatch.setattr(roadmap_market, "_keys", lambda: ["test-key"])
    monkeypatch.setattr(roadmap_market, "_models", lambda: ["gpt-5.6-terra"])

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            payload = _market_payload(json.dumps({"phases": []}))
            payload["status"] = "incomplete"
            return _response(200, payload)
        return _response(200, _market_payload(json.dumps({"phases": []})))

    monkeypatch.setattr(roadmap_market.httpx, "post", fake_post)
    roadmap_market.search_current_market("research")

    assert len(calls) == 2



def test_market_search_uses_grounded_gemini_fallback_after_openai_failure(monkeypatch):
    monkeypatch.setattr(roadmap_market, "_keys", lambda: ["openai-key"])
    monkeypatch.setattr(roadmap_market, "_models", lambda: ["gpt-5.6-terra"])
    monkeypatch.setattr(roadmap_market, "_gemini_key", lambda: "gemini-key")
    monkeypatch.setattr(roadmap_market, "_gemini_models", lambda: ["gemini-3.8-flash"])
    monkeypatch.setattr(
        roadmap_market.httpx,
        "post",
        lambda *args, **kwargs: _response(401, {"error": {"message": "openai unavailable"}}),
    )

    research_response = SimpleNamespace(
        text="Grounded market evidence",
        candidates=[
            SimpleNamespace(
                grounding_metadata=SimpleNamespace(
                    grounding_chunks=[
                        SimpleNamespace(
                            web=SimpleNamespace(
                                title="Grounded source",
                                uri="https://example.org/grounded",
                            )
                        )
                    ]
                )
            )
        ],
    )
    structured_response = SimpleNamespace(text=json.dumps({"phases": []}))
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            def generate_content(**kwargs):
                calls.append(kwargs)
                return research_response if len(calls) == 1 else structured_response
            self.models = SimpleNamespace(generate_content=generate_content)

    fake_genai = SimpleNamespace(Client=FakeClient)
    fake_types = SimpleNamespace(
        GenerateContentConfig=lambda **kwargs: kwargs,
        Tool=lambda **kwargs: kwargs,
        GoogleSearch=lambda: {},
    )
    monkeypatch.setattr(roadmap_market, "genai", fake_genai)
    monkeypatch.setattr(roadmap_market, "genai_types", fake_types)

    text, sources, model = roadmap_market.search_current_market("research")

    assert json.loads(text) == {"phases": []}
    assert sources == [{"title": "Grounded source", "url": "https://example.org/grounded"}]
    assert model == "gemini-3.8-flash"
    assert "tools" in calls[0]["config"]
    assert "response_json_schema" not in calls[0]["config"]
    assert "tools" not in calls[1]["config"]
    assert calls[1]["config"]["response_json_schema"] == roadmap_market.ROADMAP_OUTPUT_SCHEMA

def test_market_search_can_use_grounded_gemini_when_openai_is_not_configured(monkeypatch):
    monkeypatch.setattr(roadmap_market, "_keys", lambda: [])
    monkeypatch.setattr(roadmap_market, "_gemini_key", lambda: "gemini-key")
    monkeypatch.setattr(roadmap_market, "_gemini_models", lambda: ["gemini-3.8-flash"])

    research_response = SimpleNamespace(
        text="Grounded market evidence",
        candidates=[
            SimpleNamespace(
                grounding_metadata=SimpleNamespace(
                    grounding_chunks=[
                        SimpleNamespace(
                            web=SimpleNamespace(
                                title="Grounded source",
                                uri="https://example.org/grounded",
                            )
                        )
                    ]
                )
            )
        ],
    )
    structured_response = SimpleNamespace(text=json.dumps({"phases": []}))
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            def generate_content(**kwargs):
                calls.append(kwargs)
                return research_response if len(calls) == 1 else structured_response
            self.models = SimpleNamespace(generate_content=generate_content)

    monkeypatch.setattr(roadmap_market, "genai", SimpleNamespace(Client=FakeClient))
    monkeypatch.setattr(
        roadmap_market,
        "genai_types",
        SimpleNamespace(
            GenerateContentConfig=lambda **kwargs: kwargs,
            Tool=lambda **kwargs: kwargs,
            GoogleSearch=lambda: {},
        ),
    )

    _, sources, model = roadmap_market.search_current_market("research")

    assert sources
    assert model == "gemini-3.8-flash"
    assert len(calls) == 2

def test_pinned_google_genai_supports_separate_grounding_and_structuring_configs():
    if roadmap_market.genai_types is None:
        pytest.skip("google-genai is not installed in this test environment")

    grounding = roadmap_market.genai_types.GenerateContentConfig(
        tools=[
            roadmap_market.genai_types.Tool(
                google_search=roadmap_market.genai_types.GoogleSearch()
            )
        ],
    )
    structuring = roadmap_market.genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=roadmap_market.ROADMAP_OUTPUT_SCHEMA,
    )

    assert grounding.tools
    assert structuring.response_mime_type == "application/json"
    assert structuring.response_json_schema["type"] == "object"
    assert structuring.response_json_schema["additionalProperties"] is False

def test_market_search_stops_format_churn_after_repeated_transient_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(roadmap_market, "_keys", lambda: ["test-key"])
    monkeypatch.setattr(roadmap_market, "_models", lambda: ["gpt-5.6-terra", "gpt-5.6"])
    monkeypatch.setattr(roadmap_market, "_gemini_key", lambda: "")
    monkeypatch.setattr(roadmap_market.time, "sleep", lambda *_: None)

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        return _response(503, {"error": {"message": "provider unavailable"}})

    monkeypatch.setattr(roadmap_market.httpx, "post", fake_post)

    with pytest.raises(HTTPException) as exc:
        roadmap_market.search_current_market("research")

    assert exc.value.status_code == 503
    assert len(calls) == 2
    assert all(call["model"] == "gpt-5.6-terra" for call in calls)
    assert all(call["text"]["format"]["type"] == "json_schema" for call in calls)



def test_market_search_moves_to_next_model_after_repeated_429(monkeypatch):
    calls = []
    monkeypatch.setattr(roadmap_market, "_keys", lambda: ["test-key"])
    monkeypatch.setattr(roadmap_market, "_models", lambda: ["gpt-5.6-terra", "gpt-5.5"])
    monkeypatch.setattr(roadmap_market, "_gemini_key", lambda: "")
    monkeypatch.setattr(roadmap_market.time, "sleep", lambda *_: None)

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        if kwargs["json"]["model"] == "gpt-5.6-terra":
            return _response(429, {"error": {"type": "rate_limit_error", "code": "rate_limit_exceeded"}})
        return _response(200, _market_payload(json.dumps({"phases": []})))

    monkeypatch.setattr(roadmap_market.httpx, "post", fake_post)
    text, _, model = roadmap_market.search_current_market("research")

    assert json.loads(text) == {"phases": []}
    assert model == "gpt-5.5"
    assert [call["model"] for call in calls] == [
        "gpt-5.6-terra",
        "gpt-5.6-terra",
        "gpt-5.5",
    ]


def test_market_search_skips_retry_for_account_quota_and_moves_models(monkeypatch):
    calls = []
    monkeypatch.setattr(roadmap_market, "_keys", lambda: ["test-key"])
    monkeypatch.setattr(roadmap_market, "_models", lambda: ["gpt-5.6-terra", "gpt-5.5"])
    monkeypatch.setattr(roadmap_market, "_gemini_key", lambda: "")

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        if kwargs["json"]["model"] == "gpt-5.6-terra":
            return _response(429, {"error": {"type": "insufficient_quota", "code": "insufficient_quota"}})
        return _response(200, _market_payload(json.dumps({"phases": []})))

    monkeypatch.setattr(roadmap_market.httpx, "post", fake_post)
    _, _, model = roadmap_market.search_current_market("research")

    assert model == "gpt-5.5"
    assert [call["model"] for call in calls] == ["gpt-5.6-terra", "gpt-5.5"]
    assert roadmap_market._failure_code(
        httpx.HTTPStatusError(
            "quota",
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            response=_response(429, {"error": {"type": "insufficient_quota", "code": "insufficient_quota"}}),
        )
    ) == "CURRENT_MARKET_PROVIDER_QUOTA"


def test_default_roadmap_model_fallbacks_include_search_capable_alternatives(monkeypatch):
    monkeypatch.delenv("OPENAI_WEB_SEARCH_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_WEB_SEARCH_MODEL", raising=False)

    models = roadmap_market._models()
    assert "gpt-6.1-sol" in models
    assert "gpt-6-luna" in models
    assert "gpt-5.4-mini" in models
    assert "gpt-5.5" in models
    assert "gemini-3.7-flash" in roadmap_market._gemini_models()
    assert "gemini-3.5-flash" in roadmap_market._gemini_models()
