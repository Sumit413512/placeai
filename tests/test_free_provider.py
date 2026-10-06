import json

import httpx
import pytest
from fastapi import HTTPException

from app import ai_provider, free_provider


@pytest.fixture
def pilot(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "isolated-test-key")
    monkeypatch.setenv("GROQ_PROCESSING_APPROVED", "true")
    original = httpx.Client
    def transport(handler):
        monkeypatch.setattr(free_provider.httpx, "Client", lambda **kwargs: original(
            transport=httpx.MockTransport(handler), **kwargs))
    return transport


def reply(content="A grounded response", reason="stop"):
    return {"choices": [{"finish_reason": reason, "message": {"content": content}}]}


def test_new_processor_needs_explicit_approval_before_network(pilot, monkeypatch):
    monkeypatch.setenv("GROQ_PROCESSING_APPROVED", "false")
    pilot(lambda _: pytest.fail("Unapproved processor must not receive data"))
    with pytest.raises(free_provider.ProviderError, match="FREE_PROVIDER_NOT_CONFIGURED"):
        free_provider.text("private answer")


def test_fixed_endpoint_schema_and_no_partial_response(pilot):
    calls = []
    def handle(request):
        calls.append(request)
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == free_provider.TEXT_MODEL
        assert body["response_format"]["json_schema"]["strict"] is True
        return httpx.Response(200, json=reply('{"score":0}'))
    pilot(handle)
    schema = {"type": "object", "properties": {"score": {"type": "integer"}},
              "required": ["score"], "additionalProperties": False}
    assert free_provider.text("Return JSON", schema=schema) == '{"score":0}'
    assert len(calls) == 1
    pilot(lambda _: httpx.Response(200, json=reply("truncated", "length")))
    with pytest.raises(free_provider.ProviderError, match="INCOMPLETE"):
        free_provider.text("question")


def test_quota_is_not_retried_or_sent_to_other_providers(pilot, monkeypatch, caplog):
    monkeypatch.setenv("TEXT_AI_PROVIDER", "groq")
    monkeypatch.setattr(ai_provider, "_call_openai", lambda *a, **k: pytest.fail("Paid fallback forbidden"))
    monkeypatch.setattr(ai_provider, "_call_gemini", lambda *a, **k: pytest.fail("Different processor forbidden"))
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(429, text="private provider response with student data")
    pilot(handle)
    with pytest.raises(HTTPException) as error:
        ai_provider.call_ai_text("private student answer")
    assert error.value.detail["code"] == "AI_PROVIDER_CAPACITY"
    assert len(calls) == 1
    assert "private" not in caplog.text
    assert "isolated-test-key" not in caplog.text
    assert "private" not in str(error.value.detail)


def test_redirect_is_rejected_without_following(pilot):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://unapproved.example"})
    pilot(handle)
    with pytest.raises(free_provider.ProviderError) as error:
        free_provider.text("answer")
    assert error.value.code == 307 and len(calls) == 1


def test_timed_transcription_accepts_only_valid_segments(pilot):
    transcription = {"text": "An answer", "duration": 10,
                     "segments": [{"start": 1, "end": 9, "text": "An answer"}],
                     "words": [{"start": 1, "end": 2, "word": "An"}, {"start": 2, "end": 3, "word": "answer"}]}
    def handle(request):
        assert request.url.path.endswith("audio/transcriptions")
        assert b"answer.webm" in request.content
        assert b"whisper-large-v3" in request.content
        return httpx.Response(200, json=transcription)
    pilot(handle)
    assert free_provider.transcribe(b"synthetic", "audio/webm")["text"] == "An answer"
    transcription["segments"][0]["end"] = 20
    with pytest.raises(free_provider.ProviderError, match="INVALID_TRANSCRIPT"):
        free_provider.transcribe(b"synthetic", "audio/webm")


def test_bounded_output_and_remote_image_urls_are_rejected(pilot):
    pilot(lambda _: httpx.Response(200, content=b"x" * (free_provider.MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(free_provider.ProviderError, match="TOO_LARGE"):
        free_provider.text("answer")
    with pytest.raises(free_provider.ProviderError, match="INPUT_LIMIT"):
        free_provider.text("answer", images=["https://private.example/student-photo"])


def test_opt_in_status_preserves_contract(pilot, monkeypatch):
    monkeypatch.setenv("TEXT_AI_PROVIDER", "groq")
    assert ai_provider.ai_status_payload() == {"configured": True, "sdk_available": True,
                                              "model": "openai/gpt-oss-120b"}
