from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool
from app.config import get_settings

settings = get_settings()

_engine_kwargs = {
    "connect_args": {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    "pool_pre_ping": True,
}
if settings.running_on_vercel and not settings.database_url.startswith("sqlite"):
    _engine_kwargs["poolclass"] = NullPool

engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
