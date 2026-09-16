from __future__ import annotations

from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_ui_resilience_mirrors_are_identical() -> None:
    app_css = (ROOT / "app/static/ui-fixes.css").read_text(encoding="utf-8")
    public_css = (ROOT / "public/static/ui-fixes.css").read_text(encoding="utf-8")
    assert app_css == public_css


def test_auth_and_workspace_surfaces_can_shrink_without_intrinsic_overflow() -> None:
    css = (ROOT / "app/static/ui-fixes.css").read_text(encoding="utf-8")

    required = (
        ".auth-form-panel > *",
        ".form-stack > *",
        ".form-two > *",
        ".access-selection-summary > *",
        ".access-mode-row > *",
        ".app-content-wrap",
        ".page-head > *",
        ".data-toolbar > *",
        ".resume-card > *",
        "min-width: 0;",
        "max-width: 100%;",
        "overflow-x: hidden;",
        "overflow-wrap: anywhere;",
    )
    for token in required:
        assert token in css


def test_auth_reflows_at_mobile_zoom_widths() -> None:
    css = (ROOT / "app/static/ui-fixes.css").read_text(encoding="utf-8")

    assert "@media (max-width: 430px)" in css
    assert "@media (max-width: 320px)" in css
    assert "@media (max-width: 240px)" in css
    assert "width: 100vw;" in css
    assert "height: 100dvh;" in css
    assert "grid-template-columns: 1fr;" in css
    assert "font-size: 16px;" in css


def test_mock_interview_uses_shared_viewport_hardening() -> None:
    app_html = (ROOT / "app/templates/mock-interview.html").read_text(encoding="utf-8")
    public_html = (ROOT / "public/mock-interview.html").read_text(encoding="utf-8")

    assert app_html == public_html
    assert '<link rel="stylesheet" href="/static/ui-fixes.css">' in app_html


def test_production_vercel_canonical_origin_overrides_stale_public_aliases(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "placeai-rxpp.vercel.app")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://placeai-rxpp.vercel.app")
    monkeypatch.setenv("PASSWORD_RESET_BASE_URL", "https://placeai-rxpp.vercel.app")
    monkeypatch.setenv("PLACEAI_CANONICAL_PUBLIC_URL", "https://www.placeai.in")

    settings = Settings()
    assert settings.base_url == "https://www.placeai.in"


def test_vercel_config_sets_public_origin_and_favicon_content_type() -> None:
    vercel_json = (ROOT / "vercel.json").read_text(encoding="utf-8")
    assert '"PLACEAI_CANONICAL_PUBLIC_URL": "https://www.placeai.in"' in vercel_json
    assert '"source": "/favicon.ico"' in vercel_json
    assert '"value": "image/svg+xml; charset=utf-8"' in vercel_json
