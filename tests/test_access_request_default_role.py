from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_request_access_opener_defaults_to_student_and_mirrors_match() -> None:
    portal = (ROOT / "app/static/access-portal.js").read_text(encoding="utf-8")
    public_portal = (ROOT / "public/static/access-portal.js").read_text(encoding="utf-8")

    assert portal == public_portal

    request_branch = portal.split(
        "const requestOpen = event.target.closest('[data-open-access=\"request\"]');",
        1,
    )[1].split("const switcher =", 1)[0]

    assert "createRole = 'student';" in request_branch
    assert "createRole = 'institution_admin';" not in request_branch
    assert "showView('create', requestOpen);" in request_branch

    assert "let createRole = 'student';" in portal
    assert "createRole === 'student' ? studentSignupForm() : controlledAccessForm(createRole)" in portal
    assert "focusVisibleForm(createRole === 'student' ? 'role-student-signup-form' : 'role-access-request-form')" in portal
