from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_signup_ui_surfaces_fastapi_validation_details() -> None:
    source = (ROOT / "app/static/access-portal.js").read_text(encoding="utf-8")
    assert "function apiErrorMessage(data, status)" in source
    assert "Array.isArray(detail)" in source
    assert "item.msg.replace" in source
    assert "Request failed (${status})" in source


def test_signup_ui_enforces_backend_password_policy_before_submit() -> None:
    source = (ROOT / "app/static/access-portal.js").read_text(encoding="utf-8")
    assert "function validateStudentSignup(body)" in source
    assert "Password must contain an uppercase letter." in source
    assert "Password must contain a lowercase letter." in source
    assert "Password must contain a number." in source
    assert "Password must contain a symbol." in source
    assert "validateStudentSignup(body);" in source
