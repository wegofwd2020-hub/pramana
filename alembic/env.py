"""Alembic environment.

Reads the database URL from the Pramana :class:`Settings` rather than from
``alembic.ini``, so migrations honour the same configuration the application
uses.

The :data:`target_metadata` is bound to the SQLAlchemy ``Base.metadata`` once
the data model lands in Phase B. Until then, autogenerate produces empty
revisions, which is fine for scaffolding verification.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from pramana.config import get_settings

# Alembic Config object.
config = context.config

# Override sqlalchemy.url with the value from app settings.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# Configure Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import the SQLAlchemy declarative Base once Phase B lands the models.
# Until then, autogenerate produces empty revisions.
try:
    from pramana.db.base import Base

    target_metadata = Base.metadata
except ImportError:  # pragma: no cover — Phase B not yet landed
    target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and emits SQL to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations against an active connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
