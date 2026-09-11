from __future__ import annotations

from fastapi.testclient import TestClient

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import Organization, RefreshSession, StudentProfile, User, UserRole
from app.utils import get_hashed_password

client = TestClient(app)
PLATFORM_EMAIL = "batch39-platform@placeai.example.com"
ADMIN_EMAIL = "batch39-admin@placeai.example.com"
PLATFORM_PASSWORD = "Batch39Platform123!"
TEMP_PASSWORD = "Batch39Temporary123!"
NEW_PASSWORD = "Batch39Permanent456!"
ORG_SLUG = "batch39-rotation-institute"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == ORG_SLUG).first()
        if not org:
            org = Organization(name="Batch 39 Rotation Institute", slug=ORG_SLUG, is_active=True)
            db.add(org)
        user = db.query(User).filter(User.email == PLATFORM_EMAIL).first()
        if not user:
            db.add(User(email=PLATFORM_EMAIL, username="batch39_platform", hashed_password=get_hashed_password(PLATFORM_PASSWORD), role=UserRole.platform_admin, email_verified=True, must_change_password=False))
        db.commit()
    finally:
        db.close()


def login(email: str, password: str) -> str:
    response = client.post("/auth/login-json", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_provisioned_admin_must_rotate_password_before_workspace_access() -> None:
    platform_token = login(PLATFORM_EMAIL, PLATFORM_PASSWORD)
    created = client.post(
        "/platform/institution-admins",
        headers=auth(platform_token),
        json={
            "email": ADMIN_EMAIL,
            "username": "batch39_admin",
            "full_name": "Batch 39 Admin",
            "temporary_password": TEMP_PASSWORD,
            "organization_slug": ORG_SLUG,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["must_change_password"] is True

    old_token = login(ADMIN_EMAIL, TEMP_PASSWORD)
    me = client.get("/auth/me", headers=auth(old_token))
    assert me.status_code == 200, me.text
    assert me.json()["must_change_password"] is True

    blocked = client.get("/institutions/me", headers=auth(old_token))
    assert blocked.status_code == 428, blocked.text
    assert blocked.headers.get("x-placeai-action") == "change-password"

    wrong = client.post(
        "/auth/change-password",
        headers=auth(old_token),
        json={"current_password": "WrongTemporary123!", "new_password": NEW_PASSWORD},
    )
    assert wrong.status_code == 401, wrong.text

    changed = client.post(
        "/auth/change-password",
        headers=auth(old_token),
        json={"current_password": TEMP_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200, changed.text
    new_token = changed.json()["access_token"]

    stale = client.get("/auth/me", headers=auth(old_token))
    assert stale.status_code == 401
    fresh = client.get("/auth/me", headers=auth(new_token))
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["must_change_password"] is False
    workspace = client.get("/institutions/me", headers=auth(new_token))
    assert workspace.status_code == 200, workspace.text

    old_login = client.post("/auth/login-json", json={"email": ADMIN_EMAIL, "password": TEMP_PASSWORD})
    assert old_login.status_code == 401
    new_login = client.post("/auth/login-json", json={"email": ADMIN_EMAIL, "password": NEW_PASSWORD})
    assert new_login.status_code == 200, new_login.text


def test_public_signup_accounts_do_not_require_forced_rotation() -> None:
    email = "batch39-self-signup@placeai.example.com"
    response = client.post(
        "/auth/signup",
        json={"username": "batch39_self_signup", "email": email, "password": "Batch39SelfSignup123!", "role": "student"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["must_change_password"] is False


def test_rotation_ui_assets_are_present() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "/static/account-security.css" in response.text
    assert "/static/account-security.js" in response.text
    source = response = client.get("/static/account-security.js")
    assert source.status_code == 200
    assert "/auth/change-password" in source.text
    assert "must_change_password" in source.text
    assert "Current temporary password" in source.text
