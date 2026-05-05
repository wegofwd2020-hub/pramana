"""Common ORM mixins.

These mixins capture cross-cutting fields (UUID primary keys, timestamps,
soft delete) so individual model classes stay focused on their domain
fields.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key.

    Subclasses should override :meth:`__pk_name__` if their primary key column
    is named something other than ``id`` — for instance ``user_id``,
    ``course_id``. The default uses the table's logical entity name.
    """

    @declared_attr
    def id(cls) -> Mapped[uuid.UUID]:  # noqa: N805 - SQLAlchemy convention
        return mapped_column(
            UUID(as_uuid=True),
            primary_key=True,
            default=uuid.uuid4,
            nullable=False,
        )


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` columns.

    ``updated_at`` is set by the database on every row update via
    ``server_onupdate``. Both columns are timezone-aware (``timestamptz``).
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Adds an optional ``archived_at`` timestamp for soft deletion.

    Hard deletion is **never** permitted for compliance entities; archive in
    place and let retention policies sweep aged rows.
    """

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None
