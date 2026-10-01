from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_role_focused_assets_exist_in_both_static_trees():
    app_css = _read("app/static/workspace-experience.css")
    public_css = _read("public/static/workspace-experience.css")
    app_js = _read("app/static/workspace-experience.js")
    public_js = _read("public/static/workspace-experience.js")

    assert app_css == public_css
    assert app_js == public_js
    assert "data-placeai-responsive" in app_css
    assert "platform_admin" in app_js
    assert "AI tool temporarily unavailable" in app_js


def test_user_facing_ai_unavailable_copy_hides_provider_configuration():
    app_ai = _read("app/static/ai-readiness.js")
    public_ai = _read("public/static/ai-readiness.js")

    assert app_ai == public_ai
    assert "administrator must configure OpenAI" not in app_ai
    assert "Gemini fallback before this AI feature can run" not in app_ai
    assert "You can continue using the rest of your PlaceAI workspace" in app_ai


def test_workspace_experience_assets_are_loaded_by_all_production_shells():
    app_py = _read("app/app.py")
    render_gateway = _read("render_proxy.py")
    public_loader = _read("public/static/app.js")

    for asset in ("workspace-experience.css", "workspace-experience.js"):
        assert asset in app_py
        assert asset in render_gateway
        assert asset in public_loader
