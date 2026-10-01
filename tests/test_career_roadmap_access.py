from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
import pytest

from app.billing_models import StudentSubscription
from app.database import Base, SessionLocal, engine
from app.models import Organization, StudentProfile, User, UserRole, generate_uuid, utcnow
from app.roadmap_access import (
    CAREER_ROADMAP_FEATURE_CODE,
    CAREER_ROADMAP_ONE_TIME_PRICE_PAISE,
    ensure_roadmap_access,
    roadmap_access_status,
)
from app.roadmap_models import StudentFeaturePurchase
from app.student_entitlements import student_access_status
from app.utils import get_hashed_password


def _student(kind: str):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    tag = generate_uuid()[:12]
    user = User(
        email=f"roadmap-{kind}-{tag}@placeai.example.com",
        username=f"roadmap_{kind}_{tag}",
        hashed_password=get_hashed_password("StudentPass123!"),
        role=UserRole.student,
        email_verified=True,
        is_active=True,
        created_at=utcnow(),
    )
    db.add(user)
    db.flush()
    profile = StudentProfile(user_id=user.id, full_name=f"Roadmap {kind}")
    db.add(profile)
    db.commit()
    db.refresh(user)
    db.refresh(profile)
    return db, user, profile


def test_free_trial_does_not_unlock_career_roadmap():
    db, user, _ = _student("trial")
    try:
        base = student_access_status(user, db)
        assert base["access_mode"] == "trial"
        assert base["premium_access"] is True

        roadmap = roadmap_access_status(user, db, base_access=base)
        assert roadmap["allowed"] is False
        assert roadmap["access_source"] == "locked"
        assert roadmap["price_inr"] == 20

        with pytest.raises(HTTPException) as exc:
            ensure_roadmap_access(user, db)
        assert exc.value.status_code == 402
        assert exc.value.detail["code"] == "CAREER_ROADMAP_ACCESS_REQUIRED"
    finally:
        db.close()


def test_paid_premium_student_gets_career_roadmap():
    db, user, profile = _student("premium")
    try:
        db.add(StudentSubscription(
            student_id=profile.id,
            plan_code="placeai_independent_monthly",
            status="active",
            amount_paise=29900,
            starts_at=utcnow(),
            expires_at=utcnow() + timedelta(days=30),
        ))
        db.commit()
        access = ensure_roadmap_access(user, db)
        assert access["allowed"] is True
        assert access["access_source"] == "premium"
    finally:
        db.close()


def test_institution_sponsored_student_gets_career_roadmap():
    db, user, profile = _student("campus")
    try:
        org = Organization(name=f"Roadmap College {generate_uuid()[:8]}", slug=f"roadmap-college-{generate_uuid()[:8]}", is_active=True)
        db.add(org)
        db.flush()
        user.organization_id = org.id
        profile.organization_id = org.id
        db.commit()
        access = ensure_roadmap_access(user, db)
        assert access["allowed"] is True
        assert access["access_source"] == "institution"
    finally:
        db.close()


def test_roadmap_only_purchase_does_not_escalate_to_premium():
    db, user, profile = _student("feature")
    try:
        db.add(StudentFeaturePurchase(
            student_id=profile.id,
            feature_code=CAREER_ROADMAP_FEATURE_CODE,
            status="paid",
            provider="test",
            provider_payment_id=f"roadmap-test-{generate_uuid()}",
            amount_paise=CAREER_ROADMAP_ONE_TIME_PRICE_PAISE,
            purchased_at=utcnow(),
        ))
        db.commit()

        roadmap = ensure_roadmap_access(user, db)
        base = student_access_status(user, db)
        assert roadmap["allowed"] is True
        assert roadmap["access_source"] == "one_time_purchase"
        assert base["access_mode"] == "trial"
        assert base["plan_code"] == "placeai_independent_monthly"
    finally:
        db.close()
