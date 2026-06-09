"""Pramana ORM models.

Importing this package is sufficient to register all models with
:data:`pramana.db.base.Base.metadata`, which Alembic relies on for
autogeneration.
"""

from __future__ import annotations

from pramana.db.models.assignment import (
    Assignment,
    Attempt,
    AttemptAnswer,
    Certificate,
)
from pramana.db.models.audit import AuditLog
from pramana.db.models.content import ContentDraft
from pramana.db.models.content_request import ContentRequest
from pramana.db.models.course import (
    AnswerOption,
    Course,
    CourseVersion,
    Question,
    QuestionType,
)
from pramana.db.models.identity import (
    Role,
    RoleName,
    Tenant,
    User,
    UserRole,
    UserStatus,
    UserType,
)

__all__ = [  # noqa: RUF022 - grouped by domain, not alphabetical
    # Identity
    "Tenant",
    "User",
    "Role",
    "UserRole",
    "UserStatus",
    "UserType",
    "RoleName",
    # Course
    "Course",
    "CourseVersion",
    "Question",
    "AnswerOption",
    "QuestionType",
    # Content authoring
    "ContentDraft",
    "ContentRequest",
    # Assignment
    "Assignment",
    "Attempt",
    "AttemptAnswer",
    "Certificate",
    # Audit
    "AuditLog",
]
