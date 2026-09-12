from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.app import _router_import_failures, app, runtime_readiness_errors
from app.database import Base, SessionLocal, engine
from app.models import (
    Application,
    ApprovalStatus,
    DriveStatus,
    Job,
    MockInterview,
    Organization,
    PlacementDrive,
    RecruiterProfile,
    StudentProfile,
    User,
    UserRole,
)
from app.routers.account_security_secure import router as account_security_secure_router
from app.utils import create_access_token, get_hashed_password

client = TestClient(app)
PASSWORD = "FinalHardening123!"


def auth_for(email: str) -> dict[str, str]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None, email
        token = create_access_token(user.email, int(user.auth_version or 1))
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


def _ensure_fixture() -> dict[str, str]:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "final-hardening-institute").first()
        if not org:
            org = Organization(name="Final Hardening Institute", slug="final-hardening-institute", is_active=True)
            db.add(org)
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

        platform = ensure_user("final-platform@placeai.example.com", "final_platform", UserRole.platform_admin)
        tpo = ensure_user("final-tpo@placeai.example.com", "final_tpo", UserRole.institution_admin, org.id)
        recruiter_user = ensure_user("final-recruiter@placeai.example.com", "final_recruiter", UserRole.recruiter)
        other_recruiter_user = ensure_user("final-other@placeai.example.com", "final_other", UserRole.recruiter)
        student_user = ensure_user("final-student@placeai.example.com", "final_student", UserRole.student, org.id)
        unverified_user = ensure_user("final-unverified@placeai.example.com", "final_unverified", UserRole.student, org.id)

        def ensure_recruiter(user: User, company: str) -> RecruiterProfile:
            row = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == user.id).first()
            if not row:
                row = RecruiterProfile(
                    user_id=user.id,
                    full_name=company + " Recruiter",
                    company_name=company,
                    is_verified=True,
                    provisioned_by_organization_id=org.id,
                )
                db.add(row)
                db.flush()
            return row

        recruiter = ensure_recruiter(recruiter_user, "Final Employer")
        other_recruiter = ensure_recruiter(other_recruiter_user, "Other Final Employer")

        def ensure_student(user: User, *, verified: bool) -> StudentProfile:
            row = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
            if not row:
                row = StudentProfile(
                    user_id=user.id,
                    organization_id=org.id,
                    college=org.name,
                    full_name=user.username,
                    degree="B.Tech",
                    branch="Computer Science",
                    graduation_year=2026,
                    cgpa=8.4,
                    is_verified=verified,
                )
                db.add(row)
                db.flush()
            else:
                row.organization_id = org.id
                row.is_verified = verified
            return row

        student = ensure_student(student_user, verified=True)
        unverified = ensure_student(unverified_user, verified=False)

        campus_job = db.query(Job).filter(Job.title == "Final Visible Campus Role").first()
        if not campus_job:
            campus_job = Job(
                recruiter_id=recruiter.id,
                title="Final Visible Campus Role",
                description="Approved campus role for final authorization boundary tests.",
                job_type="Full-time",
                visibility="campus",
                target_organization_id=org.id,
                approval_status=ApprovalStatus.approved,
                is_active=True,
                deadline=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7),
            )
            db.add(campus_job)
            db.flush()

        open_drive = db.query(PlacementDrive).filter(PlacementDrive.title == "Final Open Drive").first()
        if not open_drive:
            open_drive = PlacementDrive(
                organization_id=org.id,
                job_id=campus_job.id,
                title="Final Open Drive",
                status=DriveStatus.open,
                registration_deadline=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=3),
            )
            db.add(open_drive)
            db.flush()

        db.commit()
        return {
            "org": org.id,
            "platform": platform.email,
            "tpo": tpo.email,
            "recruiter": recruiter_user.email,
            "other_recruiter": other_recruiter_user.email,
            "student": student_user.email,
            "unverified": unverified_user.email,
            "student_id": student.id,
            "unverified_id": unverified.id,
            "recruiter_id": recruiter.id,
            "other_recruiter_id": other_recruiter.id,
            "campus_job": campus_job.id,
            "open_drive": open_drive.id,
        }
    finally:
        db.close()


def test_hardened_router_modules_bootstrap_cleanly_and_own_runtime_contracts_once() -> None:
    # An earlier resilience test intentionally probes a missing router and verifies that
    # the failure is contained. Remove only that synthetic probe before asserting the
    # real startup state; production bootstrap never imports this name.
    synthetic_name = "intentionally_missing"
    synthetic_code = "ROUTER_IMPORT_INTENTIONALLY_MISSING_FAILED"
    _router_import_failures.pop(synthetic_name, None)
    runtime_readiness_errors[:] = [code for code in runtime_readiness_errors if code != synthetic_code]

    assert _router_import_failures == {}, _router_import_failures
    assert not [code for code in runtime_readiness_errors if code.startswith("ROUTER_IMPORT_")]

    # Password rotation has its own end-to-end test earlier in the suite. Inspect its
    # canonical hardened router here instead of the shared app route collection, which
    # other resilience tests may intentionally mutate during the same pytest process.
    change_password_routes = [
        route
        for route in account_security_secure_router.routes
        if getattr(route, "path", None) == "/auth/change-password"
        and "POST" in (getattr(route, "methods", set()) or set())
    ]
    assert len(change_password_routes) == 1
    assert "account_security_secure" in change_password_routes[0].endpoint.__module__
    app_source = Path("app/app.py").read_text(encoding="utf-8")
    assert '("/auth/change-password", "POST")' in app_source
    assert "_include_router(account_security, ACCOUNT_SECURITY_REPLACEMENTS)" in app_source
    assert "_include_router(account_security_secure)" in app_source

    contracts = {
        ("/jobs", "GET"): "jobs_secure",
        ("/jobs/{job_id}", "GET"): "jobs_secure",
        ("/enterprise/drives", "GET"): "enterprise_secure",
        ("/enterprise/drives/{drive_id}/pipeline", "GET"): "enterprise_secure",
        ("/enterprise/drives/{drive_id}/eligibility", "GET"): "enterprise_secure",
        ("/enterprise/communications", "GET"): "enterprise_secure",
        ("/enterprise/attendance/sessions", "GET"): "enterprise_secure",
        ("/enterprise/attendance/check-in", "POST"): "enterprise_secure",
        ("/enterprise/search", "GET"): "enterprise_secure",
        ("/enterprise/calendar", "GET"): "enterprise_secure",
        ("/institutions/dashboard", "GET"): "institution_secure",
        ("/institutions/jobs/{job_id}/approval", "PATCH"): "institution_secure",
        ("/institutions/drives", "POST"): "institution_secure",
        ("/institutions/drives/{drive_id}", "PUT"): "institution_secure",
        ("/institutions/applications", "GET"): "institution_secure",
        ("/enterprise/announcements", "GET"): "enterprise",
    }
    for (path, method), owner in contracts.items():
        matches = [
            route for route in app.routes
            if getattr(route, "path", None) == path and method in (getattr(route, "methods", set()) or set())
        ]
        assert len(matches) == 1, (path, method, len(matches))
        assert owner in matches[0].endpoint.__module__, (path, matches[0].endpoint.__module__)


def test_unverified_student_cannot_discover_campus_opportunities() -> None:
    fixture = _ensure_fixture()
    headers = auth_for(fixture["unverified"])

    drives = client.get("/enterprise/drives", headers=headers)
    assert drives.status_code == 200 and drives.json() == []
    search = client.get("/enterprise/search", headers=headers, params={"q": "Final Visible Campus Role"})
    assert search.status_code == 200 and search.json() == []
    generic_jobs = client.get("/jobs", headers=headers)
    assert generic_jobs.status_code == 200
    assert all(row["id"] != fixture["campus_job"] for row in generic_jobs.json())
    calendar = client.get("/enterprise/calendar", headers=headers)
    assert calendar.status_code == 403
    attendance = client.get("/enterprise/attendance/sessions", headers=headers)
    assert attendance.status_code == 403


def test_draft_campus_drive_never_leaks_to_verified_student_surfaces() -> None:
    fixture = _ensure_fixture()
    db = SessionLocal()
    try:
        draft_job = db.query(Job).filter(Job.title == "Final Hidden Draft Role").first()
        if not draft_job:
            draft_job = Job(
                recruiter_id=fixture["recruiter_id"],
                title="Final Hidden Draft Role",
                description="Campus role that must remain invisible while its drive is draft.",
                job_type="Full-time",
                visibility="campus",
                target_organization_id=fixture["org"],
                approval_status=ApprovalStatus.approved,
                is_active=True,
            )
            db.add(draft_job)
            db.flush()
        draft_drive = db.query(PlacementDrive).filter(PlacementDrive.title == "Final Hidden Draft Drive").first()
        if not draft_drive:
            draft_drive = PlacementDrive(
                organization_id=fixture["org"],
                job_id=draft_job.id,
                title="Final Hidden Draft Drive",
                status=DriveStatus.draft,
            )
            db.add(draft_drive)
            db.flush()
        db.commit()
        draft_job_id = draft_job.id
        draft_drive_id = draft_drive.id
    finally:
        db.close()

    headers = auth_for(fixture["student"])
    drives = client.get("/enterprise/drives", headers=headers)
    assert drives.status_code == 200
    assert all(row["id"] != draft_drive_id for row in drives.json())
    assert client.get(f"/enterprise/drives/{draft_drive_id}/pipeline", headers=headers).status_code == 404
    assert client.get(f"/enterprise/drives/{draft_drive_id}/eligibility", headers=headers).status_code == 404
    search = client.get("/enterprise/search", headers=headers, params={"q": "Final Hidden Draft Role"})
    assert search.status_code == 200 and search.json() == []
    mock_jobs = client.get("/mock-interview/jobs", headers=headers)
    assert mock_jobs.status_code == 200
    assert all(row["id"] != draft_job_id for row in mock_jobs.json())


def test_expired_campus_job_cannot_be_approved_or_opened() -> None:
    fixture = _ensure_fixture()
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.title == "Final Expired Campus Role").first()
        if not job:
            job = Job(
                recruiter_id=fixture["recruiter_id"],
                title="Final Expired Campus Role",
                description="Expired campus role for approval-boundary regression coverage.",
                job_type="Full-time",
                visibility="campus",
                target_organization_id=fixture["org"],
                approval_status=ApprovalStatus.pending,
                is_active=False,
                deadline=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
            )
            db.add(job)
            db.flush()
        db.commit()
        job_id = job.id
    finally:
        db.close()

    response = client.patch(
        f"/institutions/jobs/{job_id}/approval",
        headers=auth_for(fixture["tpo"]),
        json={"approval_status": "approved"},
    )
    assert response.status_code == 400


def test_institution_application_feed_is_scoped_by_student_institution() -> None:
    fixture = _ensure_fixture()
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.title == "Final Public Audit Role").first()
        if not job:
            job = Job(
                recruiter_id=fixture["recruiter_id"],
                title="Final Public Audit Role",
                description="Public role for institution reporting scope regression coverage.",
                job_type="Full-time",
                visibility="public",
                approval_status=ApprovalStatus.approved,
                is_active=True,
            )
            db.add(job)
            db.flush()
        app_row = db.query(Application).filter(
            Application.student_id == fixture["student_id"], Application.job_id == job.id
        ).first()
        if not app_row:
            app_row = Application(student_id=fixture["student_id"], job_id=job.id)
            db.add(app_row)
            db.flush()
        db.commit()
        application_id = app_row.id
    finally:
        db.close()

    feed = client.get("/institutions/applications", headers=auth_for(fixture["tpo"]))
    assert feed.status_code == 200, feed.text
    assert any(row["id"] == application_id for row in feed.json())


def test_recruiter_never_receives_other_employers_mock_interview_history() -> None:
    fixture = _ensure_fixture()
    db = SessionLocal()
    try:
        own_job = db.query(Job).filter(Job.title == "Final Recruiter Candidate Access Role").first()
        if not own_job:
            own_job = Job(
                recruiter_id=fixture["recruiter_id"],
                title="Final Recruiter Candidate Access Role",
                description="Role establishing legitimate candidate access for recruiter isolation testing.",
                job_type="Full-time",
                visibility="public",
                approval_status=ApprovalStatus.approved,
                is_active=True,
            )
            db.add(own_job)
            db.flush()
        if not db.query(Application).filter(
            Application.student_id == fixture["student_id"], Application.job_id == own_job.id
        ).first():
            db.add(Application(student_id=fixture["student_id"], job_id=own_job.id))

        other_job = db.query(Job).filter(Job.title == "Other Employer Coaching Role").first()
        if not other_job:
            other_job = Job(
                recruiter_id=fixture["other_recruiter_id"],
                title="Other Employer Coaching Role",
                description="Private coaching isolation role belonging to a different employer.",
                job_type="Full-time",
                visibility="public",
                approval_status=ApprovalStatus.approved,
                is_active=True,
            )
            db.add(other_job)
            db.flush()
        interview = db.query(MockInterview).filter(
            MockInterview.student_id == fixture["student_id"], MockInterview.job_id == other_job.id
        ).first()
        if not interview:
            interview = MockInterview(
                student_id=fixture["student_id"],
                job_id=other_job.id,
                questions_json='[{"question_id":1,"question":"Q?","category":"technical"}]',
                answers_json='[{"question_id":1,"question":"Q?","answer":"A"}]',
                evaluation_json='{"evaluations":[{"question_id":1,"score":80}]}',
                overall_score=80,
                overall_feedback="Other employer coaching data",
            )
            db.add(interview)
            db.flush()
        db.commit()
        interview_id = interview.id
    finally:
        db.close()

    response = client.get(
        f"/recruiters/students/{fixture['student_id']}/interviews",
        headers=auth_for(fixture["recruiter"]),
    )
    assert response.status_code == 200, response.text
    assert all(row["id"] != interview_id for row in response.json())
