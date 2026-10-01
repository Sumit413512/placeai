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
    assert "20261001-role-focus-2" in gateway


def test_returning_student_sees_saved_plan_before_adjustment_form():
    roadmap = Path("app/static/career-roadmap.js").read_text(encoding="utf-8")
    public_roadmap = Path("public/static/career-roadmap.js").read_text(encoding="utf-8")

    assert roadmap == public_roadmap
    assert "YOUR SAVED PLAN" in roadmap
    assert "roadmap-plan-toolbar" in roadmap
    assert "roadmap-adjust-panel" in roadmap
    assert 'data-action="roadmap-adjust"' in roadmap
    assert 'data-action="roadmap-print"' in roadmap
    assert roadmap.index("roadmapHtml(latest, esc, fmtDate)") < roadmap.index("roadmap-adjust-panel")


def test_roadmap_failures_use_safe_actionable_codes():
    roadmap = Path("app/static/career-roadmap.js").read_text(encoding="utf-8")
    public_roadmap = Path("public/static/career-roadmap.js").read_text(encoding="utf-8")

    assert roadmap == public_roadmap
    assert "roadmapFailureMessage" in roadmap
    assert "CURRENT_MARKET_PROVIDER_BUSY" in roadmap
    assert "CURRENT_MARKET_PROVIDER_AUTH" in roadmap
    assert "CURRENT_MARKET_RESPONSE_INVALID" in roadmap
    assert "CURRENT_MARKET_SOURCES_MISSING" in roadmap
    assert "Your roadmap was not generated from stale assumptions." in roadmap
    assert "toast('Roadmap generation failed', error.message" not in roadmap
