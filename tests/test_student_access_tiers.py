from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta

from fastapi.testclient import TestClient

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import (
    IndividualStudentAccess,
    Job,
    Organization,
    OrganizationType,
    PaymentTransaction,
    RecruiterProfile,
    StudentProfile,
    User,
    UserRole,
)
from app.placement_access import utcnow_naive
from app.utils import get_hashed_password

client = TestClient(app)

PASSWORD = "StudentTierPass123!"
IND_EMAIL = "tier.individual@placeai.example.com"
UNI_EMAIL = "tier.university@placeai.example.com"
RECRUITER_EMAIL = "tier.recruiter@placeai.example.com"
ORG_SLUG = "tier-test-university"


def _login(email: str, role: str = "student") -> dict[str, str]:
    response = client.post(
        "/auth/login-role",
        json={"email": email, "password": PASSWORD, "role": role},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == ORG_SLUG).first()
        if not org:
            org = Organization(
                name="Tier Test University",
                slug=ORG_SLUG,
                organization_type=OrganizationType.institution,
                is_active=True,
            )
            db.add(org)
            db.flush()

        recruiter_user = db.query(User).filter(User.email == RECRUITER_EMAIL).first()
        if not recruiter_user:
            recruiter_user = User(
                email=RECRUITER_EMAIL,
                username="tier_recruiter",
                hashed_password=get_hashed_password(PASSWORD),
                role=UserRole.recruiter,
                email_verified=True,
            )
            db.add(recruiter_user)
            db.flush()
            recruiter = RecruiterProfile(
                user_id=recruiter_user.id,
                full_name="Tier Recruiter",
                company_name="Tier Recruiter Company",
                is_verified=True,
            )
            db.add(recruiter)
            db.flush()
        else:
            recruiter = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == recruiter_user.id).one()

        if not db.query(Job).filter(Job.title == "Tier Public Opportunity").first():
            db.add(
                Job(
                    recruiter_id=recruiter.id,
                    title="Tier Public Opportunity",
                    description="Public opportunity created specifically for independent student boundary tests.",
                    visibility="public",
                    is_active=True,
                )
            )
        if not db.query(Job).filter(Job.title == "Tier Campus Opportunity").first():
            db.add(
                Job(
                    recruiter_id=recruiter.id,
                    title="Tier Campus Opportunity",
                    description="Campus opportunity that must never be exposed to independent students.",
                    visibility="campus",
                    target_organization_id=org.id,
                    is_active=True,
                )
            )
        db.commit()
    finally:
        db.close()


def teardown_module() -> None:
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.email.in_([IND_EMAIL, UNI_EMAIL, RECRUITER_EMAIL])).all()
        user_ids = [u.id for u in users]
        student_ids = [
            row[0]
            for row in db.query(StudentProfile.id).filter(StudentProfile.user_id.in_(user_ids)).all()
        ] if user_ids else []
        if user_ids:
            db.query(PaymentTransaction).filter(PaymentTransaction.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(IndividualStudentAccess).filter(IndividualStudentAccess.user_id.in_(user_ids)).delete(synchronize_session=False)
        if student_ids:
            from app.models import IncidentReport
            db.query(IncidentReport).filter(IncidentReport.student_id.in_(student_ids)).delete(synchronize_session=False)
            db.query(StudentProfile).filter(StudentProfile.id.in_(student_ids)).delete(synchronize_session=False)
        recruiter = db.query(RecruiterProfile).join(User, RecruiterProfile.user_id == User.id).filter(User.email == RECRUITER_EMAIL).first()
        if recruiter:
            db.query(Job).filter(Job.recruiter_id == recruiter.id).delete(synchronize_session=False)
            db.query(RecruiterProfile).filter(RecruiterProfile.id == recruiter.id).delete(synchronize_session=False)
        if user_ids:
            from app.models import RefreshSession
            db.query(RefreshSession).filter(RefreshSession.user_id.in_(user_ids)).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.slug == ORG_SLUG).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_independent_signup_gets_three_day_trial_and_no_university_scope() -> None:
    response = client.post(
        "/auth/signup",
        json={
            "username": "tier_individual",
            "email": IND_EMAIL,
            "password": PASSWORD,
            "role": "student",
            "organization_slug": None,
        },
    )
    assert response.status_code == 201, response.text

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == IND_EMAIL).one()
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).one()
        access = db.query(IndividualStudentAccess).filter(IndividualStudentAccess.user_id == user.id).one()
        assert user.organization_id is None
        assert profile.organization_id is None
        assert access.status == "trialing"
        duration = access.trial_ends_at - access.trial_started_at
        assert timedelta(days=2, hours=23) < duration <= timedelta(days=3, minutes=1)
    finally:
        db.close()

    status = client.get("/billing/student/status", headers=_login(IND_EMAIL))
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["account_type"] == "individual"
    assert body["university_associated"] is False
    assert body["premium_access"] is True
    assert body["payment_required"] is False
    assert body["plan"]["price_inr"] == 299
    assert body["plan"]["trial_days"] == 3


def test_university_signup_is_not_individually_billed() -> None:
    response = client.post(
        "/auth/signup",
        json={
            "username": "tier_university_student",
            "email": UNI_EMAIL,
            "password": PASSWORD,
            "role": "student",
            "organization_slug": ORG_SLUG,
        },
    )
    assert response.status_code == 201, response.text

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == UNI_EMAIL).one()
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).one()
        assert user.organization_id is not None
        assert profile.organization_id == user.organization_id
        assert db.query(IndividualStudentAccess).filter(IndividualStudentAccess.user_id == user.id).count() == 0
    finally:
        db.close()

    headers = _login(UNI_EMAIL)
    status_response = client.get("/billing/student/status", headers=headers)
    assert status_response.status_code == 200, status_response.text
    body = status_response.json()
    assert body["account_type"] == "university"
    assert body["premium_access"] is True
    assert body["payment_required"] is False

    checkout = client.post("/billing/student/checkout", headers=headers)
    assert checkout.status_code == 409, checkout.text
    assert checkout.json()["detail"]["code"] == "UNIVERSITY_ACCESS_INCLUDED"


def test_independent_student_never_sees_campus_opportunity() -> None:
    headers = _login(IND_EMAIL)
    response = client.get("/students/jobs", headers=headers)
    assert response.status_code == 200, response.text
    titles = {row["title"] for row in response.json()}
    assert "Tier Public Opportunity" in titles
    assert "Tier Campus Opportunity" not in titles


def test_expired_individual_keeps_recruiter_pipeline_but_premium_preparation_locks() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == IND_EMAIL).one()
        access = db.query(IndividualStudentAccess).filter(IndividualStudentAccess.user_id == user.id).one()
        access.trial_ends_at = utcnow_naive() - timedelta(minutes=1)
        access.paid_access_until = None
        access.status = "trialing"
        db.commit()
    finally:
        db.close()

    headers = _login(IND_EMAIL)
    billing = client.get("/billing/student/status", headers=headers)
    assert billing.status_code == 200, billing.text
    assert billing.json()["status"] == "expired"
    assert billing.json()["payment_required"] is True

    # Core recruiter journey remains available.
    assert client.get("/students/jobs", headers=headers).status_code == 200
    assert client.get("/students/applications", headers=headers).status_code == 200
    assert client.get("/enterprise/interviews", headers=headers).status_code == 200
    assert client.get("/enterprise/offers", headers=headers).status_code == 200
    assert client.get("/enterprise/documents", headers=headers).status_code == 200

    # Preparation endpoints are server-side protected, not merely hidden in the UI.
    readiness = client.get("/enterprise/readiness", headers=headers)
    assert readiness.status_code == 402, readiness.text
    assert readiness.json()["detail"]["code"] == "INDIVIDUAL_PLAN_REQUIRED"

    upload = client.post(
        "/enterprise/documents?document_type=certification&visibility=institution_only",
        headers=headers,
        files={"file": ("test.pdf", b"%PDF-1.4\n%test", "application/pdf")},
    )
    assert upload.status_code == 402, upload.text

    checkout = client.post("/billing/student/checkout", headers=headers)
    assert checkout.status_code == 503, checkout.text
    assert checkout.json()["detail"]["code"] == "PAYMENT_GATEWAY_NOT_CONFIGURED"


def test_razorpay_verification_unlocks_exactly_once(monkeypatch) -> None:
    from app.routers import billing as billing_router

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == IND_EMAIL).one()
        access = db.query(IndividualStudentAccess).filter(IndividualStudentAccess.user_id == user.id).one()
        access.status = "expired"
        access.trial_ends_at = utcnow_naive() - timedelta(days=1)
        access.paid_access_until = None
        tx = PaymentTransaction(
            user_id=user.id,
            individual_access_id=access.id,
            provider="razorpay",
            provider_order_id="order_placeai_tier_test",
            amount_paise=29900,
            currency="INR",
            status="created",
        )
        db.add(tx)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(billing_router.settings, "student_payment_provider", "razorpay")
    monkeypatch.setattr(billing_router.settings, "razorpay_key_id", "rzp_test_placeai")
    monkeypatch.setattr(billing_router.settings, "razorpay_key_secret", "test_secret_for_signature_only")

    payment_id = "pay_placeai_tier_test"
    signature = hmac.new(
        b"test_secret_for_signature_only",
        f"order_placeai_tier_test|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()

    monkeypatch.setattr(
        billing_router,
        "_razorpay_request",
        lambda *_args, **_kwargs: {
            "id": payment_id,
            "order_id": "order_placeai_tier_test",
            "amount": 29900,
            "currency": "INR",
            "status": "captured",
        },
    )

    headers = _login(IND_EMAIL)
    payload = {
        "razorpay_order_id": "order_placeai_tier_test",
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature,
    }
    first = client.post("/billing/student/verify", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["premium_access"] is True

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == IND_EMAIL).one()
        access = db.query(IndividualStudentAccess).filter(IndividualStudentAccess.user_id == user.id).one()
        first_until = access.paid_access_until
        assert first_until is not None
        assert first_until > utcnow_naive() + timedelta(days=29)
    finally:
        db.close()

    second = client.post("/billing/student/verify", headers=headers, json=payload)
    assert second.status_code == 200, second.text

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == IND_EMAIL).one()
        access = db.query(IndividualStudentAccess).filter(IndividualStudentAccess.user_id == user.id).one()
        assert access.paid_access_until == first_until
    finally:
        db.close()


def test_independent_student_can_report_issue_without_institution() -> None:
    headers = _login(IND_EMAIL)
    response = client.post(
        "/enterprise/incidents",
        headers=headers,
        json={
            "category": "fake job",
            "description": "Independent student test report for a suspicious public opportunity.",
            "confidential": True,
        },
    )
    assert response.status_code == 201, response.text

    db = SessionLocal()
    try:
        from app.models import IncidentReport
        user = db.query(User).filter(User.email == IND_EMAIL).one()
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).one()
        row = (
            db.query(IncidentReport)
            .filter(IncidentReport.student_id == profile.id)
            .order_by(IncidentReport.created_at.desc())
            .first()
        )
        assert row is not None
        assert row.organization_id is None
    finally:
        db.close()
