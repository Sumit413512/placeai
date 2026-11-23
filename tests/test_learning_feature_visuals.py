"""Feature visual and study date interactions remain mirrored on both hosts."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def read(p): return (ROOT / p).read_text(encoding="utf-8")

def test_study_calendar_accessible_and_banners_mirrored():
    study=read("app/static/study-tracker.js")
    assert study==read("public/static/study-tracker.js")
    assert "Your study rhythm" not in study and "study-welcome" not in study
    assert "activityPanel()" in study and "aria-pressed" in study
    assert "data-study-day" in study and "study-calendar-detail" in study
    learn=read("app/static/learning-hub.js")
    assert learn==read("public/static/learning-hub.js")
    assert "placeai-learning-photo" in learn
    assert "placeai-study-photo" in study
    for path in ("app/static/selected-theme.css","app/static/study-tracker.css","app/static/mock-interview.css"):
        assert read(path)==read(path.replace("app/static/","public/static/"))
    for path in ("app/templates/mock-interview.html","public/mock-interview.html","app/embedded_pages.py"):
        assert "assessment-photo-hero" in read(path)
    for name in ("placeai-study-hero.webp","placeai-learning-hero.webp","placeai-interview-hero.webp"):
        assert (ROOT / "app/static" / name).is_file()
        assert (ROOT / "public/static" / name).is_file()
