from __future__ import annotations

from fastapi.testclient import TestClient

import app.app as app_module
from app.app import app

client = TestClient(app)


def test_production_password_reset_fails_explicitly_when_email_transport_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(app_module.settings, "environment", "production")
    monkeypatch.setattr(app_module, "transactional_email_configured", lambda settings: False)

    responses = [
        client.post("/auth/forgot-password", json={"email": "existing@example.com"}),
        client.post("/auth/forgot-password", json={"email": "missing@example.com"}),
    ]

    for response in responses:
        assert response.status_code == 503, response.text
        assert response.json() == {
            "detail": "Password reset email is temporarily unavailable. Please try again later or contact support.",
            "code": "PASSWORD_RESET_EMAIL_UNAVAILABLE",
        }


def test_health_reports_transactional_email_state_without_exposing_secrets(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "transactional_email_configured", lambda settings: False)

    response = client.get("/health")
    assert response.status_code in {200, 503}, response.text
    body = response.json()
    if body.get("configuration") == "ok":
        assert body["transactional_email"] == "not_configured"
        serialized = response.text.lower()
        assert "smtp_password" not in serialized
        assert "brevo_api_key" not in serialized
