from __future__ import annotations

import os
from urllib.parse import quote

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings


def normalize_database_url_for_runtime(database_url: str) -> str:
    """Normalize Render Postgres credentials without exposing or rewriting secrets.

    Supabase pooler connection strings can be pasted with raw reserved characters in
    the password. They also require pooler usernames in the form ROLE.PROJECT_REF.
    Apply those two Render-only normalizations before SQLAlchemy/Psycopg parse the URL.
    Vercel behavior remains unchanged.
    """
    raw = (database_url or "").strip()
    if not os.getenv("RENDER_EXTERNAL_HOSTNAME"):
        return raw

    prefix = "postgresql+psycopg://"
    if not raw.startswith(prefix):
        return raw

    remainder = raw[len(prefix):]
    if "@" not in remainder:
        return raw
    credentials, endpoint = remainder.rsplit("@", 1)
    if ":" not in credentials or not endpoint:
        return raw

    username, password = credentials.split(":", 1)
    if not username:
        return raw

    endpoint_authority = endpoint.split("/", 1)[0]
    endpoint_host = endpoint_authority.rsplit(":", 1)[0].lower()
    project_ref = os.getenv("SUPABASE_PROJECT_REF", "").strip()
    if (
        project_ref
        and endpoint_host.endswith("pooler.supabase.com")
        and "." not in username
    ):
        username = f"{username}.{project_ref}"

    # Preserve existing percent escapes while encoding raw reserved characters.
    safe_username = quote(username, safe=".%")
    safe_password = quote(password, safe="%")
    return f"{prefix}{safe_username}:{safe_password}@{endpoint}"


def build_engine_kwargs(settings):
    is_sqlite = settings.database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}

    if settings.running_on_vercel and not is_sqlite:
        # Supabase recommends its transaction-mode Supavisor pooler for
        # serverless/auto-scaling workloads. Psycopg prepared statements are not
        # compatible with transaction pooling, so disable them per connection.
        # Bound connection establishment as well: a bad pooler host/credential must
        # produce a readiness result quickly rather than consuming a full invocation.
        connect_args.update(
            {
                "prepare_threshold": None,
                "connect_timeout": 5,
                "sslmode": "require",
            }
        )

    engine_kwargs = {
        "connect_args": connect_args,
        "pool_pre_ping": True,
    }
    if settings.running_on_vercel and not is_sqlite:
        # Let Supavisor own pooling; Vercel functions should not retain their own
        # SQLAlchemy connection pool between short-lived invocations.
        engine_kwargs["poolclass"] = NullPool
    return engine_kwargs


def safe_database_target(database_url: str) -> dict[str, object]:
    """Return non-secret connection metadata suitable for /health diagnostics."""
    try:
        url = make_url(normalize_database_url_for_runtime(database_url))
    except Exception:
        return {"driver": "invalid", "supabase_pooler": False, "port": None}
    host = (url.host or "").lower()
    return {
        "driver": url.drivername,
        "supabase_pooler": host.endswith("pooler.supabase.com"),
        "transaction_pooler": host.endswith("pooler.supabase.com") and url.port == 6543,
        "port": url.port,
        "username_shape_ok": bool("." in (url.username or "")),
    }


def classify_database_exception(exc: BaseException) -> str:
    """Map connection failures to safe codes without returning hosts, users or secrets."""
    current: BaseException | None = exc
    visited: set[int] = set()
    texts: list[str] = []
    sqlstates: list[str] = []
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        sqlstate = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if sqlstate:
            sqlstates.append(str(sqlstate).upper())
        texts.append(str(current).lower())
        original = getattr(current, "orig", None)
        cause = getattr(current, "__cause__", None)
        current = original if isinstance(original, BaseException) else cause

    for sqlstate in sqlstates:
        if sqlstate in {"28P01", "28000"}:
            return "DATABASE_AUTHENTICATION_FAILED"
        if sqlstate == "3D000":
            return "DATABASE_NAME_INVALID"
        if sqlstate == "42501":
            return "DATABASE_PERMISSION_DENIED"
        if sqlstate == "53300":
            return "DATABASE_CONNECTION_LIMIT"
        if sqlstate == "57P03":
            return "DATABASE_SERVER_UNAVAILABLE"
        if sqlstate == "08004":
            return "DATABASE_CONNECTION_REJECTED"
        if sqlstate in {"08003", "08006", "08007"}:
            return "DATABASE_CONNECTION_CLOSED"
        if sqlstate.startswith("08"):
            return "DATABASE_CONNECTION_FAILED"

    text = " ".join(texts)
    if "tenant or user not found" in text:
        return "DATABASE_POOLER_TENANT_OR_USER_NOT_FOUND"
    if (
        "password authentication failed" in text
        or "authentication failed" in text
        or "sasl authentication failed" in text
        or "invalid password" in text
    ):
        return "DATABASE_AUTHENTICATION_FAILED"
    if (
        "max client connections reached" in text
        or "too many connections" in text
        or "remaining connection slots are reserved" in text
    ):
        return "DATABASE_CONNECTION_LIMIT"
    if "could not translate host name" in text or "name or service not known" in text or "nodename nor servname" in text:
        return "DATABASE_DNS_RESOLUTION_FAILED"
    if "timeout expired" in text or "connection timeout" in text or "timed out" in text:
        return "DATABASE_CONNECTION_TIMEOUT"
    if "connection refused" in text:
        return "DATABASE_CONNECTION_REFUSED"
    if "no route to host" in text or "network is unreachable" in text:
        return "DATABASE_NETWORK_UNREACHABLE"
    if (
        "server closed the connection unexpectedly" in text
        or "connection is bad" in text
        or "eof detected" in text
        or "unexpected eof" in text
    ):
        return "DATABASE_CONNECTION_CLOSED"
    if "ssl" in text or "certificate" in text:
        return "DATABASE_SSL_FAILED"
    return "DATABASE_CONNECTION_FAILED"


settings = get_settings()
engine_initialization_error_code: str | None = None
try:
    runtime_database_url = normalize_database_url_for_runtime(settings.database_url)
    engine = create_engine(runtime_database_url, **build_engine_kwargs(settings))
except Exception:
    # A malformed/unsupported production URL must never make the entire Vercel
    # Python process unbootable. Bind an in-memory diagnostic engine only so the
    # FastAPI process can expose readiness; protected traffic is blocked by app.py.
    # This is never an application-data fallback.
    engine_initialization_error_code = "DATABASE_ENGINE_INITIALIZATION_FAILED"
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
