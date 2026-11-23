"""Regression contracts for the career-roadmap overview and A4 print layout."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_roadmap_visual_and_print_contract():
    app_js = (ROOT / "app/static/career-roadmap.js").read_text()
    public_js = (ROOT / "public/static/career-roadmap.js").read_text()
    assert app_js == public_js
    assert 'roadmap-board-hero.webp' not in app_js  # the photo is a CSS background
    for marker in ("roadmap-photo-hero", "roadmap-print-cover", "roadmap-journey-map",
                   "roadmap-detail-report", "roadmap-printing", "roadmap-research-notes"):
        assert marker in app_js

    app_css = (ROOT / "app/static/selected-theme.css").read_text()
    public_css = (ROOT / "public/static/selected-theme.css").read_text()
    assert app_css == public_css
    for rule in ('url("/static/roadmap-board-hero.webp")', '@page{size:A4',
                 'body.roadmap-printing', 'break-after:page', 'break-inside:avoid'):
        assert rule in app_css
    assert (ROOT / "app/static/roadmap-board-hero.webp").is_file()
    assert (ROOT / "public/static/roadmap-board-hero.webp").is_file()
    for path in ("app/templates/index.html", "public/index.html", "app/embedded_pages.py"):
        # Roadmap styles remain bundled with the current learning experience version.
        assert "selected-theme.css?v=20261124-learning-visual1" in (ROOT / path).read_text()
