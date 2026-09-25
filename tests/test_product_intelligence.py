from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import (
    ApprovalStatus,
    DriveStatus,
    Job,
    Organization,
    PlacementAction,
    PlacementDrive,
    RecruiterProfile,
    StudentProfile,
    User,
    UserRole,
    utcnow,
)
from app.utils import create_access_token, get_hashed_password


client = TestClient(app)
PASSWORD = "ProductIntelligence123!"


def _auth(email: str) -> dict[str, str]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user
        return {"Authorization": f"Bearer {create_access_token(user.email, int(user.auth_version or 1))}"}
    finally:
        db.close()


def _fixture() -> dict[str, str]:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "intelligence-fixture").first()
        if not org:
            org = Organization(name="Intelligence Fixture Institute", slug="intelligence-fixture", is_active=True)
            db.add(org)
            db.flush()

        def user(email: str, username: str, role: UserRole, org_id: str | None = None) -> User:
            row = db.query(User).filter(User.email == email).first()
            if not row:
                row = User(
                    email=email,
                    username=username,
                    hashed_password=get_hashed_password(PASSWORD),
                    role=role,
                    organization_id=org_id,
                    email_verified=True,
                    is_active=True,
                )
                db.add(row)
                db.flush()
            return row

        tpo_user = user("intelligence-tpo@placeai.example.com", "intelligence_tpo", UserRole.institution_admin, org.id)
        recruiter_user = user("intelligence-recruiter@placeai.example.com", "intelligence_recruiter", UserRole.recruiter)
        student_user = user("intelligence-student@placeai.example.com", "intelligence_student", UserRole.student, org.id)

        recruiter = db.query(RecruiterProfile).filter(RecruiterProfile.user_id == recruiter_user.id).first()
        if not recruiter:
            recruiter = RecruiterProfile(
                user_id=recruiter_user.id,
                full_name="Intelligence Recruiter",
                company_name="Intelligence Employer",
                is_verified=True,
                provisioned_by_organization_id=org.id,
            )
            db.add(recruiter)
            db.flush()

        student = db.query(StudentProfile).filter(StudentProfile.user_id == student_user.id).first()
        if not student:
            student = StudentProfile(
                user_id=student_user.id,
                organization_id=org.id,
                college=org.name,
                full_name="Intelligence Student",
                degree="B.Tech",
                branch="Computer Science",
                graduation_year=2026,
                cgpa=8.7,
                phone="9000000000",
                is_verified=True,
                placement_opt_in=True,
            )
            student.skills = ["Python", "SQL"]
            student.desired_roles = ["Backend Developer"]
            db.add(student)
            db.flush()

        job = db.query(Job).filter(Job.title == "Intelligence Backend Engineer").first()
        if not job:
            job = Job(
                recruiter_id=recruiter.id,
                title="Intelligence Backend Engineer",
                description="Backend engineering role for placement intelligence tests.",
                job_type="Full-time",
                required_skills_json='["Python", "SQL"]',
                visibility="campus",
                target_organization_id=org.id,
                approval_status=ApprovalStatus.approved,
                is_active=True,
                deadline=utcnow() + timedelta(days=4),
            )
            db.add(job)
            db.flush()

        drive = db.query(PlacementDrive).filter(PlacementDrive.title == "Intelligence Hiring Drive").first()
        if not drive:
            drive = PlacementDrive(
                organization_id=org.id,
                job_id=job.id,
                title="Intelligence Hiring Drive",
                status=DriveStatus.open,
                min_cgpa=7.0,
                registration_deadline=utcnow() + timedelta(days=2),
            )
            drive.allowed_branches = ["Computer Science"]
            drive.required_skills = ["Python", "SQL"]
            db.add(drive)
            db.flush()

        db.commit()
        return {
            "org_id": org.id,
            "tpo": tpo_user.email,
            "student": student_user.email,
            "student_id": student.id,
            "job_id": job.id,
            "drive_id": drive.id,
        }
    finally:
        db.close()


def test_drive_rescue_creates_explainable_action_and_student_next_action():
    data = _fixture()
    response = client.post("/intelligence/institution/actions/sync", headers=_auth(data["tpo"]))
    assert response.status_code == 200, response.text

    centre = client.get("/intelligence/institution/actions", headers=_auth(data["tpo"]))
    assert centre.status_code == 200, centre.text
    payload = centre.json()
    action = next(item for item in payload["actions"] if item["action_type"] == "eligible_not_applied" and item["student_id"] == data["student_id"])
    assert action["drive_id"] == data["drive_id"]
    assert action["job_id"] == data["job_id"]
    assert action["priority"] in {"normal", "medium", "high"}
    assert "eligible" in action["description"].lower()

    student = client.get("/intelligence/student/actions", headers=_auth(data["student"]))
    assert student.status_code == 200, student.text
    assert any(item["type"] == "eligible_not_applied" and item["drive_id"] == data["drive_id"] for item in student.json()["actions"])


def test_readiness_exposes_sources_confidence_and_next_best_action():
    data = _fixture()
    response = client.get("/intelligence/student/readiness", headers=_auth(data["student"]))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["evidence"]
    assert all({"key", "label", "score", "confidence", "source", "evidence"} <= set(item) for item in payload["evidence"])
    assert payload["next_best_action"]["view"]
    assert "does not predict" in payload["disclaimer"].lower()


def test_drive_rescue_auto_resolves_after_application_exists():
    data = _fixture()
    client.post("/intelligence/institution/actions/sync", headers=_auth(data["tpo"]))
    db = SessionLocal()
    try:
        from app.models import Application
        if not db.query(Application).filter(Application.student_id == data["student_id"], Application.job_id == data["job_id"]).first():
            db.add(Application(
                student_id=data["student_id"],
                job_id=data["job_id"],
                drive_id=data["drive_id"],
                pipeline_stage_key="registration",
            ))
            db.commit()
    finally:
        db.close()

    sync = client.post("/intelligence/institution/actions/sync", headers=_auth(data["tpo"]))
    assert sync.status_code == 200, sync.text
    db = SessionLocal()
    try:
        row = db.query(PlacementAction).filter(
            PlacementAction.organization_id == data["org_id"],
            PlacementAction.source_key == f"drive:{data['drive_id']}:eligible-not-applied:{data['student_id']}",
        ).first()
        assert row is not None
        assert row.status == "resolved"
        assert row.resolution_outcome == "condition_cleared"
    finally:
        db.close()
