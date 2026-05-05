"""Identity-domain ORM models.

Per the resolved decisions doc (Section 6), Pramana is multi-tenant-ready
but enforces single tenancy at the v1 application layer; the schema carries
the ``tenant_id`` columns from day one to avoid backfill later.

Tables:

- :class:`Tenant` — single row in v1 (John Thomas Corporate)
- :class:`User` — synthetic ``user_id`` PK; mutable email
- :class:`Role` — seed table with the 5 fixed roles
- :class:`UserRole` — many-to-many; supports separation of duties
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pramana.db.base import Base
from pramana.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from pramana.db.models.assignment import Assignment, Attempt, Certificate
    from pramana.db.models.audit import AuditLog
    from pramana.db.models.course import Course, CourseVersion


# ---------------------------------------------------------------------------
# Enums for identity domain
# ---------------------------------------------------------------------------
class UserStatus:
    """Allowed values for ``User.status``."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ON_LEAVE = "on_leave"
    PSEUDONYMIZED = "pseudonymized"

    @classmethod
    def values(cls) -> list[str]:
        return [cls.ACTIVE, cls.INACTIVE, cls.ON_LEAVE, cls.PSEUDONYMIZED]


class UserType:
    """Allowed values for ``User.user_type``."""

    EMPLOYEE = "employee"
    CONTRACTOR = "contractor"

    @classmethod
    def values(cls) -> list[str]:
        return [cls.EMPLOYEE, cls.CONTRACTOR]


class RoleName:
    """Fixed system roles."""

    TRAINEE = "trainee"
    MANAGER = "manager"
    CONTENT_AUTHOR = "content_author"
    COMPLIANCE_ADMIN = "compliance_admin"
    AUDITOR = "auditor"

    @classmethod
    def values(cls) -> list[str]:
        return [
            cls.TRAINEE,
            cls.MANAGER,
            cls.CONTENT_AUTHOR,
            cls.COMPLIANCE_ADMIN,
            cls.AUDITOR,
        ]


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------
class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Customer / deployment boundary.

    Single row in v1 (``John Thomas Corporate``). Multi-tenancy is enforced
    at the application layer in v4 via Postgres Row-Level Security.
    """

    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    short_code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    users: Mapped[list[User]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class User(Base, TimestampMixin):
    """Pramana user.

    Per the resolved decisions doc:

    * Primary key is a synthetic UUID ``user_id`` — never the email.
    * Email is unique-but-mutable (people get married, change names).
    * On pseudonymization, PII fields are hashed/nulled and ``status`` is
      set to ``pseudonymized``; evidence rows (assignments, attempts,
      certificates, audit log) are preserved for SOX retention.
    """

    __tablename__ = "user_account"  # `user` is reserved in PostgreSQL

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Identity (mutable; preserved across email changes)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    user_type: Mapped[str] = mapped_column(
        SQLEnum(*UserType.values(), name="user_type"),
        nullable=False,
        default=UserType.EMPLOYEE,
    )
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        SQLEnum(*UserStatus.values(), name="user_status"),
        nullable=False,
        default=UserStatus.ACTIVE,
    )

    # SSO
    sso_subject: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        comment="OIDC `sub` claim, populated on first login.",
    )

    # Pseudonymization audit
    pseudonymized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="user_tenant_email_unique"),
        Index("ix_user_status", "status"),
        CheckConstraint(
            "(status = 'pseudonymized') = (pseudonymized_at IS NOT NULL)",
            name="pseudonymized_at_consistent",
        ),
    )

    # Relationships
    tenant: Mapped[Tenant] = relationship(back_populates="users")
    manager: Mapped[User | None] = relationship(
        remote_side="User.user_id",
        back_populates="direct_reports",
    )
    direct_reports: Mapped[list[User]] = relationship(
        back_populates="manager",
        foreign_keys=[manager_user_id],
    )
    role_assignments: Mapped[list[UserRole]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserRole.user_id",
    )
    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="user",
        foreign_keys="Assignment.user_id",
    )
    certificates: Mapped[list[Certificate]] = relationship(back_populates="user")
    authored_courses: Mapped[list[Course]] = relationship(back_populates="author")

    @property
    def display_name(self) -> str:
        """Privacy-friendly display name (first name + last initial)."""
        if self.status == UserStatus.PSEUDONYMIZED:
            return "[redacted]"
        first = (self.first_name or "").strip()
        last = (self.last_name or "").strip()
        if last:
            return f"{first} {last[:1]}.".strip()
        return first


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------
class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A system role.

    Seeded with the five fixed roles (see :class:`RoleName`). Roles are not
    user-editable in v1.
    """

    __tablename__ = "role"

    name: Mapped[str] = mapped_column(
        SQLEnum(*RoleName.values(), name="role_name"),
        nullable=False,
        unique=True,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)

    user_assignments: Mapped[list[UserRole]] = relationship(back_populates="role")


# ---------------------------------------------------------------------------
# UserRole (many-to-many)
# ---------------------------------------------------------------------------
class UserRole(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Many-to-many between :class:`User` and :class:`Role`.

    A user can hold multiple roles concurrently (e.g. ``trainee`` *and*
    ``content_author``). Separation-of-duties checks are enforced in
    application logic (a content_author cannot be assigned a course they
    authored).
    """

    __tablename__ = "user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("role.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_account.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="user_role_unique"),
    )

    user: Mapped[User] = relationship(
        back_populates="role_assignments", foreign_keys=[user_id]
    )
    role: Mapped[Role] = relationship(back_populates="user_assignments")
