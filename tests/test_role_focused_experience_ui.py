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


def test_technical_integrations_stay_out_of_non_platform_navigation():
    core = _read("app/static/app.js")
    student_nav = core.split("student: [", 1)[1].split("recruiter: [", 1)[0]
    recruiter_nav = core.split("recruiter: [", 1)[1].split("institution_admin: [", 1)[0]
    institution_nav = core.split("institution_admin: [", 1)[1].split("platform_admin: [", 1)[0]
    platform_nav = core.split("platform_admin: [", 1)[1].split("};", 1)[0]

    assert "integrations" not in student_nav
    assert "integrations" not in recruiter_nav
    assert "integrations" not in institution_nav
    assert "['Platform','integrations','Integrations']" in platform_nav

    integration_runtime = _read("app/static/integration-readiness.js")
    assert "if (title !== 'Integrations' || !root) return;" in integration_runtime


def test_normal_user_copy_hides_operational_implementation_details():
    core = _read("app/static/app.js")

    assert "Notifications are stored in the PlaceAI database" not in core
    assert "merchant/payment provider is selected and verified" not in core
    assert "Candidate access in this deployment" not in core
    assert "student database from becoming an open recruiter directory" not in core
    assert "production delivery provider is configured" not in core

    assert "Your placement updates, deadlines and required actions appear here in one place." in core
    assert "You can view only candidates who have applied to your jobs." in core
    assert "Email and other external alerts are not available yet." in core

    # Operational detail remains intentionally available to Platform Admin.
    assert "<small>Database</small>" in core
    assert "<small>Brevo SMTP</small>" in core
    assert "<small>Gemini</small>" in core


def test_server_failures_use_safe_user_facing_error_copy():
    app_errors = _read("app/static/api-errors.js")
    public_errors = _read("public/static/api-errors.js")

    assert app_errors == public_errors
    assert "if (numericStatus >= 500)" in app_errors
    assert "Never render backend-provided 5xx detail into a user workspace." in app_errors
    assert "PlaceAI could not complete this request right now. Please try again." in app_errors


def test_public_and_sign_in_copy_uses_user_language_not_platform_jargon():
    app_index = _read("app/templates/index.html")
    public_index = _read("public/index.html")

    assert app_index == public_index
    assert "Institution tenancy" not in app_index
    assert "Tenant-scoped workflows" not in app_index
    assert "backend authorization checks" not in app_index
    assert "Privileged roles require authorized provisioning" not in app_index
    assert "one-time server-side state" not in app_index
    assert "when transactional email is configured" not in app_index

    assert "Institution data boundaries" in app_index
    assert "Sign in to the workspace assigned to you." in app_index
    assert "Admin access is limited to approved accounts." in app_index
    assert "PlaceAI shows the same confirmation whether or not an account exists." in app_index


def test_role_navigation_uses_progressive_disclosure_without_removing_tools():
    app_js = _read("app/static/workspace-experience.js")
    public_js = _read("public/static/workspace-experience.js")
    app_css = _read("app/static/workspace-experience.css")

    assert app_js == public_js
    assert "ROLE_SECONDARY_VIEWS" in app_js
    assert "platform_admin: new Set()" in app_js
    assert "toggle-placeai-nav-more" in app_js
    assert "placeaiMoreOpen" in app_js
    assert "placeai_nav_more_" in app_js
    assert '[data-placeai-more-open="false"]' in app_css
    assert ".placeai-nav-more" in app_css
