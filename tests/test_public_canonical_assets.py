from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.app as app_module
from app.config import Settings, _is_vercel_platform_url


PUBLIC_DIR = Path(__file__).resolve().parents[1] / "public"
CANONICAL_PUBLIC_URL = "https://www.placeai.in"
VERCEL_ORIGIN = "https://placeai-rxpp.vercel.app"


def test_production_public_base_prefers_configured_public_url(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "settings",
        SimpleNamespace(is_production=True, base_url=CANONICAL_PUBLIC_URL),
    )
    request = SimpleNamespace(base_url=f"{VERCEL_ORIGIN}/")
    assert app_module._public_base(request) == CANONICAL_PUBLIC_URL


def test_sitemap_and_robots_use_canonical_public_domain(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "settings",
        SimpleNamespace(is_production=True, base_url=CANONICAL_PUBLIC_URL),
    )
    client = TestClient(app_module.app)

    robots = client.get("/robots.txt")
    sitemap = client.get("/sitemap.xml")

    assert robots.status_code == 200
    assert f"Sitemap: {CANONICAL_PUBLIC_URL}/sitemap.xml" in robots.text
    assert sitemap.status_code == 200
    assert f"{CANONICAL_PUBLIC_URL}/" in sitemap.text
    assert "placeai-rxpp.vercel.app" not in sitemap.text


def test_static_public_crawler_assets_match_canonical_domain():
    """Vercel serves public/ assets before FastAPI routes; keep both layers aligned."""
    robots = (PUBLIC_DIR / "robots.txt").read_text(encoding="utf-8")
    sitemap = (PUBLIC_DIR / "sitemap.xml").read_text(encoding="utf-8")

    assert f"Sitemap: {CANONICAL_PUBLIC_URL}/sitemap.xml" in robots
    assert VERCEL_ORIGIN not in robots
    assert sitemap.count(f"<loc>{CANONICAL_PUBLIC_URL}") == 4
    assert VERCEL_ORIGIN not in sitemap


def test_favicon_is_served_as_svg_mime():
    client = TestClient(app_module.app)
    response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.text.lstrip().startswith("<svg")


def _clear_public_url_env(monkeypatch) -> None:
    for name in (
        "PLACEAI_CANONICAL_PUBLIC_URL",
        "PUBLIC_APP_URL",
        "PASSWORD_RESET_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def _set_vercel_production(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "placeai-rxpp.vercel.app")
    _clear_public_url_env(monkeypatch)


def _set_provider_agnostic_production(monkeypatch) -> None:
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False)
    monkeypatch.delenv("VERCEL_BRANCH_URL", raising=False)
    monkeypatch.delenv("VERCEL_URL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("BASE_URL", VERCEL_ORIGIN)
    _clear_public_url_env(monkeypatch)


def test_vercel_platform_url_detection_is_hostname_based():
    assert _is_vercel_platform_url(VERCEL_ORIGIN)
    assert _is_vercel_platform_url("placeai-rxpp.vercel.app")
    assert _is_vercel_platform_url("https://preview-abc.vercel.app/path")
    assert not _is_vercel_platform_url(CANONICAL_PUBLIC_URL)
    assert not _is_vercel_platform_url("https://vercel.app.example.com")


def test_stale_vercel_public_app_override_cannot_replace_placeai_domain(monkeypatch):
    _set_vercel_production(monkeypatch)
    monkeypatch.setenv("PUBLIC_APP_URL", VERCEL_ORIGIN)

    settings = Settings()

    assert settings.base_url == CANONICAL_PUBLIC_URL
    assert CANONICAL_PUBLIC_URL in settings.allowed_origins


def test_schemeless_vercel_public_app_override_is_also_rejected(monkeypatch):
    _set_vercel_production(monkeypatch)
    monkeypatch.setenv("PUBLIC_APP_URL", "placeai-rxpp.vercel.app")

    settings = Settings()

    assert settings.base_url == CANONICAL_PUBLIC_URL


def test_explicit_vercel_canonical_override_is_rejected(monkeypatch):
    _set_vercel_production(monkeypatch)
    monkeypatch.setenv("PLACEAI_CANONICAL_PUBLIC_URL", VERCEL_ORIGIN)

    settings = Settings()

    assert settings.base_url == CANONICAL_PUBLIC_URL
    assert CANONICAL_PUBLIC_URL in settings.allowed_origins


def test_schemeless_explicit_vercel_canonical_override_is_rejected(monkeypatch):
    _set_vercel_production(monkeypatch)
    monkeypatch.setenv("PLACEAI_CANONICAL_PUBLIC_URL", "placeai-rxpp.vercel.app")

    settings = Settings()

    assert settings.base_url == CANONICAL_PUBLIC_URL


def test_production_without_vercel_flag_defaults_to_placeai_domain(monkeypatch):
    _set_provider_agnostic_production(monkeypatch)

    settings = Settings()

    assert not settings.running_on_vercel
    assert settings.backend_base_url == VERCEL_ORIGIN
    assert settings.base_url == CANONICAL_PUBLIC_URL
    assert CANONICAL_PUBLIC_URL in settings.allowed_origins


def test_production_without_vercel_flag_rejects_explicit_vercel_canonical(monkeypatch):
    _set_provider_agnostic_production(monkeypatch)
    monkeypatch.setenv("PLACEAI_CANONICAL_PUBLIC_URL", VERCEL_ORIGIN)

    settings = Settings()

    assert settings.base_url == CANONICAL_PUBLIC_URL


def test_production_without_vercel_flag_rejects_legacy_vercel_public_url(monkeypatch):
    _set_provider_agnostic_production(monkeypatch)
    monkeypatch.setenv("PUBLIC_APP_URL", VERCEL_ORIGIN)

    settings = Settings()

    assert settings.base_url == CANONICAL_PUBLIC_URL


def test_custom_public_app_override_remains_supported(monkeypatch):
    _set_vercel_production(monkeypatch)
    monkeypatch.setenv("PUBLIC_APP_URL", "https://campus.placeai.in")

    settings = Settings()

    assert settings.base_url == "https://campus.placeai.in"


def test_explicit_custom_canonical_override_remains_supported(monkeypatch):
    _set_vercel_production(monkeypatch)
    monkeypatch.setenv("PLACEAI_CANONICAL_PUBLIC_URL", "https://campus.placeai.in")
    monkeypatch.setenv("PUBLIC_APP_URL", VERCEL_ORIGIN)

    settings = Settings()

    assert settings.base_url == "https://campus.placeai.in"


def test_explicit_canonical_override_has_priority(monkeypatch):
    _set_vercel_production(monkeypatch)
    monkeypatch.setenv("PUBLIC_APP_URL", VERCEL_ORIGIN)
    monkeypatch.setenv("PLACEAI_CANONICAL_PUBLIC_URL", CANONICAL_PUBLIC_URL)

    settings = Settings()

    assert settings.base_url == CANONICAL_PUBLIC_URL
