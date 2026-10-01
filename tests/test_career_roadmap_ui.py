from pathlib import Path


def test_career_roadmap_frontend_is_wired_without_trial_premium_gate():
    core = Path("app/static/app.js").read_text(encoding="utf-8")
    public_core = Path("public/static/app-core.js").read_text(encoding="utf-8")
    roadmap = Path("app/static/career-roadmap.js").read_text(encoding="utf-8")
    public_roadmap = Path("public/static/career-roadmap.js").read_text(encoding="utf-8")

    assert core == public_core
    assert roadmap == public_roadmap
    assert "['Career','roadmap','AI Career Roadmap']" in core
    assert "PlaceAIStudentViews" in core
    assert "register('roadmap'" in roadmap
    assert "/roadmap/generate" in roadmap
    assert "3-day free trial" in roadmap
    premium_gate = "const premiumViews = new Set(['readiness','mock-interview','resume','documents','assistant']);"
    assert premium_gate in core
    assert "roadmap" not in premium_gate


def test_production_shell_loads_roadmap_module():
    app_py = Path("app/app.py").read_text(encoding="utf-8")
    loader = Path("public/static/app.js").read_text(encoding="utf-8")
    assert "/static/career-roadmap.js" in app_py
    assert "/static/career-roadmap.js" in loader


def test_render_gateway_loads_roadmap_module():
    gateway = Path("render_proxy.py").read_text(encoding="utf-8")
    assert "/static/career-roadmap.js" in gateway
    assert "20261001-roadmap-1" in gateway
