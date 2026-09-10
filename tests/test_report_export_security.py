from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import Application, ApprovalStatus, Job, Organization, RecruiterProfile, StudentProfile, User, UserRole
from app.routers.report_export_safe import spreadsheet_safe_cell
from app.utils import get_hashed_password

client = TestClient(app)


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    org = Organization(name="Export Safety Institute", slug="export-safety")
    db.add(org)
    db.flush()
    admin = User(
        email="reports.admin@placeai.example.com",
        username="reportsadmin",
        hashed_password=get_hashed_password("ReportsAdmin123!"),
        role=UserRole.institution_admin,
        organization_id=org.id,
        email_verified=True,
    )
    student_user = User(
        email="formula.student@placeai.example.com",
        username="formulastudent",
        hashed_password=get_hashed_password("FormulaStudent123!"),
        role=UserRole.student,
        organization_id=org.id,
        email_verified=True,
    )
    recruiter_users = [
        User(
            email=f"reports.recruiter{index}@placeai.example.com",
            username=f"reportsrecruiter{index}",
            hashed_password=get_hashed_password(f"ReportsRecruiter{index}123!"),
            role=UserRole.recruiter,
            email_verified=True,
        )
        for index in range(1, 4)
    ]
    db.add_all([admin, student_user, *recruiter_users])
    db.flush()
    student = StudentProfile(
        user_id=student_user.id,
        organization_id=org.id,
        college=org.name,
        full_name='=HYPERLINK("https://example.invalid","click")',
        branch="  @SUM(1,1)",
        graduation_year=2026,
        cgpa=8.2,
    )
    recruiters = [
        RecruiterProfile(
            user_id=recruiter_users[0].id,
            full_name="Applied Recruiter",
            company_name="Applied Public Co",
            is_verified=True,
        ),
        RecruiterProfile(
            user_id=recruiter_users[1].id,
            full_name="Campus Recruiter",
            company_name="Campus Target Co",
            is_verified=True,
            provisioned_by_organization_id=org.id,
        ),
        RecruiterProfile(
            user_id=recruiter_users[2].id,
            full_name="Unrelated Recruiter",
            company_name="Unrelated Public Co",
            is_verified=True,
        ),
    ]
    db.add(student)
    db.add_all(recruiters)
    db.flush()
    applied_public_job = Job(
        recruiter_id=recruiters[0].id,
        title="Public Applied Role",
        description="A public role that becomes relevant after an institution student applies.",
        visibility="public",
        approval_status=ApprovalStatus.approved,
        is_active=True,
    )
    targeted_job = Job(
        recruiter_id=recruiters[1].id,
        title="Campus Targeted Role",
        description="A role explicitly targeted to this institution before applications arrive.",
        visibility="campus",
        target_organization_id=org.id,
        approval_status=ApprovalStatus.approved,
        is_active=True,
    )
    unrelated_public_job = Job(
        recruiter_id=recruiters[2].id,
        title="Unrelated Public Role",
        description="A platform public role with no relationship to this institution.",
        visibility="public",
        approval_status=ApprovalStatus.approved,
        is_active=True,
    )
    db.add_all([applied_public_job, targeted_job, unrelated_public_job])
    db.flush()
    db.add(Application(student_id=student.id, job_id=applied_public_job.id))
    db.commit()
    db.close()


def admin_token() -> str:
    response = client.post("/auth/login-json", json={
        "email": "reports.admin@placeai.example.com",
        "password": "ReportsAdmin123!",
    })
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_spreadsheet_safe_cell_only_changes_formula_capable_strings():
    assert spreadsheet_safe_cell("Normal Student") == "Normal Student"
    assert spreadsheet_safe_cell(12.5) == 12.5
    assert spreadsheet_safe_cell(None) is None
    assert spreadsheet_safe_cell("=1+1") == "'=1+1"
    assert spreadsheet_safe_cell("  +SUM(1,1)") == "'  +SUM(1,1)"
    assert spreadsheet_safe_cell("\t@cmd") == "'\t@cmd"
    assert spreadsheet_safe_cell("-10") == "'-10"


def test_csv_report_neutralizes_formula_shaped_student_fields():
    response = client.get("/enterprise/reports/placement-report.csv", headers=auth(admin_token()))
    assert response.status_code == 200, response.text
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][0:3] == ["Student", "Email", "Department"]
    assert rows[1][0].startswith("'=")
    assert rows[1][2].startswith("'  @")
    assert "nosniff" == response.headers.get("x-content-type-options")


def test_xlsx_report_writes_risky_values_as_literal_strings_not_formulas():
    response = client.get("/enterprise/reports/placement-report.xlsx", headers=auth(admin_token()))
    assert response.status_code == 200, response.text
    workbook = load_workbook(io.BytesIO(response.content), data_only=False)
    worksheet = workbook.active
    assert worksheet["A2"].value.startswith("'=")
    assert worksheet["A2"].data_type == "s"
    assert worksheet["C2"].value.startswith("'  @")
    assert worksheet["C2"].data_type == "s"
    assert worksheet["D2"].value == 2026
    assert worksheet["E2"].value == 8.2


def test_company_participation_only_includes_targeted_or_evidenced_public_jobs():
    response = client.get("/enterprise/reports/company-participation.csv", headers=auth(admin_token()))
    assert response.status_code == 200, response.text
    rows = list(csv.reader(io.StringIO(response.text)))
    by_company = {row[0]: row for row in rows[1:]}
    assert "Applied Public Co" in by_company
    assert "Campus Target Co" in by_company
    assert "Unrelated Public Co" not in by_company
    assert by_company["Applied Public Co"][1:3] == ["1", "1"]
    assert by_company["Campus Target Co"][1:3] == ["1", "0"]


def test_recruiter_activity_uses_the_same_institution_evidence_boundary():
    response = client.get("/enterprise/reports/recruiter-activity.csv", headers=auth(admin_token()))
    assert response.status_code == 200, response.text
    rows = list(csv.reader(io.StringIO(response.text)))
    companies = {row[0] for row in rows[1:]}
    assert "Applied Public Co" in companies
    assert "Campus Target Co" in companies
    assert "Unrelated Public Co" not in companies


def test_pdf_report_remains_available_without_spreadsheet_rewriting():
    response = client.get("/enterprise/reports/placement-report.pdf", headers=auth(admin_token()))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF-")
