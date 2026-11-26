from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

def test_premium_preview_assets_are_mirrored_and_warm():
    app_css = _text("app/static/premium-preview.css")
    app_js = _text("app/static/premium-preview.js")
    assert app_css == _text("public/static/premium-preview.css")
    assert app_js == _text("public/static/premium-preview.js")
    for token in ("#6f2f3a", "#4d5a4e", "#c27e5d", "#f8f3eb", "#fffdf9"):
        assert token in app_css.lower()
    for disallowed in ("#2459c4", "#5b5bd6", "#0879ed", "#59416f"):
        assert disallowed not in app_css.lower()
    assert "prefers-reduced-motion" in app_css
    assert "IntersectionObserver" in app_js

def test_premium_preview_is_isolated_to_preview_templates():
    html = _text("app/templates/index.html")
    public = _text("public/index.html")
    mock = _text("app/templates/mock-interview.html")
    assert html == public
    assert "premium-preview.css?v=20261127-aureon-preview1" in html
    assert "premium-preview.js?v=20261127-aureon-preview1" in html
    assert "premium-preview.css?v=20261127-aureon-preview1" in mock
    assert "premium-preview.js?v=20261127-aureon-preview1" in mock
    assert 'class="premium-intelligence section-shell"' in html
    assert 'class="premium-feature-gallery"' in html
    assert 'class="premium-faq section-shell"' in html

def test_premium_preview_uses_larger_existing_placeai_visuals():
    html = _text("app/templates/index.html")
    for asset in (
        "/static/workspace-study-tracker.webp",
        "/static/workspace-mock-interview.webp",
        "/static/workspace-roadmap.webp",
        "/static/opportunity-workplace.webp",
    ):
        assert asset in html
    css = _text("app/static/premium-preview.css")
    assert 'url("/static/workspace-study-tracker.webp")' in css
    assert 'url("/static/workspace-mock-interview.webp")' in css
