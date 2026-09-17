from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workspace_guard_recovers_invalid_loading_state_without_stale_storage() -> None:
    app_js = (ROOT / "app/static/production-polish.js").read_text(encoding="utf-8")
    public_js = (ROOT / "public/static/production-polish.js").read_text(encoding="utf-8")

    assert app_js == public_js
    assert "const invalidActiveView = loading && !activeValid;" in app_js
    assert "if (!stale && !invalidActiveView) return;" in app_js
    assert "if (stale) clearWorkspaceViewState();" in app_js
    assert "if (dashboard && invalidActiveView) dashboard.click();" in app_js


def test_cross_role_workspace_state_is_cleared_but_valid_views_are_preserved() -> None:
    js = (ROOT / "app/static/production-polish.js").read_text(encoding="utf-8")

    assert "const allowed = new Set(buttons.map(button => button.dataset.view).filter(Boolean));" in js
    assert "const stale = [requested, stored].filter(Boolean).find(view => !allowed.has(view));" in js
    assert "sessionStorage.removeItem(WORKSPACE_VIEW_KEY)" in js
    assert "url.searchParams.delete('view')" in js
    assert "if (!stale && !invalidActiveView) return;" in js


def test_institution_admin_and_platform_admin_navigation_remain_separated() -> None:
    core = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    institution_nav = core.split("institution_admin: [", 1)[1].split("platform_admin: [", 1)[0]

    assert "'leads','Access requests'" not in institution_nav
    assert "['Access','leads','Access requests']" in core
    assert "async function renderInstitution(view)" in core
    assert "async function renderPlatform(view)" in core
