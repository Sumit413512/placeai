from pathlib import Path


def test_trial_demo_dropdown_copy_matches_one_attempt_contract():
    app = Path("app/static/mock-interview.js").read_text(encoding="utf-8")
    public = Path("public/static/mock-interview.js").read_text(encoding="utf-8")

    assert app == public
    assert "REPEAT PRACTICE AVAILABLE" not in app
    assert "1 FREE DEMO ATTEMPT" in app
    assert "INCLUDED WITH ACCESS" in app
    assert "free_attempts_remaining === 1" in app
    assert "STUDENT ACCESS REQUIRED" in app
