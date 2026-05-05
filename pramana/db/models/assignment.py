"""Assignment-domain ORM models.

Tables:

- :class:`Assignment` — user × course-version, with lifecycle state
- :class:`Attempt` — single quiz attempt; up to ``max_attempts`` per assignment
- :class:`AttemptAnswer` — selected option(s) per question per attempt
- :class:`Certificate` — issued upon ``PASSED`` assignment

The ``Assignment.status`` column is intentionally backed by the same string
values as :class:`pramana.domain.enums.AssignmentStatus` so the persistence
layer and the pure domain layer agree on shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pramana.db.base import Base
from pramana.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from pramana.domain.enums import AssignmentStatus, AttemptOutcome, TerminalReason

if TYPE_CHECKING:
    from pramana.db.models.course import Course, CourseVersion, Question
    from pramana.db.models.identity import User


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------
class Assignment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A course assigned to a user.

    The ``course_version_id`` is snapshotted at creation time so that
    publishing a new course version does not retroactively change what the
    user is being tested on. The lifecycle state is governed by
    :mod:`pramana.domain.assignment_state`.
    """

    __tablename__ = "assignment"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_version.id", ondelete="RESTRICT"),
        nullable=False,
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    status: Mapped[str] = mapped_column(
        SQLEnum(
            *[s.value for s in AssignmentStatus],
            name="assignment_status",
        ),
        nullable=False,
        default=AssignmentStatus.ASSIGNED.value,
    )

    attempts_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
        comment="Snapshotted from Course.max_attempts at creation time.",
    )
    cooldown_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=365,
        comment="Snapshotted from Course.cooldown_days at creation time.",
    )

    terminal_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terminal_reason: Mapped[str | None] = mapped_column(
        SQLEnum(
            *[r.value for r in TerminalReason],
            name="terminal_reason",
        ),
        nullable=True,
    )
    cooldown_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "attempts_used >= 0 AND attempts_used <= max_attempts + 1",
            # +1 tolerance for the just-incremented "in flight" attempt.
            name="attempts_used_range",
        ),
        CheckConstraint("cooldown_days >= 0", name="cooldown_days_nonneg"),
        # terminal_at is set iff status is terminal (mirrors the domain invariant).
        CheckConstraint(
            "(status IN ('passed','blocked','cancelled','expired')) "
            "= (terminal_at IS NOT NULL)",
            name="terminal_at_consistent",
        ),
        # cooldown_until is set iff status started cooldown (PASSED or BLOCKED).
        CheckConstraint(
            "(status IN ('passed','blocked')) = (cooldown_until IS NOT NULL)",
            name="cooldown_until_consistent",
        ),
        Index("ix_assignment_user_status", "user_id", "status"),
        Index("ix_assignment_course_status", "course_id", "status"),
        Index("ix_assignment_due_at", "due_at"),
    )

    user: Mapped[User] = relationship(
        back_populates="assignments", foreign_keys=[user_id]
    )
    course: Mapped[Course] = relationship(back_populates="assignments")
    course_version: Mapped[CourseVersion] = relationship(
        back_populates="assignments"
    )
    attempts: Mapped[list[Attempt]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan"
    )
    certificate: Mapped[Certificate | None] = relationship(
        back_populates="assignment",
        uselist=False,
    )


# ---------------------------------------------------------------------------
# Attempt
# ---------------------------------------------------------------------------
class Attempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One quiz attempt.

    Each :class:`Assignment` may have up to ``max_attempts`` attempts. Per
    Section 4 of the resolved decisions doc, a failed attempt with
    remaining attempts goes back to ``ASSIGNED`` and the next attempt
    replays only the wrongly-answered questions; the persistence layer
    records each attempt independently.
    """

    __tablename__ = "attempt"

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    score_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str] = mapped_column(
        SQLEnum(*[o.value for o in AttemptOutcome], name="attempt_outcome"),
        nullable=False,
        default=AttemptOutcome.IN_PROGRESS.value,
    )

    total_active_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attestation_accepted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "attempt_number", name="attempt_number_unique"
        ),
        CheckConstraint("attempt_number >= 1", name="attempt_number_min"),
        CheckConstraint(
            "score_pct IS NULL OR (score_pct BETWEEN 0 AND 100)",
            name="score_pct_range",
        ),
        # Submitted attempts always have a score and a non-IN_PROGRESS outcome.
        CheckConstraint(
            "(submitted_at IS NULL) = (outcome = 'in_progress')",
            name="outcome_consistent_with_submission",
        ),
    )

    assignment: Mapped[Assignment] = relationship(back_populates="attempts")
    answers: Mapped[list[AttemptAnswer]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# AttemptAnswer
# ---------------------------------------------------------------------------
class AttemptAnswer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A user's answer to one question within one attempt."""

    __tablename__ = "attempt_answer"

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attempt.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("question.id", ondelete="RESTRICT"),
        nullable=False,
    )

    selected_option_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
        server_default="{}",
    )
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    time_spent_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "attempt_id", "question_id", name="attempt_answer_unique"
        ),
    )

    attempt: Mapped[Attempt] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship(back_populates="attempt_answers")


# ---------------------------------------------------------------------------
# Certificate
# ---------------------------------------------------------------------------
class Certificate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A completion certificate.

    Issued automatically upon :class:`AssignmentStatus.PASSED`. The
    ``verification_code`` is the publicly verifiable token surfaced via the
    ``GET /certificates/verify/{verification_code}`` endpoint.

    The ``attestation_*`` columns capture SOX-required attestations: who
    confirmed they took the training honestly, when, from which IP, and
    against which version of the attestation text.
    """

    __tablename__ = "certificate"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course.id", ondelete="RESTRICT"),
        nullable=False,
    )
    course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignment.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    verification_code: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True
    )

    pdf_object_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="S3 key of the rendered certificate PDF.",
    )

    # Attestation evidence
    attestation_text_version: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    attestation_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    attestation_user_agent: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    attestation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_certificate_user_issued", "user_id", "issued_at"),
    )

    user: Mapped[User] = relationship(back_populates="certificates")
    assignment: Mapped[Assignment] = relationship(back_populates="certificate")
