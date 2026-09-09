from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings


def build_engine_kwargs(settings):
    is_sqlite = settings.database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}

    if settings.running_on_vercel and not is_sqlite:
        # Supabase recommends its transaction-mode Supavisor pooler for
        # serverless/auto-scaling workloads. Psycopg prepared statements are not
        # compatible with transaction pooling, so disable them per connection.
        connect_args["prepare_threshold"] = None

    engine_kwargs = {
        "connect_args": connect_args,
        "pool_pre_ping": True,
    }
    if settings.running_on_vercel and not is_sqlite:
        # Let Supavisor own pooling; Vercel functions should not retain their own
        # SQLAlchemy connection pool between short-lived invocations.
        engine_kwargs["poolclass"] = NullPool
    return engine_kwargs


settings = get_settings()
engine_initialization_error_code: str | None = None
try:
    engine = create_engine(settings.database_url, **build_engine_kwargs(settings))
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
