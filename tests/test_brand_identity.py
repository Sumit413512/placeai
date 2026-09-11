from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_official_brand_assets_are_local_and_script_free():
    logo = _read("app/static/placeai-logo.svg")
    icon = _read("app/static/placeai-icon.svg")

    assert "PlaceAI — Skills to Opportunities" in logo
    assert "data:image/webp;base64," in logo
    assert "data:image/webp;base64," in icon
    assert "<script" not in logo.lower()
    assert "<script" not in icon.lower()
    assert "javascript:" not in logo.lower()
    assert "javascript:" not in icon.lower()


def test_every_public_html_surface_loads_the_official_brand_assets():
    application = _read("app/templates/index.html")
    mock_interview = _read("app/templates/mock-interview.html")
    public_site = _read("index.html")

    assert 'href="/static/placeai-icon.svg"' in application
    assert 'href="/static/brand.css"' in application
    assert 'href="/static/placeai-icon.svg"' in mock_interview
    assert 'href="/static/brand.css"' in mock_interview
    assert 'href="./app/static/placeai-icon.svg"' in public_site
    assert 'href="./app/static/brand.css"' in public_site


def test_brand_override_uses_supplied_lockup_and_keeps_accessible_name():
    css = _read("app/static/brand.css")

    assert 'url("./placeai-logo.svg")' in css
    assert ".brand .brand-mark span" in css
    assert ".brand .brand-mark i" in css
    assert ".brand > span:last-child" in css
    assert "clip:rect(0,0,0,0)" in css
    assert "display:none!important" not in css.split(".brand > span:last-child", 1)[1].split("}", 1)[0]
