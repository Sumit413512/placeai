from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import AuditEvent, Organization, User, UserRole
from app.utils import get_hashed_password

client = TestClient(app)
RUN = uuid.uuid4().hex[:8]
ORG_SLUG = f"batch41-{RUN}"
PLATFORM_EMAIL = f"batch41-platform-{RUN}@placeai.example.com"
PLATFORM_PASSWORD = "Batch41Platform123!"
ADMIN_EMAIL = f"batch41-admin-{RUN}@placeai.example.com"
ADMIN_TEMP = "Batch41AdminTemp123!"
ADMIN_PERMANENT = "Batch41AdminPermanent456!"
STUDENT_EMAIL = f"batch41-student-{RUN}@placeai.example.com"
STUDENT_TEMP = "Batch41StudentTemp123!"
RECRUITER_EMAIL = f"batch41-recruiter-{RUN}@placeai.example.com"
RECRUITER_TEMP = "Batch41RecruiterTemp123!"
PLATFORM_RECRUITER_EMAIL = f"batch41-platform-recruiter-{RUN}@placeai.example.com"
PLATFORM_RECRUITER_TEMP = "Batch41PlatformRecruiterTemp123!"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(email: str, password: str) -> str:
    response = client.post("/auth/login-json", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def assert_response_does_not_expose_credentials(response, credential: str) -> None:
    assert response.status_code in {200, 201}, response.text
    body = response.text
    assert credential not in body
    assert "temporary_password" not in body
    assert "hashed_password" not in body


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        org = Organization(name=f"Batch 41 Institute {RUN}", slug=ORG_SLUG, is_active=True)
        db.add(org)
        db.add(
            User(
                email=PLATFORM_EMAIL,
                username=f"batch41_platform_{RUN}",
                hashed_password=get_hashed_password(PLATFORM_PASSWORD),
                role=UserRole.platform_admin,
                email_verified=True,
                must_change_password=False,
            )
        )
        db.commit()
    finally:
        db.close()


def test_provisioning_responses_and_audit_metadata_do_not_expose_credentials() -> None:
    platform_token = login(PLATFORM_EMAIL, PLATFORM_PASSWORD)

    admin = client.post(
        "/platform/institution-admins",
        headers=auth(platform_token),
        json={
            "email": ADMIN_EMAIL,
            "username": f"batch41_admin_{RUN}",
            "full_name": "Batch 41 Admin",
            "temporary_password": ADMIN_TEMP,
            "organization_slug": ORG_SLUG,
        },
    )
    assert_response_does_not_expose_credentials(admin, ADMIN_TEMP)
    assert admin.json()["must_change_password"] is True

    platform_recruiter = client.post(
        "/platform/recruiters",
        headers=auth(platform_token),
        json={
            "email": PLATFORM_RECRUITER_EMAIL,
            "username": f"batch41_platform_recruiter_{RUN}",
            "full_name": "Batch 41 Platform Recruiter",
            "company_name": "Batch 41 Platform Co",
            "temporary_password": PLATFORM_RECRUITER_TEMP,
            "organization_slug": ORG_SLUG,
        },
    )
    assert_response_does_not_expose_credentials(platform_recruiter, PLATFORM_RECRUITER_TEMP)
    assert platform_recruiter.json()["must_change_password"] is True

    admin_token = login(ADMIN_EMAIL, ADMIN_TEMP)
    rotated = client.post(
        "/auth/change-password",
        headers=auth(admin_token),
        json={"current_password": ADMIN_TEMP, "new_password": ADMIN_PERMANENT},
    )
    assert rotated.status_code == 200, rotated.text
    admin_token = rotated.json()["access_token"]

    student = client.post(
        "/institutions/students",
        headers=auth(admin_token),
        json={
            "email": STUDENT_EMAIL,
            "username": f"batch41_student_{RUN}",
            "full_name": "Batch 41 Student",
            "temporary_password": STUDENT_TEMP,
            "degree": "B.Tech",
            "branch": "Computer Science",
            "graduation_year": 2027,
            "cgpa": 8.4,
        },
    )
    assert_response_does_not_expose_credentials(student, STUDENT_TEMP)
    assert student.json()["must_change_password"] is True

    recruiter = client.post(
        "/institutions/recruiters",
        headers=auth(admin_token),
        json={
            "email": RECRUITER_EMAIL,
            "username": f"batch41_recruiter_{RUN}",
            "full_name": "Batch 41 Recruiter",
            "company_name": "Batch 41 Campus Co",
            "temporary_password": RECRUITER_TEMP,
        },
    )
    assert_response_does_not_expose_credentials(recruiter, RECRUITER_TEMP)
    assert recruiter.json()["must_change_password"] is True

    db = SessionLocal()
    try:
        events = db.query(AuditEvent).filter(
            AuditEvent.action.in_(
                [
                    "platform.institution_admin.provisioned",
                    "platform.recruiter.provisioned",
                    "institution.student.provisioned",
                    "institution.recruiter.provisioned",
                ]
            )
        ).all()
        audit_dump = "\n".join(event.metadata_json or "" for event in events)
    finally:
        db.close()

    for credential in (ADMIN_TEMP, PLATFORM_RECRUITER_TEMP, STUDENT_TEMP, RECRUITER_TEMP):
        assert credential not in audit_dump
    assert "temporary_password" not in audit_dump
    assert "hashed_password" not in audit_dump


def test_provisioning_ui_marks_credentials_write_only_and_clears_inputs() -> None:
    source = client.get("/static/account-security.js")
    assert source.status_code == 200
    text = source.text
    assert "institution-student-form" in text
    assert "institution-recruiter-form" in text
    assert "admin-form" in text
    assert "write-only" in text
    assert "PlaceAI will not display this value again" in text
    assert "queueMicrotask" in text
    assert "student-csv-file" in text
    assert "remove completed local copies" in text
    assert "/auth/change-password" in text
