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
    assert "const status=isCurrent?'current':attempted?'attempted':'unattempted';" in js
    assert 'class="palette-question '+status+' locked"' in js
    assert "integrityWarningLimit:4" in js
    assert "autoTerminateForIntegrity" in js
    assert "/mock-interview/proctor-frame" in js
    assert "mobile_phone_detected" in js
    assert "background:#7f1d1d" in css or "#7f1d1d" in css
