from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.config import get_settings
from app.database import Base, normalize_database_url_for_runtime
from app import models  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

database_url = normalize_database_url_for_runtime(get_settings().database_url)
# Alembic's ConfigParser treats percent signs as interpolation tokens. Render URLs
# can contain percent-encoded credentials, so escape percent characters here; the
# value read back by Alembic resolves to the intended single-percent URL.
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
