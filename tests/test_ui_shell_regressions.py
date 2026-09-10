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
    assert ".generic-modal-content" in css
    assert ".app-sidebar" in css
    assert "body.modal-open" in css


def test_workspace_view_survives_reload_without_storing_auth_tokens() -> None:
    js = (ROOT / "app/static/ui-state-fixes.js").read_text(encoding="utf-8")
    assert "sessionStorage" in js
    assert "localStorage" not in js
    assert "placeai.workspace.view.v1" in js
    assert "VIEW_PARAM = 'view'" in js
    assert "restoreInitialView" in js
    assert "data-view" in js
    assert "access_token" not in js
    assert "refresh_token" not in js


def test_primary_workspace_boot_still_restores_server_session() -> None:
    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "async function refreshSession()" in js
    assert "await api('/auth/me')" in js
    assert "credentials:'include'" in js or "credentials: 'include'" in js
