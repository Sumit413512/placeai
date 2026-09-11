from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL

from app.config import get_settings
from app.database import Base, build_runtime_database_url
from app import models  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
runtime_database_url = build_runtime_database_url(get_settings().database_url)


def run_migrations_offline():
    if isinstance(runtime_database_url, URL):
        url = runtime_database_url.render_as_string(hide_password=False)
    else:
        url = runtime_database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # Build directly from the structured URL object on Render so raw password
    # characters are never reinterpreted by ConfigParser or URI parsing.
    connectable = create_engine(runtime_database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
