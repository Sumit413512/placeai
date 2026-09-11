from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_signup_ui_surfaces_fastapi_validation_details() -> None:
    source = (ROOT / "app/static/access-portal.js").read_text(encoding="utf-8")
    shared = (ROOT / "app/static/api-errors.js").read_text(encoding="utf-8")

    assert "window.PlaceAIApiErrors" in source
    assert "apiErrors.createError(data, response.status)" in source
    assert "apiErrors.applyToForm(form, error" in source
    assert "fieldErrors" in shared
    assert "Array.isArray(detail)" in shared
    assert "aria-invalid" in shared
    assert "Please correct the highlighted fields and try again." in shared


def test_signup_ui_enforces_backend_password_policy_before_submit() -> None:
    source = (ROOT / "app/static/access-portal.js").read_text(encoding="utf-8")
    assert "function validateStudentSignup(body)" in source
    assert "Password must contain an uppercase letter." in source
    assert "Password must contain a lowercase letter." in source
    assert "Password must contain a number." in source
    assert "Password must contain a symbol." in source
    assert "validateStudentSignup(body);" in source
