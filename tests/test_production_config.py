from __future__ import annotations

import os
import subprocess
import sys

import pytest

from app.config import Settings


def test_vercel_defaults_to_production_and_fails_closed(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_REFRESH_SECRET_KEY", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("AUTO_CREATE_SCHEMA", raising=False)

    settings = Settings()

    assert settings.running_on_vercel is True
    assert settings.environment == "production"
    assert settings.is_production is True
    assert settings.uses_database_file_storage is True
    assert settings.auto_create_schema is False

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        settings.validate_for_startup()


def test_vercel_framework_discovery_can_import_without_runtime_secrets():
    env = os.environ.copy()
    env["VERCEL"] = "1"
    for name in (
        "ENVIRONMENT",
        "DATABASE_URL",
        "JWT_SECRET_KEY",
        "JWT_REFRESH_SECRET_KEY",
        "BASE_URL",
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


def test_local_default_remains_development(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    settings = Settings()

    assert settings.running_on_vercel is False
    assert settings.environment == "development"
    assert settings.is_production is False
    assert settings.uses_database_file_storage is False
