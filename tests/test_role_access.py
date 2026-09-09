from __future__ import annotations

from fastapi.testclient import TestClient

from app.access_models import AccessRequest
from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import RefreshSession, User, UserRole
from app.utils import get_hashed_password

client = TestClient(app)

STUDENT_EMAIL = "role.student@placeai.test"
RECRUITER_EMAIL = "role.recruiter@placeai.test"
PLATFORM_EMAIL = "role.platform@placeai.test"
PASSWORD = "RoleAccessPass123!"


def _ensure_user(email: str, username: str, role: UserRole) -> None:
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if not existing:
            db.add(
                User(
                    email=email,
                    username=username,
                    hashed_password=get_hashed_password(PASSWORD),
                    role=role,
                    email_verified=True,
                )
            )
            db.commit()
    finally:
        db.close()


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_user(STUDENT_EMAIL, "role_student", UserRole.student)
    _ensure_user(RECRUITER_EMAIL, "role_recruiter", UserRole.recruiter)
    _ensure_user(PLATFORM_EMAIL, "role_platform", UserRole.platform_admin)


def teardown_module() -> None:
    db = SessionLocal()
    try:
        user_ids = [
            row[0]
            for row in db.query(User.id)
            .filter(User.email.in_([STUDENT_EMAIL, RECRUITER_EMAIL, PLATFORM_EMAIL]))
            .all()
        ]
        if user_ids:
            db.query(RefreshSession).filter(RefreshSession.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(AccessRequest).filter(AccessRequest.work_email == "request.recruiter@placeai.test").delete(synchronize_session=False)
        db.query(User).filter(User.email.in_([STUDENT_EMAIL, RECRUITER_EMAIL, PLATFORM_EMAIL])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_selected_role_must_match_account_role() -> None:
    correct = client.post(
        "/auth/login-role",
        json={"email": STUDENT_EMAIL, "password": PASSWORD, "role": "student"},
    )
    assert correct.status_code == 200, correct.text
    assert correct.json()["access_token"]
    assert "placeai_refresh" in correct.cookies

    wrong = client.post(
        "/auth/login-role",
        json={"email": STUDENT_EMAIL, "password": PASSWORD, "role": "platform_admin"},
    )
    assert wrong.status_code == 403, wrong.text
    assert "does not have Platform Admin workspace access" in wrong.json()["detail"]


def test_public_privileged_signup_remains_blocked() -> None:
    response = client.post(
        "/auth/signup",
        json={
            "username": "blocked_platform_signup",
            "email": "blocked.platform@placeai.test",
            "password": PASSWORD,
            "role": "platform_admin",
        },
    )
    assert response.status_code == 403, response.text


def test_real_access_request_is_persisted_and_platform_admin_can_review() -> None:
    request_response = client.post(
        "/public/access-requests",
        json={
            "requested_role": "recruiter",
            "full_name": "Recruiter Access Test",
            "work_email": "request.recruiter@placeai.test",
            "organization_name": "Access Test Company",
            "message": "Production access verification",
        },
    )
    assert request_response.status_code == 202, request_response.text
    request_id = request_response.json()["request_id"]

    db = SessionLocal()
    try:
        row = db.query(AccessRequest).filter(AccessRequest.id == request_id).first()
        assert row is not None
        assert row.status == "new"
        assert row.requested_role == "recruiter"
    finally:
        db.close()

    login = client.post(
        "/auth/login-role",
        json={"email": PLATFORM_EMAIL, "password": PASSWORD, "role": "platform_admin"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    listing = client.get("/platform/access-requests", headers=headers)
    assert listing.status_code == 200, listing.text
    assert any(item["id"] == request_id for item in listing.json())

    review = client.patch(
        f"/platform/access-requests/{request_id}",
        headers=headers,
        json={"status": "under_review", "review_note": "Ownership verification in progress"},
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "under_review"
