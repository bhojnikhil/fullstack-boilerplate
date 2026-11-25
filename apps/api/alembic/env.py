"""Alembic migration environment."""

from sqlalchemy import create_engine, pool

from alembic import context

# Import every module that defines models so autogenerate and `alembic check` see them.
from app.core.audit import AuditEvent  # noqa: F401
from app.core.config import DatabaseSettings
from app.core.idempotency import IdempotencyRecord  # noqa: F401
from app.core.logging import configure_logging
from app.core.models import Base
from app.core.ratelimit import RateLimitWindow  # noqa: F401
from app.modules.auth.models import User  # noqa: F401
from app.modules.items.models import Item  # noqa: F401

# this is the Alembic Config object
config = context.config

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    settings = DatabaseSettings()
    configure_logging(settings.env)
    url = settings.database(migration=True)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connection = config.attributes.get("connection")
    if connection is not None:
        migrate(connection)
        return

    settings = DatabaseSettings()
    configure_logging(settings.env)
    engine = create_engine(
        settings.database(migration=True), poolclass=pool.NullPool, hide_parameters=True
    )
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()


def migrate(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_server_default=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
