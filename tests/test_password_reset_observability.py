from __future__ import annotations

from fastapi.testclient import TestClient

import app.routers.access as access_router
import app.routers.auth as auth_router
from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import User, UserRole
from app.telemetry_models import EmailDeliveryEvent
from app.utils import get_hashed_password

client = TestClient(app)
PLATFORM_EMAIL = "batch40-platform@placeai.example.com"
PLATFORM_PASSWORD = "Batch40Platform123!"
USER_EMAIL = "batch40-user@placeai.example.com"
USER_PASSWORD = "Batch40User123!"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(EmailDeliveryEvent).delete()
        if not db.query(User).filter(User.email == PLATFORM_EMAIL).first():
            db.add(User(email=PLATFORM_EMAIL, username="batch40_platform", hashed_password=get_hashed_password(PLATFORM_PASSWORD), role=UserRole.platform_admin, email_verified=True))
        if not db.query(User).filter(User.email == USER_EMAIL).first():
            db.add(User(email=USER_EMAIL, username="batch40_user", hashed_password=get_hashed_password(USER_PASSWORD), role=UserRole.student, email_verified=True))
        db.commit()
    finally:
        db.close()


def platform_token() -> str:
    response = client.post("/auth/login-json", json={"email": PLATFORM_EMAIL, "password": PLATFORM_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_forgot_password_stays_non_enumerating_and_records_pii_free_failure(monkeypatch) -> None:
    monkeypatch.setattr(auth_router, "_send_reset_email", lambda recipient, link: ("failed", "smtp_delivery_failed"))
    existing = client.post("/auth/forgot-password", json={"email": USER_EMAIL})
    missing = client.post("/auth/forgot-password", json={"email": "batch40-missing@placeai.example.com"})
    assert existing.status_code == 200 and missing.status_code == 200
    assert existing.json() == missing.json()
    assert set(existing.json()) == {"message"}

    db = SessionLocal()
    try:
        rows = db.query(EmailDeliveryEvent).filter(EmailDeliveryEvent.purpose == "password_reset").all()
        assert len(rows) == 1
        assert rows[0].outcome == "failed"
        assert rows[0].reason_code == "smtp_delivery_failed"
        column_names = {column.name for column in EmailDeliveryEvent.__table__.columns}
        assert "email" not in column_names
        assert "recipient" not in column_names
        assert "user_id" not in column_names
        assert "token" not in column_names
    finally:
        db.close()


def test_platform_admin_gets_safe_delivery_health_and_success_recovers_status(monkeypatch) -> None:
    monkeypatch.setattr(access_router.settings, "smtp_host", "smtp.example.invalid")
    monkeypatch.setattr(access_router.settings, "smtp_from", "noreply@example.invalid")
    monkeypatch.setattr(access_router.settings, "smtp_user", "configured-user")
    monkeypatch.setattr(access_router.settings, "smtp_password", "configured-secret")
    monkeypatch.setattr(access_router.settings, "smtp_tls", True)
    monkeypatch.setattr(access_router.settings, "base_url", "https://placeai.example.invalid")

    token = platform_token()
    degraded = client.get("/platform/integrations/password-reset-email", headers=auth(token))
    assert degraded.status_code == 200, degraded.text
    assert degraded.json()["status"] == "degraded"
    assert degraded.json()["failures_24h"] >= 1

    monkeypatch.setattr(auth_router, "_send_reset_email", lambda recipient, link: ("sent", None))
    response = client.post("/auth/forgot-password", json={"email": USER_EMAIL})
    assert response.status_code == 200

    healthy = client.get("/platform/integrations/password-reset-email", headers=auth(token))
    assert healthy.status_code == 200, healthy.text
    body = healthy.json()
    assert body["status"] == "healthy"
    assert body["smtp_transport_configured"] is True
    assert body["smtp_authentication_configured"] is True
    assert body["successes_24h"] >= 1
    assert body["failures_24h"] >= 1
    assert body["last_success_at"] is not None
    serialized = healthy.text.lower()
    assert USER_EMAIL.lower() not in serialized
    assert "configured-secret" not in serialized


def test_delivery_observability_requires_platform_admin() -> None:
    response = client.get("/platform/integrations/password-reset-email")
    assert response.status_code == 401
