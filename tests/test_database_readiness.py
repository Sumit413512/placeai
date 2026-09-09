from __future__ import annotations

from app.config import Settings
from app.database import build_engine_kwargs, classify_database_exception, safe_database_target


class _SqlStateError(RuntimeError):
    def __init__(self, message: str, sqlstate: str):
        super().__init__(message)
        self.sqlstate = sqlstate


def test_supabase_transaction_pooler_metadata_is_safe_and_recognized(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres.projectref:password@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres",
    )
    settings = Settings()
    target = safe_database_target(settings.database_url)

    assert target["driver"] == "postgresql+psycopg"
    assert target["supabase_pooler"] is True
    assert target["transaction_pooler"] is True
    assert target["port"] == 6543
    assert target["username_shape_ok"] is True
    assert "password" not in repr(target)


def test_vercel_postgres_connection_is_bounded_and_requires_tls(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres.projectref:password@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres",
    )
    settings = Settings()
    kwargs = build_engine_kwargs(settings)

    assert kwargs["connect_args"]["connect_timeout"] == 5
    assert kwargs["connect_args"]["sslmode"] == "require"
    assert kwargs["connect_args"]["prepare_threshold"] is None


def test_database_error_classifier_never_returns_exception_text():
    cases = {
        "Tenant or user not found": "DATABASE_POOLER_TENANT_OR_USER_NOT_FOUND",
        "password authentication failed for user someone": "DATABASE_AUTHENTICATION_FAILED",
        "SASL authentication failed": "DATABASE_AUTHENTICATION_FAILED",
        "max client connections reached": "DATABASE_CONNECTION_LIMIT",
        "could not translate host name example.invalid": "DATABASE_DNS_RESOLUTION_FAILED",
        "connection timeout expired": "DATABASE_CONNECTION_TIMEOUT",
        "connection refused": "DATABASE_CONNECTION_REFUSED",
        "network is unreachable": "DATABASE_NETWORK_UNREACHABLE",
        "server closed the connection unexpectedly": "DATABASE_CONNECTION_CLOSED",
        "SSL certificate verify failed": "DATABASE_SSL_FAILED",
        "some unknown database transport problem": "DATABASE_CONNECTION_FAILED",
    }
    for message, expected in cases.items():
        code = classify_database_exception(RuntimeError(message))
        assert code == expected
        assert message not in code


def test_database_error_classifier_uses_sqlstate_when_available():
    cases = {
        "28P01": "DATABASE_AUTHENTICATION_FAILED",
        "28000": "DATABASE_AUTHENTICATION_FAILED",
        "3D000": "DATABASE_NAME_INVALID",
        "42501": "DATABASE_PERMISSION_DENIED",
        "53300": "DATABASE_CONNECTION_LIMIT",
        "57P03": "DATABASE_SERVER_UNAVAILABLE",
        "08004": "DATABASE_CONNECTION_REJECTED",
        "08006": "DATABASE_CONNECTION_CLOSED",
        "08001": "DATABASE_CONNECTION_FAILED",
    }
    for sqlstate, expected in cases.items():
        assert classify_database_exception(_SqlStateError("redacted", sqlstate)) == expected
