from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.routers.institutions import _deadline_has_passed as institution_deadline_has_passed
from app.routers.institutions import _spreadsheet_safe_cell
from app.routers.jobs import _deadline_has_passed as job_deadline_has_passed
from app.routers.platform import _ORG_FIELD_LIMITS
from app.routers.students import _deadline_has_passed as student_deadline_has_passed
from app.utils import MAX_SIGNED_TOKEN_LENGTH, decode_token

ROOT = Path(__file__).resolve().parents[1]


def test_signed_tokens_have_a_hard_input_bound():
    assert MAX_SIGNED_TOKEN_LENGTH == 4096
    with pytest.raises(ValueError):
        decode_token("x" * (MAX_SIGNED_TOKEN_LENGTH + 1), "test-secret", "access")


@pytest.mark.parametrize(
    "checker",
    [student_deadline_has_passed, job_deadline_has_passed, institution_deadline_has_passed],
)
def test_deadline_helpers_handle_aware_and_naive_utc(checker):
    now = datetime.now(timezone.utc)
    assert checker(now - timedelta(seconds=1)) is True
    assert checker(now + timedelta(minutes=1)) is False
    assert checker((now - timedelta(seconds=1)).replace(tzinfo=None)) is True
    assert checker((now + timedelta(minutes=1)).replace(tzinfo=None)) is False
    assert checker(None) is False


@pytest.mark.parametrize("value", ["=1+1", "+cmd", "-1+2", "@SUM(A1:A2)", "   =HYPERLINK(\"https://example.test\")"])
def test_institution_csv_export_neutralizes_spreadsheet_formulas(value):
    protected = _spreadsheet_safe_cell(value)
    assert isinstance(protected, str)
    assert protected.startswith("'")


def test_institution_csv_export_does_not_modify_regular_values():
    assert _spreadsheet_safe_cell("Student Name") == "Student Name"
    assert _spreadsheet_safe_cell(8.5) == 8.5
    assert _spreadsheet_safe_cell(True) is True


def test_organization_database_string_limits_have_request_guards():
    assert _ORG_FIELD_LIMITS == {
        "domain": 200,
        "website": 500,
        "city": 120,
        "state": 120,
        "country": 120,
        "primary_color": 20,
    }


def test_jobs_are_archived_instead_of_hard_deleted():
    source = (ROOT / "app" / "routers" / "jobs.py").read_text(encoding="utf-8")
    delete_section = source.split('@router.delete("/{job_id}"', 1)[1].split('@router.get("/{job_id}/applicants"', 1)[0]
    assert "job.is_active = False" in delete_section
    assert "db.delete(job)" not in delete_section


def test_drives_are_archived_instead_of_hard_deleted():
    source = (ROOT / "app" / "routers" / "institutions.py").read_text(encoding="utf-8")
    delete_section = source.split('@router.delete("/drives/{drive_id}"', 1)[1].split('@router.get("/audit"', 1)[0]
    assert "drive.status = DriveStatus.closed" in delete_section
    assert "db.delete(drive)" not in delete_section


def test_student_campus_visibility_excludes_draft_drives():
    source = (ROOT / "app" / "routers" / "students.py").read_text(encoding="utf-8")
    visibility_section = source.split("def _visible_jobs_for", 1)[1].split('@router.get("/jobs"', 1)[0]
    assert "PlacementDrive.status == DriveStatus.open" in visibility_section
    assert "DriveStatus.draft" not in visibility_section
    assert "profile.is_verified" in visibility_section
    assert "registration_deadline" in visibility_section


def test_password_reset_consumption_locks_recovery_credential():
    source = (ROOT / "app" / "routers" / "auth.py").read_text(encoding="utf-8")
    reset_section = source.split('@router.post("/reset-password")', 1)[1]
    assert ".with_for_update()" in reset_section


def test_production_api_disables_openapi_and_docs():
    source = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
    assert 'docs_url=None if settings.is_production else "/docs"' in source
    assert 'openapi_url=None if settings.is_production else "/openapi.json"' in source
    assert 'if not settings.is_production:\n        payload["database_target"]' in source
