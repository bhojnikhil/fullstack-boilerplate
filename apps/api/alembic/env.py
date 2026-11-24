"""Alembic migration environment."""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

# Import your models here to auto-generate migrations
from app.core.config import DatabaseSettings
from app.core.idempotency import IdempotencyRecord  # noqa: F401
from app.core.models import Base
from app.modules.auth.models import User  # noqa: F401
from app.modules.items.models import Item  # noqa: F401

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None and "connection" not in config.attributes:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = DatabaseSettings().database(migration=True)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connection = config.attributes.get("connection")
    if connection is not None:
        migrate(connection)
        return

    engine = create_engine(DatabaseSettings().database(migration=True), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()


def migrate(connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, compare_server_default=True
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
