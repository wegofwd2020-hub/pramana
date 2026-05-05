"""Async database session factory.

Provides:

- :func:`get_engine` — module-singleton :class:`AsyncEngine`.
- :func:`get_sessionmaker` — module-singleton session factory.
- :func:`session_scope` — async context manager that handles commit / rollback.

The engine and sessionmaker are constructed lazily so importing this module
does not open a connection — important for unit tests that don't need the
database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pramana.config import get_settings
from pramana.exceptions import DatabaseError


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return the singleton async engine.

    Returns:
        The :class:`AsyncEngine` configured from :class:`pramana.config.Settings`.

    Raises:
        DatabaseError: If the configured DSN cannot be parsed.
    """
    settings = get_settings()
    try:
        return create_async_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            echo=settings.database_echo,
            future=True,
        )
    except Exception as exc:  # noqa: BLE001 — surface as DatabaseError
        raise DatabaseError(
            f"Failed to construct async engine: {exc}",
            context={"database_url": settings.database_url},
        ) from exc


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the singleton async sessionmaker."""
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
        class_=AsyncSession,
    )


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Provide a transactional scope around a series of operations.

    Yields:
        An :class:`AsyncSession`. The transaction is committed on clean exit
        and rolled back on any exception.

    Raises:
        DatabaseError: Wraps any underlying SQLAlchemy error so callers can
            handle a single exception type.
    """
    sessionmaker_ = get_sessionmaker()
    session = sessionmaker_()
    try:
        yield session
        await session.commit()
    except DatabaseError:
        await session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise DatabaseError(f"Database operation failed: {exc}") from exc
    finally:
        await session.close()
