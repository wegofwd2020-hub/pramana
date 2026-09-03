"""Consumer subscription: packages, entitlements, and lesson tracking.

Revision ID: 0010_consumer_subscription
Revises: 0009_audit_log_grants
Create Date: 2026-09-03 00:00:00
"""

from __future__ import annotations

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
        sa.Column(
            "tenant_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_key", sa.String(500), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="usd"),
        sa.Column(
            "is_published", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_package_slug_unique"),
    )
    op.create_index("ix_package_tenant_id", "package", ["tenant_id"])
    # Suffix only — naming convention prefixes ck_package_
    op.create_check_constraint(
        "price_cents_nonneg", "package", "price_cents IS NULL OR price_cents >= 0"
    )

    op.create_table(
        "package_course",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "package_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("package.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("course.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("package_id", "course_id", name="uq_package_course_unique"),
    )
    op.create_index("ix_package_course_package_id", "package_course", ["package_id"])
    op.create_index("ix_package_course_course_id", "package_course", ["course_id"])

    op.create_table(
        "entitlement",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "package_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("package.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "revoked", "expired", name="entitlement_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "source",
            sa.Enum("manual", "stripe", name="entitlement_source"),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("external_ref", sa.String(255), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "granted_by_user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_entitlement_tenant_id", "entitlement", ["tenant_id"])
    op.create_index("ix_entitlement_user_id", "entitlement", ["user_id"])
    op.create_index("ix_entitlement_package_id", "entitlement", ["package_id"])
    op.create_index(
        "ix_entitlement_active_unique",
        "entitlement",
        ["user_id", "package_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "enrollment",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("course.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "entitlement_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("entitlement.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "first_accessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "completion_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("best_score_pct", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "course_id", name="uq_enrollment_user_course_unique"
        ),
    )
    op.create_index("ix_enrollment_tenant_id", "enrollment", ["tenant_id"])
    op.create_index("ix_enrollment_user_id", "enrollment", ["user_id"])
    op.create_index("ix_enrollment_course_id", "enrollment", ["course_id"])
    # Suffix only — naming convention prefixes ck_enrollment_
    op.create_check_constraint("view_count_nonneg", "enrollment", "view_count >= 0")
    op.create_check_constraint(
        "completion_count_nonneg", "enrollment", "completion_count >= 0"
    )

    op.create_table(
        "play_session",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "enrollment_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("enrollment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "course_version_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("course_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "media_kind",
            sa.Enum("video", "audio", name="media_kind"),
            nullable=False,
            server_default="video",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "duration_seconds", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "max_watched_pct", sa.SmallInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_play_session_tenant_id", "play_session", ["tenant_id"])
    op.create_index(
        "ix_play_session_enrollment_id", "play_session", ["enrollment_id"]
    )
    # Suffix only — naming convention prefixes ck_play_session_
    op.create_check_constraint(
        "max_watched_pct_range", "play_session", "max_watched_pct BETWEEN 0 AND 100"
    )
    op.create_check_constraint(
        "duration_seconds_nonneg", "play_session", "duration_seconds >= 0"
    )

    op.create_table(
        "consumer_attempt",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "enrollment_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("enrollment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "course_version_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("course_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score_pct", sa.Float(), nullable=True),
        sa.Column(
            "is_all_correct",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "question_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_active_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_consumer_attempt_tenant_id", "consumer_attempt", ["tenant_id"]
    )
    op.create_index(
        "ix_consumer_attempt_enrollment_id", "consumer_attempt", ["enrollment_id"]
    )
    # Suffix only — naming convention prefixes ck_consumer_attempt_
    op.create_check_constraint(
        "score_pct_range",
        "consumer_attempt",
        "score_pct IS NULL OR (score_pct BETWEEN 0 AND 100)",
    )
    op.create_check_constraint(
        "all_correct_consistent",
        "consumer_attempt",
        "submitted_at IS NULL OR (is_all_correct = (score_pct = 100))",
    )

    op.create_table(
        "consumer_attempt_answer",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "consumer_attempt_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("consumer_attempt.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("question.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "selected_option_ids",
            pg.ARRAY(pg.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "answered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "consumer_attempt_id",
            "question_id",
            name="uq_consumer_attempt_answer_unique",
        ),
    )
    op.create_index(
        "ix_consumer_attempt_answer_attempt_id",
        "consumer_attempt_answer",
        ["consumer_attempt_id"],
    )

    # Seed the single Consumer tenant.
    # Use gen_random_uuid() to avoid asyncpg VARCHAR→uuid cast issues.
    op.execute(
        sa.text(
            "INSERT INTO tenant (id, name, short_code, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'Consumer', 'consumer', now(), now())"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM tenant WHERE short_code = 'consumer'"))
    for tbl in [
        "consumer_attempt_answer",
        "consumer_attempt",
        "play_session",
        "enrollment",
        "entitlement",
        "package_course",
        "package",
    ]:
        op.drop_table(tbl)
    for enum in ["media_kind", "entitlement_source", "entitlement_status"]:
        op.execute(sa.text(f"DROP TYPE IF EXISTS {enum}"))
