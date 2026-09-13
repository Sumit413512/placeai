from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings


ROOT = Path(__file__).resolve().parents[1]


def _production_vercel_env(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "placeai-rxpp.vercel.app")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://runtime:secret@example.invalid/placeai")
    monkeypatch.setenv("JWT_SECRET_KEY", "a" * 40)
    monkeypatch.setenv("JWT_REFRESH_SECRET_KEY", "b" * 40)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://placeai-rxpp.vercel.app")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "false")
    monkeypatch.setenv("DEV_SHOW_RESET_TOKEN", "false")
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    monkeypatch.delenv("PASSWORD_RESET_BASE_URL", raising=False)


def test_vercel_production_recovery_links_land_on_primary_origin(monkeypatch) -> None:
    _production_vercel_env(monkeypatch)
    settings = Settings()
    assert settings.base_url == "https://placeai-rxpp.vercel.app"
    assert settings.configuration_error_codes() == []


def test_stale_render_public_app_override_is_retired_on_vercel(monkeypatch) -> None:
    _production_vercel_env(monkeypatch)
    monkeypatch.setenv("PUBLIC_APP_URL", "https://placeai-recovery.onrender.com")
    settings = Settings()
    assert settings.base_url == "https://placeai-rxpp.vercel.app"


def test_explicit_custom_public_domain_is_preserved(monkeypatch) -> None:
    _production_vercel_env(monkeypatch)
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.placeai.in")
    settings = Settings()
    assert settings.base_url == "https://app.placeai.in"


def test_vercel_routes_primary_origin_through_fastapi_shell() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert "rewrites" not in config
    assert config["git"]["deploymentEnabled"]["main"] is True
    assert config["git"]["deploymentEnabled"]["**"] is False

    app_source = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
    for asset in (
        "/static/workspace-runtime.js",
        "/static/provisioning-password-fix.js",
        "/static/integration-readiness.js",
        "/static/ai-readiness.js",
    ):
        assert asset in app_source
    assert 'def root()' in app_source
    assert 'TEMPLATE_DIR / "index.html"' in app_source


def test_release_version_matches_live_backend_contract() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "3.1.4"
