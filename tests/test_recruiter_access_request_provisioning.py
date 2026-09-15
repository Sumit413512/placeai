from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.access_models import AccessRequest
from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import AuditEvent, RecruiterProfile, RefreshSession, User, UserRole
from app.routers import platform
from app.telemetry_models import EmailDeliveryEvent
from app.utils import get_hashed_password

client = TestClient(app)
RUN = uuid.uuid4().hex[:10]
PLATFORM_EMAIL = f"recruiter-flow-admin-{RUN}@placeai.example.com"
PLATFORM_PASSWORD = "RecruiterFlowAdmin123!"
REQUEST_EMAIL = f"approved-recruiter-{RUN}@example.com"
REQUEST_ID = f"approved-recruiter-request-{RUN}"


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add(
            User(
                email=PLATFORM_EMAIL,
                username=f"recruiter_flow_admin_{RUN}",
                hashed_password=get_hashed_password(PLATFORM_PASSWORD),
                role=UserRole.platform_admin,
                email_verified=True,
            )
        )
        db.add(
            AccessRequest(
                id=REQUEST_ID,
                requested_role="recruiter",
                full_name="Approved Recruiter",
                work_email=REQUEST_EMAIL,
                organization_name="Approved Hiring Company",
                status="approved",
            )
        )
        db.commit()
    finally:
        db.close()


def teardown_module() -> None:
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.email.in_([PLATFORM_EMAIL, REQUEST_EMAIL])).all()
        user_ids = [user.id for user in users]
        if user_ids:
            db.query(RecruiterProfile).filter(RecruiterProfile.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(RefreshSession).filter(RefreshSession.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(AuditEvent).filter(AuditEvent.actor_user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(EmailDeliveryEvent).filter(EmailDeliveryEvent.purpose == "recruiter_setup").delete(synchronize_session=False)
        db.query(AccessRequest).filter(AccessRequest.id == REQUEST_ID).delete(synchronize_session=False)
        db.query(User).filter(User.email.in_([PLATFORM_EMAIL, REQUEST_EMAIL])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _platform_headers() -> dict[str, str]:
    response = client.post(
        "/auth/login-role",
        json={"email": PLATFORM_EMAIL, "password": PLATFORM_PASSWORD, "role": "platform_admin"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_approved_recruiter_request_creates_account_and_password_setup_link(monkeypatch) -> None:
    deliveries: list[dict[str, str]] = []

    def fake_delivery(settings, *, recipient: str, subject: str, body: str):
        del settings
        deliveries.append({"recipient": recipient, "subject": subject, "body": body})
        return "sent", None

    monkeypatch.setattr(platform, "send_transactional_email", fake_delivery)
    response = client.post(
        f"/platform/access-requests/{REQUEST_ID}/provision-recruiter",
        headers=_platform_headers(),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "provisioned"
    assert payload["account_created"] is True
    assert payload["setup_email_sent"] is True
    assert "reset_token" not in response.text
    assert "temporary_password" not in response.text
    assert deliveries and deliveries[0]["recipient"] == REQUEST_EMAIL
    assert "Set up your PlaceAI Recruiter password" in deliveries[0]["subject"]
    assert "?reset_token=" in deliveries[0]["body"]
    assert "No administrator knows or needs to set your permanent password" in deliveries[0]["body"]

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == REQUEST_EMAIL).one()
        profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == user.id).one()
        request = db.query(AccessRequest).filter(AccessRequest.id == REQUEST_ID).one()
        assert user.role == UserRole.recruiter
        assert user.reset_token_hash
        assert user.reset_token_expires
        assert user.must_change_password is False
        assert profile.full_name == "Approved Recruiter"
        assert profile.company_name == "Approved Hiring Company"
        assert profile.is_verified is True
        assert request.status == "provisioned"
    finally:
        db.close()


def test_provisioning_action_is_idempotent_for_same_recruiter(monkeypatch) -> None:
    monkeypatch.setattr(platform, "send_transactional_email", lambda *args, **kwargs: ("sent", None))
    response = client.post(
        f"/platform/access-requests/{REQUEST_ID}/provision-recruiter",
        headers=_platform_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["account_created"] is False
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == REQUEST_EMAIL, User.role == UserRole.recruiter).count() == 1
    finally:
        db.close()


def test_rendered_release_fix_uses_current_production_credential_path() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "app" / "static" / "release-ux-fixes.js").read_text(encoding="utf-8")
    public_script = (root / "public" / "static" / "release-ux-fixes.js").read_text(encoding="utf-8")
    app_script = (root / "app" / "static" / "app.js").read_text(encoding="utf-8")
    proxy = (root / "render_proxy.py").read_text(encoding="utf-8")
    assert "data-access-request-status" in app_script
    assert "data-current-status" in app_script
    assert script == public_script
    assert "/platform/access-requests/${encodeURIComponent(requestId)}/provision-recruiter" in script
    assert "/platform/recruiters" not in script
    assert "/auth/forgot-password" not in script
    assert "secureTemporaryPassword" not in script
    assert "Resend password setup link" in script
    assert "PARSED RÉSUMÉ DATA" in script and "PARSED RESUME DATA" in script
    assert "Résumé uploaded" in script and "Resume uploaded" in script
    assert "release-ux-fixes.js" in proxy
