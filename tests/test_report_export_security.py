from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.app import app
from app.database import Base, SessionLocal, engine
from app.models import Organization, StudentProfile, User, UserRole
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
    db.add_all([admin, student_user])
    db.flush()
    db.add(StudentProfile(
        user_id=student_user.id,
        organization_id=org.id,
        college=org.name,
        full_name='=HYPERLINK("https://example.invalid","click")',
        branch="  @SUM(1,1)",
        graduation_year=2026,
        cgpa=8.2,
    ))
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


def test_pdf_report_remains_available_without_spreadsheet_rewriting():
    response = client.get("/enterprise/reports/placement-report.pdf", headers=auth(admin_token()))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF-")
