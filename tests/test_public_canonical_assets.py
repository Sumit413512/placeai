from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.app as app_module
from app.config import Settings, _is_vercel_platform_url


def test_production_public_base_prefers_configured_public_url(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "settings",
        SimpleNamespace(is_production=True, base_url="https://www.placeai.in"),
    )
    request = SimpleNamespace(base_url="https://placeai-rxpp.vercel.app/")
    assert app_module._public_base(request) == "https://www.placeai.in"


def test_sitemap_and_robots_use_canonical_public_domain(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "settings",
        SimpleNamespace(is_production=True, base_url="https://www.placeai.in"),
    )
    client = TestClient(app_module.app)

    robots = client.get("/robots.txt")
    sitemap = client.get("/sitemap.xml")

    assert robots.status_code == 200
    assert "Sitemap: https://www.placeai.in/sitemap.xml" in robots.text
    assert sitemap.status_code == 200
    assert "https://www.placeai.in/" in sitemap.text
    assert "placeai-rxpp.vercel.app" not in sitemap.text


def test_favicon_is_served_as_svg_mime():
    client = TestClient(app_module.app)
    response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.text.lstrip().startswith("<svg")


def _set_vercel_production(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "placeai-rxpp.vercel.app")
    monkeypatch.delenv("PLACEAI_CANONICAL_PUBLIC_URL", raising=False)
    monkeypatch.delenv("PASSWORD_RESET_BASE_URL", raising=False)


def test_vercel_platform_url_detection_is_hostname_based():
    assert _is_vercel_platform_url("https://placeai-rxpp.vercel.app")
    assert _is_vercel_platform_url("placeai-rxpp.vercel.app")
    assert _is_vercel_platform_url("https://preview-abc.vercel.app/path")
    assert not _is_vercel_platform_url("https://www.placeai.in")
    assert not _is_vercel_platform_url("https://vercel.app.example.com")


def test_stale_vercel_public_app_override_cannot_replace_placeai_domain(monkeypatch):
    _set_vercel_production(monkeypatch)
    monkeypatch.setenv("PUBLIC_APP_URL", "https://placeai-rxpp.vercel.app")

    settings = Settings()

    assert settings.base_url == "https://www.placeai.in"
    assert "https://www.placeai.in" in settings.allowed_origins


def test_schemeless_vercel_public_app_override_is_also_rejected(monkeypatch):
    _set_vercel_production(monkeypatch)
    monkeypatch.setenv("PUBLIC_APP_URL", "placeai-rxpp.vercel.app")

    settings = Settings()

    assert settings.base_url == "https://www.placeai.in"


def test_custom_public_app_override_remains_supported(monkeypatch):
    _set_vercel_production(monkeypatch)
    monkeypatch.setenv("PUBLIC_APP_URL", "https://campus.placeai.in")

    settings = Settings()

    assert settings.base_url == "https://campus.placeai.in"


def test_explicit_canonical_override_has_priority(monkeypatch):
    _set_vercel_production(monkeypatch)
    monkeypatch.setenv("PUBLIC_APP_URL", "https://placeai-rxpp.vercel.app")
    monkeypatch.setenv("PLACEAI_CANONICAL_PUBLIC_URL", "https://www.placeai.in")

    settings = Settings()

    assert settings.base_url == "https://www.placeai.in"
