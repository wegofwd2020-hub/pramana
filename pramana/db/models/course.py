"""Course-domain ORM models.

Tables:

- :class:`Course` — course metadata (mutable; cooldown, threshold)
- :class:`CourseVersion` — published immutable version (snapshot of questions)
- :class:`Question` — quiz question, scoped to a course version
- :class:`AnswerOption` — answer choice, scoped to a question

Material changes (per the resolved decisions doc, Section 5) require
publishing a new course version and re-assigning affected users.
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pramana.db.base import Base
from pramana.db.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from pramana.db.models.assignment import Assignment, AttemptAnswer
    from pramana.db.models.identity import User


class QuestionType:
    """Allowed values for ``Question.question_type``."""

    SINGLE_SELECT = "single_select"
    TRUE_FALSE = "true_false"

    @classmethod
    def values(cls) -> list[str]:
        return [cls.SINGLE_SELECT, cls.TRUE_FALSE]


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------
class Course(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A trainable course.

    Course metadata (title, description, cooldown, threshold) is mutable.
    Question content is *not* — to change questions, publish a new
    :class:`CourseVersion`.

    Cooldown and pass threshold default to the platform-level values from
    :class:`pramana.config.Settings` but may be overridden per course.
    """

    __tablename__ = "course"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    cooldown_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=365
    )
    pass_threshold_pct: Mapped[int] = mapped_column(
        Integer, nullable=False, default=80
    )
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    framework_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)),
        nullable=False,
        default=list,
        server_default="{}",
        comment="Frameworks this course satisfies, e.g. ['sox'].",
    )
    topic_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)),
        nullable=False,
        default=list,
        server_default="{}",
        comment="Topic tags within frameworks, e.g. ['sox.ethics'].",
    )

    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_version.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
        comment="The active published version, if any.",
    )

    __table_args__ = (
        CheckConstraint(
            "pass_threshold_pct BETWEEN 0 AND 100",
            name="pass_threshold_pct_range",
        ),
        CheckConstraint("cooldown_days >= 0", name="cooldown_days_nonneg"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_min"),
        Index("ix_course_framework_tags", "framework_tags", postgresql_using="gin"),
        Index("ix_course_topic_tags", "topic_tags", postgresql_using="gin"),
    )

    author: Mapped[User | None] = relationship(back_populates="authored_courses")
    versions: Mapped[list[CourseVersion]] = relationship(
        back_populates="course",
        foreign_keys="CourseVersion.course_id",
        cascade="all, delete-orphan",
    )
    current_version: Mapped[CourseVersion | None] = relationship(
        foreign_keys=[current_version_id],
        post_update=True,
    )
    assignments: Mapped[list[Assignment]] = relationship(back_populates="course")


# ---------------------------------------------------------------------------
# CourseVersion
# ---------------------------------------------------------------------------
class CourseVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A published, immutable version of a course.

    Once a version is published, its questions and answer options are
    frozen. Material changes require a new version. The ``is_active`` flag
    identifies the version users are assigned by default — at most one
    active version per course at a time.
    """

    __tablename__ = "course_version"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    video_asset_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="S3 key of the uploaded video asset.",
    )
    min_watch_pct: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_material_change: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="If True, all assignments on the previous version must be re-issued.",
    )

    __table_args__ = (
        UniqueConstraint(
            "course_id", "version_number", name="course_version_unique"
        ),
        CheckConstraint("version_number >= 1", name="version_number_min"),
        CheckConstraint(
            "min_watch_pct BETWEEN 0 AND 100", name="min_watch_pct_range"
        ),
        # At most one active version per course.
        Index(
            "ix_course_version_active",
            "course_id",
            unique=True,
            postgresql_where="is_active = true",
        ),
    )

    course: Mapped[Course] = relationship(
        back_populates="versions", foreign_keys=[course_id]
    )
    questions: Mapped[list[Question]] = relationship(
        back_populates="course_version", cascade="all, delete-orphan"
    )
    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="course_version"
    )


# ---------------------------------------------------------------------------
# Question
# ---------------------------------------------------------------------------
class Question(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A quiz question scoped to a :class:`CourseVersion`.

    Questions are immutable once their parent version is published. The
    ``weight`` field allows authors to score certain questions more heavily;
    defaults to ``1.0`` (uniform).
    """

    __tablename__ = "question"

    course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("course_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(
        SQLEnum(*QuestionType.values(), name="question_type"),
        nullable=False,
    )
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("weight > 0", name="weight_positive"),
    )

    course_version: Mapped[CourseVersion] = relationship(
        back_populates="questions"
    )
    options: Mapped[list[AnswerOption]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="AnswerOption.display_order",
    )
    attempt_answers: Mapped[list[AttemptAnswer]] = relationship(
        back_populates="question"
    )


# ---------------------------------------------------------------------------
# AnswerOption
# ---------------------------------------------------------------------------
class AnswerOption(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One choice for a :class:`Question`.

    For ``single_select`` and ``true_false`` questions, exactly one option
    must have ``is_correct = True``. This is enforced at the application
    layer (a CHECK constraint can't easily span rows in the same table
    without a trigger).
    """

    __tablename__ = "answer_option"

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("question.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    option_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "question_id", "display_order", name="answer_option_order_unique"
        ),
    )

    question: Mapped[Question] = relationship(back_populates="options")
