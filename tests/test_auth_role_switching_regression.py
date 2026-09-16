from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_auth_role_switching_source_contract_and_mirrors_match() -> None:
    portal = (ROOT / "app/static/access-portal.js").read_text(encoding="utf-8")
    public_portal = (ROOT / "public/static/access-portal.js").read_text(encoding="utf-8")

    assert portal == public_portal
    assert 'role="tablist"' in portal
    assert 'role="tab"' in portal
    assert 'aria-selected=' in portal
    assert 'aria-pressed=' not in portal
    assert "function updateLoginRole(roleKey)" in portal
    assert "firstInput.removeAttribute('tabindex');" in portal
    assert "focusVisibleForm('role-login-form')" in portal

    login_role_branch = portal.split(
        "if (roleButton.dataset.accessRoleMode === 'login')",
        1,
    )[1].split("} else {", 1)[0]

    assert "updateLoginRole(roleButton.dataset.accessRole);" in login_role_branch
    assert "renderLogin();" not in login_role_branch
