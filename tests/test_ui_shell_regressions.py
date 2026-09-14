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


def test_production_loader_deduplicates_scripts_and_exposes_sentinels() -> None:
    loader = (ROOT / "public/static/app.js").read_text(encoding="utf-8")

    assert "if (window.__PLACEAI_PRODUCTION_BOOTSTRAP__) return;" in loader
    assert "const candidateSrc = new URL(scripts[index], document.baseURI).href;" in loader
    assert "const existing = [...document.scripts].find(script => script.src === candidateSrc);" in loader
    assert "script.dataset.placeaiLoaderState = 'loading';" in loader
    assert "script.dataset.placeaiLoaderState = 'loaded';" in loader
    assert "script.dataset.placeaiLoaderState = 'error';" in loader
    assert "existing.addEventListener('load', settle, {once: true});" in loader
    assert "existing.addEventListener('error', settle, {once: true});" in loader


def test_workspace_boot_reuses_inflight_and_completed_result() -> None:
    core = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    public_core = (ROOT / "public/static/app-core.js").read_text(encoding="utf-8")

    assert core == public_core
    assert "let bootWorkspaceCompleted = false;" in core
    assert "if (bootWorkspaceCompleted) return Promise.resolve(true);" in core
    assert "if (bootWorkspaceInFlight) return bootWorkspaceInFlight;" in core
    assert "if (result) bootWorkspaceCompleted = true;" in core


def test_modal_lock_ownership_and_escape_priority_are_coordinated() -> None:
    core = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    html = (ROOT / "app/templates/index.html").read_text(encoding="utf-8")

    assert "const modalScrollLockOwners = new Set();" in core
    assert "modalScrollLockOwners.add(kind)" in core
    assert "modalScrollLockOwners.delete(kind)" in core
    assert "document.body.classList.toggle('modal-open', modalScrollLockOwners.size > 0);" in core
    assert "if(e.key==='Tab') trapModalTab(e);" in core
    escape = core.split("if(e.key==='Escape')", 1)[1]
    assert escape.index("closeCommandPalette()") < escape.index("closeModal()") < escape.index("closeAuth()")
    assert "restoreModalOpener('auth')" in core
    assert "restoreModalOpener('generic')" in core
    assert 'id="auth-overlay" class="modal-overlay hidden" role="dialog" aria-modal="true" aria-labelledby="auth-title" tabindex="-1"' in html
    assert 'id="generic-modal" class="modal-overlay hidden" role="dialog" aria-modal="true" aria-label="Dialog" tabindex="-1"' in html


def test_auth_role_focus_contract_and_mirror_equivalence() -> None:
    portal = (ROOT / "app/static/access-portal.js").read_text(encoding="utf-8")
    public_portal = (ROOT / "public/static/access-portal.js").read_text(encoding="utf-8")
    ui_state = (ROOT / "app/static/ui-state-fixes.js").read_text(encoding="utf-8")
    public_ui_state = (ROOT / "public/static/ui-state-fixes.js").read_text(encoding="utf-8")
    html = (ROOT / "app/templates/index.html").read_text(encoding="utf-8")
    public_html = (ROOT / "public/index.html").read_text(encoding="utf-8")
    embedded = (ROOT / "app/embedded_pages.py").read_text(encoding="utf-8")

    assert portal == public_portal
    assert ui_state == public_ui_state
    assert html == public_html
    assert portal.count('<h2 id="auth-create-title">') == 1
    assert "name === 'create' ? 'auth-create-title'" in portal
    assert "function focusAccessForm(formId)" in portal
    assert "if (panel) panel.scrollTop = 0;" in portal
    assert "const formTop = formRect.top - panelRect.top + panel.scrollTop;" in portal
    assert "firstInput.focus({preventScroll: true});" in portal
    assert "const roleOrder = ['student', 'recruiter', 'institution_admin', 'platform_admin'];" in portal
    assert 'id="auth-create-title"' in embedded
    assert 'id="auth-reset-title"' in embedded
    assert 'aria-label="Dialog"' in embedded
