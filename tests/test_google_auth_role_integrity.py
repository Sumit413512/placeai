from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import google_login
from app.database import Base, get_db
from app.dependencies import get_current_user
from app.models import (
    GoogleIdentity, Organization, RateLimitBucket, RecruiterProfile, RefreshSession,
    StudentProfile, User, UserRole,
)
from app.routers import auth
from app.utils import get_hashed_password, verify_password

PASSWORD = "Account-linking-test-123!"
CREDENTIAL = "synthetic-google-id-token-for-tests"


@pytest.fixture
def google_auth(monkeypatch):
    """Exercise real endpoints, sessions, password hashes and rate limits in isolation."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = [Organization, User, GoogleIdentity, StudentProfile, RecruiterProfile, RefreshSession, RateLimitBucket]
    Base.metadata.create_all(engine, tables=[model.__table__ for model in tables])
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(auth.settings, "google_client_id", "placeai-test.apps.googleusercontent.com")
    monkeypatch.setattr(auth.settings, "environment", "test")
    monkeypatch.setattr(auth.settings, "public_recruiter_signup", False)
    monkeypatch.setattr(google_login, "get_settings", lambda: auth.settings)
    claims = {"sub": "google-subject-1", "email": "student@gmail.com", "email_verified": True, "name": "Test Student"}
    verifier = Mock(side_effect=lambda credential: dict(claims))
    monkeypatch.setattr(google_login, "verify_credential", verifier)
    app = FastAPI()
    app.include_router(auth.router)

    def database():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = database

    @app.get("/protected")
    def protected(user: User = Depends(get_current_user)):
        return {"id": user.id}

    password_hash = get_hashed_password(PASSWORD)

    def make_user(role="student", email=None, **fields):
        with sessions() as db:
            user = User(email=email or claims["email"], username=f"user_{db.query(User).count()}",
                        hashed_password=password_hash, role=UserRole(role), **fields)
            db.add(user)
            db.commit()
            return user.id

    with TestClient(app) as client:
        def challenge():
            result = client.get("/auth/google-config")
            if result.json().get("nonce"):
                claims["nonce"] = result.json()["nonce"]
            return result

        def sign_in(role="student", password=None, *, fresh_challenge=True):
            if fresh_challenge:
                challenge()
            payload = {"credential": CREDENTIAL, "role": role}
            if password is not None:
                payload["password"] = password
            return client.post("/auth/google", json=payload)

        yield SimpleNamespace(client=client, sessions=sessions, claims=claims, verifier=verifier,
                              make_user=make_user, challenge=challenge, sign_in=sign_in)
    engine.dispose()


def test_challenge_is_private_short_lived_and_bound_to_auth_path(google_auth):
    result = google_auth.challenge()
    cookie = result.headers["set-cookie"]
    assert result.json()["enabled"] is True
    assert result.headers["cache-control"] == "no-store"
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Max-Age=600" in cookie and "Path=/auth/google" in cookie
    first_nonce = result.json()["nonce"]
    assert google_auth.challenge().json()["nonce"] != first_nonce


def test_production_challenge_cookie_is_secure(google_auth, monkeypatch):
    monkeypatch.setattr(auth.settings, "environment", "production")
    result = google_auth.challenge()
    assert "Secure" in result.headers["set-cookie"]


def test_unconfigured_google_sign_in_is_disabled(google_auth, monkeypatch):
    monkeypatch.setattr(auth.settings, "google_client_id", "")
    config = google_auth.challenge()
    assert config.json() == {"enabled": False, "client_id": None}
    assert "set-cookie" not in config.headers
    response = google_auth.sign_in()
    assert response.status_code == 503
    google_auth.verifier.assert_not_called()


@pytest.mark.parametrize("failure", ["missing", "tampered", "expired", "future", "token-mismatch"])
def test_invalid_nonce_never_creates_an_account(google_auth, monkeypatch, failure):
    google_auth.challenge()
    if failure == "missing":
        google_auth.client.cookies.clear()
    elif failure == "tampered":
        value = google_auth.client.cookies.get(google_login.COOKIE)
        google_auth.client.cookies.clear()
        google_auth.client.cookies.set(google_login.COOKIE, value + "bad", path="/auth/google")
    elif failure in {"expired", "future"}:
        timestamp = int(google_auth.claims["nonce"].split(".", 1)[0])
        monkeypatch.setattr(google_login.time, "time", lambda: timestamp + (601 if failure == "expired" else -1))
    else:
        google_auth.claims["nonce"] = "nonce-from-another-browser"
    result = google_auth.sign_in(fresh_challenge=False)
    assert result.status_code == 401
    with google_auth.sessions() as db:
        assert db.query(User).count() == 0
        assert db.query(GoogleIdentity).count() == 0
        assert db.query(RefreshSession).count() == 0
    if failure != "token-mismatch":
        google_auth.verifier.assert_not_called()


def test_provider_rejection_is_safe_and_does_not_issue_a_session(google_auth):
    google_auth.verifier.side_effect = ValueError("private upstream token diagnostics")
    response = google_auth.sign_in()
    assert response.status_code == 401
    assert "private upstream" not in response.text
    assert "placeai_refresh" not in response.cookies


@pytest.mark.parametrize("claim,value", [
    ("email_verified", False), ("email_verified", "true"), ("email", None),
    ("sub", None), ("sub", ""), ("sub", "s" * 256),
])
def test_required_verified_identity_claims(google_auth, claim, value):
    google_auth.claims[claim] = value
    assert google_auth.sign_in().status_code == 403
    with google_auth.sessions() as db:
        assert db.query(User).count() == 0


@pytest.mark.parametrize("role", ["student", "recruiter", "institution_admin", "platform_admin"])
def test_provisioned_roles_can_sign_in_without_changing_role_or_tenant(google_auth, role):
    with google_auth.sessions() as db:
        org = Organization(name="Existing Institution", slug="existing-institution")
        db.add(org)
        db.commit()
        organization_id = org.id
    user_id = google_auth.make_user(role, organization_id=organization_id, auth_version=3)
    result = google_auth.sign_in(role)
    assert result.status_code == 200, result.text
    assert result.cookies.get("placeai_refresh")
    assert "Max-Age=0" in result.headers.get_list("set-cookie")[0]
    me = google_auth.client.get("/auth/me", headers={"Authorization": f"Bearer {result.json()['access_token']}"})
    assert me.status_code == 200
    assert me.json()["id"] == user_id
    assert me.json()["role"] == role
    assert me.json()["organization_id"] == organization_id
    with google_auth.sessions() as db:
        user = db.get(User, user_id)
        assert user.auth_version == 3
        assert user.last_login_at is not None
        assert verify_password(PASSWORD, user.hashed_password)
        assert db.query(User).count() == 1
        assert db.get(GoogleIdentity, google_auth.claims["sub"]).user_id == user_id
        assert db.query(RefreshSession).one().user_id == user_id


def test_google_sign_in_preserves_required_password_rotation(google_auth):
    google_auth.make_user("institution_admin", must_change_password=True)
    result = google_auth.sign_in("institution_admin")
    assert result.status_code == 200
    token = result.json()["access_token"]
    protected = google_auth.client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert protected.status_code == 428


def test_role_mismatch_cannot_bind_or_upgrade_account(google_auth):
    user_id = google_auth.make_user()
    assert google_auth.sign_in("platform_admin").status_code == 403
    with google_auth.sessions() as db:
        assert db.get(User, user_id).role == UserRole.student
        assert db.query(GoogleIdentity).count() == 0
        assert db.query(RefreshSession).count() == 0


@pytest.mark.parametrize("bound", [False, True])
def test_inactive_account_cannot_sign_in(google_auth, bound):
    user_id = google_auth.make_user(is_active=False)
    if bound:
        with google_auth.sessions() as db:
            db.add(GoogleIdentity(subject=google_auth.claims["sub"], user_id=user_id))
            db.commit()
    assert google_auth.sign_in().status_code == 403
    with google_auth.sessions() as db:
        assert db.query(RefreshSession).count() == 0


@pytest.mark.parametrize("role", ["recruiter", "institution_admin", "platform_admin"])
def test_unprovisioned_restricted_roles_cannot_register(google_auth, role):
    assert google_auth.sign_in(role).status_code == 403
    with google_auth.sessions() as db:
        assert db.query(User).count() == 0
        assert db.query(GoogleIdentity).count() == 0


def test_new_student_receives_only_student_profile_and_identity(google_auth):
    result = google_auth.sign_in()
    assert result.status_code == 200, result.text
    with google_auth.sessions() as db:
        user = db.query(User).one()
        profile = db.query(StudentProfile).one()
        assert user.role == UserRole.student
        assert user.organization_id is None and profile.organization_id is None
        assert user.email_verified is True
        assert profile.user_id == user.id and profile.full_name == "Test Student"
        assert db.query(RecruiterProfile).count() == 0
        assert db.query(GoogleIdentity).one().user_id == user.id


def test_enabled_public_recruiter_signup_remains_unverified(google_auth, monkeypatch):
    monkeypatch.setattr(auth.settings, "public_recruiter_signup", True)
    result = google_auth.sign_in("recruiter")
    assert result.status_code == 200
    with google_auth.sessions() as db:
        assert db.query(User).one().role == UserRole.recruiter
        assert db.query(RecruiterProfile).one().is_verified is False
        assert db.query(StudentProfile).count() == 0


def test_third_party_email_requires_correct_password_for_initial_binding(google_auth):
    google_auth.claims["email"] = "student@example.com"
    user_id = google_auth.make_user()
    challenge = google_auth.sign_in()
    assert challenge.status_code == 403
    assert challenge.json()["detail"]["code"] == "GOOGLE_LINK_PASSWORD_REQUIRED"
    rejected = google_auth.sign_in(password="incorrect", fresh_challenge=False)
    assert rejected.status_code == 401
    with google_auth.sessions() as db:
        assert db.query(GoogleIdentity).count() == 0
        assert db.query(RefreshSession).count() == 0
    linked = google_auth.sign_in(password=PASSWORD, fresh_challenge=False)
    assert linked.status_code == 200, linked.text
    with google_auth.sessions() as db:
        assert db.query(GoogleIdentity).one().user_id == user_id
    assert google_auth.sign_in().status_code == 200


def test_workspace_email_can_link_without_password(google_auth):
    google_auth.claims.update(email="student@institution.example", hd="institution.example")
    google_auth.make_user()
    assert google_auth.sign_in().status_code == 200


def test_changed_google_email_uses_bound_subject_not_another_users_email(google_auth):
    original_id = google_auth.make_user()
    other_email = "another@gmail.com"
    other_id = google_auth.make_user(email=other_email)
    assert google_auth.sign_in().status_code == 200
    google_auth.claims["email"] = other_email
    result = google_auth.sign_in()
    assert result.status_code == 200
    me = google_auth.client.get("/auth/me", headers={"Authorization": f"Bearer {result.json()['access_token']}"})
    assert me.json()["id"] == original_id
    with google_auth.sessions() as db:
        assert db.get(User, original_id).email == "student@gmail.com"
        assert db.query(GoogleIdentity).one().user_id != other_id
        assert db.query(User).count() == 2


def test_different_google_subject_cannot_replace_existing_binding(google_auth):
    google_auth.make_user()
    assert google_auth.sign_in().status_code == 200
    google_auth.claims["sub"] = "different-google-subject"
    assert google_auth.sign_in().status_code == 403
    with google_auth.sessions() as db:
        assert db.query(GoogleIdentity).one().subject == "google-subject-1"
        assert db.query(RefreshSession).count() == 1


def test_concurrent_link_conflict_rolls_back_without_session(google_auth, monkeypatch):
    google_auth.make_user()
    def conflict(*args, **kwargs):
        raise IntegrityError("synthetic binding conflict", {}, Exception("private database details"))
    monkeypatch.setattr(auth, "_token_response", conflict)
    result = google_auth.sign_in()
    assert result.status_code == 409
    assert "private database" not in result.text
    assert "placeai_refresh" not in result.cookies
    with google_auth.sessions() as db:
        assert db.query(GoogleIdentity).count() == 0
        assert db.query(RefreshSession).count() == 0


def test_google_token_verifier_supplies_configured_audience(monkeypatch):
    from google.oauth2 import id_token
    verifier = Mock(return_value={"sub": "verified-subject"})
    monkeypatch.setattr(id_token, "verify_oauth2_token", verifier)
    monkeypatch.setattr(google_login, "get_settings", lambda: SimpleNamespace(google_client_id="expected-client"))
    assert google_login.verify_credential(CREDENTIAL) == {"sub": "verified-subject"}
    assert verifier.call_args.args[0] == CREDENTIAL
    assert verifier.call_args.args[2] == "expected-client"
