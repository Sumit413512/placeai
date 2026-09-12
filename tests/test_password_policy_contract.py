from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas import AdminUserProvision, InstitutionStudentCreate


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_password_policy_matches_backend_requirements() -> None:
    source = (ROOT / "app/static/api-errors.js").read_text(encoding="utf-8")
    assert "Use 12–128 characters with uppercase, lowercase, a number and a symbol." in source
    assert "temporary_password" in source
    assert "new_password" in source
    assert "setCustomValidity" in source
    assert "MutationObserver" in source
    assert "Password must contain a lowercase letter." in source
    assert "Password must contain an uppercase letter." in source
    assert "Password must contain a number." in source
    assert "Password must contain a symbol." in source


def test_provisioning_forms_are_covered_by_shared_password_policy() -> None:
    app_js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    for form_id in ("admin-form", "institution-student-form", "institution-recruiter-form"):
        assert form_id in app_js
    policy = (ROOT / "app/static/api-errors.js").read_text(encoding="utf-8")
    assert "name === 'temporary_password'" in policy


@pytest.mark.parametrize(
    "password",
    [
        "abcdefghijklmnop",
        "ABCDEFGHIJKLMNOP1!",
        "Abcdefghijklmnop!",
        "Abcdefghijklmnop1",
        "Short1!",
    ],
)
def test_admin_provision_rejects_passwords_missing_any_required_class(password: str) -> None:
    with pytest.raises(ValidationError):
        AdminUserProvision(
            email="tpo@example.com",
            username="exampletpo",
            full_name="Example TPO",
            temporary_password=password,
            organization_slug="example-campus",
        )


def test_valid_strong_password_is_accepted_for_all_provisioning_models() -> None:
    password = "PlaceAITemp123!"
    admin = AdminUserProvision(
        email="tpo@example.com",
        username="exampletpo",
        full_name="Example TPO",
        temporary_password=password,
        organization_slug="example-campus",
    )
    student = InstitutionStudentCreate(
        email="student@example.com",
        username="examplestudent",
        full_name="Example Student",
        temporary_password=password,
    )
    assert admin.temporary_password == password
    assert student.temporary_password == password
