from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import ai_provider


def test_openai_primary_is_preferred(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key")
    monkeypatch.setenv("OPENAI_BACKUP_API_KEY", "backup-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    seen = []

    def fake_openai(key, prompt):
        seen.append((key, prompt))
        return "primary-ok"

    monkeypatch.setattr(ai_provider, "_call_openai", fake_openai)
    monkeypatch.setattr(ai_provider, "_call_gemini", lambda *_: pytest.fail("Gemini should not be used"))
    assert ai_provider.call_ai_text("hello") == "primary-ok"
    assert seen == [("primary-key", "hello")]


def test_second_openai_key_then_gemini_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key")
    monkeypatch.setenv("OPENAI_BACKUP_API_KEY", "backup-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    attempted = []

    def fake_openai(key, _prompt):
        attempted.append(key)
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(ai_provider, "_call_openai", fake_openai)
    monkeypatch.setattr(ai_provider, "_call_gemini", lambda key, prompt: f"gemini:{key}:{prompt}")
    assert ai_provider.call_ai_text("hello") == "gemini:gemini-key:hello"
    assert attempted == ["primary-key", "backup-key"]


def test_duplicate_openai_keys_are_not_retried(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "same-key")
    monkeypatch.setenv("OPENAI_BACKUP_API_KEY", "same-key")
    assert ai_provider._openai_keys() == ["same-key"]


def test_no_provider_fails_closed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BACKUP_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setattr(ai_provider.settings, "openai_api_key", "")
    monkeypatch.setattr(ai_provider.settings, "openai_backup_api_key", "")
    monkeypatch.setattr(ai_provider.settings, "gemini_api_key", "")
    with pytest.raises(HTTPException) as exc:
        ai_provider.call_ai_text("hello")
    assert exc.value.status_code == 503


def test_status_keeps_public_contract(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key")
    monkeypatch.setenv("OPENAI_BACKUP_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    payload = ai_provider.ai_status_payload()
    assert set(payload) == {"configured", "sdk_available", "model"}
    assert payload["configured"] is True
    assert payload["sdk_available"] is True
    assert payload["model"] == ai_provider.settings.openai_model


def test_interactive_controls_are_forwarded_to_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key")
    monkeypatch.setenv("OPENAI_BACKUP_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    seen = {}

    def fake_openai(key, prompt, **kwargs):
        seen.update({"key": key, "prompt": prompt, **kwargs})
        return "interactive-ok"

    monkeypatch.setattr(ai_provider, "_call_openai", fake_openai)
    result = ai_provider.call_ai_text(
        "hello",
        reasoning_effort="none",
        max_output_tokens=900,
        model_override="gpt-5.6-luna",
        timeout_seconds=10,
        retry_count_per_provider=0,
    )
    assert result == "interactive-ok"
    assert seen["model_override"] == "gpt-5.6-luna"
    assert seen["timeout_seconds"] == 10
    assert seen["retry_count"] == 0
    assert seen["max_output_tokens"] == 900


def test_controlled_gemini_fallback_obeys_retry_budget(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key")
    monkeypatch.setenv("OPENAI_BACKUP_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(ai_provider, "_call_openai", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    seen = {}

    def fake_gemini(key, prompt, *, retry_count=1):
        seen.update({"key": key, "prompt": prompt, "retry_count": retry_count})
        return "gemini-ok"

    monkeypatch.setattr(ai_provider, "_call_gemini", fake_gemini)
    assert ai_provider.call_ai_text("hello", max_output_tokens=700, retry_count_per_provider=0) == "gemini-ok"
    assert seen["retry_count"] == 0
