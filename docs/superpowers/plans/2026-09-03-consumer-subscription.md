# Consumer Subscription & Lesson-Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a consumer self-serve mode — buy a package, watch lessons, take quizzes, and track views/completions/durations — alongside the untouched B2B compliance runtime.

**Architecture:** Seven new "consumer" tables (`package`, `package_course`, `entitlement`, `enrollment`, `play_session`, `consumer_attempt`, `consumer_attempt_answer`) plus a pure completion domain and thin async services. They reuse the shared content models (`Course`/`CourseVersion`/`Question`/`AnswerOption`), the pure grader `pramana.domain.scoring.grade_attempt`, and the `AssetUrlSigner` seam. The B2B `Assignment`/`Attempt`/`Certificate` tables and their CHECK constraints are never modified. Access is gated by a `require_course_entitlement` dependency (the consumer analog of `require_roles`).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Postgres, pytest / pytest-asyncio, Hypothesis.

**Spec:** `docs/superpowers/specs/2026-09-03-consumer-subscription-design.md`

## Global Constraints

- **Python floor:** 3.12. **pytest:** 8.x (not 9). Async services take `AsyncSession`; pure domain is I/O-free.
- **Layering:** pure logic in `pramana/domain/consumer/`, transactional shells in `pramana/services/consumer/`, ORM in `pramana/db/models/consumer.py`, HTTP in `pramana/api/`. Services raise errors from `pramana/exceptions.py`; routers never build SQL.
- **Naming-convention gotcha:** `db/base.py` prefixes `ck_<table>_` onto CHECK constraint names on BOTH create and drop. Pass the **suffix only** to `op.create_check_constraint` / `op.drop_constraint` (see the `_CK` pattern in `alembic/versions/0006_assignment_watch_progress.py`).
- **Lint/type gate:** CI runs `ruff` + `mypy` over `pramana tests scripts` (all three paths). Run `ruff format pramana tests scripts` and `ruff check pramana tests scripts` and `mypy pramana` before every commit, or CI fails. `alembic/versions` is `extend-exclude`d from ruff.
- **Migration head is `0009_audit_log_grants`.** The new migration is `0010_consumer_subscription`, `down_revision = "0009_audit_log_grants"`.
- **Consumers live under one seeded tenant** with `short_code = "consumer"` (created in migration `0010`). Consumer routes authorize by **entitlement**, never by RBAC role. Admin grants require role `compliance_admin` (`RoleName.COMPLIANCE_ADMIN`) for v1.
- **Completion rule:** an attempt is a completion iff `score_pct >= 100.0`. No cooldown, unlimited attempts, full question set each time.
- **Test DB:** DB-touching service/integration tests use the real-Postgres integration layer (`tests/integration/`, `DATABASE_URL` scratch PG). Pure-domain and seam-overridden API tests need no DB. Never run two pytest processes against the same scratch PG.

---

## File Structure

**Create:**
- `pramana/db/models/consumer.py` — the 7 ORM models.
- `pramana/domain/consumer/__init__.py`, `pramana/domain/consumer/completion.py` — pure completion rule + counter derivation.
- `pramana/services/consumer/__init__.py`, `entitlements.py`, `enrollment.py`, `play.py`, `quiz.py` — async shells.
- `pramana/api/consumer_admin.py` — admin create-consumer + grant/revoke router.
- `pramana/api/consumer.py` — consumer-facing router (me/packages/lessons/views/quiz).
- `alembic/versions/0010_consumer_subscription.py` — migration + Consumer-tenant seed.
- `scripts/recompute_enrollment_counters.py` — counter reconciliation.
- Test files listed per task.

**Modify:**
- `pramana/db/models/__init__.py` — import consumer models so `Base.metadata` sees them.
- `pramana/exceptions.py` — add `EntitlementRequiredError`.
- `pramana/api/errors.py` — map `EntitlementRequiredError` → HTTP 403.
- `pramana/api/dependencies.py` — add `get_entitlement_checker` seam + `require_course_entitlement`.
- `pramana/api/schemas.py` — consumer Pydantic schemas.
- `pramana/api/app.py` — register the two consumer routers.
- `Makefile` — `recompute-counters` target.

---

## Task 1: Consumer ORM models

**Files:**
- Create: `pramana/db/models/consumer.py`
- Modify: `pramana/db/models/__init__.py`
- Test: `tests/db/test_consumer_models_metadata.py`

**Interfaces:**
- Produces: ORM classes `Package`, `PackageCourse`, `Entitlement`, `Enrollment`, `PlaySession`, `ConsumerAttempt`, `ConsumerAttemptAnswer` (tablenames `package`, `package_course`, `entitlement`, `enrollment`, `play_session`, `consumer_attempt`, `consumer_attempt_answer`). Column names per the spec §3 and used verbatim by later tasks.

- [ ] **Step 1: Write the failing test**

```python
# tests/db/test_consumer_models_metadata.py
"""Metadata-only checks — no database needed."""
from pramana.db.base import Base
import pramana.db.models  # noqa: F401  (ensure all models are registered)


def _table(name: str):
    return Base.metadata.tables[name]


def test_all_consumer_tables_registered():
    for name in [
        "package", "package_course", "entitlement", "enrollment",
        "play_session", "consumer_attempt", "consumer_attempt_answer",
    ]:
        assert name in Base.metadata.tables


def test_entitlement_has_partial_unique_active_index():
    ent = _table("entitlement")
    partials = [
        ix for ix in ent.indexes
        if ix.dialect_options["postgresql"].get("where") is not None
    ]
    cols = [sorted(c.name for c in ix.columns) for ix in partials]
    assert ["package_id", "user_id"] in cols


def test_enrollment_unique_user_course():
    enr = _table("enrollment")
    uniques = [tuple(sorted(c.name for c in con.columns))
               for con in enr.constraints if con.__class__.__name__ == "UniqueConstraint"]
    assert ("course_id", "user_id") in uniques


def test_consumer_attempt_score_check_present():
    ca = _table("consumer_attempt")
    check_names = [c.name for c in ca.constraints if c.__class__.__name__ == "CheckConstraint"]
    assert any("score_pct" in (n or "") for n in check_names)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/db/test_consumer_models_metadata.py -v`
Expected: FAIL — `KeyError: 'package'` (tables not registered).

- [ ] **Step 3: Write the models**

```python
# pramana/db/models/consumer.py
"""Consumer-domain ORM models (self-serve subscription mode).

Parallel to the B2B assignment runtime: these tables reuse the shared content
models (Course/CourseVersion/Question/AnswerOption) but never touch the audited
Assignment machinery. See docs/superpowers/specs/2026-09-03-consumer-subscription-design.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer,
    SmallInteger, String, Text, UniqueConstraint, func,
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
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False, index=True,
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
        UUID(as_uuid=True), ForeignKey("package.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("package_id", "course_id", name="package_course_unique"),
    )


class Entitlement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "entitlement"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.user_id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("package.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    status: Mapped[str] = mapped_column(
        SQLEnum(*_ENTITLEMENT_STATUS, name="entitlement_status"),
        nullable=False, default="active",
    )
    source: Mapped[str] = mapped_column(
        SQLEnum(*_ENTITLEMENT_SOURCE, name="entitlement_source"),
        nullable=False, default="manual",
    )
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index(
            "ix_entitlement_active_unique", "user_id", "package_id",
            unique=True, postgresql_where="status = 'active'",
        ),
    )


class Enrollment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "enrollment"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_account.user_id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    entitlement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entitlement.id", ondelete="RESTRICT"),
        nullable=False,
    )
    first_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    completion_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0")
    best_score_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="enrollment_user_course_unique"),
        CheckConstraint("view_count >= 0", name="view_count_nonneg"),
        CheckConstraint("completion_count >= 0", name="completion_count_nonneg"),
    )


class PlaySession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "play_session"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enrollment.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    media_kind: Mapped[str] = mapped_column(
        SQLEnum(*_MEDIA_KIND, name="media_kind"), nullable=False, default="video")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
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
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("enrollment.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_all_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_active_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "score_pct IS NULL OR (score_pct BETWEEN 0 AND 100)", name="score_pct_range"),
        # When submitted, is_all_correct must agree with a perfect score.
        CheckConstraint(
            "submitted_at IS NULL OR (is_all_correct = (score_pct = 100))",
            name="all_correct_consistent"),
    )


class ConsumerAttemptAnswer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "consumer_attempt_answer"

    consumer_attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consumer_attempt.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("question.id", ondelete="RESTRICT"),
        nullable=False,
    )
    selected_option_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default="{}")
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "consumer_attempt_id", "question_id", name="consumer_attempt_answer_unique"),
    )
```

Then add to `pramana/db/models/__init__.py` (follow the existing import style there):

```python
from pramana.db.models.consumer import (  # noqa: F401
    ConsumerAttempt, ConsumerAttemptAnswer, Enrollment, Entitlement,
    Package, PackageCourse, PlaySession,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/db/test_consumer_models_metadata.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint, type, commit**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
git add pramana/db/models/consumer.py pramana/db/models/__init__.py tests/db/test_consumer_models_metadata.py
git commit -m "feat(consumer): ORM models for packages, entitlements, and tracking"
```

---

## Task 2: Migration 0010 + Consumer tenant seed

**Files:**
- Create: `alembic/versions/0010_consumer_subscription.py`
- Test: `tests/integration/test_consumer_migration.py`

**Interfaces:**
- Consumes: the ORM models from Task 1 (as the source of truth for column shapes).
- Produces: a migration that upgrades `0009` → `0010`, creating the 7 tables + a `tenant` row `short_code="consumer"`.

- [ ] **Step 1: Write the failing test** (integration — real PG)

```python
# tests/integration/test_consumer_migration.py
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def test_consumer_tables_and_seed_present(db_session):
    # (db_session is the existing integration fixture bound to the migrated scratch DB)
    for table in ["package", "entitlement", "enrollment", "play_session",
                  "consumer_attempt", "consumer_attempt_answer", "package_course"]:
        got = await db_session.execute(text(f"SELECT to_regclass('{table}')"))
        assert got.scalar() is not None, f"{table} missing"

    seed = await db_session.execute(
        text("SELECT count(*) FROM tenant WHERE short_code = 'consumer'"))
    assert seed.scalar() == 1
```

> Match the existing integration fixture names in `tests/integration/conftest.py`; if the session fixture is named differently there, use that name.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_consumer_migration.py -v`
Expected: FAIL — `to_regclass` returns None (tables not created).

- [ ] **Step 3: Write the migration**

```python
# alembic/versions/0010_consumer_subscription.py
"""Consumer subscription: packages, entitlements, and lesson tracking.

Revision ID: 0010_consumer_subscription
Revises: 0009_audit_log_grants
Create Date: 2026-09-03 00:00:00
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0010_consumer_subscription"
down_revision: str | None = "0009_audit_log_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "package",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("slug", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_key", sa.String(500), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="usd"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_package_slug_unique"),
    )
    op.create_index("ix_package_tenant_id", "package", ["tenant_id"])
    op.create_check_constraint(
        "price_cents_nonneg", "package", "price_cents IS NULL OR price_cents >= 0")

    op.create_table(
        "package_course",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("package_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("package.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("course.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("package_id", "course_id", name="uq_package_course_unique"),
    )
    op.create_index("ix_package_course_package_id", "package_course", ["package_id"])
    op.create_index("ix_package_course_course_id", "package_course", ["course_id"])

    op.create_table(
        "entitlement",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("user_account.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("package_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("package.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.Enum("active", "revoked", "expired", name="entitlement_status"),
                  nullable=False, server_default="active"),
        sa.Column("source", sa.Enum("manual", "stripe", name="entitlement_source"),
                  nullable=False, server_default="manual"),
        sa.Column("external_ref", sa.String(255), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("granted_by_user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("user_account.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_entitlement_tenant_id", "entitlement", ["tenant_id"])
    op.create_index("ix_entitlement_user_id", "entitlement", ["user_id"])
    op.create_index("ix_entitlement_package_id", "entitlement", ["package_id"])
    op.create_index(
        "ix_entitlement_active_unique", "entitlement", ["user_id", "package_id"],
        unique=True, postgresql_where=sa.text("status = 'active'"))

    op.create_table(
        "enrollment",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("user_account.user_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("course_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("course.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("entitlement_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("entitlement.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("first_accessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_score_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "course_id", name="uq_enrollment_user_course_unique"),
    )
    op.create_index("ix_enrollment_tenant_id", "enrollment", ["tenant_id"])
    op.create_index("ix_enrollment_user_id", "enrollment", ["user_id"])
    op.create_index("ix_enrollment_course_id", "enrollment", ["course_id"])
    op.create_check_constraint("view_count_nonneg", "enrollment", "view_count >= 0")
    op.create_check_constraint("completion_count_nonneg", "enrollment", "completion_count >= 0")

    op.create_table(
        "play_session",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("enrollment_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("enrollment.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_version_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("course_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("media_kind", sa.Enum("video", "audio", name="media_kind"),
                  nullable=False, server_default="video"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_watched_pct", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_play_session_tenant_id", "play_session", ["tenant_id"])
    op.create_index("ix_play_session_enrollment_id", "play_session", ["enrollment_id"])
    op.create_check_constraint(
        "max_watched_pct_range", "play_session", "max_watched_pct BETWEEN 0 AND 100")
    op.create_check_constraint(
        "duration_seconds_nonneg", "play_session", "duration_seconds >= 0")

    op.create_table(
        "consumer_attempt",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("enrollment_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("enrollment.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_version_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("course_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score_pct", sa.Float(), nullable=True),
        sa.Column("is_all_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_active_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_consumer_attempt_tenant_id", "consumer_attempt", ["tenant_id"])
    op.create_index("ix_consumer_attempt_enrollment_id", "consumer_attempt", ["enrollment_id"])
    op.create_check_constraint(
        "score_pct_range", "consumer_attempt",
        "score_pct IS NULL OR (score_pct BETWEEN 0 AND 100)")
    op.create_check_constraint(
        "all_correct_consistent", "consumer_attempt",
        "submitted_at IS NULL OR (is_all_correct = (score_pct = 100))")

    op.create_table(
        "consumer_attempt_answer",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer_attempt_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("consumer_attempt.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", pg.UUID(as_uuid=True),
                  sa.ForeignKey("question.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("selected_option_ids", pg.ARRAY(pg.UUID(as_uuid=True)),
                  nullable=False, server_default="{}"),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "consumer_attempt_id", "question_id", name="uq_consumer_attempt_answer_unique"),
    )
    op.create_index(
        "ix_consumer_attempt_answer_attempt_id", "consumer_attempt_answer",
        ["consumer_attempt_id"])

    # Seed the single Consumer tenant.
    op.execute(
        sa.text(
            "INSERT INTO tenant (id, name, short_code, created_at, updated_at) "
            "VALUES (:id, 'Consumer', 'consumer', now(), now())"
        ).bindparams(id=str(uuid.uuid4()))
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM tenant WHERE short_code = 'consumer'"))
    for tbl in ["consumer_attempt_answer", "consumer_attempt", "play_session",
                "enrollment", "entitlement", "package_course", "package"]:
        op.drop_table(tbl)
    for enum in ["media_kind", "entitlement_source", "entitlement_status"]:
        op.execute(sa.text(f"DROP TYPE IF EXISTS {enum}"))
```

> Naming note: for `UniqueConstraint`s created inside `create_table`, pass the fully-qualified `uq_...` name (the naming convention does not auto-prefix names passed to `create_table`). For standalone `create_check_constraint`, pass the **suffix only** (the convention prefixes `ck_<table>_`). This mirrors migration `0006`.

- [ ] **Step 4: Run migration + test to verify pass**

```bash
alembic upgrade head
pytest tests/integration/test_consumer_migration.py -v
```
Expected: PASS.

- [ ] **Step 5: Round-trip downgrade check, then commit**

```bash
alembic downgrade -1 && alembic upgrade head
git add alembic/versions/0010_consumer_subscription.py tests/integration/test_consumer_migration.py
git commit -m "feat(consumer): migration 0010 — consumer tables + Consumer tenant seed"
```

---

## Task 3: Pure completion domain

**Files:**
- Create: `pramana/domain/consumer/__init__.py` (empty), `pramana/domain/consumer/completion.py`
- Test: `tests/domain/test_consumer_completion.py`

**Interfaces:**
- Produces:
  - `is_all_correct(score_pct: float) -> bool`
  - `EnrollmentCounters` (frozen dataclass: `view_count: int`, `completion_count: int`, `best_score_pct: float | None`)
  - `derive_counters(*, num_views: int, attempt_scores: Sequence[float]) -> EnrollmentCounters`

- [ ] **Step 1: Write the failing test**

```python
# tests/domain/test_consumer_completion.py
from pramana.domain.consumer.completion import (
    EnrollmentCounters, derive_counters, is_all_correct,
)


def test_is_all_correct_only_at_100():
    assert is_all_correct(100.0) is True
    assert is_all_correct(99.9) is False
    assert is_all_correct(0.0) is False


def test_derive_counters_counts_perfect_scores_and_best():
    got = derive_counters(num_views=3, attempt_scores=[100.0, 80.0, 100.0, 60.0])
    assert got == EnrollmentCounters(view_count=3, completion_count=2, best_score_pct=100.0)


def test_derive_counters_empty_scores():
    got = derive_counters(num_views=0, attempt_scores=[])
    assert got == EnrollmentCounters(view_count=0, completion_count=0, best_score_pct=None)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/domain/test_consumer_completion.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# pramana/domain/consumer/completion.py
"""Consumer completion rule + counter derivation — pure, no I/O.

A consumer 'completion' is a single quiz attempt at a perfect score. This is
deliberately a stricter bar than the B2B pass threshold (which lives in
pramana.config.Settings.default_pass_threshold_pct).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_PERFECT_SCORE = 100.0


def is_all_correct(score_pct: float) -> bool:
    """True iff every question was answered correctly (a perfect score)."""
    return score_pct >= _PERFECT_SCORE


@dataclass(frozen=True, slots=True)
class EnrollmentCounters:
    view_count: int
    completion_count: int
    best_score_pct: float | None


def derive_counters(*, num_views: int, attempt_scores: Sequence[float]) -> EnrollmentCounters:
    """Reduce raw event history to the denormalized enrollment counters."""
    completion_count = sum(1 for s in attempt_scores if is_all_correct(s))
    best = max(attempt_scores) if attempt_scores else None
    return EnrollmentCounters(
        view_count=num_views, completion_count=completion_count, best_score_pct=best)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/domain/test_consumer_completion.py -v`
Expected: PASS.

- [ ] **Step 5: Lint, type, commit**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
git add pramana/domain/consumer tests/domain/test_consumer_completion.py
git commit -m "feat(consumer): pure completion rule and counter derivation"
```

---

## Task 4: EntitlementRequiredError + HTTP mapping

**Files:**
- Modify: `pramana/exceptions.py`, `pramana/api/errors.py`
- Test: `tests/api/test_consumer_error_mapping.py`

**Interfaces:**
- Produces: `EntitlementRequiredError` (subclass of the same base the other domain errors use, e.g. `AuthorizationError`'s base) → maps to HTTP **403**.

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_consumer_error_mapping.py
from pramana.exceptions import EntitlementRequiredError


def test_entitlement_required_is_a_domain_error():
    err = EntitlementRequiredError("no entitlement", context={"course_id": "x"})
    assert err.context == {"course_id": "x"}


def test_entitlement_required_maps_to_403():
    from pramana.api.errors import status_code_for  # existing helper; adjust name if different
    assert status_code_for(EntitlementRequiredError("x")) == 403
```

> Open `pramana/api/errors.py` first and use its actual exception→status mechanism (a dict, a match, or a helper). If it has no single `status_code_for`, add the mapping wherever the other `AuthorizationError`→403 entry lives and assert via a `TestClient` 403 instead.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/api/test_consumer_error_mapping.py -v`
Expected: FAIL — `ImportError: cannot import name 'EntitlementRequiredError'`.

- [ ] **Step 3: Implement**

In `pramana/exceptions.py`, alongside `AuthorizationError`:

```python
class EntitlementRequiredError(AuthorizationError):
    """The caller has no active entitlement covering the requested course."""
```

In `pramana/api/errors.py`, register `EntitlementRequiredError` → 403 in the same table/handler that maps `AuthorizationError` (subclassing `AuthorizationError` may already yield 403 — if so, this step only adds an explicit entry + test coverage).

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/api/test_consumer_error_mapping.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
git add pramana/exceptions.py pramana/api/errors.py tests/api/test_consumer_error_mapping.py
git commit -m "feat(consumer): EntitlementRequiredError mapped to HTTP 403"
```

---

## Task 5: Entitlements service

**Files:**
- Create: `pramana/services/consumer/__init__.py` (empty), `pramana/services/consumer/entitlements.py`
- Test: `tests/integration/test_consumer_entitlements.py`

**Interfaces:**
- Produces (all async, all take `session: AsyncSession` first):
  - `get_consumer_tenant_id(session) -> uuid.UUID` — looks up the `short_code="consumer"` tenant.
  - `create_consumer_user(session, *, tenant_id, email, first_name, last_name, now) -> User`
  - `grant_package(session, *, tenant_id, user_id, package_id, granted_by_user_id, now, source="manual", external_ref=None, expires_at=None) -> Entitlement` — idempotent: returns the existing active entitlement if one exists for `(user_id, package_id)`; appends `entitlement.granted` to the audit chain on create.
  - `revoke_entitlement(session, *, tenant_id, entitlement_id, revoked_by_user_id, now, reason=None) -> Entitlement` — sets status `revoked`, appends `entitlement.revoked`.
  - `has_active_entitlement_for_course(session, *, tenant_id, user_id, course_id, now) -> bool` — true iff an active, unexpired entitlement covers a package containing `course_id`.

- [ ] **Step 1: Write the failing test** (integration)

```python
# tests/integration/test_consumer_entitlements.py
import pytest
from pramana.services.consumer import entitlements as ent

pytestmark = pytest.mark.integration


async def test_grant_is_idempotent_and_gates_by_course(db_session, make_course, utcnow):
    # make_course: an integration helper that inserts a Course (+active version) and
    # returns it. If none exists yet, add one to tests/integration/conftest.py.
    tenant_id = await ent.get_consumer_tenant_id(db_session)
    course = await make_course(tenant_id=tenant_id)
    user = await ent.create_consumer_user(
        db_session, tenant_id=tenant_id, email="a@example.com",
        first_name="Ann", last_name="Lee", now=utcnow)

    # A package containing the course:
    from pramana.db.models.consumer import Package, PackageCourse
    pkg = Package(tenant_id=tenant_id, slug="sox", title="SOX", is_published=True)
    db_session.add(pkg); await db_session.flush()
    db_session.add(PackageCourse(package_id=pkg.id, course_id=course.id))
    await db_session.flush()

    assert await ent.has_active_entitlement_for_course(
        db_session, tenant_id=tenant_id, user_id=user.user_id,
        course_id=course.id, now=utcnow) is False

    e1 = await ent.grant_package(
        db_session, tenant_id=tenant_id, user_id=user.user_id, package_id=pkg.id,
        granted_by_user_id=None, now=utcnow)
    e2 = await ent.grant_package(
        db_session, tenant_id=tenant_id, user_id=user.user_id, package_id=pkg.id,
        granted_by_user_id=None, now=utcnow)
    assert e1.id == e2.id  # idempotent

    assert await ent.has_active_entitlement_for_course(
        db_session, tenant_id=tenant_id, user_id=user.user_id,
        course_id=course.id, now=utcnow) is True

    await ent.revoke_entitlement(
        db_session, tenant_id=tenant_id, entitlement_id=e1.id,
        revoked_by_user_id=None, now=utcnow)
    assert await ent.has_active_entitlement_for_course(
        db_session, tenant_id=tenant_id, user_id=user.user_id,
        course_id=course.id, now=utcnow) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/integration/test_consumer_entitlements.py -v`
Expected: FAIL — module not found / attribute errors.

- [ ] **Step 3: Implement**

```python
# pramana/services/consumer/entitlements.py
"""Entitlement service — the consumer access grant + check.

This is the single seam a future payment webhook calls: manual and paid grants
differ only by ``source``/``external_ref``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.consumer import Entitlement, Package, PackageCourse
from pramana.db.models.identity import Tenant, User, UserStatus, UserType
from pramana.exceptions import NotFoundError
from pramana.services.audit import append_audit


async def get_consumer_tenant_id(session: AsyncSession) -> uuid.UUID:
    tid = (
        await session.execute(select(Tenant.id).where(Tenant.short_code == "consumer"))
    ).scalar_one_or_none()
    if tid is None:
        raise NotFoundError("consumer tenant not seeded")
    return tid


async def create_consumer_user(
    session: AsyncSession, *, tenant_id: uuid.UUID, email: str,
    first_name: str | None, last_name: str | None, now: datetime,
) -> User:
    user = User(
        tenant_id=tenant_id, email=email, first_name=first_name, last_name=last_name,
        user_type=UserType.EMPLOYEE, status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()
    await append_audit(
        session, tenant_id=tenant_id, actor_user_id=None,
        entity_type="user", entity_id=str(user.user_id),
        event_type="user.consumer_created", payload={"email": email}, occurred_at=now)
    return user


async def grant_package(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
    package_id: uuid.UUID, granted_by_user_id: uuid.UUID | None, now: datetime,
    source: str = "manual", external_ref: str | None = None,
    expires_at: datetime | None = None,
) -> Entitlement:
    existing = (
        await session.execute(
            select(Entitlement).where(
                Entitlement.user_id == user_id,
                Entitlement.package_id == package_id,
                Entitlement.status == "active",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    ent = Entitlement(
        tenant_id=tenant_id, user_id=user_id, package_id=package_id, status="active",
        source=source, external_ref=external_ref, granted_by_user_id=granted_by_user_id,
        granted_at=now, expires_at=expires_at,
    )
    session.add(ent)
    await session.flush()
    await append_audit(
        session, tenant_id=tenant_id, actor_user_id=granted_by_user_id,
        entity_type="entitlement", entity_id=str(ent.id),
        event_type="entitlement.granted",
        payload={"user_id": str(user_id), "package_id": str(package_id), "source": source},
        occurred_at=now)
    return ent


async def revoke_entitlement(
    session: AsyncSession, *, tenant_id: uuid.UUID, entitlement_id: uuid.UUID,
    revoked_by_user_id: uuid.UUID | None, now: datetime, reason: str | None = None,
) -> Entitlement:
    ent = await session.get(Entitlement, entitlement_id)
    if ent is None or ent.tenant_id != tenant_id:
        raise NotFoundError("entitlement not found", context={"entitlement_id": str(entitlement_id)})
    if ent.status == "active":
        ent.status = "revoked"
        ent.revoked_at = now
        ent.revoked_reason = reason
        await append_audit(
            session, tenant_id=tenant_id, actor_user_id=revoked_by_user_id,
            entity_type="entitlement", entity_id=str(ent.id),
            event_type="entitlement.revoked", payload={"reason": reason}, occurred_at=now)
    return ent


async def has_active_entitlement_for_course(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
    course_id: uuid.UUID, now: datetime,
) -> bool:
    covered = (
        select(Entitlement.id)
        .join(PackageCourse, PackageCourse.package_id == Entitlement.package_id)
        .where(
            Entitlement.tenant_id == tenant_id,
            Entitlement.user_id == user_id,
            Entitlement.status == "active",
            or_(Entitlement.expires_at.is_(None), Entitlement.expires_at > now),
            PackageCourse.course_id == course_id,
        )
    )
    return bool((await session.execute(select(exists(covered)))).scalar())
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/integration/test_consumer_entitlements.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
git add pramana/services/consumer tests/integration/test_consumer_entitlements.py
git commit -m "feat(consumer): entitlement grant/revoke/check service"
```

---

## Task 6: Enrollment service (lazy create + recompute)

**Files:**
- Create: `pramana/services/consumer/enrollment.py`
- Test: `tests/integration/test_consumer_enrollment.py`

**Interfaces:**
- Consumes: `pramana.domain.consumer.completion.derive_counters` (Task 3); `has_active_entitlement_for_course` is NOT called here (access is checked at the router).
- Produces:
  - `get_or_create_enrollment(session, *, tenant_id, user_id, course_id, entitlement_id, now) -> Enrollment` — idempotent on `(user_id, course_id)`; sets `first_accessed_at`/`last_accessed_at` on create.
  - `recompute_counters(session, *, enrollment_id) -> Enrollment` — recomputes `view_count`/`completion_count`/`best_score_pct` from `play_session` + submitted `consumer_attempt` rows via `derive_counters`, writes them back, returns the enrollment.

- [ ] **Step 1: Write the failing test** (integration)

```python
# tests/integration/test_consumer_enrollment.py
import pytest
from pramana.services.consumer import enrollment as enr

pytestmark = pytest.mark.integration


async def test_get_or_create_is_idempotent(db_session, consumer_setup, utcnow):
    # consumer_setup: helper returning (tenant_id, user, course, entitlement)
    s = await consumer_setup(db_session)
    e1 = await enr.get_or_create_enrollment(
        db_session, tenant_id=s.tenant_id, user_id=s.user.user_id,
        course_id=s.course.id, entitlement_id=s.entitlement.id, now=utcnow)
    e2 = await enr.get_or_create_enrollment(
        db_session, tenant_id=s.tenant_id, user_id=s.user.user_id,
        course_id=s.course.id, entitlement_id=s.entitlement.id, now=utcnow)
    assert e1.id == e2.id


async def test_recompute_counters_matches_events(db_session, consumer_setup, utcnow):
    s = await consumer_setup(db_session)
    e = await enr.get_or_create_enrollment(
        db_session, tenant_id=s.tenant_id, user_id=s.user.user_id,
        course_id=s.course.id, entitlement_id=s.entitlement.id, now=utcnow)

    from pramana.db.models.consumer import PlaySession, ConsumerAttempt
    db_session.add(PlaySession(
        tenant_id=s.tenant_id, enrollment_id=e.id,
        course_version_id=s.course.current_version_id, duration_seconds=10, max_watched_pct=100))
    db_session.add(ConsumerAttempt(
        tenant_id=s.tenant_id, enrollment_id=e.id,
        course_version_id=s.course.current_version_id, submitted_at=utcnow,
        score_pct=100.0, is_all_correct=True, question_count=3, correct_count=3))
    db_session.add(ConsumerAttempt(
        tenant_id=s.tenant_id, enrollment_id=e.id,
        course_version_id=s.course.current_version_id, submitted_at=utcnow,
        score_pct=66.7, is_all_correct=False, question_count=3, correct_count=2))
    await db_session.flush()

    got = await enr.recompute_counters(db_session, enrollment_id=e.id)
    assert got.view_count == 1
    assert got.completion_count == 1
    assert got.best_score_pct == 100.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/integration/test_consumer_enrollment.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# pramana/services/consumer/enrollment.py
"""Enrollment service — per-(user, lesson) progress anchor.

Access is NOT granted here; enrollment is progress state. The router checks the
live entitlement before calling in.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.consumer import ConsumerAttempt, Enrollment, PlaySession
from pramana.domain.consumer.completion import derive_counters
from pramana.exceptions import NotFoundError


async def get_or_create_enrollment(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
    course_id: uuid.UUID, entitlement_id: uuid.UUID, now: datetime,
) -> Enrollment:
    existing = (
        await session.execute(
            select(Enrollment).where(
                Enrollment.user_id == user_id, Enrollment.course_id == course_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.last_accessed_at = now
        return existing

    enrollment = Enrollment(
        tenant_id=tenant_id, user_id=user_id, course_id=course_id,
        entitlement_id=entitlement_id, first_accessed_at=now, last_accessed_at=now)
    session.add(enrollment)
    await session.flush()
    return enrollment


async def recompute_counters(session: AsyncSession, *, enrollment_id: uuid.UUID) -> Enrollment:
    enrollment = await session.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("enrollment not found", context={"enrollment_id": str(enrollment_id)})

    num_views = (
        await session.execute(
            select(func.count()).select_from(PlaySession).where(
                PlaySession.enrollment_id == enrollment_id))
    ).scalar_one()
    scores = list(
        (
            await session.execute(
                select(ConsumerAttempt.score_pct).where(
                    ConsumerAttempt.enrollment_id == enrollment_id,
                    ConsumerAttempt.submitted_at.is_not(None),
                    ConsumerAttempt.score_pct.is_not(None),
                )
            )
        ).scalars()
    )
    counters = derive_counters(num_views=num_views, attempt_scores=scores)
    enrollment.view_count = counters.view_count
    enrollment.completion_count = counters.completion_count
    enrollment.best_score_pct = counters.best_score_pct
    return enrollment
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/integration/test_consumer_enrollment.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
git add pramana/services/consumer/enrollment.py tests/integration/test_consumer_enrollment.py
git commit -m "feat(consumer): enrollment lazy-create + counter recompute"
```

---

## Task 7: Play service (start/end view)

**Files:**
- Create: `pramana/services/consumer/play.py`
- Test: `tests/integration/test_consumer_play.py`

**Interfaces:**
- Consumes: `get_or_create_enrollment` (Task 6); the `AssetUrlSigner` seam (`pramana.services.player.AssetUrlSigner`, `null_asset_signer`).
- Produces:
  - `PlaySessionManifest` (frozen dataclass: `play_session_id: uuid.UUID`, `enrollment_id: uuid.UUID`, `course_version_id: uuid.UUID`, `media_url: str | None`, `media_kind: str`, `min_watch_pct: int`).
  - `start_view(session, *, tenant_id, user_id, course_id, entitlement_id, media_kind, now, sign_asset=null_asset_signer) -> PlaySessionManifest` — lazily creates the enrollment, opens a `play_session`, returns the signed media URL from the active course version.
  - `end_view(session, *, tenant_id, user_id, play_session_id, duration_seconds, max_watched_pct, now) -> None` — sets `ended_at`/`duration`/`pct`, bumps `enrollment.view_count += 1` and `last_accessed_at`. Idempotent: a play_session already ended is left unchanged (no double count).

- [ ] **Step 1: Write the failing test** (integration)

```python
# tests/integration/test_consumer_play.py
import pytest
from pramana.services.consumer import play

pytestmark = pytest.mark.integration


async def test_start_then_end_view_bumps_view_count_once(db_session, consumer_setup, utcnow):
    s = await consumer_setup(db_session)
    manifest = await play.start_view(
        db_session, tenant_id=s.tenant_id, user_id=s.user.user_id, course_id=s.course.id,
        entitlement_id=s.entitlement.id, media_kind="video", now=utcnow)
    assert manifest.course_version_id == s.course.current_version_id

    await play.end_view(
        db_session, tenant_id=s.tenant_id, user_id=s.user.user_id,
        play_session_id=manifest.play_session_id, duration_seconds=42,
        max_watched_pct=100, now=utcnow)
    # ending the same session again must not double-count
    await play.end_view(
        db_session, tenant_id=s.tenant_id, user_id=s.user.user_id,
        play_session_id=manifest.play_session_id, duration_seconds=42,
        max_watched_pct=100, now=utcnow)

    from pramana.db.models.consumer import Enrollment
    from sqlalchemy import select
    enr = (await db_session.execute(
        select(Enrollment).where(Enrollment.id == manifest.enrollment_id))).scalar_one()
    assert enr.view_count == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/integration/test_consumer_play.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# pramana/services/consumer/play.py
"""Play service — opens/closes a lesson view (the '# times viewed' event)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.consumer import Enrollment, PlaySession
from pramana.db.models.course import Course, CourseVersion
from pramana.exceptions import NotFoundError, ValidationError
from pramana.services.consumer.enrollment import get_or_create_enrollment
from pramana.services.player import AssetUrlSigner, null_asset_signer


@dataclass(frozen=True, slots=True)
class PlaySessionManifest:
    play_session_id: uuid.UUID
    enrollment_id: uuid.UUID
    course_version_id: uuid.UUID
    media_url: str | None
    media_kind: str
    min_watch_pct: int


async def start_view(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
    course_id: uuid.UUID, entitlement_id: uuid.UUID, media_kind: str, now: datetime,
    sign_asset: AssetUrlSigner = null_asset_signer,
) -> PlaySessionManifest:
    course = await session.get(Course, course_id)
    if course is None or course.current_version_id is None:
        raise NotFoundError("course has no active version", context={"course_id": str(course_id)})
    version = await session.get(CourseVersion, course.current_version_id)
    if version is None:
        raise NotFoundError("course version not found")

    enrollment = await get_or_create_enrollment(
        session, tenant_id=tenant_id, user_id=user_id, course_id=course_id,
        entitlement_id=entitlement_id, now=now)

    ps = PlaySession(
        tenant_id=tenant_id, enrollment_id=enrollment.id, course_version_id=version.id,
        media_kind=media_kind, started_at=now)
    session.add(ps)
    await session.flush()
    return PlaySessionManifest(
        play_session_id=ps.id, enrollment_id=enrollment.id, course_version_id=version.id,
        media_url=sign_asset(version.video_asset_id), media_kind=media_kind,
        min_watch_pct=version.min_watch_pct)


async def end_view(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
    play_session_id: uuid.UUID, duration_seconds: int, max_watched_pct: int, now: datetime,
) -> None:
    if not (0 <= max_watched_pct <= 100):
        raise ValidationError("max_watched_pct out of range")
    ps = await session.get(PlaySession, play_session_id)
    if ps is None or ps.tenant_id != tenant_id:
        raise NotFoundError("play session not found")
    if ps.ended_at is not None:
        return  # idempotent: already closed, don't double-count
    ps.ended_at = now
    ps.duration_seconds = duration_seconds
    ps.max_watched_pct = max_watched_pct

    enrollment = await session.get(Enrollment, ps.enrollment_id)
    if enrollment is not None:
        enrollment.view_count += 1
        enrollment.last_accessed_at = now
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/integration/test_consumer_play.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
git add pramana/services/consumer/play.py tests/integration/test_consumer_play.py
git commit -m "feat(consumer): play-session start/end with single view count"
```

---

## Task 8: Quiz service (start/submit, grade)

**Files:**
- Create: `pramana/services/consumer/quiz.py`
- Test: `tests/integration/test_consumer_quiz.py`

**Interfaces:**
- Consumes: `grade_attempt`, `GradedQuestion` from `pramana.domain.scoring`; `is_all_correct` from `pramana.domain.consumer.completion`; `get_or_create_enrollment`.
- Produces:
  - `QuizQuestion` (frozen dataclass: `question_id: uuid.UUID`, `question_text: str`, `question_type: str`, `options: tuple[QuizOption, ...]`) and `QuizOption` (`option_id: uuid.UUID`, `option_text: str`) — **no `is_correct` leaked**.
  - `QuizForm` (frozen dataclass: `attempt_id: uuid.UUID`, `course_version_id: uuid.UUID`, `questions: tuple[QuizQuestion, ...]`).
  - `QuizResult` (frozen dataclass: `attempt_id: uuid.UUID`, `score_pct: float`, `is_all_correct: bool`, `correct_count: int`, `question_count: int`).
  - `start_quiz(session, *, tenant_id, user_id, course_id, entitlement_id, now) -> QuizForm`
  - `submit_quiz(session, *, tenant_id, user_id, attempt_id, answers, now) -> QuizResult` where `answers: Mapping[uuid.UUID, list[uuid.UUID]]`. Grades, sets `score_pct`/`is_all_correct`/`correct_count`, writes `ConsumerAttemptAnswer` rows, and if `is_all_correct` bumps `enrollment.completion_count += 1`; updates `enrollment.best_score_pct`.

- [ ] **Step 1: Write the failing test** (integration)

```python
# tests/integration/test_consumer_quiz.py
import pytest
from pramana.services.consumer import quiz

pytestmark = pytest.mark.integration


async def test_perfect_submission_counts_a_completion(db_session, consumer_setup, utcnow):
    s = await consumer_setup(db_session)  # course has a version with graded questions
    form = await quiz.start_quiz(
        db_session, tenant_id=s.tenant_id, user_id=s.user.user_id,
        course_id=s.course.id, entitlement_id=s.entitlement.id, now=utcnow)
    assert form.questions  # non-empty
    # answer every question with its correct option(s) — consumer_setup exposes them
    answers = {q.question_id: s.correct_options[q.question_id] for q in form.questions}

    result = await quiz.submit_quiz(
        db_session, tenant_id=s.tenant_id, user_id=s.user.user_id,
        attempt_id=form.attempt_id, answers=answers, now=utcnow)
    assert result.is_all_correct is True
    assert result.score_pct == 100.0

    from pramana.db.models.consumer import Enrollment
    from sqlalchemy import select
    enr = (await db_session.execute(
        select(Enrollment).where(Enrollment.user_id == s.user.user_id,
                                 Enrollment.course_id == s.course.id))).scalar_one()
    assert enr.completion_count == 1
    assert enr.best_score_pct == 100.0


async def test_options_do_not_leak_correctness(db_session, consumer_setup, utcnow):
    s = await consumer_setup(db_session)
    form = await quiz.start_quiz(
        db_session, tenant_id=s.tenant_id, user_id=s.user.user_id,
        course_id=s.course.id, entitlement_id=s.entitlement.id, now=utcnow)
    for q in form.questions:
        for opt in q.options:
            assert not hasattr(opt, "is_correct")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/integration/test_consumer_quiz.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# pramana/services/consumer/quiz.py
"""Quiz service — consumer quiz sitting. Reuses the pure grader (domain.scoring).

Consumer rules: unlimited attempts, no cooldown, always the full active-version
question set. A completion is a submission at 100%.
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pramana.db.models.consumer import (
    ConsumerAttempt, ConsumerAttemptAnswer, Enrollment)
from pramana.db.models.course import AnswerOption, Course, CourseVersion, Question
from pramana.domain.consumer.completion import is_all_correct
from pramana.domain.scoring import GradedQuestion, grade_attempt
from pramana.exceptions import NotFoundError, ValidationError
from pramana.services.consumer.enrollment import get_or_create_enrollment


@dataclass(frozen=True, slots=True)
class QuizOption:
    option_id: uuid.UUID
    option_text: str


@dataclass(frozen=True, slots=True)
class QuizQuestion:
    question_id: uuid.UUID
    question_text: str
    question_type: str
    options: tuple[QuizOption, ...]


@dataclass(frozen=True, slots=True)
class QuizForm:
    attempt_id: uuid.UUID
    course_version_id: uuid.UUID
    questions: tuple[QuizQuestion, ...]


@dataclass(frozen=True, slots=True)
class QuizResult:
    attempt_id: uuid.UUID
    score_pct: float
    is_all_correct: bool
    correct_count: int
    question_count: int


async def _load_version_questions(
    session: AsyncSession, course_version_id: uuid.UUID
) -> list[Question]:
    return list(
        (
            await session.execute(
                select(Question)
                .where(Question.course_version_id == course_version_id)
                .options(selectinload(Question.options))
                .order_by(Question.display_order)
            )
        ).scalars()
    )


async def start_quiz(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
    course_id: uuid.UUID, entitlement_id: uuid.UUID, now: datetime,
) -> QuizForm:
    course = await session.get(Course, course_id)
    if course is None or course.current_version_id is None:
        raise NotFoundError("course has no active version", context={"course_id": str(course_id)})
    questions = await _load_version_questions(session, course.current_version_id)
    if not questions:
        raise ValidationError("course version has no questions")

    enrollment = await get_or_create_enrollment(
        session, tenant_id=tenant_id, user_id=user_id, course_id=course_id,
        entitlement_id=entitlement_id, now=now)

    attempt = ConsumerAttempt(
        tenant_id=tenant_id, enrollment_id=enrollment.id,
        course_version_id=course.current_version_id, started_at=now,
        question_count=len(questions))
    session.add(attempt)
    await session.flush()

    return QuizForm(
        attempt_id=attempt.id,
        course_version_id=course.current_version_id,
        questions=tuple(
            QuizQuestion(
                question_id=q.id, question_text=q.question_text,
                question_type=q.question_type,
                options=tuple(QuizOption(option_id=o.id, option_text=o.option_text)
                              for o in q.options),
            )
            for q in questions
        ),
    )


async def submit_quiz(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
    attempt_id: uuid.UUID, answers: Mapping[uuid.UUID, list[uuid.UUID]], now: datetime,
) -> QuizResult:
    attempt = await session.get(ConsumerAttempt, attempt_id)
    if attempt is None or attempt.tenant_id != tenant_id:
        raise NotFoundError("attempt not found", context={"attempt_id": str(attempt_id)})
    if attempt.submitted_at is not None:
        raise ValidationError("attempt already submitted")

    questions = await _load_version_questions(session, attempt.course_version_id)
    graded = [
        GradedQuestion(
            question_id=q.id, weight=q.weight,
            correct_option_ids=frozenset(o.id for o in q.options if o.is_correct))
        for q in questions
    ]
    result = grade_attempt(graded, {qid: opts for qid, opts in answers.items()})

    correct_ids = {r.question_id for r in result.per_question if r.is_correct}
    for q in questions:
        session.add(ConsumerAttemptAnswer(
            consumer_attempt_id=attempt.id, question_id=q.id,
            selected_option_ids=list(answers.get(q.id, [])),
            is_correct=q.id in correct_ids, answered_at=now))

    attempt.submitted_at = now
    attempt.score_pct = result.score_pct
    attempt.correct_count = len(correct_ids)
    attempt.is_all_correct = is_all_correct(result.score_pct)

    enrollment = await session.get(Enrollment, attempt.enrollment_id)
    if enrollment is not None:
        if attempt.is_all_correct:
            enrollment.completion_count += 1
        if enrollment.best_score_pct is None or result.score_pct > enrollment.best_score_pct:
            enrollment.best_score_pct = result.score_pct
        enrollment.last_accessed_at = now

    return QuizResult(
        attempt_id=attempt.id, score_pct=result.score_pct,
        is_all_correct=attempt.is_all_correct, correct_count=len(correct_ids),
        question_count=len(questions))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/integration/test_consumer_quiz.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
git add pramana/services/consumer/quiz.py tests/integration/test_consumer_quiz.py
git commit -m "feat(consumer): quiz start/submit reusing the pure grader"
```

---

## Task 9: Entitlement gate dependency

**Files:**
- Modify: `pramana/api/dependencies.py`
- Test: `tests/api/test_require_entitlement.py`

**Interfaces:**
- Consumes: `has_active_entitlement_for_course` (Task 5).
- Produces:
  - `EntitlementChecker` type alias = `Callable[..., Awaitable[bool]]`.
  - `get_entitlement_checker() -> EntitlementChecker` — the injectable seam (default returns `has_active_entitlement_for_course`); tests override it via `app.dependency_overrides`.
  - `require_course_entitlement` — an async dependency that reads `course_id` from the path, the `Principal` from `get_principal`, the session from `get_db_session`, and the checker from `get_entitlement_checker`; raises `EntitlementRequiredError` on absence, else returns the `Principal`.

- [ ] **Step 1: Write the failing test** (no DB — checker overridden)

```python
# tests/api/test_require_entitlement.py
import uuid
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from pramana.api.dependencies import (
    get_entitlement_checker, get_principal, require_course_entitlement)
from pramana.services.auth import Principal


def _app_with_gate(has_entitlement: bool) -> FastAPI:
    app = FastAPI()

    @app.get("/lessons/{course_id}/probe", dependencies=[Depends(require_course_entitlement)])
    async def probe(course_id: uuid.UUID) -> dict:
        return {"ok": True}

    fake = Principal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())
    app.dependency_overrides[get_principal] = lambda: fake

    async def checker(*args, **kwargs) -> bool:
        return has_entitlement
    app.dependency_overrides[get_entitlement_checker] = lambda: checker
    # also override the DB session dependency to a no-op if require_course_entitlement depends on it
    return app


@pytest.mark.asyncio
async def test_gate_allows_when_entitled():
    app = _app_with_gate(True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/lessons/{uuid.uuid4()}/probe")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_gate_forbids_when_not_entitled():
    app = _app_with_gate(False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/lessons/{uuid.uuid4()}/probe")
    assert r.status_code == 403
```

> If `require_course_entitlement` depends on `get_db_session`, add `app.dependency_overrides[get_db_session] = lambda: None` in `_app_with_gate` since the overridden checker ignores the session.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/api/test_require_entitlement.py -v`
Expected: FAIL — `ImportError` on `require_course_entitlement`.

- [ ] **Step 3: Implement** (add to `pramana/api/dependencies.py`)

```python
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from pramana.exceptions import EntitlementRequiredError
from pramana.services.consumer.entitlements import has_active_entitlement_for_course

EntitlementChecker = Callable[..., Awaitable[bool]]


def get_entitlement_checker() -> EntitlementChecker:
    """Seam: the entitlement predicate. Overridden in tests."""
    return has_active_entitlement_for_course


async def require_course_entitlement(
    course_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, Depends(get_principal)],
    checker: Annotated[EntitlementChecker, Depends(get_entitlement_checker)],
) -> Principal:
    ok = await checker(
        session, tenant_id=principal.tenant_id, user_id=principal.user_id,
        course_id=course_id, now=datetime.now(UTC))
    if not ok:
        raise EntitlementRequiredError(
            "no active entitlement for this lesson", context={"course_id": str(course_id)})
    return principal
```

> Reuse the module's existing `uuid`, `Annotated`, `Depends`, `AsyncSession`, `get_db_session`, `get_principal`, `Principal` imports — add only what's missing.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/api/test_require_entitlement.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
git add pramana/api/dependencies.py tests/api/test_require_entitlement.py
git commit -m "feat(consumer): require_course_entitlement gate + checker seam"
```

---

## Task 10: Admin router — create consumer + grant/revoke

**Files:**
- Create: `pramana/api/consumer_admin.py`
- Modify: `pramana/api/schemas.py`, `pramana/api/app.py`
- Test: `tests/api/test_consumer_admin.py`

**Interfaces:**
- Consumes: `create_consumer_user`, `grant_package`, `revoke_entitlement`, `get_consumer_tenant_id` (Task 5); `require_roles(RoleName.COMPLIANCE_ADMIN)`; `get_principal`.
- Produces: router `APIRouter(prefix="/admin/consumers", tags=["consumer-admin"])` with:
  - `POST ""` → create consumer user + grant a package (body: `email`, `first_name`, `last_name`, `package_id`) → `ConsumerGrantOut`.
  - `POST "/entitlements/{entitlement_id}/revoke"` → revoke → `EntitlementOut`.

- [ ] **Step 1: Write the failing test** (services overridden — no DB)

```python
# tests/api/test_consumer_admin.py
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from pramana.api.app import create_app
from pramana.api.dependencies import get_principal
from pramana.services.auth import Principal
from pramana.domain.enums import ... # not needed; see note


@pytest.mark.asyncio
async def test_create_and_grant_requires_compliance_admin(monkeypatch):
    app = create_app()

    # A caller lacking compliance_admin is forbidden.
    weak = Principal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=frozenset())
    app.dependency_overrides[get_principal] = lambda: weak
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/admin/consumers", json={
            "email": "a@example.com", "first_name": "A", "last_name": "B",
            "package_id": str(uuid.uuid4())})
    assert r.status_code == 403
```

> The happy-path create+grant is exercised end-to-end in the integration test (Task 12), where a real DB and a `compliance_admin` principal exist. This unit test pins the **denial** direction, which is the one that leaks paid content if a gate is forgotten.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/api/test_consumer_admin.py -v`
Expected: FAIL — route 404 (router not registered).

- [ ] **Step 3: Implement**

Add schemas to `pramana/api/schemas.py`:

```python
class ConsumerGrantIn(BaseModel):
    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    package_id: uuid.UUID


class EntitlementOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    package_id: uuid.UUID
    status: str
    model_config = ConfigDict(from_attributes=True)


class ConsumerGrantOut(BaseModel):
    user_id: uuid.UUID
    entitlement: EntitlementOut
```

Create `pramana/api/consumer_admin.py`:

```python
"""Admin router: create a consumer account and grant/revoke package access."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.api.dependencies import get_db_session, get_principal, require_roles
from pramana.api.schemas import ConsumerGrantIn, ConsumerGrantOut, EntitlementOut
from pramana.domain.enums import ...  # not used
from pramana.db.models.identity import RoleName
from pramana.services.auth import Principal
from pramana.services.consumer import entitlements as ent
from pramana.api.assignments import utcnow  # reuse the existing time helper

router = APIRouter(prefix="/admin/consumers", tags=["consumer-admin"])

Session = Annotated[AsyncSession, Depends(get_db_session)]
Caller = Annotated[Principal, Depends(get_principal)]
_ADMIN = require_roles(RoleName.COMPLIANCE_ADMIN)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConsumerGrantOut,
             dependencies=[Depends(_ADMIN)])
async def create_and_grant(body: ConsumerGrantIn, session: Session, caller: Caller) -> ConsumerGrantOut:
    now = utcnow()
    tenant_id = await ent.get_consumer_tenant_id(session)
    user = await ent.create_consumer_user(
        session, tenant_id=tenant_id, email=body.email,
        first_name=body.first_name, last_name=body.last_name, now=now)
    entitlement = await ent.grant_package(
        session, tenant_id=tenant_id, user_id=user.user_id, package_id=body.package_id,
        granted_by_user_id=caller.user_id, now=now)
    return ConsumerGrantOut(
        user_id=user.user_id, entitlement=EntitlementOut.model_validate(entitlement))


@router.post("/entitlements/{entitlement_id}/revoke", response_model=EntitlementOut,
             dependencies=[Depends(_ADMIN)])
async def revoke(entitlement_id: uuid.UUID, session: Session, caller: Caller) -> EntitlementOut:
    tenant_id = await ent.get_consumer_tenant_id(session)
    e = await ent.revoke_entitlement(
        session, tenant_id=tenant_id, entitlement_id=entitlement_id,
        revoked_by_user_id=caller.user_id, now=utcnow())
    return EntitlementOut.model_validate(e)
```

> Remove the two `import ...  # not used` placeholder lines — they are markers, not code. If `utcnow` is not importable from `pramana.api.assignments`, import it from wherever that module imports it (grep `def utcnow`).

Register in `pramana/api/app.py` (next to the other `include_router` calls):

```python
from pramana.api import consumer_admin
app.include_router(consumer_admin.router)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/api/test_consumer_admin.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
git add pramana/api/consumer_admin.py pramana/api/schemas.py pramana/api/app.py tests/api/test_consumer_admin.py
git commit -m "feat(consumer): admin create-consumer + grant/revoke endpoints"
```

---

## Task 11: Consumer-facing router — catalog, views, quiz

**Files:**
- Create: `pramana/api/consumer.py`
- Modify: `pramana/api/schemas.py`, `pramana/api/app.py`
- Test: `tests/api/test_consumer_catalog_access.py`

**Interfaces:**
- Consumes: `require_course_entitlement` (Task 9); `play.start_view`/`end_view`, `quiz.start_quiz`/`submit_quiz`; `get_asset_signer` seam.
- Produces: router `APIRouter(tags=["consumer"])` with:
  - `GET /me/packages` → the caller's active entitlements + packages (`MyPackageOut[]`).
  - `GET /packages/{package_id}/lessons` → lessons in a package + the caller's per-lesson progress (`LessonListItemOut[]`); gated: caller must hold an active entitlement for that package.
  - `POST /lessons/{course_id}/views` → start a view (`PlaySessionOut`); gated by `require_course_entitlement`.
  - `POST /lessons/{course_id}/views/{play_session_id}/end` (body: `duration_seconds`, `max_watched_pct`) → 204; gated.
  - `POST /lessons/{course_id}/quiz/start` → `QuizFormOut`; gated.
  - `POST /lessons/{course_id}/quiz/{attempt_id}/submit` (body: `answers`) → `QuizResultOut`; gated.

- [ ] **Step 1: Write the failing test** (gate overridden — no DB)

```python
# tests/api/test_consumer_catalog_access.py
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from pramana.api.app import create_app
from pramana.api.dependencies import get_entitlement_checker, get_principal
from pramana.services.auth import Principal


def _client_app(entitled: bool):
    app = create_app()
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4())

    async def checker(*a, **k):
        return entitled
    app.dependency_overrides[get_entitlement_checker] = lambda: checker
    return app


@pytest.mark.asyncio
async def test_view_start_forbidden_without_entitlement():
    app = _client_app(entitled=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(f"/lessons/{uuid.uuid4()}/views", json={"media_kind": "video"})
    assert r.status_code == 403
```

> This is the paid-content denial table entry — a forgotten gate on the view/quiz routes would leak lessons. The entitled happy path is covered by the integration test (Task 12).

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/api/test_consumer_catalog_access.py -v`
Expected: FAIL — route 404.

- [ ] **Step 3: Implement**

Add schemas to `pramana/api/schemas.py`:

```python
class MyPackageOut(BaseModel):
    package_id: uuid.UUID
    slug: str
    title: str
    model_config = ConfigDict(from_attributes=True)


class LessonListItemOut(BaseModel):
    course_id: uuid.UUID
    title: str
    display_order: int
    view_count: int
    completion_count: int
    best_score_pct: float | None


class StartViewIn(BaseModel):
    media_kind: str = "video"


class PlaySessionOut(BaseModel):
    play_session_id: uuid.UUID
    course_version_id: uuid.UUID
    media_url: str | None
    media_kind: str
    min_watch_pct: int


class EndViewIn(BaseModel):
    duration_seconds: int = Field(ge=0)
    max_watched_pct: int = Field(ge=0, le=100)


class QuizOptionOut(BaseModel):
    option_id: uuid.UUID
    option_text: str


class QuizQuestionOut(BaseModel):
    question_id: uuid.UUID
    question_text: str
    question_type: str
    options: list[QuizOptionOut]


class QuizFormOut(BaseModel):
    attempt_id: uuid.UUID
    course_version_id: uuid.UUID
    questions: list[QuizQuestionOut]


class SubmitQuizIn(BaseModel):
    answers: dict[uuid.UUID, list[uuid.UUID]]


class QuizResultOut(BaseModel):
    attempt_id: uuid.UUID
    score_pct: float
    is_all_correct: bool
    correct_count: int
    question_count: int
```

Create `pramana/api/consumer.py`:

```python
"""Consumer-facing router: my packages, lesson list, views, and quiz."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.api.assignments import utcnow
from pramana.api.dependencies import (
    get_asset_signer, get_db_session, get_principal, require_course_entitlement)
from pramana.api.schemas import (
    EndViewIn, LessonListItemOut, MyPackageOut, PlaySessionOut, QuizFormOut,
    QuizOptionOut, QuizQuestionOut, QuizResultOut, StartViewIn, SubmitQuizIn)
from pramana.db.models.consumer import (
    Enrollment, Entitlement, Package, PackageCourse)
from pramana.db.models.course import Course
from pramana.services.auth import Principal
from pramana.services.consumer import entitlements as ent
from pramana.services.consumer import play, quiz
from pramana.services.player import AssetUrlSigner

router = APIRouter(tags=["consumer"])

Session = Annotated[AsyncSession, Depends(get_db_session)]
Caller = Annotated[Principal, Depends(get_principal)]
Gated = Annotated[Principal, Depends(require_course_entitlement)]


@router.get("/me/packages", response_model=list[MyPackageOut])
async def my_packages(session: Session, caller: Caller) -> list[MyPackageOut]:
    rows = (
        await session.execute(
            select(Package)
            .join(Entitlement, Entitlement.package_id == Package.id)
            .where(Entitlement.user_id == caller.user_id, Entitlement.status == "active")
        )
    ).scalars()
    return [MyPackageOut.model_validate(p) for p in rows]


@router.get("/packages/{package_id}/lessons", response_model=list[LessonListItemOut])
async def package_lessons(package_id: uuid.UUID, session: Session, caller: Caller
                          ) -> list[LessonListItemOut]:
    # Access: caller must hold an active entitlement for THIS package.
    held = (
        await session.execute(
            select(Entitlement.id).where(
                Entitlement.user_id == caller.user_id,
                Entitlement.package_id == package_id,
                Entitlement.status == "active",
            )
        )
    ).scalar_one_or_none()
    if held is None:
        from pramana.exceptions import EntitlementRequiredError
        raise EntitlementRequiredError("no entitlement for this package",
                                       context={"package_id": str(package_id)})

    rows = (
        await session.execute(
            select(Course, PackageCourse.display_order)
            .join(PackageCourse, PackageCourse.course_id == Course.id)
            .where(PackageCourse.package_id == package_id)
            .order_by(PackageCourse.display_order)
        )
    ).all()
    enrollments = {
        e.course_id: e
        for e in (
            await session.execute(
                select(Enrollment).where(Enrollment.user_id == caller.user_id))
        ).scalars()
    }
    out: list[LessonListItemOut] = []
    for course, order in rows:
        e = enrollments.get(course.id)
        out.append(LessonListItemOut(
            course_id=course.id, title=course.title, display_order=order,
            view_count=e.view_count if e else 0,
            completion_count=e.completion_count if e else 0,
            best_score_pct=e.best_score_pct if e else None))
    return out


@router.post("/lessons/{course_id}/views", response_model=PlaySessionOut,
             status_code=status.HTTP_201_CREATED)
async def start_view(course_id: uuid.UUID, body: StartViewIn, session: Session,
                     caller: Gated,
                     sign_asset: Annotated[AssetUrlSigner, Depends(get_asset_signer)]
                     ) -> PlaySessionOut:
    tenant_id = await ent.get_consumer_tenant_id(session)
    entitlement_id = await _active_entitlement_id_for_course(session, caller.user_id, course_id)
    manifest = await play.start_view(
        session, tenant_id=tenant_id, user_id=caller.user_id, course_id=course_id,
        entitlement_id=entitlement_id, media_kind=body.media_kind, now=utcnow(),
        sign_asset=sign_asset)
    return PlaySessionOut(
        play_session_id=manifest.play_session_id, course_version_id=manifest.course_version_id,
        media_url=manifest.media_url, media_kind=manifest.media_kind,
        min_watch_pct=manifest.min_watch_pct)


@router.post("/lessons/{course_id}/views/{play_session_id}/end",
             status_code=status.HTTP_204_NO_CONTENT)
async def end_view(course_id: uuid.UUID, play_session_id: uuid.UUID, body: EndViewIn,
                   session: Session, caller: Gated) -> Response:
    tenant_id = await ent.get_consumer_tenant_id(session)
    await play.end_view(
        session, tenant_id=tenant_id, user_id=caller.user_id,
        play_session_id=play_session_id, duration_seconds=body.duration_seconds,
        max_watched_pct=body.max_watched_pct, now=utcnow())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/lessons/{course_id}/quiz/start", response_model=QuizFormOut,
             status_code=status.HTTP_201_CREATED)
async def start_quiz(course_id: uuid.UUID, session: Session, caller: Gated) -> QuizFormOut:
    tenant_id = await ent.get_consumer_tenant_id(session)
    entitlement_id = await _active_entitlement_id_for_course(session, caller.user_id, course_id)
    form = await quiz.start_quiz(
        session, tenant_id=tenant_id, user_id=caller.user_id, course_id=course_id,
        entitlement_id=entitlement_id, now=utcnow())
    return QuizFormOut(
        attempt_id=form.attempt_id, course_version_id=form.course_version_id,
        questions=[QuizQuestionOut(
            question_id=q.question_id, question_text=q.question_text,
            question_type=q.question_type,
            options=[QuizOptionOut(option_id=o.option_id, option_text=o.option_text)
                     for o in q.options]) for q in form.questions])


@router.post("/lessons/{course_id}/quiz/{attempt_id}/submit", response_model=QuizResultOut)
async def submit_quiz(course_id: uuid.UUID, attempt_id: uuid.UUID, body: SubmitQuizIn,
                      session: Session, caller: Gated) -> QuizResultOut:
    tenant_id = await ent.get_consumer_tenant_id(session)
    result = await quiz.submit_quiz(
        session, tenant_id=tenant_id, user_id=caller.user_id, attempt_id=attempt_id,
        answers=body.answers, now=utcnow())
    return QuizResultOut(
        attempt_id=result.attempt_id, score_pct=result.score_pct,
        is_all_correct=result.is_all_correct, correct_count=result.correct_count,
        question_count=result.question_count)


async def _active_entitlement_id_for_course(
    session: AsyncSession, user_id: uuid.UUID, course_id: uuid.UUID
) -> uuid.UUID:
    row = (
        await session.execute(
            select(Entitlement.id)
            .join(PackageCourse, PackageCourse.package_id == Entitlement.package_id)
            .where(Entitlement.user_id == user_id, Entitlement.status == "active",
                   PackageCourse.course_id == course_id)
            .limit(1)
        )
    ).scalar_one()
    return row
```

Register in `pramana/api/app.py`:

```python
from pramana.api import consumer
app.include_router(consumer.router)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/api/test_consumer_catalog_access.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
git add pramana/api/consumer.py pramana/api/schemas.py pramana/api/app.py tests/api/test_consumer_catalog_access.py
git commit -m "feat(consumer): catalog, view, and quiz endpoints (entitlement-gated)"
```

---

## Task 12: End-to-end integration flow

**Files:**
- Test: `tests/integration/test_consumer_end_to_end.py`
- Possibly modify: `tests/integration/conftest.py` (add `consumer_setup` / `make_course` helpers if not present)

**Interfaces:**
- Consumes: the whole stack. Drives the real ASGI app against the scratch PG with a `compliance_admin` principal for the admin call and a consumer principal for the learner calls.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_consumer_end_to_end.py
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from pramana.api.app import create_app
from pramana.api.dependencies import get_principal
from pramana.services.auth import Principal

pytestmark = pytest.mark.integration


async def test_grant_then_view_then_perfect_quiz(db_app, admin_principal, seed_package_with_lesson):
    # db_app: the create_app() wired to the migrated scratch DB session (integration conftest).
    # seed_package_with_lesson: inserts a Package + a Course(active version, graded questions),
    #   returns (package_id, course_id, correct_options_by_question).
    app = db_app
    pkg = await seed_package_with_lesson()

    # 1) Admin creates a consumer + grants the package.
    app.dependency_overrides[get_principal] = lambda: admin_principal  # holds compliance_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/admin/consumers", json={
            "email": "learner@example.com", "first_name": "Lee", "last_name": "Roy",
            "package_id": str(pkg.package_id)})
        assert r.status_code == 201
        consumer_user_id = uuid.UUID(r.json()["user_id"])

    # 2) Switch to the consumer principal (consumer tenant).
    from pramana.services.consumer.entitlements import get_consumer_tenant_id
    consumer_tenant = await get_consumer_tenant_id(app.state_session)  # or the conftest session
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=consumer_user_id, tenant_id=consumer_tenant)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # lessons visible with zeroed progress
        r = await c.get(f"/packages/{pkg.package_id}/lessons")
        assert r.status_code == 200 and r.json()[0]["view_count"] == 0

        # view
        r = await c.post(f"/lessons/{pkg.course_id}/views", json={"media_kind": "video"})
        assert r.status_code == 201
        ps = r.json()["play_session_id"]
        r = await c.post(f"/lessons/{pkg.course_id}/views/{ps}/end",
                         json={"duration_seconds": 30, "max_watched_pct": 100})
        assert r.status_code == 204

        # quiz — answer everything correctly
        r = await c.post(f"/lessons/{pkg.course_id}/quiz/start")
        form = r.json()
        answers = {q["question_id"]: pkg.correct_options[uuid.UUID(q["question_id"])]
                   for q in form["questions"]}
        answers = {k: [str(x) for x in v] for k, v in answers.items()}
        r = await c.post(f"/lessons/{pkg.course_id}/quiz/{form['attempt_id']}/submit",
                         json={"answers": answers})
        assert r.status_code == 200 and r.json()["is_all_correct"] is True

        # progress now shows 1 view, 1 completion
        r = await c.get(f"/packages/{pkg.package_id}/lessons")
        item = r.json()[0]
        assert item["view_count"] == 1 and item["completion_count"] == 1
```

> Wire `db_app`, `admin_principal`, and `seed_package_with_lesson` in `tests/integration/conftest.py` following the existing integration fixtures (the ones the learner-runtime integration tests already use for a migrated session + seeded course). Reuse the existing course-seeding helper rather than writing a new one; only add the Package + PackageCourse insert on top.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/integration/test_consumer_end_to_end.py -v`
Expected: FAIL — fixtures/endpoints incomplete.

- [ ] **Step 3: Make it pass**

Add the fixtures/helpers to the integration conftest; fix any wiring surfaced by the failure. No new production code should be needed if Tasks 1–11 are correct — this task proves they compose.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/integration/test_consumer_end_to_end.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
git add tests/integration/test_consumer_end_to_end.py tests/integration/conftest.py
git commit -m "test(consumer): end-to-end grant -> view -> perfect quiz -> progress"
```

---

## Task 13: Counter recompute script + make target

**Files:**
- Create: `scripts/recompute_enrollment_counters.py`
- Modify: `Makefile`
- Test: `tests/integration/test_recompute_script.py`

**Interfaces:**
- Consumes: `recompute_counters` (Task 6).
- Produces: a CLI (`--dry-run`, `--tenant <short_code>`) that iterates all enrollments, calls `recompute_counters`, reports drift (rows whose stored counters differed), and commits unless `--dry-run`. `make recompute-counters` invokes it.

- [ ] **Step 1: Write the failing test** (integration)

```python
# tests/integration/test_recompute_script.py
import pytest
from scripts.recompute_enrollment_counters import recompute_all

pytestmark = pytest.mark.integration


async def test_recompute_all_fixes_drift(db_session, consumer_setup, utcnow):
    s = await consumer_setup(db_session)
    from pramana.db.models.consumer import Enrollment, PlaySession
    e = Enrollment(tenant_id=s.tenant_id, user_id=s.user.user_id, course_id=s.course.id,
                   entitlement_id=s.entitlement.id, first_accessed_at=utcnow,
                   last_accessed_at=utcnow, view_count=99)  # deliberately wrong
    db_session.add(e); await db_session.flush()
    db_session.add(PlaySession(tenant_id=s.tenant_id, enrollment_id=e.id,
                               course_version_id=s.course.current_version_id))
    await db_session.flush()

    drifted = await recompute_all(db_session, dry_run=False)
    await db_session.refresh(e)
    assert e.view_count == 1
    assert any(d["enrollment_id"] == e.id for d in drifted)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/integration/test_recompute_script.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# scripts/recompute_enrollment_counters.py
"""Reconcile enrollment counters against the play_session / consumer_attempt event tables.

Usage:
    python -m scripts.recompute_enrollment_counters [--dry-run] [--tenant consumer]
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.consumer import Enrollment
from pramana.db.session import session_scope
from pramana.services.consumer.enrollment import recompute_counters


async def recompute_all(session: AsyncSession, *, dry_run: bool) -> list[dict[str, Any]]:
    drift: list[dict[str, Any]] = []
    ids = list((await session.execute(select(Enrollment.id))).scalars())
    for enrollment_id in ids:
        before = await session.get(Enrollment, enrollment_id)
        prev = (before.view_count, before.completion_count, before.best_score_pct)
        after = await recompute_counters(session, enrollment_id=enrollment_id)
        now = (after.view_count, after.completion_count, after.best_score_pct)
        if prev != now:
            drift.append({"enrollment_id": enrollment_id, "before": prev, "after": now})
    if dry_run:
        await session.rollback()
    return drift


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tenant", default="consumer")
    args = parser.parse_args()
    async with session_scope() as session:
        drift = await recompute_all(session, dry_run=args.dry_run)
    print(f"{len(drift)} enrollment(s) drifted" + (" (dry-run, not written)" if args.dry_run else ""))
    for d in drift:
        print(f"  {d['enrollment_id']}: {d['before']} -> {d['after']}")


if __name__ == "__main__":
    asyncio.run(_main())
```

> Confirm the session helper name — the agent report shows `session_scope()` used by `get_db_session`. If it lives at a different import path, adjust.

Add to `Makefile`:

```makefile
recompute-counters:  ## Reconcile consumer enrollment counters against event tables
	python -m scripts.recompute_enrollment_counters $(ARGS)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/integration/test_recompute_script.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
git add scripts/recompute_enrollment_counters.py Makefile tests/integration/test_recompute_script.py
git commit -m "feat(consumer): enrollment counter recompute script + make target"
```

---

## Task 14: Full-suite green + status manifest

**Files:**
- Modify: `project-status.yaml` (add a `consumer-subscription` entry), and the README status table is regenerated from it.

- [ ] **Step 1: Run the whole suite**

```bash
pytest --ignore=tests/integration -q       # unit, ~fast
pytest tests/integration -q                # integration, ~2.5 min, run once, serially
```
Expected: all green.

- [ ] **Step 2: Lint + type the three paths**

```bash
ruff format pramana tests scripts && ruff check pramana tests scripts && mypy pramana
```
Expected: clean.

- [ ] **Step 3: Add the manifest entry + regenerate the README table**

Add a `consumer-subscription` item to `project-status.yaml` (copy the shape of an existing entry; `stage` is free-form). Then:

```bash
make status        # regenerates the README table between the GENERATED markers
```

- [ ] **Step 4: Verify status drift check passes**

```bash
pytest tests/test_project_status.py -q
```
Expected: PASS (no drift).

- [ ] **Step 5: Commit**

```bash
git add project-status.yaml README.md
git commit -m "docs(consumer): record consumer-subscription in the status manifest"
```

---

## Self-Review

**Spec coverage:**
- §3.1 `package` → Task 1/2. §3.2 `package_course` → Task 1/2. §3.3 `entitlement` (partial-unique active) → Task 1/2/5. §3.4 `enrollment` lazy-create + denormalized counters → Task 6. §3.5 `play_session` view event → Task 7. §3.6 `consumer_attempt` → Task 8. §3.7 `consumer_attempt_answer` → Task 8. §3.8 metrics derivation + recompute → Task 3/6/13. §4 isolation boundaries → package layout across Tasks 1/3/5–8/10–11. §5 access flow → Tasks 10/11. §5.1 authorization gate + denial test → Task 9/10/11. §6 tenancy seed → Task 2. §7 migration + audit → Task 2/5. §8 edge cases (version pinning, revoke mid-flight, cross-package aggregation, idempotent end_view) → Tasks 7/8/11/12. §9 testing (pure/service/API-denial/integration) → every task + Task 12. §10 deferred → not built (correct). All spec sections map to a task.
- **Quiz ≤5 (soft guideline):** intentionally NOT enforced structurally, per the spec — no task, by design.

**Placeholder scan:** the two `from pramana.domain.enums import ...  # not used` lines in Task 10's code block are explicitly flagged in-line as markers to delete; no other TODO/TBD. Test bodies contain real assertions. Fixture-dependent integration tests name the exact helpers to add and where.

**Type consistency:** service signatures declared in each task's Interfaces block match their call sites — `has_active_entitlement_for_course(session, *, tenant_id, user_id, course_id, now)` (Task 5) is called identically by `require_course_entitlement` (Task 9) and the checker seam; `get_or_create_enrollment(..., entitlement_id, now)` (Task 6) is called with those kwargs by `play.start_view` and `quiz.start_quiz` (Tasks 7/8); `PlaySessionManifest.play_session_id` (Task 7) is read by the router (Task 11); `QuizForm.attempt_id`/`QuizResult.*` (Task 8) match the router's response mapping (Task 11). `append_audit(session, *, tenant_id, entity_type, entity_id, event_type, payload, occurred_at, actor_user_id=None)` is called with exactly those kwargs in Task 5.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-09-03-consumer-subscription.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — a fresh subagent per task with two-stage review between tasks; fast iteration and each task stays in a clean context.

**2. Inline Execution** — execute tasks in this session with checkpoints for review.

**Which approach?**
