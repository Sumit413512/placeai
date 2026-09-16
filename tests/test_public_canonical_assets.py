from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.app as app_module


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
