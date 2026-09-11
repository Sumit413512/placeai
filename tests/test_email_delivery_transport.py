from __future__ import annotations

from types import SimpleNamespace

import httpx

import app.email_delivery as email_delivery


def _settings(**overrides):
    values = {
        "app_name": "PlaceAI",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_from": "",
        "smtp_tls": True,
        "brevo_api_key": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_no_transport_is_reported_as_not_configured() -> None:
    outcome, reason = email_delivery.send_transactional_email(
        _settings(), recipient="user@example.com", subject="Test", body="Body"
    )
    assert outcome == "not_configured"
    assert reason == "transactional_email_not_configured"


def test_brevo_api_transport_sends_when_smtp_is_absent(monkeypatch) -> None:
    class Response:
        status_code = 201

    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        captured["api_key"] = headers.get("api-key")
        return Response()

    monkeypatch.setattr(email_delivery.httpx, "post", fake_post)
    settings = _settings(smtp_from="noreply@example.com", brevo_api_key="secret-api-key")
    outcome, reason = email_delivery.send_transactional_email(
        settings, recipient="user@example.com", subject="Reset", body="Use link"
    )
    assert outcome == "sent"
    assert reason is None
    assert captured["url"] == email_delivery.BREVO_TRANSACTIONAL_EMAIL_URL
    assert captured["timeout"] == 8.0
    assert captured["api_key"] == "secret-api-key"
    assert captured["json"]["sender"]["name"] == "PlaceAI"
    assert captured["json"]["to"] == [{"email": "user@example.com"}]


def test_brevo_400_retries_with_escaped_html_and_verified_email_only(monkeypatch) -> None:
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append(json)
        status_code = 400 if len(calls) == 1 else 201
        return SimpleNamespace(status_code=status_code)

    monkeypatch.setattr(email_delivery.httpx, "post", fake_post)
    settings = _settings(smtp_from="verified@example.com", brevo_api_key="api-key")
    outcome, reason = email_delivery.send_transactional_email(
        settings,
        recipient="user@example.com",
        subject="Reset",
        body="Use https://example.com/?a=1&b=2\nDo not share <this>.",
    )

    assert outcome == "sent"
    assert reason is None
    assert len(calls) == 2
    assert calls[0]["sender"] == {"name": "PlaceAI", "email": "verified@example.com"}
    assert "textContent" in calls[0]
    assert calls[1]["sender"] == {"email": "verified@example.com"}
    assert "htmlContent" in calls[1]
    assert "&amp;" in calls[1]["htmlContent"]
    assert "&lt;this&gt;" in calls[1]["htmlContent"]
    assert "<br>" in calls[1]["htmlContent"]


def test_smtp_failure_falls_back_to_brevo_api(monkeypatch) -> None:
    class BrokenSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            raise OSError("network unavailable")

        def __exit__(self, exc_type, exc, tb):
            return False

    class Response:
        status_code = 201

    monkeypatch.setattr(email_delivery.smtplib, "SMTP", BrokenSMTP)
    monkeypatch.setattr(email_delivery.httpx, "post", lambda *args, **kwargs: Response())
    settings = _settings(
        smtp_host="smtp-relay.brevo.com",
        smtp_user="login",
        smtp_password="smtp-key",
        smtp_from="noreply@example.com",
        brevo_api_key="api-key",
    )
    outcome, reason = email_delivery.send_transactional_email(
        settings, recipient="user@example.com", subject="Reset", body="Use link"
    )
    assert outcome == "sent"
    assert reason is None


def test_brevo_api_failure_statuses_are_sanitized(monkeypatch) -> None:
    settings = _settings(smtp_from="noreply@example.com", brevo_api_key="api-key")
    cases = {
        400: "brevo_api_request_rejected",
        401: "brevo_api_auth_failed",
        403: "brevo_api_auth_failed",
        429: "brevo_api_rate_limited",
        503: "brevo_api_provider_unavailable",
        418: "brevo_api_delivery_failed",
    }

    for status_code, expected_reason in cases.items():
        monkeypatch.setattr(
            email_delivery.httpx,
            "post",
            lambda *args, _status=status_code, **kwargs: SimpleNamespace(status_code=_status),
        )
        outcome, reason = email_delivery.send_transactional_email(
            settings, recipient="user@example.com", subject="Reset", body="Use link"
        )
        assert outcome == "failed"
        assert reason == expected_reason


def test_brevo_api_transport_distinguishes_timeout_and_network_failures(monkeypatch) -> None:
    settings = _settings(smtp_from="noreply@example.com", brevo_api_key="api-key")

    def raise_timeout(*args, **kwargs):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(email_delivery.httpx, "post", raise_timeout)
    outcome, reason = email_delivery.send_transactional_email(
        settings, recipient="user@example.com", subject="Reset", body="Use link"
    )
    assert outcome == "failed"
    assert reason == "brevo_api_timeout"

    def raise_network(*args, **kwargs):
        raise httpx.ConnectError("network unavailable")

    monkeypatch.setattr(email_delivery.httpx, "post", raise_network)
    outcome, reason = email_delivery.send_transactional_email(
        settings, recipient="user@example.com", subject="Reset", body="Use link"
    )
    assert outcome == "failed"
    assert reason == "brevo_api_network_failed"
