from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    source = file.read_text(encoding="utf-8")
    if old not in source:
        raise SystemExit(f"expected source block not found in {path}: {old[:120]!r}")
    file.write_text(source.replace(old, new, 1), encoding="utf-8")


# PII-free delivery telemetry model. Deliberately contains no recipient/user/token fields.
Path("app/telemetry_models.py").write_text(
    '''from __future__ import annotations\n\nfrom sqlalchemy import Column, DateTime, Index, String\n\nfrom app.database import Base\nfrom app.models import generate_uuid, utcnow\n\n\nclass EmailDeliveryEvent(Base):\n    __tablename__ = "email_delivery_events"\n    __table_args__ = (Index("ix_email_delivery_events_purpose_created_at", "purpose", "created_at"),)\n\n    id = Column(String, primary_key=True, default=generate_uuid)\n    purpose = Column(String(80), nullable=False, index=True)\n    outcome = Column(String(32), nullable=False, index=True)\n    reason_code = Column(String(80), nullable=True)\n    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)\n''',
    encoding="utf-8",
)

Path("alembic/versions/20260911_0008_email_delivery_observability.py").write_text(
    '''"""Add PII-free transactional email delivery observability.\n\nRevision ID: 20260911_0008\nRevises: 20260911_0007\n"""\nfrom alembic import op\nimport sqlalchemy as sa\nfrom sqlalchemy import inspect\n\nrevision = "20260911_0008"\ndown_revision = "20260911_0007"\nbranch_labels = None\ndepends_on = None\n\n\ndef upgrade() -> None:\n    bind = op.get_bind()\n    if "email_delivery_events" in inspect(bind).get_table_names():\n        return\n    op.create_table(\n        "email_delivery_events",\n        sa.Column("id", sa.String(), nullable=False),\n        sa.Column("purpose", sa.String(length=80), nullable=False),\n        sa.Column("outcome", sa.String(length=32), nullable=False),\n        sa.Column("reason_code", sa.String(length=80), nullable=True),\n        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),\n        sa.PrimaryKeyConstraint("id"),\n    )\n    op.create_index("ix_email_delivery_events_purpose", "email_delivery_events", ["purpose"], unique=False)\n    op.create_index("ix_email_delivery_events_outcome", "email_delivery_events", ["outcome"], unique=False)\n    op.create_index("ix_email_delivery_events_created_at", "email_delivery_events", ["created_at"], unique=False)\n    op.create_index("ix_email_delivery_events_purpose_created_at", "email_delivery_events", ["purpose", "created_at"], unique=False)\n\n\ndef downgrade() -> None:\n    bind = op.get_bind()\n    if "email_delivery_events" in inspect(bind).get_table_names():\n        op.drop_table("email_delivery_events")\n''',
    encoding="utf-8",
)

# Authentication: return sanitized transport outcomes and persist only PII-free events.
replace_once(
    "app/routers/auth.py",
    "from app.models import Organization, RecruiterProfile, RefreshSession, StudentProfile, User, UserRole\n",
    "from app.models import Organization, RecruiterProfile, RefreshSession, StudentProfile, User, UserRole\nfrom app.telemetry_models import EmailDeliveryEvent\n",
)

old_send = '''def _send_reset_email(recipient: str, link: str) -> bool:\n    if not (settings.smtp_host and settings.smtp_from):\n        return False\n    message = EmailMessage()\n    message["Subject"] = f"Reset your {settings.app_name} password"\n    message["From"] = settings.smtp_from\n    message["To"] = recipient\n    message.set_content(f"Use this one-time link to reset your password. It expires in 15 minutes:\\n\\n{link}\\n\\nIf you did not request this, ignore this email.")\n    try:\n        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:\n            if settings.smtp_tls:\n                smtp.starttls()\n            if settings.smtp_user:\n                smtp.login(settings.smtp_user, settings.smtp_password)\n            smtp.send_message(message)\n        return True\n    except Exception:\n        return False\n'''
new_send = '''def _send_reset_email(recipient: str, link: str) -> tuple[str, str | None]:\n    """Send reset mail and return only sanitized operational outcome codes."""\n    credentials_consistent = bool(settings.smtp_user) == bool(settings.smtp_password)\n    if not (settings.smtp_host and settings.smtp_from and credentials_consistent):\n        return "not_configured", "smtp_not_configured"\n    message = EmailMessage()\n    message["Subject"] = f"Reset your {settings.app_name} password"\n    message["From"] = settings.smtp_from\n    message["To"] = recipient\n    message.set_content(f"Use this one-time link to reset your password. It expires in 15 minutes:\\n\\n{link}\\n\\nIf you did not request this, ignore this email.")\n    try:\n        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:\n            if settings.smtp_tls:\n                smtp.starttls()\n            if settings.smtp_user:\n                smtp.login(settings.smtp_user, settings.smtp_password)\n            smtp.send_message(message)\n        return "sent", None\n    except Exception:\n        # Never persist exception text: SMTP/provider errors can contain addresses or infrastructure detail.\n        return "failed", "smtp_delivery_failed"\n\n\ndef _record_reset_delivery_event(db: Session, outcome: str, reason_code: str | None) -> None:\n    """Persist aggregate-safe telemetry without changing the public recovery response."""\n    try:\n        db.add(EmailDeliveryEvent(purpose="password_reset", outcome=outcome, reason_code=reason_code))\n        db.commit()\n    except Exception:\n        db.rollback()\n'''
replace_once("app/routers/auth.py", old_send, new_send)
replace_once(
    "app/routers/auth.py",
    "    _send_reset_email(user.email, link)\n\n    if settings.environment == \"development\" and settings.dev_show_reset_token:\n",
    "    delivery_outcome, delivery_reason = _send_reset_email(user.email, link)\n    _record_reset_delivery_event(db, delivery_outcome, delivery_reason)\n\n    if settings.environment == \"development\" and settings.dev_show_reset_token:\n",
)

# Platform-only operational summary. Returns configuration booleans, aggregate counts and timestamps only.
replace_once(
    "app/routers/access.py",
    "import smtplib\nfrom email.message import EmailMessage\n",
    "import smtplib\nfrom datetime import timedelta\nfrom email.message import EmailMessage\n",
)
replace_once(
    "app/routers/access.py",
    "from app.models import User\n",
    "from app.models import User\nfrom app.telemetry_models import EmailDeliveryEvent\n",
)
access = Path("app/routers/access.py")
source = access.read_text(encoding="utf-8")
append = '''\n\n@router.get("/platform/integrations/password-reset-email")\ndef password_reset_email_observability(\n    current_user: User = Depends(require_platform_admin),\n    db: Session = Depends(get_db),\n):\n    """Expose PII-free password-reset delivery health to Platform Admin only."""\n    del current_user\n    now = _utcnow()\n    cutoff = now - timedelta(hours=24)\n    base = db.query(EmailDeliveryEvent).filter(EmailDeliveryEvent.purpose == "password_reset")\n    recent = base.filter(EmailDeliveryEvent.created_at >= cutoff)\n    last_attempt = base.order_by(EmailDeliveryEvent.created_at.desc()).first()\n    last_success = base.filter(EmailDeliveryEvent.outcome == "sent").order_by(EmailDeliveryEvent.created_at.desc()).first()\n    last_failure = base.filter(EmailDeliveryEvent.outcome == "failed").order_by(EmailDeliveryEvent.created_at.desc()).first()\n\n    credentials_consistent = bool(settings.smtp_user) == bool(settings.smtp_password)\n    transport_configured = bool(settings.smtp_host and settings.smtp_from and credentials_consistent)\n    authentication_enabled = bool(settings.smtp_user)\n    authentication_configured = bool(settings.smtp_user and settings.smtp_password)\n\n    if not transport_configured:\n        operational_status = "not_configured"\n    elif last_attempt and last_attempt.outcome == "failed":\n        operational_status = "degraded"\n    elif last_success:\n        operational_status = "healthy"\n    else:\n        operational_status = "configured_no_recent_delivery"\n\n    return {\n        "status": operational_status,\n        "smtp_transport_configured": transport_configured,\n        "smtp_authentication_enabled": authentication_enabled,\n        "smtp_authentication_configured": authentication_configured,\n        "tls_enabled": settings.smtp_tls,\n        "base_url_https": settings.base_url.startswith("https://"),\n        "attempts_24h": recent.count(),\n        "successes_24h": recent.filter(EmailDeliveryEvent.outcome == "sent").count(),\n        "failures_24h": recent.filter(EmailDeliveryEvent.outcome == "failed").count(),\n        "not_configured_24h": recent.filter(EmailDeliveryEvent.outcome == "not_configured").count(),\n        "last_attempt_at": last_attempt.created_at if last_attempt else None,\n        "last_success_at": last_success.created_at if last_success else None,\n        "last_failure_at": last_failure.created_at if last_failure else None,\n    }\n'''
if '/platform/integrations/password-reset-email' in source:
    raise SystemExit('password reset observability endpoint already exists')
access.write_text(source.rstrip() + append + "\n", encoding="utf-8")

# Platform Admin UI: add an Integrations view without exposing any secret values.
app_js = Path("app/static/app.js")
source = app_js.read_text(encoding="utf-8")
source = source.replace(
    "  navIcons['mock-interview'] = navIcons.interviews;\n",
    "  navIcons['mock-interview'] = navIcons.interviews;\n  navIcons.integrations = navIcons.verification;\n",
    1,
)
old_nav = "      ['Platform','dashboard','Overview'],['Platform','organizations','Institutions'],['Access','leads','Access requests'],['Updates','notifications','Notifications']\n"
new_nav = "      ['Platform','dashboard','Overview'],['Platform','organizations','Institutions'],['Platform','integrations','Integrations'],['Access','leads','Access requests'],['Updates','notifications','Notifications']\n"
if old_nav not in source:
    raise SystemExit('platform nav block not found')
source = source.replace(old_nav, new_nav, 1)
start = source.index("  async function renderPlatform(view) {")
next_function = source.find("\n  async function ", start + 10)
if next_function == -1:
    next_function = source.find("\n  function ", start + 10)
if next_function == -1:
    raise SystemExit('could not locate renderPlatform boundary')
block = source[start:next_function]
close = block.rfind("\n    }\n  }")
if close == -1:
    raise SystemExit('could not locate renderPlatform closing block')
integration_branch = '''\n    } else if (view === 'integrations') {\n      setPage('Integrations','Platform control'); setContextAction();\n      const [summary, reset] = await Promise.all([api('/platform/integrations/status'), api('/platform/integrations/password-reset-email')]);\n      const resetLabel = String(reset.status || 'unknown').replaceAll('_',' ');\n      const safeBool = value => value ? statusBadge('approved') : statusBadge('pending');\n      $('#app-content').innerHTML = `${pageHead('Integrations','Production integration readiness and privacy-safe delivery telemetry.')}<div class="metric-grid"><article class="metric-card"><small>Database</small><strong>${summary.database ? 'Connected' : 'Not ready'}</strong><span>Persistent production data</span></article><article class="metric-card"><small>Brevo SMTP</small><strong>${summary.brevo_smtp ? 'Configured' : 'Not ready'}</strong><span>Transactional email transport</span></article><article class="metric-card"><small>Password reset email</small><strong>${esc(resetLabel)}</strong><span>${reset.successes_24h} successful / ${reset.failures_24h} failed in 24h</span></article><article class="metric-card"><small>Gemini</small><strong>${summary.gemini ? 'Configured' : 'Not configured'}</strong><span>AI provider readiness</span></article></div><div class="data-panel"><div class="data-toolbar"><div><span class="table-primary">Password recovery delivery health</span><span class="table-secondary">Aggregate operational telemetry only. Recipient addresses, reset tokens and SMTP secrets are never displayed or stored in this telemetry.</span></div></div><div class="table-wrap"><table class="data-table"><tbody><tr><th>SMTP transport</th><td>${safeBool(reset.smtp_transport_configured)}</td><th>TLS</th><td>${safeBool(reset.tls_enabled)}</td></tr><tr><th>SMTP authentication</th><td>${reset.smtp_authentication_enabled ? safeBool(reset.smtp_authentication_configured) : 'Not required by transport'}</td><th>HTTPS reset links</th><td>${safeBool(reset.base_url_https)}</td></tr><tr><th>Attempts (24h)</th><td>${reset.attempts_24h}</td><th>Not configured (24h)</th><td>${reset.not_configured_24h}</td></tr><tr><th>Last success</th><td>${reset.last_success_at ? fmtDate(reset.last_success_at) : 'None recorded'}</td><th>Last failure</th><td>${reset.last_failure_at ? fmtDate(reset.last_failure_at) : 'None recorded'}</td></tr></tbody></table></div></div>`;\n'''
block = block[:close] + integration_branch + "\n    }\n  }" + block[close + len("\n    }\n  }"):]
source = source[:start] + block + source[next_function:]
app_js.write_text(source, encoding="utf-8")

# Focused regression coverage.
Path("tests/test_password_reset_observability.py").write_text(
    '''from __future__ import annotations\n\nfrom fastapi.testclient import TestClient\n\nimport app.routers.access as access_router\nimport app.routers.auth as auth_router\nfrom app.app import app\nfrom app.database import Base, SessionLocal, engine\nfrom app.models import User, UserRole\nfrom app.telemetry_models import EmailDeliveryEvent\nfrom app.utils import get_hashed_password\n\nclient = TestClient(app)\nPLATFORM_EMAIL = "batch40-platform@placeai.example.com"\nPLATFORM_PASSWORD = "Batch40Platform123!"\nUSER_EMAIL = "batch40-user@placeai.example.com"\nUSER_PASSWORD = "Batch40User123!"\n\n\ndef auth(token: str) -> dict[str, str]:\n    return {"Authorization": f"Bearer {token}"}\n\n\ndef setup_module() -> None:\n    Base.metadata.create_all(bind=engine)\n    db = SessionLocal()\n    try:\n        db.query(EmailDeliveryEvent).delete()\n        if not db.query(User).filter(User.email == PLATFORM_EMAIL).first():\n            db.add(User(email=PLATFORM_EMAIL, username="batch40_platform", hashed_password=get_hashed_password(PLATFORM_PASSWORD), role=UserRole.platform_admin, email_verified=True))\n        if not db.query(User).filter(User.email == USER_EMAIL).first():\n            db.add(User(email=USER_EMAIL, username="batch40_user", hashed_password=get_hashed_password(USER_PASSWORD), role=UserRole.student, email_verified=True))\n        db.commit()\n    finally:\n        db.close()\n\n\ndef platform_token() -> str:\n    response = client.post("/auth/login-json", json={"email": PLATFORM_EMAIL, "password": PLATFORM_PASSWORD})\n    assert response.status_code == 200, response.text\n    return response.json()["access_token"]\n\n\ndef test_forgot_password_stays_non_enumerating_and_records_pii_free_failure(monkeypatch) -> None:\n    monkeypatch.setattr(auth_router, "_send_reset_email", lambda recipient, link: ("failed", "smtp_delivery_failed"))\n    existing = client.post("/auth/forgot-password", json={"email": USER_EMAIL})\n    missing = client.post("/auth/forgot-password", json={"email": "batch40-missing@placeai.example.com"})\n    assert existing.status_code == 200 and missing.status_code == 200\n    assert existing.json() == missing.json()\n    assert set(existing.json()) == {"message"}\n\n    db = SessionLocal()\n    try:\n        rows = db.query(EmailDeliveryEvent).filter(EmailDeliveryEvent.purpose == "password_reset").all()\n        assert len(rows) == 1\n        assert rows[0].outcome == "failed"\n        assert rows[0].reason_code == "smtp_delivery_failed"\n        column_names = {column.name for column in EmailDeliveryEvent.__table__.columns}\n        assert "email" not in column_names\n        assert "recipient" not in column_names\n        assert "user_id" not in column_names\n        assert "token" not in column_names\n    finally:\n        db.close()\n\n\ndef test_platform_admin_gets_safe_delivery_health_and_success_recovers_status(monkeypatch) -> None:\n    monkeypatch.setattr(access_router.settings, "smtp_host", "smtp.example.invalid")\n    monkeypatch.setattr(access_router.settings, "smtp_from", "noreply@example.invalid")\n    monkeypatch.setattr(access_router.settings, "smtp_user", "configured-user")\n    monkeypatch.setattr(access_router.settings, "smtp_password", "configured-secret")\n    monkeypatch.setattr(access_router.settings, "smtp_tls", True)\n    monkeypatch.setattr(access_router.settings, "base_url", "https://placeai.example.invalid")\n\n    token = platform_token()\n    degraded = client.get("/platform/integrations/password-reset-email", headers=auth(token))\n    assert degraded.status_code == 200, degraded.text\n    assert degraded.json()["status"] == "degraded"\n    assert degraded.json()["failures_24h"] >= 1\n\n    monkeypatch.setattr(auth_router, "_send_reset_email", lambda recipient, link: ("sent", None))\n    response = client.post("/auth/forgot-password", json={"email": USER_EMAIL})\n    assert response.status_code == 200\n\n    healthy = client.get("/platform/integrations/password-reset-email", headers=auth(token))\n    assert healthy.status_code == 200, healthy.text\n    body = healthy.json()\n    assert body["status"] == "healthy"\n    assert body["smtp_transport_configured"] is True\n    assert body["smtp_authentication_configured"] is True\n    assert body["successes_24h"] >= 1\n    assert body["failures_24h"] >= 1\n    assert body["last_success_at"] is not None\n    serialized = healthy.text.lower()\n    assert USER_EMAIL.lower() not in serialized\n    assert "configured-secret" not in serialized\n\n\ndef test_delivery_observability_requires_platform_admin() -> None:\n    response = client.get("/platform/integrations/password-reset-email")\n    assert response.status_code == 401\n''',
    encoding="utf-8",
)

# Build a release manifest that excludes temporary transformer automation so it remains valid after cleanup.
exclude = {
    "MANIFEST.sha256",
    "scripts/batch40_email_observability.py",
    ".github/workflows/batch40-email-observability.yml",
}
tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
entries: list[str] = []
for name in sorted(tracked):
    if name in exclude or not Path(name).is_file():
        continue
    digest = hashlib.sha256(Path(name).read_bytes()).hexdigest()
    entries.append(f"{digest}  {name}")
Path("MANIFEST.sha256").write_text("\n".join(entries) + "\n", encoding="utf-8")

print("batch40 email observability transformation complete")
