from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_preview_demo_account_is_explicitly_preview_only():
    source = _text("app/preview_demo.py")
    auth = _text("app/routers/auth.py")
    app = _text("app/app.py")

    assert 'PREVIEW_DEMO_EMAIL = "preview.student@placeai.in"' in source
    assert 'PREVIEW_DEMO_PASSWORD = "PlaceAI-Preview#2026!"' in source
    assert 'settings.vercel_environment == "preview"' in source
    assert "and not settings.is_production" in source
    assert "organization_id=None" in source
    assert "seed_preview_demo_account()" in app
    assert "normalized_email == PREVIEW_DEMO_EMAIL and not preview_demo_enabled()" in auth
