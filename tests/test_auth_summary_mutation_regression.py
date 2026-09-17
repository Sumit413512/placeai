from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "app" / "static" / "production-polish.js"
PUBLIC_JS = ROOT / "public" / "static" / "production-polish.js"
APP_CSS = ROOT / "app" / "static" / "access-portal.css"
PUBLIC_CSS = ROOT / "public" / "static" / "access-portal.css"


def test_auth_summary_script_never_targets_decorative_dot_as_detail():
    app_js = APP_JS.read_text(encoding="utf-8")
    public_js = PUBLIC_JS.read_text(encoding="utf-8")
    assert app_js == public_js
    assert "[data-access-summary-short]" in app_js
    assert "summary.querySelector(':scope > div > span')" in app_js
    assert "summary.querySelector('[data-access-summary-detail], div > span')" not in app_js
    assert "dot.textContent = ''" in app_js
    assert "dot.setAttribute('aria-hidden', 'true')" in app_js


def test_extreme_width_password_control_keeps_reserved_text_space():
    app_css = APP_CSS.read_text(encoding="utf-8")
    public_css = PUBLIC_CSS.read_text(encoding="utf-8")
    assert app_css == public_css
    assert "@media(max-width:320px){.password-wrap input{padding-right:55px!important}}" in app_css
    assert ".auth-form-panel input::placeholder,.auth-form-panel textarea::placeholder{color:transparent}" in app_css
