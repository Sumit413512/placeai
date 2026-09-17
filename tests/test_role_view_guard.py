from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_production_polish_recovers_stale_cross_role_workspace_views() -> None:
    app_js = (ROOT / "app/static/production-polish.js").read_text(encoding="utf-8")
    public_js = (ROOT / "public/static/production-polish.js").read_text(encoding="utf-8")

    assert app_js == public_js
    assert "const WORKSPACE_VIEW_KEY = 'placeai.workspace.view.v1';" in app_js
    assert "function repairInvalidWorkspaceView()" in app_js
    assert "const allowed = new Set(buttons.map(button => button.dataset.view).filter(Boolean));" in app_js
    assert "const stale = [requested, stored].filter(Boolean).find(view => !allowed.has(view));" in app_js
    assert "sessionStorage.removeItem(WORKSPACE_VIEW_KEY)" in app_js
    assert "url.searchParams.delete('view')" in app_js
    assert "button[data-view=\"dashboard\"]" in app_js
    assert "dashboard.click();" in app_js


def test_institution_admin_does_not_expose_platform_access_requests_view() -> None:
    core = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    institution_nav = core.split("institution_admin: [", 1)[1].split("],\n    platform_admin:", 1)[0]
    platform_nav = core.split("platform_admin: [", 1)[1].split("]", 1)[0]

    assert "'leads','Access requests'" not in institution_nav
    assert "'leads','Access requests'" in platform_nav
    assert "async function renderInstitution(view)" in core
    assert "async function renderPlatform(view)" in core
