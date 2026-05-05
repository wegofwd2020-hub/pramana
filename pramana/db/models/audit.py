"""Audit log model.

Per the resolved decisions doc (Section 6 entity 12) and SOX requirements:

* The audit log is **append-only**. The application never updates or deletes
  rows. Triggers in the migration enforce this at the database level.
* Each row carries ``prev_audit_hash`` so the log forms a hash chain;
  tampering is detectable.
* Rows are mirrored to S3 with Object Lock for immutable archival in v2.

The audit log is the single source of truth for "what happened, when, and
who did it" — the entity tables tell you the *current* state, but the
audit log tells you the *history*.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pramana.db.base import Base


class AuditLog(Base):
    """One audit-log entry.

    Attributes:
        audit_id: Monotonically increasing primary key (BIGINT IDENTITY).
        tenant_id: Tenant whose data is described.
        actor_user_id: User who performed the action (None for system events).
        actor_ip: IP address of the actor (None for system events).
        entity_type: Logical entity type (e.g. ``"assignment"``, ``"user"``).
        entity_id: String form of the entity's primary key.
        event_type: Stable event name (e.g. ``"assignment.passed"``).
        payload: JSONB blob of event-specific context.
        occurred_at: When the event occurred (timezone-aware).
        prev_audit_hash: SHA-256 hex of the previous row, forming a chain.
        audit_hash: SHA-256 hex of this row's canonical form.
    """

    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    actor_user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)

    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    prev_audit_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audit_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_event_type", "event_type"),
        Index("ix_audit_occurred_at", "occurred_at"),
    )
