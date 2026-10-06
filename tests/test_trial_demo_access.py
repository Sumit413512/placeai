from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.billing_models import StudentSubscription
from app.database import Base, SessionLocal, engine
from app.models import Job, MockInterview, Organization, RecruiterProfile, StudentProfile, User, UserRole, utcnow
from app.trial_demo_access import (
    TRIAL_DEMO_COMPANY_NAME,
    TRIAL_DEMO_FREE_ATTEMPTS,
    TRIAL_DEMO_JOB_TITLE,
    enforce_trial_demo_start,
    trial_demo_access_state,
)
from app.utils import get_hashed_password


def _fixture(tag: str):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    recruiter_user = User(
        email=f"technova-demo-recruiter-{tag}@placeai.example.com",
        username=f"technova_demo_recruiter_{tag}",
        hashed_password=get_hashed_password("RecruiterPass123!"),
        role=UserRole.recruiter,
        email_verified=True,
        is_active=True,
    )
    student_user = User(
        email=f"fresh-demo-student-{tag}@placeai.example.com",
        username=f"fresh_demo_student_{tag}",
        hashed_password=get_hashed_password("StudentPass123!"),
        role=UserRole.student,
        email_verified=True,
        is_active=True,
        created_at=utcnow(),
    )
    db.add_all([recruiter_user, student_user])
    db.flush()

    recruiter = RecruiterProfile(
        user_id=recruiter_user.id,
        full_name="TechNova Demo Recruiter",
        company_name=TRIAL_DEMO_COMPANY_NAME,
        is_verified=True,
    )
    student = StudentProfile(
        user_id=student_user.id,
        full_name="Fresh Demo Student",
        placement_opt_in=True,
    )
    db.add_all([recruiter, student])
    db.flush()

    job = Job(
        recruiter_id=recruiter.id,
        title=TRIAL_DEMO_JOB_TITLE,
        description="Public PlaceAI demo assessment role.",
        visibility="public",
        is_active=True,
        deadline=utcnow() + timedelta(days=90),
    )
    job.required_skills = ["Python", "Problem Solving"]
    db.add(job)
    db.commit()
    db.refresh(student_user)
    db.refresh(student)
    db.refresh(job)
    return db, student_user, student, job


def test_active_trial_student_gets_exactly_one_free_demo_attempt():
    db, user, profile, job = _fixture("free")
    try:
        before = trial_demo_access_state(user, profile, job, db)
        assert before["access_mode"] == "trial"
        assert before["can_start"] is True
        assert before["attempts_used"] == 0
        assert before["free_attempts_remaining"] == TRIAL_DEMO_FREE_ATTEMPTS == 1
        assert enforce_trial_demo_start(user, profile, job, db)["can_start"] is True

        db.add(MockInterview(
            student_id=profile.id,
            job_id=job.id,
            questions_json='[{"question_id":1,"question":"Demo?","category":"technical"}]',
            answers_json="[]",
        ))
        db.commit()

        after = trial_demo_access_state(user, profile, job, db)
        assert after["can_start"] is False
        assert after["attempts_used"] == 1
        assert after["free_attempts_remaining"] == 0
        assert "one free TechNova demo assessment attempt" in after["access_note"]

        with pytest.raises(HTTPException) as exc:
            enforce_trial_demo_start(user, profile, job, db)
        assert exc.value.status_code == 402
        assert exc.value.detail["code"] == "PREMIUM_REQUIRED"
        assert exc.value.detail["attempts_used"] == 1
        assert exc.value.detail["free_attempts_remaining"] == 0
        assert "already used your one free TechNova demo assessment attempt" in exc.value.detail["message"]
    finally:
        db.close()


def test_expired_trial_without_demo_attempt_cannot_start_free_demo():
    db, user, profile, job = _fixture("expired")
    try:
        user.created_at = utcnow() - timedelta(days=5)
        db.commit()

        state = trial_demo_access_state(user, profile, job, db)
        assert state["access_mode"] != "trial"
        assert state["attempts_used"] == 0
        assert state["can_start"] is False
        assert state["free_attempts_remaining"] == 0

        with pytest.raises(HTTPException) as exc:
            enforce_trial_demo_start(user, profile, job, db)
        assert exc.value.status_code == 402
        assert exc.value.detail["code"] == "PREMIUM_REQUIRED"
        assert "trial has ended" in exc.value.detail["message"].lower()
    finally:
        db.close()


def test_paid_independent_student_can_continue_after_free_attempt():
    db, user, profile, job = _fixture("paid")
    try:
        db.add(MockInterview(
            student_id=profile.id,
            job_id=job.id,
            questions_json='[{"question_id":1,"question":"Demo?","category":"technical"}]',
            answers_json="[]",
        ))
        db.add(StudentSubscription(
            student_id=profile.id,
            plan_code="placeai_independent_monthly",
            status="active",
            amount_paise=29900,
            starts_at=utcnow(),
            expires_at=utcnow() + timedelta(days=30),
        ))
        db.commit()

        state = enforce_trial_demo_start(user, profile, job, db)
        assert state["access_mode"] == "premium"
        assert state["can_start"] is True
        assert state["free_attempts_remaining"] is None
    finally:
        db.close()


def test_institution_sponsored_student_can_continue_after_demo_attempt():
    db, user, profile, job = _fixture("campus")
    try:
        org = Organization(
            name="Contract College",
            slug="contract-college-demo-access",
            is_active=True,
        )
        db.add(org)
        db.flush()
        user.organization_id = org.id
        profile.organization_id = org.id
        profile.college = org.name
        profile.is_verified = True
        db.add(MockInterview(
            student_id=profile.id,
            job_id=job.id,
            questions_json='[{"question_id":1,"question":"Demo?","category":"technical"}]',
            answers_json="[]",
        ))
        db.commit()

        state = enforce_trial_demo_start(user, profile, job, db)
        assert state["access_mode"] == "campus_sponsored"
        assert state["can_start"] is True
        assert state["free_attempts_remaining"] is None
    finally:
        db.close()
