from __future__ import annotations

import os
import subprocess
import sys

from app.config import Settings


def test_malformed_numeric_environment_values_use_safe_defaults(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_MINUTES", "replace-me")
    monkeypatch.setenv("REFRESH_TOKEN_DAYS", "not-a-number")
    monkeypatch.setenv("MAX_RESUME_MB", "-100")
    monkeypatch.setenv("SMTP_PORT", "999999")

    settings = Settings()

    assert settings.access_token_minutes == 30
    assert settings.refresh_token_days == 14
    assert settings.max_resume_mb == 5
    assert settings.smtp_port == 587


def test_vercel_production_import_survives_stale_numeric_placeholders():
    env = os.environ.copy()
    env.update(
        {
            "VERCEL": "1",
            "VERCEL_ENV": "production",
            "ENVIRONMENT": "production",
            "VERCEL_PROJECT_PRODUCTION_URL": "placeai-rxpp.vercel.app",
            "DATABASE_URL": "postgresql://postgres.example:placeholder@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres",
            "JWT_SECRET_KEY": "A" * 48,
            "JWT_REFRESH_SECRET_KEY": "B" * 48,
            "AUTO_CREATE_SCHEMA": "false",
            "ACCESS_TOKEN_MINUTES": "replace-me",
            "REFRESH_TOKEN_DAYS": "replace-me",
            "MAX_RESUME_MB": "replace-me",
            "SMTP_PORT": "replace-me",
        }
    )
    env.pop("BASE_URL", None)
    env.pop("ALLOWED_ORIGINS", None)

    result = subprocess.run(
        [sys.executable, "-c", "import app.app; print(app.app.app.title)"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PlaceAI API" in result.stdout


def test_router_import_failure_is_contained():
    import app.app as application

    code = "ROUTER_IMPORT_INTENTIONALLY_MISSING_FAILED"
    application.runtime_readiness_errors[:] = [
        item for item in application.runtime_readiness_errors if item != code
    ]

    assert application._import_router("intentionally_missing") is None
    assert code in application.runtime_readiness_errors
