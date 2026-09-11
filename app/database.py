from __future__ import annotations

import os
from urllib.parse import parse_qsl

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings


def build_runtime_database_url(database_url: str):
    """Return the effective database URL for the current runtime.

    On Render, an optional dedicated ``RENDER_DB_PASSWORD`` secret takes precedence.
    When present, all non-secret Supabase connection fields come from explicit Render
    environment variables and the password is passed to SQLAlchemy as a structured
    value, so it is never reinterpreted as URI syntax. Existing Vercel behavior is
    unchanged.
    """
    raw = (database_url or "").strip()
    if not os.getenv("RENDER_EXTERNAL_HOSTNAME"):
        return raw

    render_password = os.getenv("RENDER_DB_PASSWORD", "")
    if render_password:
        project_ref = os.getenv("SUPABASE_PROJECT_REF", "").strip()
        role = os.getenv("RENDER_DB_ROLE", "placeai_render_runtime").strip() or "placeai_render_runtime"
        host = os.getenv("RENDER_DB_HOST", "aws-0-ap-southeast-1.pooler.supabase.com").strip()
        port_raw = os.getenv("RENDER_DB_PORT", "5432").strip()
        database = os.getenv("RENDER_DB_NAME", "postgres").strip() or "postgres"
        username = role
        if project_ref and host.lower().endswith("pooler.supabase.com") and "." not in username:
            username = f"{username}.{project_ref}"
        try:
            port = int(port_raw)
        except ValueError:
            port = 5432
        return URL.create(
            "postgresql+psycopg",
            username=username,
            password=render_password,
            host=host,
            port=port,
            database=database,
            query={"sslmode": "require"},
        )

    # Backward-compatible fallback for an existing full DATABASE_URL on Render.
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

    authority, slash, path_and_query = endpoint.partition("/")
    if not authority:
        return raw
    host, port = authority, None
    if ":" in authority:
        host_candidate, port_candidate = authority.rsplit(":", 1)
        if port_candidate.isdigit():
            host = host_candidate
            port = int(port_candidate)

    database = None
    query = {}
    if slash:
        database_part, query_sep, query_string = path_and_query.partition("?")
        database = database_part or None
        if query_sep:
            query = dict(parse_qsl(query_string, keep_blank_values=True))

    project_ref = os.getenv("SUPABASE_PROJECT_REF", "").strip()
    if project_ref and host.lower().endswith("pooler.supabase.com") and "." not in username:
        username = f"{username}.{project_ref}"

    return URL.create(
        "postgresql+psycopg",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query=query,
    )


def normalize_database_url_for_runtime(database_url: str) -> str:
    runtime_url = build_runtime_database_url(database_url)
    if isinstance(runtime_url, URL):
        return runtime_url.render_as_string(hide_password=False)
    return runtime_url


def build_engine_kwargs(settings):
    is_sqlite = settings.database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}

    if settings.running_on_vercel and not is_sqlite:
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
        engine_kwargs["poolclass"] = NullPool
    return engine_kwargs


def safe_database_target(database_url: str) -> dict[str, object]:
    """Return non-secret connection metadata suitable for /health diagnostics."""
    try:
        url = make_url(build_runtime_database_url(database_url))
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
    runtime_database_url = build_runtime_database_url(settings.database_url)
    engine = create_engine(runtime_database_url, **build_engine_kwargs(settings))
except Exception:
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
