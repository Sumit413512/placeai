from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_mock_interview_frontend_is_mirrored_for_vercel_static_delivery():
    app_js = _text("app/static/mock-interview.js")
    public_js = _text("public/static/mock-interview.js")
    assert app_js == public_js
    assert "Resilient role-grounded practice" in app_js
    assert "resilient_baseline" in app_js


def test_interview_intelligence_secure_ui_is_mirrored():
    app_html = _text("app/templates/mock-interview.html")
    public_html = _text("public/mock-interview.html")
    app_css = _text("app/static/mock-interview.css")
    public_css = _text("public/static/mock-interview.css")
    app_js = _text("app/static/mock-interview.js")
    public_js = _text("public/static/mock-interview.js")

    assert app_html == public_html
    assert app_css == public_css
    assert app_js == public_js
    assert 'id="question-canvas"' in app_html
    assert 'id="integrity-overlay"' in app_html
    assert 'id="run-liveness"' in app_html
    assert "TOTAL_QUESTIONS" in app_js
    assert "FULL_MOCK" not in app_js
    assert "requestFullscreen" in app_js
    assert "FaceDetector" in app_js
    assert "clipboard" in app_js.lower()


def test_proctored_assessment_navigation_and_warning_ui_contract():
    html = _text("app/templates/mock-interview.html")
    css = _text("app/static/mock-interview.css")
    js = _text("app/static/mock-interview.js")

    assert 'id="save-question"' in html
    assert 'id="next-question"' in html
    assert 'id="section-nav"' in html
    assert 'id="integrity-warning-badge"' in html
    assert 'id="integrity-event-list"' in html
    assert 'PROCTORED TEST' in html
    assert 'Save &amp; Next' in html
    assert "const status=attempted?'attempted':isCurrent?'current':'unattempted';" in js
    assert "const currentClass=isCurrent?' is-current':'';" in js
    assert "palette-question" in js
    assert ".palette-question.attempted.is-current" in css
    assert ".palette-question.current.is-current" in css
    assert "integrityWarningLimit:4" in js
    assert "autoTerminateForIntegrity" in js
    assert "/mock-interview/proctor-frame" in js
    assert "mobile_phone_detected" in js
    assert "background:#7f1d1d" in css or "#7f1d1d" in css


def test_mcq_options_use_single_delegated_handler_and_navigator_is_expandable():
    js = _text("app/static/mock-interview.js")
    css = _text("app/static/mock-interview.css")

    assert "area.onclick=function(event)" in js
    assert "event.target.closest('.option-button')" in js
    assert "aria-checked" in js
    assert "data-section-toggle" in js
    assert "toggleNavigatorSection" in js
    assert "palette-section-toggle" in css
    assert "palette-question-wrap" in css
    assert ".option-select-indicator" in css
    assert "demo==='assessment'" in js


def test_mcq_interaction_and_expandable_navigator_contract():
    html = _text("app/templates/mock-interview.html")
    css = _text("app/static/mock-interview.css")
    js = _text("app/static/mock-interview.js")

    assert "mock-interview.css?v=20260921-mcqfix3" in html
    assert "mock-interview.js?v=20260921-mcqfix3" in html
    assert 'role="radiogroup"' in js
    assert 'role="radio"' in js
    assert "option-select-indicator" in js
    assert "aria-checked" in js
    assert "data-section-toggle" in js
    assert "palette-question-wrap" in js
    assert "expandedSections" in js
    assert ".option-select-indicator" in css
    assert "pointer-events:none" in css


def test_mcq_handler_does_not_call_foreach_on_single_element_helper():
    js = _text("app/static/mock-interview.js")
    assert "area.onclick=function(event)" in js
    assert "$('.option-button',area).forEach" not in js


def test_mcq_fail_safe_blocks_progression_when_options_are_invalid():
    js = _text("app/static/mock-interview.js")
    css = _text("app/static/mock-interview.css")
    assert "options.length!==4" in js
    assert "mcq_options_invalid" in js
    assert "Question options unavailable" in js
    assert ".answer-load-error" in css
