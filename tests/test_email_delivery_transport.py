from __future__ import annotations

from types import SimpleNamespace

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
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["api_key"] = request.headers.get("Api-key") or request.headers.get("api-key")
        return Response()

    monkeypatch.setattr(email_delivery, "urlopen", fake_urlopen)
    settings = _settings(smtp_from="noreply@example.com", brevo_api_key="secret-api-key")
    outcome, reason = email_delivery.send_transactional_email(
        settings, recipient="user@example.com", subject="Reset", body="Use link"
    )
    assert outcome == "sent"
    assert reason is None
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert captured["timeout"] == 8
    assert captured["api_key"] == "secret-api-key"


def test_smtp_failure_falls_back_to_brevo_api(monkeypatch) -> None:
    class BrokenSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            raise OSError("network unavailable")

        def __exit__(self, exc_type, exc, tb):
            return False

    class Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(email_delivery.smtplib, "SMTP", BrokenSMTP)
    monkeypatch.setattr(email_delivery, "urlopen", lambda request, timeout: Response())
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
