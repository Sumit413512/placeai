from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.routers.ai as ai_router
from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import (
    Application,
    ApplicationStatus,
    ApprovalStatus,
    Job,
    Organization,
    RecruiterProfile,
    StudentProfile,
    User,
    UserRole,
)
from app.utils import get_hashed_password

client = TestClient(app)
PASSWORD = "HardeningPass123!"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(email: str) -> str:
    response = client.post("/auth/login-json", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _ensure_fixture_data() -> dict[str, str]:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        org_a = db.query(Organization).filter(Organization.slug == "hardening-a").first()
        if not org_a:
            org_a = Organization(name="Hardening Institute A", slug="hardening-a", is_active=True)
            db.add(org_a)
            db.flush()
        org_b = db.query(Organization).filter(Organization.slug == "hardening-b").first()
        if not org_b:
            org_b = Organization(name="Hardening Institute B", slug="hardening-b", is_active=True)
            db.add(org_b)
            db.flush()

        def ensure_user(email: str, username: str, role: UserRole, org_id: str | None = None) -> User:
            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(
                    email=email,
                    username=username,
                    hashed_password=get_hashed_password(PASSWORD),
                    role=role,
                    organization_id=org_id,
                    email_verified=True,
                    is_active=True,
                )
                db.add(user)
                db.flush()
            return user

        tpo = ensure_user("hardening-tpo@placeai.example.com", "hardening_tpo", UserRole.institution_admin, org_a.id)
        recruiter_user = ensure_user("hardening-recruiter@placeai.example.com", "hardening_recruiter", UserRole.recruiter)
        student_a_user = ensure_user("hardening-student-a@placeai.example.com", "hardening_student_a", UserRole.student, org_a.id)
        student_b_user = ensure_user("hardening-student-b@placeai.example.com", "hardening_student_b", UserRole.student, org_b.id)

        recruiter = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == recruiter_user.id).first()
        if not recruiter:
            recruiter = RecruiterProfile(
                user_id=recruiter_user.id,
                full_name="Hardening Recruiter",
                company_name="Hardening Employer",
                is_verified=True,
            )
            db.add(recruiter)
            db.flush()

        student_a = db.query(StudentProfile).filter(StudentProfile.user_id == student_a_user.id).first()
        if not student_a:
            student_a = StudentProfile(
                user_id=student_a_user.id,
                organization_id=org_a.id,
                college=org_a.name,
                full_name="Hardening Student A",
                cgpa=8.5,
            )
            student_a.skills = ["Python", "SQL"]
            db.add(student_a)
            db.flush()
        student_b = db.query(StudentProfile).filter(StudentProfile.user_id == student_b_user.id).first()
        if not student_b:
            student_b = StudentProfile(
                user_id=student_b_user.id,
                organization_id=org_b.id,
                college=org_b.name,
                full_name="Hardening Student B",
                cgpa=8.0,
            )
            db.add(student_b)
            db.flush()

        campus_job = db.query(Job).filter(Job.title == "Hardening Campus Role").first()
        if not campus_job:
            campus_job = Job(
                recruiter_id=recruiter.id,
                title="Hardening Campus Role",
                description="Campus-targeted role used for production approval integrity testing.",
                visibility="campus",
                target_organization_id=org_a.id,
                approval_status=ApprovalStatus.approved,
                is_active=True,
            )
            campus_job.required_skills = ["Python"]
            db.add(campus_job)
            db.flush()

        public_job = db.query(Job).filter(Job.title == "Hardening Public Role").first()
        if not public_job:
            public_job = Job(
                recruiter_id=recruiter.id,
                title="Hardening Public Role",
                description="Public role used to verify institution activity follows its own students.",
                visibility="public",
                target_organization_id=None,
                approval_status=ApprovalStatus.approved,
                is_active=True,
            )
            public_job.required_skills = ["SQL"]
            db.add(public_job)
            db.flush()

        app_a_public = db.query(Application).filter(Application.student_id == student_a.id, Application.job_id == public_job.id).first()
        if not app_a_public:
            app_a_public = Application(student_id=student_a.id, job_id=public_job.id, status=ApplicationStatus.hired)
            db.add(app_a_public)
        else:
            app_a_public.status = ApplicationStatus.hired

        app_a_campus = db.query(Application).filter(Application.student_id == student_a.id, Application.job_id == campus_job.id).first()
        if not app_a_campus:
            app_a_campus = Application(student_id=student_a.id, job_id=campus_job.id, status=ApplicationStatus.applied)
            db.add(app_a_campus)

        foreign_app = db.query(Application).filter(Application.student_id == student_b.id, Application.job_id == campus_job.id).first()
        if not foreign_app:
            foreign_app = Application(student_id=student_b.id, job_id=campus_job.id, status=ApplicationStatus.offered)
            db.add(foreign_app)
        else:
            foreign_app.status = ApplicationStatus.offered

        db.commit()
        return {
            "org_a": org_a.id,
            "campus_job": campus_job.id,
            "public_job": public_job.id,
            "public_application": app_a_public.id,
            "tpo_email": tpo.email,
            "recruiter_email": recruiter_user.email,
            "student_a_email": student_a_user.email,
        }
    finally:
        db.close()


def test_institution_dashboard_follows_its_students_not_only_target_jobs() -> None:
    fixture = _ensure_fixture_data()
    tpo_token = login(fixture["tpo_email"])
    response = client.get("/institutions/dashboard", headers=auth(tpo_token))
    assert response.status_code == 200, response.text
    data = response.json()
    # Student A applied to one campus job and one platform-wide public job.
    assert data["total_applications"] == 2
    # The offered application from Student B must not leak into Institute A metrics.
    assert data["offers"] == 1
    assert data["hires"] == 1
    assert data["placement_rate"] == 100.0
    assert data["active_jobs"] == 1


def test_campus_job_material_edit_requires_reapproval_and_deactivation() -> None:
    fixture = _ensure_fixture_data()
    recruiter_token = login(fixture["recruiter_email"])
    tpo_token = login(fixture["tpo_email"])

    updated = client.put(
        f"/jobs/{fixture['campus_job']}",
        headers=auth(recruiter_token),
        json={"salary_range": "₹12–14 LPA"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["approval_status"] == "pending"
    assert updated.json()["is_active"] is False

    approved = client.patch(
        f"/institutions/jobs/{fixture['campus_job']}/approval",
        headers=auth(tpo_token),
        json={"approval_status": "approved"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval_status"] == "approved"
    assert approved.json()["is_active"] is True


def test_public_job_target_consistency_and_campus_approval_guard() -> None:
    fixture = _ensure_fixture_data()
    recruiter_token = login(fixture["recruiter_email"])
    tpo_token = login(fixture["tpo_email"])

    invalid_create = client.post(
        "/jobs",
        headers=auth(recruiter_token),
        json={
            "title": "Invalid Public Target",
            "description": "A public listing must not carry a hidden campus target institution.",
            "visibility": "public",
            "target_organization_slug": "hardening-a",
        },
    )
    assert invalid_create.status_code == 400

    db = SessionLocal()
    try:
        public_job = db.query(Job).filter(Job.id == fixture["public_job"]).first()
        public_job.target_organization_id = fixture["org_a"]
        db.commit()
    finally:
        db.close()

    improper_approval = client.patch(
        f"/institutions/jobs/{fixture['public_job']}/approval",
        headers=auth(tpo_token),
        json={"approval_status": "approved"},
    )
    assert improper_approval.status_code == 404

    db = SessionLocal()
    try:
        public_job = db.query(Job).filter(Job.id == fixture["public_job"]).first()
        public_job.target_organization_id = None
        db.commit()
    finally:
        db.close()


def test_ai_score_normalization_is_finite_clamped_and_reasoning_is_bounded() -> None:
    assert ai_router._normalize_ai_score(-20) == 0.0
    assert ai_router._normalize_ai_score(120) == 100.0
    assert ai_router._normalize_ai_score("81.5") == 81.5
    for invalid in ("NaN", "Infinity", float("nan"), float("inf"), object()):
        with pytest.raises(HTTPException) as exc:
            ai_router._normalize_ai_score(invalid)
        assert exc.value.status_code == 502
    assert len(ai_router._bounded_reasoning("x" * 5000)) == ai_router.MAX_AI_REASONING_CHARS


def test_ai_candidate_ranking_sanitizes_before_database_persistence(monkeypatch) -> None:
    fixture = _ensure_fixture_data()
    recruiter_token = login(fixture["recruiter_email"])

    monkeypatch.setattr(ai_router, "get_gemini_client", lambda: object())
    monkeypatch.setattr(
        ai_router,
        "call_gemini",
        lambda _client, _prompt: json.dumps([
            {
                "application_id": fixture["public_application"],
                "score": 145,
                "reasoning": "R" * 5000,
            }
        ]),
    )
    response = client.post(f"/ai/rank-candidates/{fixture['public_job']}", headers=auth(recruiter_token))
    assert response.status_code == 200, response.text
    ranked = response.json()["ranked_candidates"][0]
    assert ranked["ai_match_score"] == 100.0
    assert len(ranked["ai_match_reasoning"]) == ai_router.MAX_AI_REASONING_CHARS

    db = SessionLocal()
    try:
        application = db.query(Application).filter(Application.id == fixture["public_application"]).first()
        assert application.ai_match_score == 100.0
        assert len(application.ai_match_reasoning) == ai_router.MAX_AI_REASONING_CHARS
    finally:
        db.close()

    monkeypatch.setattr(
        ai_router,
        "call_gemini",
        lambda _client, _prompt: json.dumps([
            {
                "application_id": fixture["public_application"],
                "score": "NaN",
                "reasoning": "must not persist",
            }
        ]),
    )
    invalid = client.post(f"/ai/rank-candidates/{fixture['public_job']}", headers=auth(recruiter_token))
    assert invalid.status_code == 502

    db = SessionLocal()
    try:
        application = db.query(Application).filter(Application.id == fixture["public_application"]).first()
        assert application.ai_match_score == 100.0
        assert "must not persist" not in (application.ai_match_reasoning or "")
    finally:
        db.close()
