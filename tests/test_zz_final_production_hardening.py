from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.app import app
from app.database import SessionLocal
from app.models import Job, MockInterview, Organization, RecruiterProfile, StudentProfile, User
from app.utils import create_access_token

client = TestClient(app)


def auth_for(email: str) -> dict[str, str]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None, email
        token = create_access_token(user.email, int(user.auth_version or 1))
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


def test_hardened_routes_replace_legacy_handlers_exactly_once() -> None:
    contracts = {
        ("/enterprise/drives", "GET"): "enterprise_secure",
        ("/enterprise/drives/{drive_id}/pipeline", "GET"): "enterprise_secure",
        ("/enterprise/drives/{drive_id}/eligibility", "GET"): "enterprise_secure",
        ("/enterprise/communications", "GET"): "enterprise_secure",
        ("/enterprise/announcements", "GET"): "enterprise_secure",
        ("/enterprise/attendance/sessions", "GET"): "enterprise_secure",
        ("/enterprise/attendance/check-in", "POST"): "enterprise_secure",
        ("/enterprise/search", "GET"): "enterprise_secure",
        ("/enterprise/calendar", "GET"): "enterprise_secure",
        ("/institutions/dashboard", "GET"): "institution_secure",
        ("/institutions/jobs/{job_id}/approval", "PATCH"): "institution_secure",
        ("/institutions/drives", "POST"): "institution_secure",
        ("/institutions/drives/{drive_id}", "PUT"): "institution_secure",
        ("/institutions/applications", "GET"): "institution_secure",
    }
    for (path, method), owner in contracts.items():
        matches = [
            route for route in app.routes
            if getattr(route, "path", None) == path and method in (getattr(route, "methods", set()) or set())
        ]
        assert len(matches) == 1, (path, method, len(matches))
        assert owner in matches[0].endpoint.__module__


def test_unverified_self_signup_cannot_enter_campus_enterprise_surfaces() -> None:
    platform = auth_for("platform@placeai.example.com")
    organizations = client.get("/platform/organizations", headers=platform)
    assert organizations.status_code == 200
    assert any(row["slug"] == "northstar" for row in organizations.json())

    email = "unverified.final@northstar.example.com"
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
    finally:
        db.close()
    if not existing:
        signup = client.post("/auth/signup", json={
            "username": "unverifiedfinal",
            "email": email,
            "password": "UnverifiedPass123!",
            "role": "student",
            "organization_slug": "northstar",
        })
        assert signup.status_code == 201, signup.text
    headers = auth_for(email)

    drives = client.get("/enterprise/drives", headers=headers)
    assert drives.status_code == 200 and drives.json() == []
    announcements = client.get("/enterprise/announcements", headers=headers)
    assert announcements.status_code == 403
    attendance = client.get("/enterprise/attendance/sessions", headers=headers)
    assert attendance.status_code == 403
    calendar = client.get("/enterprise/calendar", headers=headers)
    assert calendar.status_code == 403
    communications = client.get("/enterprise/communications", headers=headers)
    assert communications.status_code == 403

    search = client.get("/enterprise/search", headers=headers, params={"q": "Graduate"})
    assert search.status_code == 200
    assert all(row["type"] != "opportunity" or row["title"] != "Graduate Software Engineer" for row in search.json())


def test_draft_or_expired_campus_drives_do_not_leak_to_verified_students_or_mock_interviews() -> None:
    tpo = auth_for("tpo@northstar.example.com")
    recruiter = auth_for("recruiter@acme.example.com")
    student = auth_for("student@northstar.example.com")

    create_job = client.post("/jobs", headers=recruiter, json={
        "title": "Final Hidden Campus Role",
        "description": "A campus-only role used to verify draft-drive visibility boundaries in production.",
        "location": "Pune",
        "job_type": "Full-time",
        "required_skills": ["Python"],
        "visibility": "campus",
        "target_organization_slug": "northstar",
    })
    assert create_job.status_code == 201, create_job.text
    job_id = create_job.json()["id"]
    approval = client.patch(
        f"/institutions/jobs/{job_id}/approval",
        headers=tpo,
        json={"approval_status": "approved"},
    )
    assert approval.status_code == 200, approval.text
    draft = client.post("/institutions/drives", headers=tpo, json={
        "job_id": job_id,
        "title": "Final Draft Drive",
        "status": "draft",
    })
    assert draft.status_code == 201, draft.text
    draft_id = draft.json()["id"]

    drives = client.get("/enterprise/drives", headers=student)
    assert drives.status_code == 200
    assert all(row["id"] != draft_id for row in drives.json())
    pipeline = client.get(f"/enterprise/drives/{draft_id}/pipeline", headers=student)
    assert pipeline.status_code == 404
    eligibility = client.get(f"/enterprise/drives/{draft_id}/eligibility", headers=student)
    assert eligibility.status_code == 404
    search = client.get("/enterprise/search", headers=student, params={"q": "Final Hidden Campus Role"})
    assert search.status_code == 200 and search.json() == []
    mock_jobs = client.get("/mock-interview/jobs", headers=student)
    assert mock_jobs.status_code == 200
    assert all(row["id"] != job_id for row in mock_jobs.json())

    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    opened = client.put(f"/institutions/drives/{draft_id}", headers=tpo, json={
        "status": "open",
        "registration_deadline": expired,
    })
    assert opened.status_code == 400


def test_expired_campus_job_cannot_be_approved() -> None:
    recruiter = auth_for("recruiter@acme.example.com")
    tpo = auth_for("tpo@northstar.example.com")
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    response = client.post("/jobs", headers=recruiter, json={
        "title": "Expired Final Campus Role",
        "description": "This intentionally expired role must never become an active campus listing.",
        "location": "Pune",
        "job_type": "Full-time",
        "required_skills": ["SQL"],
        "deadline": expired,
        "visibility": "campus",
        "target_organization_slug": "northstar",
    })
    assert response.status_code == 201, response.text
    approval = client.patch(
        f"/institutions/jobs/{response.json()['id']}/approval",
        headers=tpo,
        json={"approval_status": "approved"},
    )
    assert approval.status_code == 400


def test_institution_application_feed_includes_own_students_public_job_activity() -> None:
    recruiter = auth_for("recruiter@acme.example.com")
    student = auth_for("student@northstar.example.com")
    tpo = auth_for("tpo@northstar.example.com")

    response = client.post("/jobs", headers=recruiter, json={
        "title": "Final Public Audit Role",
        "description": "A public role used to verify institution application reporting remains student-scoped.",
        "location": "Remote",
        "job_type": "Full-time",
        "required_skills": ["Python"],
        "visibility": "public",
    })
    assert response.status_code == 201, response.text
    job_id = response.json()["id"]
    apply = client.post(f"/students/jobs/{job_id}/apply", headers=student, json={"cover_note": "Public audit."})
    assert apply.status_code == 201, apply.text
    application_id = apply.json()["id"]

    feed = client.get("/institutions/applications", headers=tpo)
    assert feed.status_code == 200, feed.text
    assert any(row["id"] == application_id for row in feed.json())


def test_recruiter_sees_only_mock_interviews_for_own_jobs() -> None:
    recruiter_headers = auth_for("recruiter@acme.example.com")
    student_headers = auth_for("student@northstar.example.com")
    other_headers = auth_for("other@company.example.com")

    db = SessionLocal()
    try:
        student_user = db.query(User).filter(User.email == "student@northstar.example.com").first()
        other_user = db.query(User).filter(User.email == "other@company.example.com").first()
        acme_user = db.query(User).filter(User.email == "recruiter@acme.example.com").first()
        assert student_user and other_user and acme_user
        student_profile = db.query(StudentProfile).filter(StudentProfile.user_id == student_user.id).first()
        other_profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == other_user.id).first()
        acme_profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == acme_user.id).first()
        assert student_profile and other_profile and acme_profile
        org = db.query(Organization).filter(Organization.slug == "northstar").first()
        assert org

        other_job = Job(
            recruiter_id=other_profile.id,
            title="Other Employer Coaching Role",
            description="Private recruiter isolation test role with sufficient description length.",
            job_type="Full-time",
            visibility="public",
            is_active=True,
        )
        db.add(other_job)
        db.flush()
        interview = MockInterview(
            student_id=student_profile.id,
            job_id=other_job.id,
            questions_json='[{"question_id":1,"question":"Q?","category":"technical"}]',
            answers_json='[{"question_id":1,"question":"Q?","answer":"A"}]',
            evaluation_json='{"evaluations":[{"question_id":1,"score":80}]}',
            overall_score=80,
            overall_feedback="Other employer coaching data",
        )
        db.add(interview)
        db.commit()
        interview_id = interview.id
        student_id = student_profile.id
    finally:
        db.close()

    acme_view = client.get(f"/recruiters/students/{student_id}/interviews", headers=recruiter_headers)
    assert acme_view.status_code == 200, acme_view.text
    assert all(row["id"] != interview_id for row in acme_view.json())

    # The other recruiter only receives the row if they have candidate access. This call
    # primarily proves the endpoint remains authenticated after the scope restriction.
    other_view = client.get(f"/recruiters/students/{student_id}/interviews", headers=other_headers)
    assert other_view.status_code in {200, 404}
    assert client.get("/recruiters/students/search", headers=recruiter_headers).status_code == 200
    assert client.get("/students/profile", headers=student_headers).status_code == 200
