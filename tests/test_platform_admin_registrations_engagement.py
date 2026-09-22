from __future__ import annotations

from fastapi.testclient import TestClient

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import Organization, RefreshSession, StudentProfile, User, UserRole
from app.telemetry_models import PageViewEvent
from app.utils import get_hashed_password

client = TestClient(app)

PLATFORM_EMAIL = "analytics.platform@placeai.example.com"
STUDENT_EMAIL = "analytics.student@placeai.example.com"
PASSWORD = "PlatformAnalytics123!"
TEST_PATH = "/test/platform-admin-engagement"


def _ensure_user(email: str, username: str, role: UserRole) -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                username=username,
                hashed_password=get_hashed_password(PASSWORD),
                role=role,
                email_verified=True,
            )
            db.add(user)
            db.flush()
            if role == UserRole.student:
                db.add(
                    StudentProfile(
                        user_id=user.id,
                        full_name="Platform Analytics Student",
                        college="PlaceAI Test Institute",
                        degree="B.Tech",
                        branch="Computer Science",
                        graduation_year=2027,
                        cgpa=8.4,
                        is_verified=True,
                    )
                )
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()


def _platform_headers() -> dict[str, str]:
    response = client.post(
        "/auth/login-role",
        json={"email": PLATFORM_EMAIL, "password": PASSWORD, "role": "platform_admin"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_user(PLATFORM_EMAIL, "analytics_platform", UserRole.platform_admin)
    _ensure_user(STUDENT_EMAIL, "analytics_student", UserRole.student)


def teardown_module() -> None:
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.email.in_([PLATFORM_EMAIL, STUDENT_EMAIL])).all()
        user_ids = [user.id for user in users]
        db.query(PageViewEvent).filter(PageViewEvent.path == TEST_PATH).delete(synchronize_session=False)
        if user_ids:
            db.query(PageViewEvent).filter(PageViewEvent.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(RefreshSession).filter(RefreshSession.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(StudentProfile).filter(StudentProfile.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_page_view_telemetry_is_public_and_privacy_safe() -> None:
    response = client.post(
        "/telemetry/page-view",
        json={
            "visitor_id": "visitor_analytics_test_123456789",
            "session_id": "session_analytics_test_123456789",
            "path": TEST_PATH + "?secret=must-not-be-stored",
            "referrer_host": "example.com",
        },
    )
    assert response.status_code == 204, response.text

    db = SessionLocal()
    try:
        event = db.query(PageViewEvent).filter(PageViewEvent.path == TEST_PATH).one()
        assert event.user_id is None
        assert event.visitor_hash != "visitor_analytics_test_123456789"
        assert event.session_hash != "session_analytics_test_123456789"
        assert len(event.visitor_hash) == 64
        assert "secret" not in event.path
        assert event.referrer_host == "example.com"
    finally:
        db.close()


def test_platform_admin_can_view_registrations_and_details_without_secrets() -> None:
    headers = _platform_headers()
    listing = client.get("/platform/registrations?role=student", headers=headers)
    assert listing.status_code == 200, listing.text
    payload = listing.json()
    row = next(item for item in payload["items"] if item["email"] == STUDENT_EMAIL)
    assert row["name"] == "Platform Analytics Student"
    assert row["role"] == "student"
    assert "last_login_at" in row
    assert "mock_interview_attempts" in row["activity"]

    detail = client.get(f"/platform/registrations/{row['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["profile"]["degree"] == "B.Tech"
    assert body["profile"]["branch"] == "Computer Science"
    serialized = detail.text.lower()
    assert "hashed_password" not in serialized
    assert "reset_token" not in serialized
    assert "refresh_token" not in serialized


def test_platform_admin_engagement_includes_page_views() -> None:
    headers = _platform_headers()
    response = client.get("/platform/engagement?days=30", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["page_views"] >= 1
    assert body["summary"]["unique_visitors"] >= 1
    assert any(item["path"] == TEST_PATH for item in body["top_pages"])


def test_platform_organizations_tolerates_legacy_null_primary_color() -> None:
    """A legacy organization row with a NULL color must not crash Platform Admin."""
    slug = "legacy-null-color-regression"
    db = SessionLocal()
    try:
        row = db.query(Organization).filter(Organization.slug == slug).first()
        if not row:
            row = Organization(
                name="Legacy Null Color Institution",
                slug=slug,
                primary_color=None,
                is_active=True,
            )
            db.add(row)
            db.commit()
    finally:
        db.close()

    try:
        response = client.get("/platform/organizations", headers=_platform_headers())
        assert response.status_code == 200, response.text
        payload = next(item for item in response.json() if item["slug"] == slug)
        assert payload["primary_color"] == "#5B5BD6"
    finally:
        db = SessionLocal()
        try:
            db.query(Organization).filter(Organization.slug == slug).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


def test_non_platform_user_cannot_access_registration_directory() -> None:
    login = client.post(
        "/auth/login-role",
        json={"email": STUDENT_EMAIL, "password": PASSWORD, "role": "student"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = client.get("/platform/registrations", headers=headers)
    assert response.status_code == 403, response.text
