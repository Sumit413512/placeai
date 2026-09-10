from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_google_auth_does_not_silently_downgrade_recruiter_requests() -> None:
    source = (ROOT / "app/routers/auth.py").read_text(encoding="utf-8")
    assert 'if requested_role == "recruiter" and not settings.public_recruiter_signup:' in source
    assert 'Recruiter self-registration is disabled' in source
    assert 'requested_role = "student"' not in source


def test_google_auth_existing_account_role_must_match_request() -> None:
    source = (ROOT / "app/routers/auth.py").read_text(encoding="utf-8")
    assert 'Google sign-in role does not match this account' in source
    assert 'Google sign-in is not enabled for privileged administrator accounts' in source
