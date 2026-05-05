"""SQLAlchemy declarative base.

Centralised so Alembic can import :data:`Base.metadata` without circular
imports. All ORM models inherit from :class:`Base`.

We use SQLAlchemy 2.x typed ORM (``Mapped`` + ``mapped_column``) and the
asyncio extension. PostgreSQL is the only supported dialect — we lean on
``CITEXT`` for case-insensitive email columns and native ``ENUM`` types for
the lifecycle enums.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Naming convention for constraints, used by Alembic autogenerate to produce
# stable, predictable constraint names across environments.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all Pramana ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
