from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_brand_assets_are_mirrored_and_use_official_wordmark() -> None:
    for name in ("placeai-logo.svg", "placeai-icon.svg", "brand.css"):
        app = _read(f"app/static/{name}")
        public = _read(f"public/static/{name}")
        assert app == public
    logo = _read("app/static/placeai-logo.svg")
    assert "PlaceAI official company logo" in logo
    assert ">Place</text>" in logo
    assert ">AI</text>" in logo
    css = _read("app/static/brand.css")
    assert 'url("./placeai-logo.svg")' in css
    assert "width:208px" in css


def test_homepage_enhancements_are_mirrored_and_loaded() -> None:
    js = _read("app/static/homepage-enhancements.js")
    public_js = _read("public/static/homepage-enhancements.js")
    css = _read("app/static/homepage-enhancements.css")
    public_css = _read("public/static/homepage-enhancements.css")
    runtime = _read("app/static/workspace-runtime.js")
    public_runtime = _read("public/static/workspace-runtime.js")

    assert js == public_js
    assert css == public_css
    assert runtime == public_runtime
    assert "Placement Preparation Lab" in js
    assert "Aptitude & reasoning tests" in js
    assert "Technical & role courses" in js
    assert "Communication & interview lab" in js
    assert "Readiness diagnostics" in js
    assert "https://www.linkedin.com/company/placeai-in/" in js
    assert "mailto:sumitjagtap@placeai.in" in js
    assert "https://www.placeai.in/" in js
    assert "/static/homepage-enhancements.css" in runtime
    assert "/static/homepage-enhancements.js" in runtime


def test_preparation_role_buttons_map_to_existing_roles() -> None:
    js = _read("app/static/homepage-enhancements.js")
    for role in ("student", "recruiter", "institution_admin"):
        assert f'data-prep-role="{role}"' in js
    assert '#login-view [data-access-role="${role}"]' in js
