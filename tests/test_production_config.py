from __future__ import annotations

import os
import subprocess
import sys

import pytest
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.database import build_engine_kwargs


def test_vercel_defaults_to_production_and_fails_closed(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_REFRESH_SECRET_KEY", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    monkeypatch.delenv("PASSWORD_RESET_BASE_URL", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("AUTO_CREATE_SCHEMA", raising=False)

    settings = Settings()

    assert settings.running_on_vercel is True
    assert settings.vercel_environment == ""
    assert settings.environment == "production"
    assert settings.is_production is True
    assert settings.uses_database_file_storage is True
    assert settings.auto_create_schema is False

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        settings.validate_for_startup()


def test_vercel_production_uses_stable_public_url_and_system_backend_url(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "placeai-rxpp.vercel.app")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    monkeypatch.delenv("PASSWORD_RESET_BASE_URL", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres.example:placeholder@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres",
    )
    monkeypatch.setenv("JWT_SECRET_KEY", "A" * 40)
    monkeypatch.setenv("JWT_REFRESH_SECRET_KEY", "B" * 40)
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "false")

    settings = Settings()

    assert settings.backend_base_url == "https://placeai-rxpp.vercel.app"
    assert settings.base_url == "https://placeai-recovery.onrender.com"
    assert settings.allowed_origins == ["https://placeai-rxpp.vercel.app"]
    settings.validate_for_startup()


def test_public_app_url_override_wins_for_production_links(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "placeai-rxpp.vercel.app")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.placeai.example/")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres.example:placeholder@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres",
    )
    monkeypatch.setenv("JWT_SECRET_KEY", "A" * 40)
    monkeypatch.setenv("JWT_REFRESH_SECRET_KEY", "B" * 40)
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "false")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.placeai.example")

    settings = Settings()

    assert settings.base_url == "https://app.placeai.example"
    settings.validate_for_startup()


def test_vercel_preview_uses_test_defaults(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_REFRESH_SECRET_KEY", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    monkeypatch.delenv("PASSWORD_RESET_BASE_URL", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("AUTO_CREATE_SCHEMA", raising=False)

    settings = Settings()

    assert settings.running_on_vercel is True
    assert settings.vercel_environment == "preview"
    assert settings.environment == "test"
    assert settings.is_production is False
    assert settings.uses_database_file_storage is True
    assert settings.auto_create_schema is True
    settings.validate_for_startup()


def test_vercel_framework_discovery_can_import_without_runtime_secrets():
    env = os.environ.copy()
    env["VERCEL"] = "1"
    env["VERCEL_ENV"] = "preview"
    for name in (
        "ENVIRONMENT",
        "DATABASE_URL",
        "JWT_SECRET_KEY",
        "JWT_REFRESH_SECRET_KEY",
        "BASE_URL",
        "PUBLIC_APP_URL",
        "PASSWORD_RESET_BASE_URL",
        "ALLOWED_ORIGINS",
        "AUTO_CREATE_SCHEMA",
    ):
        env.pop(name, None)

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


def test_vercel_production_runtime_reports_missing_configuration_without_crashing():
    env = os.environ.copy()
    env["VERCEL"] = "1"
    env["VERCEL_ENV"] = "production"
    env["VERCEL_PROJECT_PRODUCTION_URL"] = "placeai-rxpp.vercel.app"
    for name in (
        "ENVIRONMENT",
        "DATABASE_URL",
        "JWT_SECRET_KEY",
        "JWT_REFRESH_SECRET_KEY",
        "BASE_URL",
        "PUBLIC_APP_URL",
        "PASSWORD_RESET_BASE_URL",
        "ALLOWED_ORIGINS",
        "AUTO_CREATE_SCHEMA",
    ):
        env.pop(name, None)

    script = """
from fastapi.testclient import TestClient
from app.app import app
with TestClient(app) as client:
    root = client.get('/')
    assert root.status_code == 200, root.text
    health = client.get('/health')
    assert health.status_code == 503, health.text
    payload = health.json()
    assert payload['configuration'] == 'invalid'
    assert 'JWT_SECRET_KEY_MISSING_OR_WEAK' in payload['configuration_errors']
    assert 'JWT_REFRESH_SECRET_KEY_MISSING_OR_WEAK' in payload['configuration_errors']
    assert 'DATABASE_URL_NOT_POSTGRESQL' in payload['configuration_errors']
    login = client.post('/auth/login-json', json={'email':'owner@example.com','password':'irrelevant'})
    assert login.status_code == 503, login.text
    assert login.json()['code'] == 'SERVICE_CONFIGURATION_ERROR'
print('runtime-diagnostic-ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "runtime-diagnostic-ok" in result.stdout


def test_supabase_postgresql_url_is_normalized_to_psycopg3(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres.example:placeholder@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres",
    )

    settings = Settings()

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "pooler.supabase.com:6543/postgres" in settings.database_url


def test_vercel_postgres_disables_prepared_statements_and_local_pool(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres.example:placeholder@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres",
    )

    settings = Settings()
    kwargs = build_engine_kwargs(settings)

    assert kwargs["poolclass"] is NullPool
    assert kwargs["connect_args"]["prepare_threshold"] is None
    assert kwargs["pool_pre_ping"] is True


def test_local_default_remains_development(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    settings = Settings()

    assert settings.running_on_vercel is False
    assert settings.environment == "development"
    assert settings.is_production is False
    assert settings.uses_database_file_storage is False
