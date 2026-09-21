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

    assert "mock-interview.css?v=20260921-coding1" in html
    assert "mock-interview.js?v=20260921-coding1" in html
    assert 'role="radiogroup"' in js
    assert 'role="radio"' in js
    assert "option-select-indicator" in js
    assert "aria-checked" in js
    assert "data-section-toggle" in js
    assert "palette-question-wrap" in js
    assert "expandedSections" in js
    assert ".option-select-indicator" in css
    assert "pointer-events:none" in css


def test_mcq_handler_uses_collection_helper_and_delegated_click_handler():
    js = _text("app/static/mock-interview.js")
    assert "area.onclick=function(event)" in js
    assert "$('.option-button',area).forEach(function(button,i)" in js
    assert "$('.option-button',area).forEach(function(x)" in js


def test_mcq_fail_safe_blocks_progression_when_options_are_invalid():
    js = _text("app/static/mock-interview.js")
    css = _text("app/static/mock-interview.css")
    assert "options.length!==4" in js
    assert "mcq_options_invalid" in js
    assert "Question options unavailable" in js
    assert ".answer-load-error" in css


def test_proctor_runtime_is_required_and_active_in_preview_and_production():
    html = _text("app/templates/mock-interview.html")
    js = _text("app/static/mock-interview.js")
    css = _text("app/static/mock-interview.css")

    assert "@tensorflow/tfjs@4.22.0" in html
    assert "tf.es2017.min.js" in html
    assert "/dist/tf.min.js" not in html
    assert "@tensorflow-models/coco-ssd@2.2.3" in html
    assert 'data-check="screen"' in html
    assert 'data-check="proctor"' in html
    assert 'data-check="monitor"' in html
    assert 'id="proctor-warning-banner"' in html
    assert "ensureProctorModel" in js
    assert "runLocalProctorCheck" in js
    assert "setInterval(runLocalProctorCheck,1500)" in js
    assert "item.class==='cell phone'" in js
    assert "candidate_not_visible" in js
    assert "multiple_people" in js
    assert "integrityWarningLimit:4" in js
    assert "getDisplayMedia" in js
    assert "screen_share_stopped" in js
    assert "currentMonitorStatus" in js
    assert ".proctor-warning-banner" in css
    assert "if(previewMode||!state.assessmentActive" in js  # only secondary cloud vision is preview-disabled
    assert "Preview workflow passed" not in js


def test_render_assessment_demo_requires_real_preflight_instead_of_bypassing_proctoring():
    js = _text("app/static/mock-interview.js")
    demo_block = js.split("if(demo==='assessment'){", 1)[1].split("if(demo==='result'||demo==='integrity'){", 1)[0]
    assert "$('#system-panel').classList.remove('hidden')" in demo_block
    assert "$('#interview-panel').classList.remove('hidden')" not in demo_block
    assert "renderQuestion()" not in demo_block


def test_mock_assessment_copy_is_professional_and_drops_plus_marketing():
    html = _text("app/templates/mock-interview.html")
    assert "Secure Placement Assessment" in html
    assert "Institution-grade simulation" in html
    assert "50+" not in html
    assert "50-question minimum" not in html


def test_preview_mode_does_not_treat_all_render_hosts_as_demo():
    js = _text("app/static/mock-interview.js")
    assert "placeai-interview-intelligence-preview.onrender.com" in js
    assert "location.hostname.endsWith('.onrender.com')" not in js
    assert "get('preview') === '1'" in js


def test_integrity_warning_overlay_does_not_pause_assessment_clock():
    js = _text("app/static/mock-interview.js")
    assert "if(!state.assessmentActive || state.finishing || state.autoSubmittedIntegrity) return;" in js
    timer_block = js.split("function startTimer()", 1)[1].split("function updateIntegrityWarningUI()", 1)[0]
    assert "integrity-overlay" not in timer_block


def test_coding_ide_and_result_evidence_are_mirrored():
    html = _text("app/templates/mock-interview.html")
    js = _text("app/static/mock-interview.js")
    css = _text("app/static/mock-interview.css")
    assert "mock-interview.css?v=20260921-coding1" in html
    assert "mock-interview.js?v=20260921-coding1" in html
    assert "coding-workspace" in js
    assert 'id="coding-editor"' in js
    assert 'id="coding-language"' in js
    assert "Run sample tests" in js
    assert "Submit code" in js
    assert "/mock-interview/coding/run" in js
    assert "hidden tests" in js
    assert "Sandbox tests + AI review" in js
    assert ".coding-editor" in css
    assert ".coding-test-row" in css
    assert ".coding-result-tests" in css


def test_coding_save_next_requires_current_full_submission():
    js = _text("app/static/mock-interview.js")
    submit_block = js.split("async function submitAndContinue()", 1)[1].split("const RESULT_SECTION_WEIGHTS", 1)[0]
    assert "q?.answer_type==='code'" in submit_block
    assert "prior.submitted" in submit_block
    assert "prior.language===saved.language" in submit_block
    assert "prior.source===saved.answer" in submit_block
    assert "runCodingQuestion(q,'submit')" in submit_block


def test_coding_blueprint_uses_dedicated_ide_label():
    js = _text("app/static/mock-interview.js")
    assert "{key:'coding', label:'Coding Challenges', count:2, minutes:30, kind:'code'}" in js
    assert "Coding IDE + test cases" in js
