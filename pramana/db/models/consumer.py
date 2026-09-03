"""Consumer-domain ORM models (self-serve subscription mode).

Parallel to the B2B assignment runtime: these tables reuse the shared content
models (Course/CourseVersion/Question/AnswerOption) but never touch the audited
Assignment machinery. See docs/superpowers/specs/2026-09-03-consumer-subscription-design.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pramana.db.base import Base
from pramana.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

_ENTITLEMENT_STATUS = ("active", "revoked", "expired")
_ENTITLEMENT_SOURCE = ("manual", "stripe")
_MEDIA_KIND = ("video", "audio")


class Package(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "package"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="usd")
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="package_slug_unique"),
        CheckConstraint("price_cents IS NULL OR price_cents >= 0", name="price_cents_nonneg"),
    )


class PackageCourse(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "package_course"

    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("package.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("package_id", "course_id", name="package_course_unique"),)


class Entitlement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "entitlement"

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
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("package.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        SQLEnum(*_ENTITLEMENT_STATUS, name="entitlement_status"),
        nullable=False,
        default="active",
    )
    source: Mapped[str] = mapped_column(
        SQLEnum(*_ENTITLEMENT_SOURCE, name="entitlement_source"),
        nullable=False,
        default="manual",
    )
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index(
            "ix_entitlement_active_unique",
            "user_id",
            "package_id",
            unique=True,
            postgresql_where="status = 'active'",
        ),
    )


class Enrollment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "enrollment"

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
    entitlement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entitlement.id", ondelete="RESTRICT"),
        nullable=False,
    )
    first_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    completion_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    best_score_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="enrollment_user_course_unique"),
        CheckConstraint("view_count >= 0", name="view_count_nonneg"),
        CheckConstraint("completion_count >= 0", name="completion_count_nonneg"),
    )


class PlaySession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "play_session"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enrollment.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    media_kind: Mapped[str] = mapped_column(
        SQLEnum(*_MEDIA_KIND, name="media_kind"), nullable=False, default="video"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_watched_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("max_watched_pct BETWEEN 0 AND 100", name="max_watched_pct_range"),
        CheckConstraint("duration_seconds >= 0", name="duration_seconds_nonneg"),
    )


class ConsumerAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "consumer_attempt"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enrollment.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_all_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_active_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "score_pct IS NULL OR (score_pct BETWEEN 0 AND 100)", name="score_pct_range"
        ),
        # When submitted, is_all_correct must agree with a perfect score.
        CheckConstraint(
            "submitted_at IS NULL OR (is_all_correct = (score_pct = 100))",
            name="all_correct_consistent",
        ),
    )


class ConsumerAttemptAnswer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "consumer_attempt_answer"

    consumer_attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("consumer_attempt.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("question.id", ondelete="RESTRICT"),
        nullable=False,
    )
    selected_option_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "consumer_attempt_id", "question_id", name="consumer_attempt_answer_unique"
        ),
    )
