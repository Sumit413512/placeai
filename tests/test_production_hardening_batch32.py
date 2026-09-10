from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import app.routers.mock_interview as mock_interview_router
from app import storage
from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import (
    Announcement,
    Application,
    ApprovalStatus,
    Job,
    Notification,
    Offer,
    Organization,
    PlacementDrive,
    RecruiterProfile,
    StoredFile,
    StudentProfile,
    User,
    UserRole,
)
from app.utils import get_hashed_password

client = TestClient(app)
PASSWORD = "Batch32Pass123!"
PDF_A = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PDF_B = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Version /1.7 >>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(email: str) -> str:
    response = client.post("/auth/login-json", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _ensure_fixture() -> dict[str, str]:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "batch32-institute").first()
        if not org:
            org = Organization(name="Batch 32 Institute", slug="batch32-institute", is_active=True)
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

        admin = ensure_user(
            "batch32-tpo@placeai.example.com", "batch32_tpo", UserRole.institution_admin, org.id
        )
        recruiter_user = ensure_user(
            "batch32-recruiter@placeai.example.com", "batch32_recruiter", UserRole.recruiter
        )
        student_user = ensure_user(
            "batch32-student@placeai.example.com", "batch32_student", UserRole.student, org.id
        )

        recruiter = db.query(RecruiterProfile).filter(
            RecruiterProfile.user_id == recruiter_user.id
        ).first()
        if not recruiter:
            recruiter = RecruiterProfile(
                user_id=recruiter_user.id,
                full_name="Batch 32 Recruiter",
                company_name="Batch 32 Employer",
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
                full_name="Batch 32 Student",
                placement_status="unplaced",
            )
            db.add(student)
            db.flush()

        job = db.query(Job).filter(Job.title == "Batch 32 Campus Role").first()
        if not job:
            job = Job(
                recruiter_id=recruiter.id,
                title="Batch 32 Campus Role",
                description="Campus role used for hardening batch 32 regression coverage.",
                visibility="campus",
                target_organization_id=org.id,
                approval_status=ApprovalStatus.approved,
                is_active=True,
            )
            db.add(job)
            db.flush()

        drive = db.query(PlacementDrive).filter(
            PlacementDrive.title == "Batch 32 Drive"
        ).first()
        if not drive:
            drive = PlacementDrive(
                organization_id=org.id,
                job_id=job.id,
                title="Batch 32 Drive",
                status="open",
            )
            db.add(drive)
            db.flush()

        application = db.query(Application).filter(
            Application.student_id == student.id,
            Application.job_id == job.id,
        ).first()
        if not application:
            application = Application(student_id=student.id, job_id=job.id, status="offered")
            db.add(application)
            db.flush()

        offer = db.query(Offer).filter(Offer.application_id == application.id).first()
        if not offer:
            offer = Offer(
                application_id=application.id,
                company_name=recruiter.company_name,
                role=job.title,
                status="issued",
            )
            db.add(offer)
            db.flush()

        db.commit()
        return {
            "org": org.id,
            "admin_email": admin.email,
            "recruiter_email": recruiter_user.email,
            "student_email": student_user.email,
            "student": student.id,
            "drive": drive.id,
            "offer": offer.id,
            "recruiter": recruiter.id,
        }
    finally:
        db.close()


def test_scheduled_announcements_are_hidden_until_active_and_notify_once() -> None:
    fixture = _ensure_fixture()
    admin_token = login(fixture["admin_email"])
    student_token = login(fixture["student_email"])
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    expiry = future + timedelta(hours=4)
    title = "Batch 32 scheduled announcement"

    created = client.post(
        "/enterprise/announcements",
        headers=auth(admin_token),
        json={
            "title": title,
            "body": "This should become visible only after its configured start time.",
            "audience_type": "all_students",
            "audience_value": {},
            "priority": "normal",
            "starts_at": future.isoformat(),
            "expires_at": expiry.isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["delivery_state"] == "scheduled"
    assert created.json()["notified_students"] == 0
    announcement_id = created.json()["id"]

    student_rows = client.get("/enterprise/announcements", headers=auth(student_token))
    assert student_rows.status_code == 200
    assert not any(row["id"] == announcement_id for row in student_rows.json())

    admin_rows = client.get("/enterprise/announcements", headers=auth(admin_token))
    assert admin_rows.status_code == 200
    scheduled = next(row for row in admin_rows.json() if row["id"] == announcement_id)
    assert scheduled["delivery_state"] == "scheduled"

    db = SessionLocal()
    try:
        row = db.query(Announcement).filter(Announcement.id == announcement_id).first()
        row.starts_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        db.commit()
    finally:
        db.close()

    visible = client.get("/enterprise/announcements", headers=auth(student_token))
    assert visible.status_code == 200
    assert any(row["id"] == announcement_id for row in visible.json())
    again = client.get("/enterprise/announcements", headers=auth(student_token))
    assert again.status_code == 200

    db = SessionLocal()
    try:
        count = db.query(Notification).filter(
            Notification.user_id == db.query(StudentProfile).filter(
                StudentProfile.id == fixture["student"]
            ).first().user_id,
            Notification.category == "announcement",
            Notification.link == f"announcements:{announcement_id}",
        ).count()
        assert count == 1
    finally:
        db.close()


def test_pipeline_structure_is_institution_controlled() -> None:
    fixture = _ensure_fixture()
    recruiter_token = login(fixture["recruiter_email"])
    admin_token = login(fixture["admin_email"])

    denied = client.post(
        f"/enterprise/drives/{fixture['drive']}/pipeline/default",
        headers=auth(recruiter_token),
    )
    assert denied.status_code == 403

    allowed = client.post(
        f"/enterprise/drives/{fixture['drive']}/pipeline/default",
        headers=auth(admin_token),
    )
    assert allowed.status_code == 200, allowed.text
    assert len(allowed.json()) >= 1

    recruiter_add = client.post(
        f"/enterprise/drives/{fixture['drive']}/pipeline",
        headers=auth(recruiter_token),
        json={"name": "Recruiter injected stage", "stage_key": "recruiter-stage"},
    )
    assert recruiter_add.status_code == 403


def test_offer_status_recalculates_student_placement_state() -> None:
    fixture = _ensure_fixture()
    student_token = login(fixture["student_email"])

    accepted = client.patch(
        f"/enterprise/offers/{fixture['offer']}",
        headers=auth(student_token),
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    db = SessionLocal()
    try:
        student = db.query(StudentProfile).filter(StudentProfile.id == fixture["student"]).first()
        assert student.placement_status == "placed"
    finally:
        db.close()

    declined = client.patch(
        f"/enterprise/offers/{fixture['offer']}",
        headers=auth(student_token),
        json={"status": "declined"},
    )
    assert declined.status_code == 200, declined.text
    db = SessionLocal()
    try:
        student = db.query(StudentProfile).filter(StudentProfile.id == fixture["student"]).first()
        assert student.placement_status == "unplaced"
    finally:
        db.close()


def test_replacing_offer_and_authorization_files_removes_old_database_blob() -> None:
    fixture = _ensure_fixture()
    recruiter_token = login(fixture["recruiter_email"])
    previous_storage_mode = storage.settings.running_on_vercel
    try:
        storage.settings.running_on_vercel = True

        first_offer = client.post(
            f"/enterprise/offers/{fixture['offer']}/letter",
            headers=auth(recruiter_token),
            files={"file": ("offer-a.pdf", PDF_A, "application/pdf")},
        )
        assert first_offer.status_code == 200, first_offer.text
        db = SessionLocal()
        try:
            offer = db.query(Offer).filter(Offer.id == fixture["offer"]).first()
            first_offer_ref = offer.offer_letter_path
            assert first_offer_ref.startswith("dbfile:")
            first_offer_id = first_offer_ref.split(":", 1)[1]
        finally:
            db.close()

        second_offer = client.post(
            f"/enterprise/offers/{fixture['offer']}/letter",
            headers=auth(recruiter_token),
            files={"file": ("offer-b.pdf", PDF_B, "application/pdf")},
        )
        assert second_offer.status_code == 200, second_offer.text
        db = SessionLocal()
        try:
            offer = db.query(Offer).filter(Offer.id == fixture["offer"]).first()
            assert offer.offer_letter_path != first_offer_ref
            assert db.query(StoredFile).filter(StoredFile.id == first_offer_id).first() is None
        finally:
            db.close()

        first_auth = client.post(
            "/enterprise/company-verification/authorization-letter",
            headers=auth(recruiter_token),
            files={"file": ("authorization-a.pdf", PDF_A, "application/pdf")},
        )
        assert first_auth.status_code == 200, first_auth.text
        db = SessionLocal()
        try:
            recruiter = db.query(RecruiterProfile).filter(RecruiterProfile.id == fixture["recruiter"]).first()
            first_auth_ref = recruiter.authorization_letter_path
            first_auth_id = first_auth_ref.split(":", 1)[1]
        finally:
            db.close()

        second_auth = client.post(
            "/enterprise/company-verification/authorization-letter",
            headers=auth(recruiter_token),
            files={"file": ("authorization-b.pdf", PDF_B, "application/pdf")},
        )
        assert second_auth.status_code == 200, second_auth.text
        db = SessionLocal()
        try:
            recruiter = db.query(RecruiterProfile).filter(RecruiterProfile.id == fixture["recruiter"]).first()
            assert recruiter.authorization_letter_path != first_auth_ref
            assert db.query(StoredFile).filter(StoredFile.id == first_auth_id).first() is None
        finally:
            db.close()
    finally:
        storage.settings.running_on_vercel = previous_storage_mode


def test_mock_interview_score_normalizer_rejects_non_finite_values() -> None:
    assert mock_interview_router._clamp_score(-5) == 0
    assert mock_interview_router._clamp_score(105) == 100
    assert mock_interview_router._clamp_score("81.6") == 82
    assert mock_interview_router._clamp_score("NaN") == 0
    assert mock_interview_router._clamp_score("Infinity") == 0
    assert mock_interview_router._clamp_score(float("-inf")) == 0
