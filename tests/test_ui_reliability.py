from pathlib import Path

from fastapi.testclient import TestClient

from app.app import app


ROOT = Path(__file__).resolve().parents[1]


def test_root_loads_ui_reliability_assets():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    html = response.text
    assert '/static/ui-reliability.css' in html
    assert '/static/ui-reliability.js' in html
    assert html.index('/static/ui-reliability.js') < html.index('/static/app.js')


def test_ui_reliability_css_keeps_dialog_controls_inside_viewport():
    css = (ROOT / "app/static/ui-reliability.css").read_text(encoding="utf-8")
    assert "max-height:calc(100dvh - 32px)" in css
    assert ".auth-form-panel" in css and "overflow-y:auto" in css
    assert ".auth-modal>.modal-close" in css
    assert ".auth-inline-cancel" in css
    assert ".app-nav" in css and "overflow-y:auto" in css


def test_ui_reliability_js_restores_session_and_last_workspace_view():
    js = (ROOT / "app/static/ui-reliability.js").read_text(encoding="utf-8")
    assert "placeai:last-view" in js
    assert "refreshAccessToken" in js
    assert "path === '/auth/me'" in js
    assert "sessionStorage.setItem(LAST_VIEW_KEY" in js
    assert "button.click()" in js
    assert "auth-inline-cancel" in js
