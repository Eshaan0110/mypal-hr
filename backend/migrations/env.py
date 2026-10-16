"""Alembic environment: connects migrations to our models and settings.

The database URL comes from mypal.config.Settings (MYPAL_DATABASE_URL), unless a caller such as
the test suite has already set `sqlalchemy.url` on the Alembic config programmatically.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from mypal.config import Settings
from mypal.db import models  # noqa: F401  (registers every table on Base.metadata)
from mypal.db.base import Base

config = context.config

# Only configure logging when run from the command line, not when tests call Alembic.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or Settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
