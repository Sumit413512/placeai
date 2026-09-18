from __future__ import annotations

from fastapi.testclient import TestClient

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import User, UserRole
from app.utils import get_hashed_password

client = TestClient(app)
ROTATED_PASSWORDS: dict[str, str] = {}
ROTATED_TEST_PASSWORD = "PlaceAIRotated456!"


def auth(token: str):
    return {"Authorization": f"Bearer {token}"}


def login(email: str, password: str):
    current_password = ROTATED_PASSWORDS.get(email, password)
    r = client.post("/auth/login-json", json={"email": email, "password": current_password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers=auth(token))
    assert me.status_code == 200, me.text
    if me.json().get("must_change_password"):
        changed = client.post(
            "/auth/change-password",
            headers=auth(token),
            json={"current_password": current_password, "new_password": ROTATED_TEST_PASSWORD},
        )
        assert changed.status_code == 200, changed.text
        token = changed.json()["access_token"]
        ROTATED_PASSWORDS[email] = ROTATED_TEST_PASSWORD
    return token


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(User(
        email="platform@placeai.example.com",
        username="platformadmin",
        hashed_password=get_hashed_password("PlatformPass123!"),
        role=UserRole.platform_admin,
        email_verified=True,
    ))
    db.commit()
    db.close()


def test_commercial_end_to_end_flow():
    platform = login("platform@placeai.example.com", "PlatformPass123!")

    r = client.post("/platform/organizations", headers=auth(platform), json={
        "name": "Northstar Institute of Technology",
        "slug": "northstar",
        "city": "Pune",
        "state": "Maharashtra",
    })
    assert r.status_code == 201, r.text

    r = client.post("/platform/institution-admins", headers=auth(platform), json={
        "email": "tpo@northstar.example.com",
        "username": "northstartpo",
        "full_name": "Placement Officer",
        "temporary_password": "AdminPass123!",
        "organization_slug": "northstar",
    })
    assert r.status_code == 201, r.text
    tpo = login("tpo@northstar.example.com", "AdminPass123!")

    r = client.post("/institutions/recruiters", headers=auth(tpo), json={
        "email": "recruiter@acme.example.com",
        "username": "acmerecruiter",
        "full_name": "Aarav Recruiter",
        "company_name": "Acme Technologies",
        "temporary_password": "RecruiterPass123!",
    })
    assert r.status_code == 201, r.text
    recruiter = login("recruiter@acme.example.com", "RecruiterPass123!")

    r = client.put("/recruiters/profile", headers=auth(recruiter), json={
        "industry": "Technology",
        "company_website": "https://acme.example.com",
        "linkedin_url": "https://www.linkedin.com/company/acme-technologies-demo",
    })
    assert r.status_code == 200, r.text
    r = client.get("/recruiters/company-trust", headers=auth(recruiter))
    assert r.status_code == 200, r.text
    assert r.json()["score"] >= 90 and r.json()["level"] == "verified"

    r = client.get("/institutions/recruiters", headers=auth(tpo))
    assert r.status_code == 200 and any(x["company_name"] == "Acme Technologies" for x in r.json())
    recruiter_profile_id = next(x["id"] for x in r.json() if x["company_name"] == "Acme Technologies")
    r = client.get(f"/institutions/recruiters/{recruiter_profile_id}/trust-review", headers=auth(tpo))
    assert r.status_code == 200 and r.json()["score"] >= 90

    r = client.post("/jobs", headers=auth(recruiter), json={
        "title": "Graduate Software Engineer",
        "description": "Build and maintain production APIs and web services with the engineering team.",
        "location": "Pune",
        "job_type": "Full-time",
        "salary_range": "₹7–9 LPA",
        "required_skills": ["Python", "SQL"],
        "preferred_roles": ["Backend Developer"],
        "visibility": "campus",
        "target_organization_slug": "northstar",
    })
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["approval_status"] == "pending"

    r = client.patch(f"/institutions/jobs/{job['id']}/approval", headers=auth(tpo), json={"approval_status": "approved"})
    assert r.status_code == 200, r.text

    r = client.post("/institutions/drives", headers=auth(tpo), json={
        "job_id": job["id"],
        "title": "Acme Graduate Hiring 2026",
        "min_cgpa": 7.0,
        "allowed_graduation_years": [2026],
        "allowed_branches": ["Computer Science"],
        "status": "open",
    })
    assert r.status_code == 201, r.text
    drive_id = r.json()["id"]

    r = client.post("/institutions/students", headers=auth(tpo), json={
        "email": "student@northstar.example.com",
        "username": "studentone",
        "full_name": "Student One",
        "temporary_password": "StudentPass123!",
        "degree": "B.Tech",
        "branch": "Computer Science",
        "graduation_year": 2026,
        "cgpa": 8.4,
    })
    assert r.status_code == 201, r.text
    student = login("student@northstar.example.com", "StudentPass123!")

    r = client.put("/students/profile", headers=auth(student), json={
        "skills": ["Python", "SQL", "FastAPI"],
        "desired_roles": ["Backend Developer"],
    })
    assert r.status_code == 200, r.text

    r = client.get(f"/students/drives/{drive_id}/eligibility", headers=auth(student))
    assert r.status_code == 200 and r.json()["eligible"] is True

    r = client.get("/students/jobs", headers=auth(student))
    assert r.status_code == 200 and any(x["id"] == job["id"] for x in r.json())

    r = client.post(f"/students/jobs/{job['id']}/apply", headers=auth(student), json={"cover_note": "Interested in the backend engineering role."})
    assert r.status_code == 201, r.text
    application = r.json()

    r = client.get(f"/jobs/{job['id']}/applicants", headers=auth(recruiter))
    assert r.status_code == 200 and len(r.json()) == 1

    r = client.patch(f"/jobs/{job['id']}/applicants/{application['id']}/status", headers=auth(recruiter), json={
        "status": "offered",
        "recruiter_notes": "Strong technical profile",
    })
    assert r.status_code == 200 and r.json()["status"] == "offered"

    r = client.get("/institutions/dashboard", headers=auth(tpo))
    assert r.status_code == 200, r.text
    assert r.json()["offers"] == 1
    assert r.json()["total_applications"] == 1

    r = client.get("/institutions/audit", headers=auth(tpo))
    assert r.status_code == 200
    actions = {x["action"] for x in r.json()}
    assert "institution.recruiter.provisioned" in actions
    assert "institution.job.approval_changed" in actions
    assert "recruiter.application.status_changed" in actions


def test_recruiter_privacy_and_registration_controls():
    r = client.post("/auth/signup", json={
        "username": "selfrecruiter", "email": "self@recruiter.example.com", "password": "Password123!", "role": "recruiter"
    })
    assert r.status_code == 403

    tpo = login("tpo@northstar.example.com", "AdminPass123!")
    r = client.post("/institutions/recruiters", headers=auth(tpo), json={
        "email": "other@company.example.com",
        "username": "otherrecruiter",
        "company_name": "Other Company",
        "temporary_password": "OtherPass123!",
    })
    assert r.status_code == 201, r.text
    other = login("other@company.example.com", "OtherPass123!")
    r = client.get("/recruiters/students/search", headers=auth(other))
    assert r.status_code == 200 and r.json() == []


def test_password_reset_is_non_enumerating_and_refresh_cookie_works():
    existing = client.post("/auth/forgot-password", json={"email": "student@northstar.example.com"})
    missing = client.post("/auth/forgot-password", json={"email": "missing@northstar.example.com"})
    assert existing.status_code == 200 and missing.status_code == 200
    assert existing.json()["message"] == missing.json()["message"]
    assert "reset_token" not in existing.json()

    r = client.post("/auth/login-json", json={
        "email": "student@northstar.example.com",
        "password": ROTATED_PASSWORDS.get("student@northstar.example.com", "StudentPass123!"),
    })
    assert r.status_code == 200
    assert "placeai_refresh" in r.cookies
    r = client.post("/auth/refresh", json={})
    assert r.status_code == 200 and r.json()["access_token"]


def test_public_access_request_and_platform_review_pipeline():
    r = client.post("/public/access-requests", json={
        "requested_role": "institution_admin",
        "full_name": "Priya Placement",
        "work_email": "priya@college.example.com",
        "organization_name": "Example College",
        "message": "We want controlled access for our placement office.",
    })
    assert r.status_code == 202, r.text
    assert set(r.json()) == {"message"}
    assert "request_id" not in r.json()
    assert "status" not in r.json()

    db = SessionLocal()
    try:
        from app.access_models import AccessRequest
        access_request = db.query(AccessRequest).filter(
            AccessRequest.work_email == "priya@college.example.com",
            AccessRequest.requested_role == "institution_admin",
        ).order_by(AccessRequest.created_at.desc()).first()
        assert access_request is not None
        request_id = access_request.id
    finally:
        db.close()

    platform = login("platform@placeai.example.com", "PlatformPass123!")
    r = client.get("/platform/access-requests", headers=auth(platform))
    assert r.status_code == 200 and any(x["id"] == request_id for x in r.json())

    r = client.patch(
        f"/platform/access-requests/{request_id}",
        headers=auth(platform),
        json={"status": "under_review", "review_note": "Validated institutional request."},
    )
    assert r.status_code == 200 and r.json()["status"] == "under_review"

def test_cross_institution_campus_job_isolation():
    platform = login("platform@placeai.example.com", "PlatformPass123!")
    r = client.post("/platform/organizations", headers=auth(platform), json={
        "name": "Southside Institute", "slug": "southside", "city": "Mumbai", "state": "Maharashtra"
    })
    assert r.status_code == 201, r.text
    r = client.post("/platform/institution-admins", headers=auth(platform), json={
        "email": "tpo@southside.example.com", "username": "southsidetpo", "full_name": "Southside TPO",
        "temporary_password": "AdminPass123!", "organization_slug": "southside"
    })
    assert r.status_code == 201, r.text
    tpo2 = login("tpo@southside.example.com", "AdminPass123!")
    r = client.post("/institutions/students", headers=auth(tpo2), json={
        "email": "student@southside.example.com", "username": "southstudent", "full_name": "South Student",
        "temporary_password": "StudentPass123!", "degree": "B.Tech", "branch": "Computer Science",
        "graduation_year": 2026, "cgpa": 8.0
    })
    assert r.status_code == 201, r.text
    south_student = login("student@southside.example.com", "StudentPass123!")

    db = SessionLocal()
    try:
        from app.models import Job
        north_job = db.query(Job).filter(Job.title == "Graduate Software Engineer").first()
        assert north_job is not None
        north_job_id = north_job.id
    finally:
        db.close()

    r = client.get(f"/jobs/{north_job_id}", headers=auth(south_student))
    assert r.status_code == 404
    r = client.get("/jobs", headers=auth(south_student))
    assert r.status_code == 200 and all(x["id"] != north_job_id for x in r.json())
    r = client.get("/students/jobs", headers=auth(south_student))
    assert r.status_code == 200 and all(x["id"] != north_job_id for x in r.json())


def test_institution_bulk_student_csv_import():
    tpo = login("tpo@northstar.example.com", "AdminPass123!")
    csv_body = (
        "full_name,email,username,temporary_password,degree,branch,graduation_year,cgpa\n"
        "Bulk Student,bulk.student@northstar.example.com,bulkstudent,BulkPass123!,B.Tech,Computer Science,2026,8.2\n"
    )
    r = client.post(
        "/institutions/import/students.csv",
        headers=auth(tpo),
        files={"file": ("students.csv", csv_body.encode("utf-8"), "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1 and r.json()["failed"] == 0
    r = client.get("/institutions/students", headers=auth(tpo))
    assert r.status_code == 200 and any(x["full_name"] == "Bulk Student" for x in r.json())


def test_enterprise_placement_operations_suite():
    """Smoke the V3 enterprise workflows without calling any external AI provider."""
    from datetime import datetime, timedelta, timezone
    from app.models import Application, Job, PlacementDrive, RecruiterProfile, StudentProfile

    tpo = login("tpo@northstar.example.com", "AdminPass123!")
    recruiter = login("recruiter@acme.example.com", "RecruiterPass123!")
    student = login("student@northstar.example.com", "StudentPass123!")

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.title == "Graduate Software Engineer").first()
        drive = db.query(PlacementDrive).filter(PlacementDrive.job_id == job.id).first()
        app_row = db.query(Application).filter(Application.job_id == job.id).first()
        recruiter_profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == job.recruiter.user_id).first()
        student_user = db.query(User).filter(User.email == "student@northstar.example.com").first()
        student_profile = db.query(StudentProfile).filter(StudentProfile.user_id == student_user.id).first()
        job_id, drive_id, app_id, recruiter_profile_id, student_profile_id = job.id, drive.id, app_row.id, recruiter_profile.id, student_profile.id
    finally:
        db.close()

    # Company Verification Centre.
    r = client.get("/enterprise/company-verification", headers=auth(recruiter))
    assert r.status_code == 200, r.text
    assert r.json()["assessment"]["verification_status"] in {"Verified", "Partially Verified", "Manual Review Required", "High Risk"}
    r = client.get(f"/enterprise/institution/company-verification/{recruiter_profile_id}", headers=auth(tpo))
    assert r.status_code == 200, r.text

    # Configurable drive pipeline and movement.
    r = client.get(f"/enterprise/drives/{drive_id}/pipeline", headers=auth(tpo))
    assert r.status_code == 200 and len(r.json()) >= 8
    r = client.post(f"/enterprise/drives/{drive_id}/pipeline", headers=auth(tpo), json={"name":"Managerial Round","stage_type":"interview"})
    assert r.status_code == 200, r.text
    custom_stage = r.json()["stage_key"]
    r = client.patch(f"/enterprise/applications/{app_id}/pipeline/{custom_stage}", headers=auth(recruiter))
    assert r.status_code == 200, r.text

    # Interview scheduler + human evaluation.
    when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = client.post("/enterprise/interviews", headers=auth(recruiter), json={
        "application_id": app_id, "drive_id": drive_id, "round_name": "Managerial Round",
        "scheduled_at": when, "mode": "online", "meeting_url": "https://meet.example.com/test",
        "interviewer": "Hiring Manager", "student_slot": "11:00 AM", "instructions": "Join 10 minutes early."
    })
    assert r.status_code == 201, r.text
    interview_id = r.json()["id"]
    revised_when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = client.patch(f"/enterprise/interviews/{interview_id}", headers=auth(recruiter), json={
        "scheduled_at": revised_when, "status": "rescheduled", "attendance_status": "present", "result": "proceed"
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rescheduled" and r.json()["attendance_status"] == "present" and r.json()["result"] == "proceed"
    r = client.put(f"/enterprise/interviews/{interview_id}/evaluation", headers=auth(recruiter), json={
        "technical_knowledge": 8, "communication": 8, "problem_solving": 9, "role_fit": 8,
        "recommendation": "Proceed", "notes": "Human-reviewed test evaluation."
    })
    assert r.status_code == 200 and r.json()["human_reviewed"] is True

    # Real DB notifications and preferences.
    r = client.get("/enterprise/notifications", headers=auth(student))
    assert r.status_code == 200 and any(x["category"] == "interview" for x in r.json()["items"])
    r = client.put("/enterprise/notification-preferences", headers=auth(student), json={
        "in_app": True, "email": True, "whatsapp": False, "sms": False, "high_priority_only_external": True
    })
    assert r.status_code == 200

    # Readiness and explainable eligibility.
    r = client.get("/enterprise/readiness", headers=auth(student))
    assert r.status_code == 200 and 0 <= r.json()["score"] <= 100 and len(r.json()["components"]) == 7
    r = client.get(f"/enterprise/drives/{drive_id}/eligibility", headers=auth(student))
    assert r.status_code == 200 and "checks" in r.json() and "summary" in r.json()

    # Placement policy engine.
    r = client.post("/enterprise/policies", headers=auth(tpo), json={
        "policy_key": "enterprise-test-policy", "name": "Enterprise Test Policy",
        "description": "Test explainable offer participation controls.",
        "rules": {"max_offers_per_student": 3, "internship_offers_do_not_block": True, "dream_company_exception": True, "dream_company_min_ctc_lpa": 12}
    })
    assert r.status_code == 201, r.text
    r = client.get("/enterprise/policies", headers=auth(tpo))
    assert r.status_code == 200 and any(x["policy_key"] == "enterprise-test-policy" for x in r.json())

    # Offer management.
    r = client.post("/enterprise/offers", headers=auth(recruiter), json={
        "application_id": app_id, "ctc_lpa": 9.0, "fixed_pay_lpa": 8.0, "variable_pay_lpa": 1.0,
        "location": "Pune", "status": "issued", "ppo_status": "Not applicable"
    })
    assert r.status_code == 201, r.text
    offer_id = r.json()["id"]
    offer_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    r = client.post(f"/enterprise/offers/{offer_id}/letter", headers=auth(recruiter), files={"file": ("offer-letter.pdf", offer_pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    r = client.get(f"/enterprise/offers/{offer_id}/letter", headers=auth(student))
    assert r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf")
    r = client.patch(f"/enterprise/offers/{offer_id}", headers=auth(student), json={"status":"accepted"})
    assert r.status_code == 200 and r.json()["status"] == "accepted"

    # Student document vault.
    pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    r = client.post("/enterprise/documents?document_type=marksheet&visibility=institution_only", headers=auth(student), files={"file": ("marksheet.pdf", pdf, "application/pdf")})
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    r = client.get(f"/enterprise/documents/{doc_id}/download", headers=auth(student))
    assert r.status_code == 200

    # QR attendance session + student check-in.
    r = client.post("/enterprise/attendance/sessions", headers=auth(tpo), json={"drive_id":drive_id,"title":"Test Placement Session","session_type":"placement_drive"})
    assert r.status_code == 201, r.text
    session_id = r.json()["id"]
    token = r.json()["token"]
    r = client.get(f"/enterprise/attendance/sessions/{session_id}/qr", headers=auth(tpo))
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("image/png")
    assert r.headers.get("cache-control") == "no-store"
    assert r.content.startswith(b"\x89PNG\r\n\x1a\n")
    r = client.post(f"/enterprise/attendance/check-in?token={token}", headers=auth(student))
    assert r.status_code == 200 and r.json()["checked_in"] is True

    # Attention centre + Analytics 2.0 + recruiter intelligence.
    r = client.get("/enterprise/attention-centre", headers=auth(tpo))
    assert r.status_code == 200 and "signals" in r.json()
    r = client.get("/enterprise/analytics/institution", headers=auth(tpo))
    assert r.status_code == 200 and "drive_conversion" in r.json() and "unplaced_segmentation" in r.json() and "monthly_placement_trend" in r.json()
    r = client.get("/enterprise/analytics/recruiter", headers=auth(recruiter))
    assert r.status_code == 200 and "skill_availability" in r.json() and "campus_comparison" in r.json()

    # Role-scoped command search: role title, company, skill and location should be searchable.
    r = client.get("/enterprise/search?q=Graduate", headers=auth(recruiter))
    assert r.status_code == 200 and isinstance(r.json(), list)
    r = client.get("/enterprise/search?q=Python", headers=auth(student))
    assert r.status_code == 200 and any(x["type"] == "opportunity" for x in r.json())
    r = client.get("/enterprise/search?q=Acme", headers=auth(student))
    assert r.status_code == 200 and any("Acme" in x["subtitle"] for x in r.json())
    r = client.get("/students/jobs?search=Pune", headers=auth(student))
    assert r.status_code == 200 and any(x["id"] == job_id for x in r.json())

    # Student command search must not leak pending/unapproved campus opportunities.
    r = client.post("/jobs", headers=auth(recruiter), json={
        "title": "Hidden Pending Search Role",
        "description": "Pending campus opportunity used to verify search visibility controls remain enforced.",
        "location": "Pune",
        "job_type": "Internship",
        "required_skills": ["HiddenSkill"],
        "visibility": "campus",
        "target_organization_slug": "northstar",
    })
    assert r.status_code == 201 and r.json()["approval_status"] == "pending", r.text
    r = client.get("/enterprise/search?q=HiddenSkill", headers=auth(student))
    assert r.status_code == 200 and not any(x.get("title") == "Hidden Pending Search Role" for x in r.json())

    # Announcements.
    r = client.post("/enterprise/announcements", headers=auth(tpo), json={"title":"Test drive update","body":"Placement test announcement.","audience_type":"all_students","audience_value":{},"priority":"normal"})
    assert r.status_code == 201, r.text
    r = client.get("/enterprise/announcements", headers=auth(student))
    assert r.status_code == 200 and any(x["title"] == "Test drive update" for x in r.json())

    # Recruiter communication hub including document attachment.
    r = client.post("/enterprise/communications", headers=auth(tpo), json={"recruiter_profile_id":recruiter_profile_id,"drive_id":drive_id,"subject":"Enterprise Test Thread"})
    assert r.status_code == 201, r.text
    thread_id = r.json()["id"]
    r = client.post(f"/enterprise/communications/{thread_id}/messages", headers=auth(recruiter), json={"message":"Assessment slots confirmed."})
    assert r.status_code == 201
    r = client.post(f"/enterprise/communications/{thread_id}/attachments?message=Assessment%20schedule", headers=auth(tpo), files={"file": ("schedule.pdf", pdf, "application/pdf")})
    assert r.status_code == 201, r.text
    message_id = r.json()["id"]
    r = client.get(f"/enterprise/communications/{thread_id}/messages/{message_id}/attachment", headers=auth(recruiter))
    assert r.status_code == 200

    # Confidential incident report and institution review.
    r = client.post("/enterprise/incidents", headers=auth(student), json={"recruiter_id":recruiter_profile_id,"job_id":job_id,"category":"misleading_ctc","description":"Test-only incident report for workflow validation.","confidential":True})
    assert r.status_code == 201, r.text
    incident_id = r.json()["id"]
    r = client.patch(f"/enterprise/incidents/{incident_id}", headers=auth(tpo), json={"status":"resolved","resolution_notes":"Validated in automated test."})
    assert r.status_code == 200

    # Reports in all supported output formats.
    for fmt in ("csv", "xlsx", "pdf"):
        r = client.get(f"/enterprise/reports/placement-report.{fmt}", headers=auth(tpo))
        assert r.status_code == 200, (fmt, r.text[:200])

    # Custom institution fields.
    r = client.post("/enterprise/custom-fields", headers=auth(tpo), json={"entity_type":"student","label":"SAP ID","field_key":"sap_id","field_type":"text","required":False,"options":[]})
    assert r.status_code == 201, r.text
    r = client.put(f"/enterprise/custom-fields/values/{student_profile_id}", headers=auth(student), json={"values":{"sap_id":"SAP-TEST-001"}})
    assert r.status_code == 200
    r = client.get(f"/enterprise/custom-fields/values/{student_profile_id}", headers=auth(tpo))
    assert r.status_code == 200 and r.json().get("sap_id") == "SAP-TEST-001"

    # Unified placement calendar.
    r = client.get("/enterprise/calendar", headers=auth(student))
    assert r.status_code == 200 and isinstance(r.json(), list)

    # Student profile approval workflow.
    r = client.put("/students/profile", headers=auth(student), json={"cgpa": 8.6})
    assert r.status_code == 200, r.text
    r = client.get("/enterprise/profile-change-requests", headers=auth(tpo))
    assert r.status_code == 200
    pending = next((x for x in r.json() if x["student_id"] == student_profile_id and x["field_name"] == "cgpa" and x["status"] == "pending"), None)
    assert pending is not None
    r = client.patch(f"/enterprise/profile-change-requests/{pending['id']}", headers=auth(tpo), json={"status":"approved"})
    assert r.status_code == 200 and r.json()["status"] == "approved"


def test_refresh_rotation_logout_revocation_and_password_reset_invalidation():
    from datetime import datetime, timedelta, timezone
    from app.models import RefreshSession
    from app.utils import generate_reset_token, hash_reset_token

    email = "session-security@placeai.example.com"
    password = "InitialPass123!"
    new_password = "ChangedPass456!"
    r = client.post("/auth/signup", json={
        "username": "sessionsecurity", "email": email, "password": password, "role": "student"
    })
    assert r.status_code == 201, r.text

    r = client.post("/auth/login-json", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    first = r.json()
    first_refresh = first["refresh_token"]
    first_access = first["access_token"]

    # Refresh tokens are one-time use: successful rotation revokes the old JTI.
    r = client.post("/auth/refresh", json={"refresh_token": first_refresh})
    assert r.status_code == 200, r.text
    second_refresh = r.json()["refresh_token"]
    replay = client.post("/auth/refresh", json={"refresh_token": first_refresh})
    assert replay.status_code == 401

    # Logout revokes the currently cookie-bound refresh token.
    r = client.post("/auth/logout")
    assert r.status_code == 204
    revoked = client.post("/auth/refresh", json={"refresh_token": second_refresh})
    assert revoked.status_code == 401

    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    assert user is not None
    reset_token = generate_reset_token()
    user.reset_token_hash = hash_reset_token(reset_token)
    user.reset_token_expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=15)
    before_version = user.auth_version
    db.commit()
    db.close()

    reset = client.post("/auth/reset-password", json={"token": reset_token, "new_password": new_password})
    assert reset.status_code == 200, reset.text

    # Password reset invalidates all pre-reset access and refresh credentials.
    me = client.get("/auth/me", headers=auth(first_access))
    assert me.status_code == 401
    old_refresh = client.post("/auth/refresh", json={"refresh_token": second_refresh})
    assert old_refresh.status_code == 401

    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    assert user.auth_version == before_version + 1
    assert db.query(RefreshSession).filter(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)).count() == 0
    db.close()

    fresh = client.post("/auth/login-json", json={"email": email, "password": new_password})
    assert fresh.status_code == 200


def test_database_backed_file_storage_survives_without_local_disk():
    from app import storage
    from app.models import Resume, StoredFile

    email = "storage-security@placeai.example.com"
    r = client.post("/auth/signup", json={
        "username": "storagesecurity", "email": email, "password": "StoragePass123!", "role": "student"
    })
    assert r.status_code == 201, r.text
    token = login(email, "StoragePass123!")

    previous_vercel = storage.settings.running_on_vercel
    try:
        storage.settings.running_on_vercel = True
        pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"
        uploaded = client.post(
            "/students/resume", headers=auth(token),
            files={"file": ("resume.pdf", pdf, "application/pdf")},
        )
        assert uploaded.status_code == 201, uploaded.text

        db = SessionLocal()
        user = db.query(User).filter(User.email == email).first()
        resume = db.query(Resume).join(Resume.student).filter_by(user_id=user.id).first()
        assert resume is not None and resume.filepath.startswith("dbfile:")
        stored_id = resume.filepath.split(":", 1)[1]
        stored = db.query(StoredFile).filter(StoredFile.id == stored_id).first()
        assert stored is not None and bytes(stored.data) == pdf and stored.size_bytes == len(pdf)
        db.close()

        downloaded = client.get("/students/resume/download", headers=auth(token))
        assert downloaded.status_code == 200
        assert downloaded.content == pdf
        assert downloaded.headers.get("cache-control") == "private, no-store"
    finally:
        storage.settings.running_on_vercel = previous_vercel


def test_cross_tenant_reference_integrity_and_attendance_window_guards():
    from datetime import datetime, timedelta, timezone
    from app.models import Application, Job, PlacementDrive, RecruiterProfile, User

    north_tpo = login("tpo@northstar.example.com", "AdminPass123!")
    south_tpo = login("tpo@southside.example.com", "AdminPass123!")
    north_recruiter = login("recruiter@acme.example.com", "RecruiterPass123!")
    north_student = login("student@northstar.example.com", "StudentPass123!")

    # Create a recruiter/job/drive that belongs to Southside only.
    r = client.post("/institutions/recruiters", headers=auth(south_tpo), json={
        "email": "south-recruiter@company.example.com",
        "username": "southrecruiter",
        "company_name": "Southside Employer",
        "temporary_password": "SouthRecruiter123!",
    })
    assert r.status_code == 201, r.text
    south_recruiter_token = login("south-recruiter@company.example.com", "SouthRecruiter123!")
    r = client.post("/jobs", headers=auth(south_recruiter_token), json={
        "title": "Southside Graduate Role",
        "description": "Role scoped to Southside Institute for integrity testing.",
        "location": "Mumbai",
        "job_type": "Full-time",
        "required_skills": ["Python"],
        "visibility": "campus",
        "target_organization_slug": "southside",
    })
    assert r.status_code == 201, r.text
    south_job_id = r.json()["id"]
    r = client.patch(f"/institutions/jobs/{south_job_id}/approval", headers=auth(south_tpo), json={"approval_status": "approved"})
    assert r.status_code == 200, r.text
    r = client.post("/institutions/drives", headers=auth(south_tpo), json={
        "job_id": south_job_id, "title": "Southside Isolated Drive", "status": "open"
    })
    assert r.status_code == 201, r.text
    south_drive_id = r.json()["id"]

    db = SessionLocal()
    south_user = db.query(User).filter(User.email == "south-recruiter@company.example.com").first()
    south_profile = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == south_user.id).first()
    south_recruiter_id = south_profile.id
    north_job = db.query(Job).filter(Job.title == "Graduate Software Engineer").first()
    north_drive = db.query(PlacementDrive).filter(PlacementDrive.job_id == north_job.id).first()
    north_app = db.query(Application).filter(Application.job_id == north_job.id).first()
    north_drive_id = north_drive.id
    north_app_id = north_app.id
    db.close()

    # Northstar cannot bind an attendance session to Southside's drive.
    r = client.post("/enterprise/attendance/sessions", headers=auth(north_tpo), json={
        "drive_id": south_drive_id, "title": "Invalid cross-tenant attendance"
    })
    assert r.status_code == 404

    # Northstar cannot create a communication thread with Southside's recruiter/drive.
    r = client.post("/enterprise/communications", headers=auth(north_tpo), json={
        "recruiter_profile_id": south_recruiter_id,
        "drive_id": south_drive_id,
        "subject": "Invalid cross-tenant thread",
    })
    assert r.status_code == 404

    # A Northstar application cannot be scheduled against Southside's drive.
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = client.post("/enterprise/interviews", headers=auth(north_recruiter), json={
        "application_id": north_app_id,
        "drive_id": south_drive_id,
        "round_name": "Invalid round",
        "scheduled_at": future,
        "mode": "online",
    })
    assert r.status_code == 400

    # A Northstar student cannot reference an unrelated Southside job/recruiter in an incident.
    r = client.post("/enterprise/incidents", headers=auth(north_student), json={
        "job_id": south_job_id,
        "recruiter_id": south_recruiter_id,
        "category": "conduct",
        "description": "This deliberately references another institution and must be rejected.",
        "confidential": True,
    })
    assert r.status_code == 404

    # Attendance cannot be checked in before its configured opening time.
    starts = datetime.now(timezone.utc) + timedelta(hours=2)
    closes = starts + timedelta(hours=2)
    r = client.post("/enterprise/attendance/sessions", headers=auth(north_tpo), json={
        "drive_id": north_drive_id,
        "title": "Future attendance window",
        "starts_at": starts.isoformat(),
        "closes_at": closes.isoformat(),
    })
    assert r.status_code == 201, r.text
    attendance_token = r.json()["token"]
    early = client.post(f"/enterprise/attendance/check-in?token={attendance_token}", headers=auth(north_student))
    assert early.status_code == 425


def test_password_strength_and_durable_login_rate_limit():
    weak = client.post("/auth/signup", json={
        "username": "weakpassword", "email": "weakpassword@northstar.example.com",
        "password": "weakpass123", "role": "student"
    })
    assert weak.status_code == 422

    email = "ratelimit@northstar.example.com"
    created = client.post("/auth/signup", json={
        "username": "ratelimitstudent", "email": email,
        "password": "RateLimitPass123!", "role": "student"
    })
    assert created.status_code == 201, created.text

    for _ in range(12):
        failed = client.post("/auth/login-json", json={"email": email, "password": "WrongPassword123!"})
        assert failed.status_code == 401, failed.text
    blocked = client.post("/auth/login-json", json={"email": email, "password": "WrongPassword123!"})
    assert blocked.status_code == 429, blocked.text
    assert int(blocked.headers["retry-after"]) > 0


def test_auth_input_bounds_pdf_limits_and_frontend_token_hygiene():
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch

    from fastapi import HTTPException
    from app.routers import ai as ai_router

    # Bound credential payloads before expensive auth/provider work.
    oversized_login = client.post("/auth/login-json", json={
        "email": "platform@placeai.example.com",
        "password": "A" * 129,
    })
    assert oversized_login.status_code == 422

    invalid_google = client.post("/auth/google", json={
        "credential": "short",
        "role": "platform_admin",
    })
    assert invalid_google.status_code == 422

    # Resume parsing refuses pathological page counts before extracting content.
    class FakeReader:
        is_encrypted = False
        pages = [object()] * 31
        def __init__(self, *_args, **_kwargs):
            pass

    with patch.object(ai_router, "pypdf", SimpleNamespace(PdfReader=FakeReader)):
        try:
            ai_router.extract_pdf_text(b"%PDF-1.4 fake")
            assert False, "31-page resume must be rejected"
        except HTTPException as exc:
            assert exc.status_code == 422
            assert "30 pages" in str(exc.detail)

    js = Path("app/static/app.js").read_text(encoding="utf-8")
    html = Path("app/templates/index.html").read_text(encoding="utf-8")
    assert "sessionStorage" not in js
    assert 'minlength="8"' not in js + html
    assert 'accept=".pdf,.doc,.docx,.xls,.xlsx' not in js



def test_mock_interview_server_issued_session_integrity(monkeypatch):
    import json
    import app.routers.mock_interview_v2 as mock_router
    from app.models import Job, MockInterview, StudentProfile

    student = login("student@northstar.example.com", "StudentPass123!")
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.title == "Graduate Software Engineer").first()
        assert job is not None
        job_id = job.id
        student_user = db.query(User).filter(User.email == "student@northstar.example.com").first()
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == student_user.id).first()
        scored_before = db.query(MockInterview).filter(MockInterview.student_id == profile.id, MockInterview.overall_score.isnot(None)).count()
    finally:
        db.close()

    def fake_ai(prompt, *, max_output_tokens, fast=False):
        if "Generate exactly" in prompt:
            return json.dumps({"questions": [
                {"question_id": 1, "question": "Explain a production API decision you made.", "category": "technical"},
                {"question_id": 2, "question": "How would you debug a failing service?", "category": "situational"},
                {"question_id": 3, "question": "Describe a disagreement you resolved.", "category": "behavioral"},
            ]})
        return json.dumps({
            "overall_score": 82,
            "overall_feedback": "Strong structured practice response.",
            "dimensions": {
                "relevance": 84, "clarity": 82, "structure": 80, "language_precision": 81,
                "role_knowledge": 85, "problem_solving": 83, "professionalism": 79
            },
            "strengths": ["Relevant reasoning"],
            "improvements": ["Add measurable outcomes"],
            "evaluations": [
                {"question_id": 1, "score": 83, "feedback": "Good", "better_answer_outline": "Context → decision → result"},
                {"question_id": 2, "score": 82, "feedback": "Good", "better_answer_outline": "Triage → isolate → verify"},
                {"question_id": 3, "score": 81, "feedback": "Good", "better_answer_outline": "Situation → action → result"},
            ],
        })

    monkeypatch.setattr(mock_router, "_call_interview_ai", fake_ai)

    started = client.post("/mock-interview/start", headers=auth(student), json={
        "job_id": job_id, "focus": "balanced", "question_count": 3
    })
    assert started.status_code == 200, started.text
    payload = started.json()
    assert payload["interview_id"]
    assert len(payload["questions"]) == 3

    dashboard = client.get("/students/dashboard", headers=auth(student))
    assert dashboard.status_code == 200
    assert dashboard.json()["interviews_completed"] == scored_before

    incomplete = client.post("/mock-interview/evaluate", headers=auth(student), json={
        "interview_id": payload["interview_id"],
        "answers": [{"question_id": 1, "answer": "Only one answer"}],
    })
    assert incomplete.status_code == 422

    injected = client.post("/mock-interview/evaluate", headers=auth(student), json={
        "interview_id": payload["interview_id"],
        "job_id": job_id,
        "answers": [
            {"question_id": q["question_id"], "question": "Replace with an easier question", "answer": "Answer"}
            for q in payload["questions"]
        ],
    })
    assert injected.status_code == 422

    answers = [
        {"question_id": q["question_id"], "answer": f"Structured answer for question {q['question_id']}"}
        for q in payload["questions"]
    ]
    evaluated = client.post("/mock-interview/evaluate", headers=auth(student), json={
        "interview_id": payload["interview_id"], "answers": answers
    })
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.json()["overall_score"] == 82

    repeated = client.post("/mock-interview/evaluate", headers=auth(student), json={
        "interview_id": payload["interview_id"], "answers": answers
    })
    assert repeated.status_code == 409

    history = client.get("/mock-interview/history", headers=auth(student))
    assert history.status_code == 200
    assert any(row["id"] == payload["interview_id"] and row["overall_score"] == 82 for row in history.json())

    dashboard = client.get("/students/dashboard", headers=auth(student))
    assert dashboard.status_code == 200
    assert dashboard.json()["interviews_completed"] == scored_before + 1
