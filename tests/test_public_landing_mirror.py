from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_landing_preview_is_mirrored_and_keeps_approved_brand():
    app_html = _text("app/templates/index.html")
    public_html = _text("public/index.html")
    app_css = _text("app/static/app.css")
    public_css = _text("public/static/app.css")
    app_brand = _text("app/static/brand.css")
    public_brand = _text("public/static/brand.css")

    assert app_html == public_html
    assert app_css == public_css
    assert app_brand == public_brand

    assert "/static/placeai-logo.webp" in app_brand
    assert 'href="#platform">Platform</a>' in app_html
    assert 'href="#institutions">Institutions</a>' in app_html
    assert 'href="#recruiters">Recruiters</a>' in app_html
    assert 'href="#preparation-lab">Preparation Lab</a>' in app_html
    assert 'href="#security">Security</a>' in app_html

    assert 'id="preparation-lab"' in app_html
    assert "data:image/webp;base64," in app_html
    assert "<video" not in app_html.lower()
