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

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pramana.config import get_settings
from pramana.exceptions import DatabaseError, PramanaError

logger = structlog.get_logger(__name__)

#: What a caller is told when the database fails in a way we did not anticipate.
#: Deliberately says nothing about the statement, the data or the schema — the
#: detail goes to the log under the incident id returned alongside it.
_OPAQUE_DB_FAILURE = "A database operation failed."
_OPAQUE_ENGINE_FAILURE = "The database connection is not configured correctly."


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
    except Exception as exc:
        # settings.database_url is a DSN with a password in it. It used to go
        # into context, and context is rendered into the HTTP response body.
        incident_id = uuid.uuid4()
        logger.error(
            "engine_construction_failed",
            incident_id=str(incident_id),
            detail=str(exc),
            exc_info=True,
        )
        raise DatabaseError(_OPAQUE_ENGINE_FAILURE, incident_id=incident_id) from exc


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
        DatabaseError: Wraps an *unexpected* error (e.g. a raw SQLAlchemy
            failure) so callers can handle a single exception type.
    """
    sessionmaker_ = get_sessionmaker()
    session = sessionmaker_()
    try:
        yield session
        await session.commit()
    except PramanaError:
        # The application's own typed errors — AuthenticationError,
        # AuthorizationError, NotFoundError, DomainError, and so on — must reach
        # the API's exception handler with their class intact. Every DB-backed
        # route resolves its principal *inside* this scope, so those errors
        # propagate back through here; wrapping them as DatabaseError would turn
        # a 401/403/404 into a 502. Roll back the (untouched) transaction and
        # re-raise unchanged. DatabaseError is itself a PramanaError, so this
        # also covers the error already raised below on a re-entrant scope.
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        # SQLAlchemy's str() on a DBAPIError carries "[SQL: ...]" and
        # "[parameters: (...)]" — the statement and every bound value, which is
        # PII on most of our tables. Log it, do not return it.
        incident_id = uuid.uuid4()
        logger.error(
            "database_operation_failed",
            incident_id=str(incident_id),
            detail=str(exc),
            exc_info=True,
        )
        raise DatabaseError(_OPAQUE_DB_FAILURE, incident_id=incident_id) from exc
    finally:
        await session.close()
