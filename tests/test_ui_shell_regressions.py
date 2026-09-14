from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.app import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_root_injects_ui_resilience_assets() -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "/static/access-portal.css" in html
    assert "/static/access-portal.js" in html
    assert "/static/ui-fixes.css" in html
    assert "/static/ui-state-fixes.js" in html


def test_auth_dialog_is_bounded_to_dynamic_viewport() -> None:
    css = (ROOT / "app/static/ui-fixes.css").read_text(encoding="utf-8")
    assert "100dvh" in css
    assert ".auth-modal" in css
    assert ".auth-form-panel" in css
    assert "overflow-y: auto" in css
    assert ".modal-close" in css
    assert ".auth-inline-cancel" in css
    assert ".generic-modal-content" in css
    assert ".app-sidebar" in css
    assert ".app-nav" in css
    assert "body.modal-open" in css


def test_signup_cancel_button_stays_in_normal_flow() -> None:
    app_css = (ROOT / "app/static/ui-fixes.css").read_text(encoding="utf-8")
    public_css = (ROOT / "public/static/ui-fixes.css").read_text(encoding="utf-8")

    assert app_css == public_css
    cancel_rules = [part.split("}", 1)[0] for part in app_css.split(".auth-inline-cancel")[1:]]
    assert len(cancel_rules) == 1

    cancel_rule = cancel_rules[0]
    assert "position: static" in cancel_rule
    assert "box-shadow: none" in cancel_rule
    for forbidden in ("position: sticky", "position: fixed", "bottom:", "z-index:"):
        assert forbidden not in cancel_rule


def test_workspace_reload_restores_session_and_view_without_web_storage_tokens() -> None:
    js = (ROOT / "app/static/ui-state-fixes.js").read_text(encoding="utf-8")
    assert "sessionStorage" in js
    assert "localStorage" not in js
    assert "placeai.workspace.view.v1" in js
    assert "placeai.session.active.v1" in js
    assert "VIEW_PARAM = 'view'" in js
    assert "restoreInitialView" in js
    assert "refreshRuntimeToken" in js
    assert "'/auth/refresh'" in js
    assert "credentials: 'include'" in js
    assert "runtimeToken" in js
    assert "auth-inline-cancel" in js
    assert "data-view" in js
    # JWTs may be held in JS memory for the current page, but must never be written
    # to localStorage/sessionStorage.
    assert "sessionStorage.setItem('access_token'" not in js
    assert 'sessionStorage.setItem("access_token"' not in js
    assert "localStorage.setItem" not in js


def test_primary_workspace_boot_keeps_server_session_refresh_path() -> None:
    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "async function refreshSession()" in js
    assert "await api('/auth/me')" in js
    assert "credentials:'include'" in js or "credentials: 'include'" in js
