"""Content-authoring ORM models.

Tables:

- :class:`ContentDraft` — an AI-drafted (or hand-authored) training-content
  draft moving through the approval workflow (``docs/03_ai_drafted_human_
  approved_content.md``). On approval + publish it materialises into an
  immutable :class:`pramana.db.models.course.CourseVersion`; the draft records
  which version it produced.

The approval *rules* live in the pure
:mod:`pramana.domain.content_approval` state machine; this table is the
persistent representation the service layer reads/writes around it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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
from pramana.domain.enums import ContentDraftStatus

_CONTENT_DRAFT_STATUS_VALUES = [s.value for s in ContentDraftStatus]


class ContentDraft(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A draft of training content under human review.

    Generation is a drafting aid: a draft is **never** assignable. It must reach
    ``APPROVED`` (by someone other than its generator — separation of duties) and
    be ``PUBLISHED`` into a :class:`CourseVersion` before any assignment can pin
    to it. Approval freezes the content via ``content_hash`` and records the
    approver + attestation as audit evidence.
    """

    __tablename__ = "content_draft"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        SQLEnum(*_CONTENT_DRAFT_STATUS_VALUES, name="content_draft_status"),
        nullable=False,
        default=ContentDraftStatus.DRAFT.value,
        server_default=ContentDraftStatus.DRAFT.value,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # Structured content body (sections, quiz, deck/video render hints).
    body: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Framework clauses each section is based on, e.g. [{"section": 0, "ref": "sox.404"}].
    source_citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Provenance (how the draft was produced) ────────────────────────────────
    gen_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    gen_provider: Mapped[str | None] = mapped_column(String(60), nullable=True)
    gen_prompt_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Review / approval (the audit evidence) ─────────────────────────────────
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attestation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Hash of the exact approved content body; set on approval.",
    )

    # ── Published output ───────────────────────────────────────────────────────
    published_course_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_version.id", ondelete="SET NULL"),
        nullable=True,
        comment="The immutable CourseVersion this draft materialised into.",
    )

    __table_args__ = (
        # Approval evidence must be present together (or absent together).
        # Names are short; the metadata naming convention prefixes ck_content_draft_.
        CheckConstraint(
            "(approved_by_user_id IS NULL) = (approved_at IS NULL)",
            name="approval_pair",
        ),
        # Separation of duties: the approver may not be the generator.
        CheckConstraint(
            "approved_by_user_id IS NULL "
            "OR generated_by_user_id IS NULL "
            "OR approved_by_user_id <> generated_by_user_id",
            name="separation_of_duties",
        ),
        Index("ix_content_draft_course_status", "course_id", "status"),
    )
