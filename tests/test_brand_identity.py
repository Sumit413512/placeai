from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_official_brand_assets_are_local_and_script_free():
    logo = _read("app/static/placeai-logo.svg")
    icon = _read("app/static/placeai-icon.svg")
    supplied = (ROOT / "app/static/placeai-logo.webp").read_bytes()

    assert "PlaceAI — Skills to Opportunities" in logo
    assert "data:image/webp;base64," in logo
    assert "data:image/webp;base64," in icon
    assert supplied[:4] == b"RIFF"
    assert supplied[8:12] == b"WEBP"
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

    assert 'url("/static/placeai-logo.webp")' in css
    assert "placeai-logo.svg" not in css
    assert ".brand .brand-mark span" in css
    assert ".brand .brand-mark i" in css
    assert ".brand > span:last-child" in css
    assert "clip:rect(0,0,0,0)" in css
    assert "display:none!important" not in css.split(".brand > span:last-child", 1)[1].split("}", 1)[0]


def test_search_favicon_is_square_crisp_and_mirrored():
    from PIL import Image

    name = "placeai-favicon-96.png"
    source = ROOT / "app/static" / name
    with Image.open(source) as icon:
        assert icon.format == "PNG"
        assert icon.size == (96, 96)
        assert icon.getpixel((0, 0)) == (255, 255, 255)
    assert source.read_bytes() == (ROOT / "public/static" / name).read_bytes()
    assert (ROOT / "app/static/favicon.ico").read_bytes() == (ROOT / "public/favicon.ico").read_bytes()
    with Image.open(ROOT / "public/favicon.ico") as icon:
        assert {(16, 16), (32, 32), (48, 48), (96, 96)} <= icon.ico.sizes()
    for name in ("app/templates/index.html", "public/index.html"):
        html = _read(name)
        assert 'type="image/png" sizes="96x96" href="/static/placeai-favicon-96.png"' in html
        assert html.index("placeai-favicon-96.png") < html.index("placeai-icon.svg")
