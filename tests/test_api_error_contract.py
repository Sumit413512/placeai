from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.app import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]


def test_backend_validation_contract_is_structured_for_field_mapping() -> None:
    response = client.post(
        "/auth/signup",
        json={
            "username": "bad username with spaces",
            "email": "not-an-email",
            "password": "weak",
            "role": "student",
        },
    )
    assert response.status_code == 422
    detail = response.json().get("detail")
    assert isinstance(detail, list) and detail
    assert all(isinstance(item.get("loc"), list) for item in detail)
    assert all(isinstance(item.get("msg"), str) for item in detail)


def test_production_shell_loads_shared_error_contract_before_consumers() -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "/static/api-errors.css" in html
    assert "/static/api-errors.js" in html
    assert html.index("/static/api-errors.js") < html.index("/static/access-portal.js")
    assert html.index("/static/api-errors.js") < html.index("/static/app.js")


def test_mock_interview_uses_shared_error_contract() -> None:
    response = client.get("/mock-interview")
    assert response.status_code == 200
    html = response.text
    assert "/static/api-errors.css" in html
    assert "/static/api-errors.js" in html
    assert html.index("/static/api-errors.js") < html.index("/static/mock-interview.js")


def test_duplicate_frontend_error_parsers_are_retired() -> None:
    app_js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    access_js = (ROOT / "app/static/access-portal.js").read_text(encoding="utf-8")
    security_js = (ROOT / "app/static/account-security.js").read_text(encoding="utf-8")
    mock_js = (ROOT / "app/static/mock-interview.js").read_text(encoding="utf-8")
    shared = (ROOT / "app/static/api-errors.js").read_text(encoding="utf-8")

    assert "data.detail.map(x => x.msg).join(', ')" not in app_js
    assert "function apiErrorMessage" not in access_js
    assert "function validationMessage" not in security_js
    assert "Request failed (${response.status})" not in mock_js

    for source in (app_js, access_js, security_js, mock_js):
        assert "PlaceAIApiErrors" in source

    assert "fieldErrors" in shared
    assert "applyToForm" in shared
    assert "aria-invalid" in shared
    assert "Request failed (" not in shared
    assert "Please correct the highlighted fields and try again." in shared


def test_workspace_submit_handlers_apply_field_level_errors() -> None:
    app_js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    access_js = (ROOT / "app/static/access-portal.js").read_text(encoding="utf-8")
    security_js = (ROOT / "app/static/account-security.js").read_text(encoding="utf-8")
    mock_js = (ROOT / "app/static/mock-interview.js").read_text(encoding="utf-8")

    assert "apiErrors.applyToForm(f,err)" in app_js
    assert "apiErrors.applyToForm(form, error" in access_js
    assert "apiErrors.applyToForm(form, err, error)" in security_js
    assert "apiErrors.applyToForm(form, error)" in mock_js
