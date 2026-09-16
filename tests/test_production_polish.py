from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_production_polish_assets_are_mirrored() -> None:
    assert _read("app/static/production-polish.js") == _read("public/static/production-polish.js")
    assert _read("app/static/production-polish.css") == _read("public/static/production-polish.css")
    assert _read("app/static/legal-links.js") == _read("public/static/legal-links.js")


def test_polish_loader_and_mobile_navigation_contract() -> None:
    loader = _read("app/static/legal-links.js")
    polish = _read("app/static/production-polish.js")
    styles = _read("app/static/production-polish.css")
    template = _read("app/templates/index.html")

    assert "'/static/production-polish.js'" in loader
    assert 'data-action="toggle-mobile-menu"' in template
    assert ".mobile-menu[data-action=\"toggle-mobile-menu\"]" in polish
    assert "setMobileNavigation(!header?.classList.contains('mobile-open'))" in polish
    assert "event.stopImmediatePropagation();" in polish
    assert "aria-expanded" in polish
    assert "Close navigation" in polish
    assert "#marketing-site .site-header.mobile-open .marketing-nav" in styles
    assert "display: flex !important" in styles
    assert "#marketing-site .site-header.mobile-open .header-actions" in styles


def test_login_summary_is_deterministically_synchronized_and_spaced() -> None:
    polish = _read("app/static/production-polish.js")
    styles = _read("app/static/production-polish.css")

    for role in ("student", "recruiter", "institution_admin", "platform_admin"):
        assert f"{role}:" in polish
    assert "syncLoginRoleSummary" in polish
    assert '[data-access-role-mode="login"].is-selected' in polish
    assert "data.accessSummaryLabel" not in polish
    assert "label.dataset.accessSummaryLabel" in polish
    assert "detail.dataset.accessSummaryDetail" in polish
    assert "summary.setAttribute('aria-live', 'polite')" in polish
    assert ".access-selection-summary b" in styles
    assert "display: block" in styles
    assert "margin-top: 3px" in styles


def test_recruiter_inline_cancel_remains_in_normal_flow() -> None:
    app_css = _read("app/static/ui-fixes.css")
    public_css = _read("public/static/ui-fixes.css")
    assert app_css == public_css

    rule = app_css.split(".auth-inline-cancel", 1)[1].split("}", 1)[0]
    assert "position: static" in rule
    assert "box-shadow: none" in rule
