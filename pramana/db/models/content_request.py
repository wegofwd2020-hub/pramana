"""Content-request ORM model — the Create phase (commission → Mentible).

A :class:`ContentRequest` is the persistent record of a commissioning request
(US-PLATFORM-0003): the **spec side** of the Mentible ADR-011 manifest that an
author submits, captured as an auditable artifact (``requested_by``) and pushed
to Mentible. It tracks the work until the manufactured Consumable Package is
ingested as a :class:`~pramana.db.models.content.ContentDraft` (``draft_id``) and
published.

The request *spec* (scope, source_definitions, learning_objectives, assessment,
constraints, deliverables, visuals) is validated by the pure
:mod:`pramana.domain.package_request` and stored verbatim on ``spec`` — Pramana
does not re-derive it, and the exact bytes pushed to Mentible stay on record.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Enum as SQLEnum,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pramana.db.base import Base
from pramana.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from pramana.domain.enums import ContentRequestStatus

_STATUS_VALUES = [s.value for s in ContentRequestStatus]


class ContentRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A commissioned Package Request and its lifecycle status."""

    __tablename__ = "content_request"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    framework: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    status: Mapped[str] = mapped_column(
        SQLEnum(*_STATUS_VALUES, name="content_request_status"),
        nullable=False,
        default=ContentRequestStatus.REQUESTED.value,
        server_default=ContentRequestStatus.REQUESTED.value,
        index=True,
    )

    # Who authorized the generation (audit). String, not an FK: the principal's
    # id, kept even if the user is later removed.
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # The full Package Request spec (scope/source_definitions/assessment/…),
    # stored verbatim as the exact payload pushed to Mentible.
    spec: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Target course lineage (NULL = a new course will be created on ingest).
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Mentible round-trip references (set as the request progresses) ──────────
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Mentible package_id, once a package is returned.",
    )
    draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_draft.id", ondelete="SET NULL"),
        nullable=True,
        comment="The ContentDraft created when the package was ingested.",
    )
    # Set if a regenerate re-issued this request: the draft it supersedes.
    regenerated_from_draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_draft.id", ondelete="SET NULL"),
        nullable=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_content_request_tenant_status", "tenant_id", "status"),
        Index("ix_content_request_tenant_framework", "tenant_id", "framework"),
    )
