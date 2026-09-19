from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.app import app
from app.billing_models import StudentSubscription
from app.database import Base, SessionLocal, engine
from app.models import Organization, OrganizationType, RefreshSession, StudentProfile, User, UserRole
from app.placement_access import utcnow_naive
from app.student_entitlements import student_access_status
from app.utils import get_hashed_password

client = TestClient(app)

PASSWORD = "IndependentStudent123!"
UNIVERSITY_EMAIL = "campus.entitlement@placeai.example.com"
INDEPENDENT_EMAIL = "independent.entitlement@placeai.example.com"
ORG_SLUG = "entitlement-university"


def _ensure_records() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == ORG_SLUG).first()
        if not org:
            org = Organization(name="Entitlement University", slug=ORG_SLUG, organization_type=OrganizationType.institution)
            db.add(org)
            db.flush()

        campus = db.query(User).filter(User.email == UNIVERSITY_EMAIL).first()
        if not campus:
            campus = User(
                email=UNIVERSITY_EMAIL,
                username="campus_entitlement",
                hashed_password=get_hashed_password(PASSWORD),
                role=UserRole.student,
                organization_id=org.id,
                email_verified=True,
            )
            db.add(campus)
            db.flush()
            db.add(StudentProfile(user_id=campus.id, organization_id=org.id, college=org.name, is_verified=True))

        independent = db.query(User).filter(User.email == INDEPENDENT_EMAIL).first()
        if not independent:
            independent = User(
                email=INDEPENDENT_EMAIL,
                username="independent_entitlement",
                hashed_password=get_hashed_password(PASSWORD),
                role=UserRole.student,
                email_verified=True,
                created_at=utcnow_naive(),
            )
            db.add(independent)
            db.flush()
            db.add(StudentProfile(user_id=independent.id, organization_id=None, college=None, is_verified=False))
        db.commit()
    finally:
        db.close()


def setup_module() -> None:
    _ensure_records()


def teardown_module() -> None:
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.email.in_([UNIVERSITY_EMAIL, INDEPENDENT_EMAIL])).all()
        ids = [u.id for u in users]
        student_ids = [p.id for p in db.query(StudentProfile).filter(StudentProfile.user_id.in_(ids)).all()] if ids else []
        if student_ids:
            db.query(StudentSubscription).filter(StudentSubscription.student_id.in_(student_ids)).delete(synchronize_session=False)
        if ids:
            db.query(RefreshSession).filter(RefreshSession.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(StudentProfile).filter(StudentProfile.user_id.in_(ids)).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.slug == ORG_SLUG).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _login(email: str) -> dict[str, str]:
    response = client.post("/auth/login-role", json={"email": email, "password": PASSWORD, "role": "student"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_university_student_is_sponsored_and_never_trial_gated() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == UNIVERSITY_EMAIL).one()
        status = student_access_status(user, db)
        assert status["student_kind"] == "university"
        assert status["access_mode"] == "campus_sponsored"
        assert status["premium_access"] is True
        assert status["campus_access"] is True
        assert status["payment_required"] is False
    finally:
        db.close()

    response = client.get("/billing/status", headers=_login(UNIVERSITY_EMAIL))
    assert response.status_code == 200
    assert response.json()["price_inr"] == 0


def test_independent_student_gets_three_day_trial_and_no_campus_access() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == INDEPENDENT_EMAIL).one()
        user.created_at = utcnow_naive()
        db.commit()
        status = student_access_status(user, db)
        assert status["student_kind"] == "independent"
        assert status["access_mode"] == "trial"
        assert status["premium_access"] is True
        assert status["campus_access"] is False
        assert status["trial_days"] == 3
        assert status["price_inr"] == 299
    finally:
        db.close()


def test_expired_independent_student_is_server_side_gated() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == INDEPENDENT_EMAIL).one()
        user.created_at = utcnow_naive() - timedelta(days=4)
        db.commit()
    finally:
        db.close()

    headers = _login(INDEPENDENT_EMAIL)
    status = client.get("/billing/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["access_mode"] == "expired"
    assert status.json()["payment_required"] is True

    readiness = client.get("/enterprise/readiness", headers=headers)
    assert readiness.status_code == 402
    assert readiness.json()["detail"]["code"] == "PREMIUM_REQUIRED"

    resume = client.get("/students/resume", headers=headers)
    assert resume.status_code == 402


def test_live_checkout_is_not_faked_before_provider_selection() -> None:
    headers = _login(INDEPENDENT_EMAIL)
    response = client.post("/billing/checkout", headers=headers)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PAYMENT_PROVIDER_NOT_ACTIVATED"
