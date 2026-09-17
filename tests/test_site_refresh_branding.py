from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_supplied_logo_is_mirrored_and_canonical() -> None:
    app_logo = (ROOT / "app/static/placeai-logo.webp").read_bytes()
    public_logo = (ROOT / "public/static/placeai-logo.webp").read_bytes()
    assert app_logo == public_logo
    assert app_logo[:4] == b"RIFF"
    assert app_logo[8:12] == b"WEBP"

    app_brand = _text("app/static/brand.css")
    public_brand = _text("public/static/brand.css")
    assert app_brand == public_brand
    assert '/static/placeai-logo.webp' in app_brand
    assert 'placeai-logo.svg' not in app_brand


def test_site_refresh_modules_are_mirrored_and_loaded() -> None:
    app_js = _text("app/static/site-refresh.js")
    public_js = _text("public/static/site-refresh.js")
    app_css = _text("app/static/site-refresh.css")
    public_css = _text("public/static/site-refresh.css")
    runtime = _text("app/static/workspace-runtime.js")
    public_runtime = _text("public/static/workspace-runtime.js")

    assert app_js == public_js
    assert app_css == public_css
    assert runtime == public_runtime
    assert "loadSiteRefresh" in runtime
    assert "'/static/site-refresh.js'" in runtime


def test_preparation_lab_has_role_based_courses_tests_and_interviews() -> None:
    js = _text("app/static/site-refresh.js")
    assert "Placement Preparation Lab" in js
    assert "preparation-lab" in js
    assert "STUDENT" in js
    assert "RECRUITER" in js
    assert "INSTITUTION" in js
    assert "Aptitude, reasoning and communication courses" in js
    assert "Timed tests and diagnostic assessments" in js
    assert "Mock interviews with structured feedback" in js
    assert "Structured screening and assessment criteria" in js
    assert "Campus test campaigns and readiness diagnostics" in js


def test_footer_exposes_exact_public_contact_destinations() -> None:
    js = _text("app/static/site-refresh.js")
    assert "https://www.linkedin.com/company/placeai-in/" in js
    assert "sumitjagtap@placeai.in" in js
    assert "https://www.placeai.in/" in js
    assert "Follow PlaceAI on LinkedIn" in js
    assert "mailto:${EMAIL}" in js
    assert 'target="_blank" rel="noopener noreferrer"' in js


def test_institution_access_uses_shared_session_and_timeout_recovery() -> None:
    app_js = _text("app/static/institution-access.js")
    public_js = _text("public/static/institution-access.js")
    assert app_js == public_js
    assert "async function accessToken()" not in app_js
    assert "REQUEST_TIMEOUT_MS = 15000" in app_js
    assert "new AbortController()" in app_js
    assert "credentials: 'include'" in app_js
    assert "Access requests took too long to load" in app_js
    assert "renderGeneration" in app_js
    assert "institution-access-requests" in app_js
