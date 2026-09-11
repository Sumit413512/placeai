from __future__ import annotations

import hashlib
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    source = file.read_text(encoding="utf-8")
    if old not in source:
        raise SystemExit(f"expected source block not found in {path}: {old[:100]!r}")
    file.write_text(source.replace(old, new, 1), encoding="utf-8")


replace_once(
    "app/models.py",
    "    email_verified = Column(Boolean, default=False)\n    last_login_at = Column(DateTime, nullable=True)\n",
    "    email_verified = Column(Boolean, default=False)\n    must_change_password = Column(Boolean, nullable=False, default=False)\n    last_login_at = Column(DateTime, nullable=True)\n",
)

replace_once(
    "app/schemas.py",
    "    email_verified: bool = False\n\n    model_config = {\"from_attributes\": True}\n",
    "    email_verified: bool = False\n    must_change_password: bool = False\n\n    model_config = {\"from_attributes\": True}\n",
)

replace_once(
    "app/dependencies.py",
    "from fastapi import Depends, HTTPException, status\n",
    "from fastapi import Depends, HTTPException, Request, status\n",
)
replace_once(
    "app/dependencies.py",
    "def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:\n",
    "def get_current_user(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:\n",
)
replace_once(
    "app/dependencies.py",
    "    if not user.is_active:\n        raise HTTPException(status_code=403, detail=\"Account is inactive\")\n    return user\n",
    "    if not user.is_active:\n        raise HTTPException(status_code=403, detail=\"Account is inactive\")\n    if user.must_change_password and request.url.path not in {\"/auth/me\", \"/auth/change-password\"}:\n        raise HTTPException(\n            status_code=status.HTTP_428_PRECONDITION_REQUIRED,\n            detail=\"Password change required before workspace access.\",\n            headers={\"X-PlaceAI-Action\": \"change-password\"},\n        )\n    return user\n",
)

# Mark all administrator-created accounts as temporary-password accounts.
platform = Path("app/routers/platform.py")
source = platform.read_text(encoding="utf-8")
source = source.replace(
    "hashed_password=get_hashed_password(data.temporary_password), role=UserRole.institution_admin, organization_id=org.id)",
    "hashed_password=get_hashed_password(data.temporary_password), role=UserRole.institution_admin, organization_id=org.id, must_change_password=True)",
)
source = source.replace(
    "hashed_password=get_hashed_password(data.temporary_password), role=UserRole.recruiter)",
    "hashed_password=get_hashed_password(data.temporary_password), role=UserRole.recruiter, must_change_password=True)",
)
if source.count("must_change_password=True") < 2:
    raise SystemExit("platform provisioning replacements incomplete")
platform.write_text(source, encoding="utf-8")

institutions = Path("app/routers/institutions.py")
source = institutions.read_text(encoding="utf-8")
source = source.replace(
    "role=UserRole.student, organization_id=org.id,\n    )",
    "role=UserRole.student, organization_id=org.id, must_change_password=True,\n    )",
    1,
)
source = source.replace(
    "role=UserRole.student, organization_id=org.id,\n        )",
    "role=UserRole.student, organization_id=org.id, must_change_password=True,\n        )",
    1,
)
source = source.replace(
    "hashed_password=get_hashed_password(data.temporary_password), role=UserRole.recruiter)",
    "hashed_password=get_hashed_password(data.temporary_password), role=UserRole.recruiter, must_change_password=True)",
    1,
)
if source.count("must_change_password=True") < 3:
    raise SystemExit("institution provisioning replacements incomplete")
institutions.write_text(source, encoding="utf-8")

migration = Path("alembic/versions/20260911_0007_must_change_password.py")
migration.write_text('''\"\"\"Require newly provisioned accounts to rotate temporary passwords.\n\nRevision ID: 20260911_0007\nRevises: 20260910_0006\n\"\"\"\nfrom alembic import op\nimport sqlalchemy as sa\nfrom sqlalchemy import inspect\n\nrevision = \"20260911_0007\"\ndown_revision = \"20260910_0006\"\nbranch_labels = None\ndepends_on = None\n\n\ndef upgrade() -> None:\n    bind = op.get_bind()\n    columns = {column[\"name\"] for column in inspect(bind).get_columns(\"users\")}\n    if \"must_change_password\" not in columns:\n        op.add_column(\n            \"users\",\n            sa.Column(\"must_change_password\", sa.Boolean(), nullable=False, server_default=sa.false()),\n        )\n\n\ndef downgrade() -> None:\n    bind = op.get_bind()\n    columns = {column[\"name\"] for column in inspect(bind).get_columns(\"users\")}\n    if \"must_change_password\" in columns:\n        op.drop_column(\"users\", \"must_change_password\")\n''', encoding="utf-8")

router = Path("app/routers/account_security.py")
router.write_text('''from __future__ import annotations\n\nfrom fastapi import APIRouter, Depends, HTTPException, Request, Response, status\nfrom pydantic import BaseModel, Field, field_validator\nfrom sqlalchemy.orm import Session\n\nfrom app.database import get_db\nfrom app.dependencies import get_current_user\nfrom app.models import RefreshSession, User\nfrom app.rate_limit import enforce_rate_limit\nfrom app.routers.auth import _token_response, _utcnow\nfrom app.schemas import TokenSchema, _strong_password\nfrom app.utils import get_hashed_password, verify_password\n\nrouter = APIRouter(tags=[\"Account security\"])\n\n\nclass ChangePasswordRequest(BaseModel):\n    current_password: str = Field(min_length=1, max_length=128)\n    new_password: str = Field(min_length=12, max_length=128)\n\n    @field_validator(\"new_password\")\n    @classmethod\n    def password_strength(cls, value: str) -> str:\n        return _strong_password(value)\n\n\n@router.post(\"/auth/change-password\", response_model=TokenSchema)\ndef change_password(\n    body: ChangePasswordRequest,\n    request: Request,\n    response: Response,\n    current_user: User = Depends(get_current_user),\n    db: Session = Depends(get_db),\n):\n    \"\"\"Rotate a password and invalidate every pre-rotation session.\"\"\"\n    enforce_rate_limit(\n        db,\n        request,\n        scope=\"change-password\",\n        identifier=current_user.email,\n        limit=8,\n        window_seconds=900,\n        block_seconds=1800,\n        include_client_address=False,\n    )\n    if not verify_password(body.current_password, current_user.hashed_password):\n        raise HTTPException(status_code=401, detail=\"Current password is incorrect\")\n    if verify_password(body.new_password, current_user.hashed_password):\n        raise HTTPException(status_code=400, detail=\"New password must be different from the current password\")\n\n    now = _utcnow()\n    current_user.hashed_password = get_hashed_password(body.new_password)\n    current_user.must_change_password = False\n    current_user.reset_token_hash = None\n    current_user.reset_token_expires = None\n    current_user.auth_version = int(current_user.auth_version or 1) + 1\n    db.query(RefreshSession).filter(\n        RefreshSession.user_id == current_user.id,\n        RefreshSession.revoked_at.is_(None),\n    ).update({RefreshSession.revoked_at: now}, synchronize_session=False)\n    db.commit()\n    db.refresh(current_user)\n    return _token_response(current_user, response, db)\n''', encoding="utf-8")

css = Path("app/static/account-security.css")
css.write_text('''html.placeai-password-rotation-open,\nhtml.placeai-password-rotation-open body { overflow: hidden !important; }\n\n.password-rotation-overlay {\n  position: fixed; inset: 0; z-index: 30000; display: grid; place-items: center;\n  padding: 20px; background: rgba(10, 18, 32, .72); backdrop-filter: blur(8px);\n}\n.password-rotation-card {\n  width: min(520px, 100%); max-height: calc(100dvh - 40px); overflow-y: auto;\n  border-radius: 20px; background: #fff; padding: 34px; box-shadow: 0 24px 80px rgba(0,0,0,.28);\n}\n.password-rotation-card h2 { margin: 8px 0 10px; font: 750 28px/1.15 Manrope, sans-serif; color: #172033; }\n.password-rotation-card p { margin: 0 0 20px; color: #657084; line-height: 1.55; }\n.password-rotation-kicker { font-size: 11px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: #5b5bd6; }\n.password-rotation-form { display: grid; gap: 14px; }\n.password-rotation-form label { display: grid; gap: 7px; font-size: 13px; font-weight: 700; color: #39445a; }\n.password-rotation-form input { width: 100%; box-sizing: border-box; border: 1px solid #d8deea; border-radius: 11px; padding: 12px 13px; font: inherit; }\n.password-rotation-form input:focus { outline: 2px solid rgba(91,91,214,.20); border-color: #5b5bd6; }\n.password-rotation-help { margin: -3px 0 2px; font-size: 12px; color: #69758a; }\n.password-rotation-error { display: none; border: 1px solid #f2c8c8; border-radius: 10px; padding: 10px 12px; background: #fff5f5; color: #9c2c2c; font-size: 13px; }\n.password-rotation-error.is-visible { display: block; }\n.password-rotation-submit { border: 0; border-radius: 11px; padding: 13px 16px; background: #273a51; color: white; font: 700 14px/1 DM Sans, sans-serif; cursor: pointer; }\n.password-rotation-submit:disabled { opacity: .65; cursor: wait; }\n@media (max-width: 560px) { .password-rotation-overlay { padding: 10px; } .password-rotation-card { padding: 24px 20px; max-height: calc(100dvh - 20px); } }\n''', encoding="utf-8")

js = Path("app/static/account-security.js")
js.write_text('''(() => {\n  'use strict';\n\n  const esc = value => String(value ?? '').replace(/[&<>\"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[char]));\n\n  function validationMessage(data, status) {\n    const detail = data?.detail;\n    if (typeof detail === 'string' && detail.trim()) return detail.trim();\n    if (Array.isArray(detail)) {\n      const messages = detail.map(item => typeof item?.msg === 'string' ? item.msg.replace(/^Value error,\\s*/i, '').trim() : '').filter(Boolean);\n      if (messages.length) return [...new Set(messages)].join(' ');\n    }\n    return `Request failed (${status})`;\n  }\n\n  function validatePassword(password) {\n    if (password.length < 12) return 'Password must be at least 12 characters long.';\n    if (!/[a-z]/.test(password)) return 'Password must contain a lowercase letter.';\n    if (!/[A-Z]/.test(password)) return 'Password must contain an uppercase letter.';\n    if (!/[0-9]/.test(password)) return 'Password must contain a number.';\n    if (!/[^A-Za-z0-9]/.test(password)) return 'Password must contain a symbol.';\n    return '';\n  }\n\n  function showRotation(user) {\n    if (document.querySelector('#password-rotation-overlay')) return;\n    document.documentElement.classList.add('placeai-password-rotation-open');\n    const overlay = document.createElement('div');\n    overlay.id = 'password-rotation-overlay';\n    overlay.className = 'password-rotation-overlay';\n    overlay.setAttribute('role', 'dialog');\n    overlay.setAttribute('aria-modal', 'true');\n    overlay.setAttribute('aria-labelledby', 'password-rotation-title');\n    overlay.innerHTML = `<section class=\"password-rotation-card\"><span class=\"password-rotation-kicker\">Account security</span><h2 id=\"password-rotation-title\">Create your permanent password</h2><p>${esc(user?.username || user?.email || 'This account')} was provisioned with a temporary password. Change it before entering the PlaceAI workspace.</p><form id=\"password-rotation-form\" class=\"password-rotation-form\"><label>Current temporary password<input type=\"password\" name=\"current_password\" autocomplete=\"current-password\" maxlength=\"128\" required autofocus></label><label>New password<input type=\"password\" name=\"new_password\" autocomplete=\"new-password\" minlength=\"12\" maxlength=\"128\" required></label><div class=\"password-rotation-help\">Use 12+ characters with uppercase, lowercase, a number and a symbol.</div><label>Confirm new password<input type=\"password\" name=\"confirm_password\" autocomplete=\"new-password\" minlength=\"12\" maxlength=\"128\" required></label><div id=\"password-rotation-error\" class=\"password-rotation-error\" role=\"alert\"></div><button class=\"password-rotation-submit\" type=\"submit\">Change password and continue</button></form></section>`;\n    document.body.appendChild(overlay);\n\n    const form = overlay.querySelector('#password-rotation-form');\n    const error = overlay.querySelector('#password-rotation-error');\n    const button = overlay.querySelector('button[type=\"submit\"]');\n    form.addEventListener('submit', async event => {\n      event.preventDefault();\n      error.classList.remove('is-visible');\n      error.textContent = '';\n      const body = Object.fromEntries(new FormData(form).entries());\n      const passwordError = validatePassword(String(body.new_password || ''));\n      if (passwordError) { error.textContent = passwordError; error.classList.add('is-visible'); return; }\n      if (body.new_password !== body.confirm_password) { error.textContent = 'New password and confirmation do not match.'; error.classList.add('is-visible'); return; }\n      if (body.current_password === body.new_password) { error.textContent = 'New password must be different from the temporary password.'; error.classList.add('is-visible'); return; }\n      button.disabled = true;\n      button.textContent = 'Updating password…';\n      try {\n        const response = await fetch('/auth/change-password', {method: 'POST', credentials: 'include', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({current_password: body.current_password, new_password: body.new_password})});\n        const data = await response.json().catch(() => ({}));\n        if (!response.ok) throw new Error(validationMessage(data, response.status));\n        location.reload();\n      } catch (err) {\n        error.textContent = err?.message || 'Password update failed.';\n        error.classList.add('is-visible');\n        button.disabled = false;\n        button.textContent = 'Change password and continue';\n      }\n    });\n  }\n\n  async function init() {\n    try {\n      const response = await fetch('/auth/me', {credentials: 'include'});\n      if (!response.ok) return;\n      const user = await response.json();\n      if (user?.must_change_password) showRotation(user);\n    } catch {\n      // Unauthenticated public visitors should not see the rotation surface.\n    }\n  }\n\n  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});\n  else init();\n})();\n''', encoding="utf-8")

# Wire router and assets into the app bootstrap.
replace_once(
    "app/app.py",
    'auth = _import_router("auth")\naccess = _import_router("access")\n',
    'auth = _import_router("auth")\naccount_security = _import_router("account_security")\naccess = _import_router("access")\n',
)
replace_once(
    "app/app.py",
    "    auth_refresh_atomic,\n    auth,\n    access,\n",
    "    auth_refresh_atomic,\n    auth,\n    account_security,\n    access,\n",
)
replace_once(
    "app/app.py",
    "        '<link rel=\"stylesheet\" href=\"/static/ui-fixes.css\">\\n'\n        '<script src=\"/static/access-portal.js\" defer></script>\\n'\n        '<script src=\"/static/ui-state-fixes.js\" defer></script>\\n'\n",
    "        '<link rel=\"stylesheet\" href=\"/static/ui-fixes.css\">\\n'\n        '<link rel=\"stylesheet\" href=\"/static/account-security.css\">\\n'\n        '<script src=\"/static/access-portal.js\" defer></script>\\n'\n        '<script src=\"/static/ui-state-fixes.js\" defer></script>\\n'\n        '<script src=\"/static/account-security.js\" defer></script>\\n'\n",
)

# Regression coverage.
test = Path("tests/test_first_login_password_rotation.py")
test.write_text('''from __future__ import annotations\n\nfrom fastapi.testclient import TestClient\n\nfrom app.app import app\nfrom app.database import Base, SessionLocal, engine\nfrom app.models import Organization, RefreshSession, StudentProfile, User, UserRole\nfrom app.utils import get_hashed_password\n\nclient = TestClient(app)\nPLATFORM_EMAIL = \"batch39-platform@placeai.example.com\"\nADMIN_EMAIL = \"batch39-admin@placeai.example.com\"\nPLATFORM_PASSWORD = \"Batch39Platform123!\"\nTEMP_PASSWORD = \"Batch39Temporary123!\"\nNEW_PASSWORD = \"Batch39Permanent456!\"\nORG_SLUG = \"batch39-rotation-institute\"\n\n\ndef auth(token: str) -> dict[str, str]:\n    return {\"Authorization\": f\"Bearer {token}\"}\n\n\ndef setup_module() -> None:\n    Base.metadata.create_all(bind=engine)\n    db = SessionLocal()\n    try:\n        org = db.query(Organization).filter(Organization.slug == ORG_SLUG).first()\n        if not org:\n            org = Organization(name=\"Batch 39 Rotation Institute\", slug=ORG_SLUG, is_active=True)\n            db.add(org)\n        user = db.query(User).filter(User.email == PLATFORM_EMAIL).first()\n        if not user:\n            db.add(User(email=PLATFORM_EMAIL, username=\"batch39_platform\", hashed_password=get_hashed_password(PLATFORM_PASSWORD), role=UserRole.platform_admin, email_verified=True, must_change_password=False))\n        db.commit()\n    finally:\n        db.close()\n\n\ndef login(email: str, password: str) -> str:\n    response = client.post(\"/auth/login-json\", json={\"email\": email, \"password\": password})\n    assert response.status_code == 200, response.text\n    return response.json()[\"access_token\"]\n\n\ndef test_provisioned_admin_must_rotate_password_before_workspace_access() -> None:\n    platform_token = login(PLATFORM_EMAIL, PLATFORM_PASSWORD)\n    created = client.post(\n        \"/platform/institution-admins\",\n        headers=auth(platform_token),\n        json={\n            \"email\": ADMIN_EMAIL,\n            \"username\": \"batch39_admin\",\n            \"full_name\": \"Batch 39 Admin\",\n            \"temporary_password\": TEMP_PASSWORD,\n            \"organization_slug\": ORG_SLUG,\n        },\n    )\n    assert created.status_code == 201, created.text\n    assert created.json()[\"must_change_password\"] is True\n\n    old_token = login(ADMIN_EMAIL, TEMP_PASSWORD)\n    me = client.get(\"/auth/me\", headers=auth(old_token))\n    assert me.status_code == 200, me.text\n    assert me.json()[\"must_change_password\"] is True\n\n    blocked = client.get(\"/institutions/me\", headers=auth(old_token))\n    assert blocked.status_code == 428, blocked.text\n    assert blocked.headers.get(\"x-placeai-action\") == \"change-password\"\n\n    wrong = client.post(\n        \"/auth/change-password\",\n        headers=auth(old_token),\n        json={\"current_password\": \"WrongTemporary123!\", \"new_password\": NEW_PASSWORD},\n    )\n    assert wrong.status_code == 401, wrong.text\n\n    changed = client.post(\n        \"/auth/change-password\",\n        headers=auth(old_token),\n        json={\"current_password\": TEMP_PASSWORD, \"new_password\": NEW_PASSWORD},\n    )\n    assert changed.status_code == 200, changed.text\n    new_token = changed.json()[\"access_token\"]\n\n    stale = client.get(\"/auth/me\", headers=auth(old_token))\n    assert stale.status_code == 401\n    fresh = client.get(\"/auth/me\", headers=auth(new_token))\n    assert fresh.status_code == 200, fresh.text\n    assert fresh.json()[\"must_change_password\"] is False\n    workspace = client.get(\"/institutions/me\", headers=auth(new_token))\n    assert workspace.status_code == 200, workspace.text\n\n    old_login = client.post(\"/auth/login-json\", json={\"email\": ADMIN_EMAIL, \"password\": TEMP_PASSWORD})\n    assert old_login.status_code == 401\n    new_login = client.post(\"/auth/login-json\", json={\"email\": ADMIN_EMAIL, \"password\": NEW_PASSWORD})\n    assert new_login.status_code == 200, new_login.text\n\n\ndef test_public_signup_accounts_do_not_require_forced_rotation() -> None:\n    email = \"batch39-self-signup@placeai.example.com\"\n    response = client.post(\n        \"/auth/signup\",\n        json={\"username\": \"batch39_self_signup\", \"email\": email, \"password\": \"Batch39SelfSignup123!\", \"role\": \"student\"},\n    )\n    assert response.status_code == 201, response.text\n    assert response.json()[\"must_change_password\"] is False\n\n\ndef test_rotation_ui_assets_are_present() -> None:\n    response = client.get(\"/\")\n    assert response.status_code == 200\n    assert \"/static/account-security.css\" in response.text\n    assert \"/static/account-security.js\" in response.text\n    source = response = client.get(\"/static/account-security.js\")\n    assert source.status_code == 200\n    assert \"/auth/change-password\" in source.text\n    assert \"must_change_password\" in source.text\n    assert \"Current temporary password\" in source.text\n''', encoding="utf-8")

# Refresh only production-file manifest entries. Temporary transformer/workflow are deliberately excluded.
manifest = Path("MANIFEST.sha256")
entries: dict[str, str] = {}
for line in manifest.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    digest, filename = line.split("  ", 1)
    entries[filename] = digest
changed = [
    "app/models.py",
    "app/schemas.py",
    "app/dependencies.py",
    "app/routers/platform.py",
    "app/routers/institutions.py",
    "app/routers/account_security.py",
    "app/app.py",
    "app/static/account-security.css",
    "app/static/account-security.js",
    "alembic/versions/20260911_0007_must_change_password.py",
    "tests/test_first_login_password_rotation.py",
]
for filename in changed:
    entries[filename] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
manifest.write_text("".join(f"{entries[name]}  {name}\n" for name in sorted(entries)), encoding="utf-8")
