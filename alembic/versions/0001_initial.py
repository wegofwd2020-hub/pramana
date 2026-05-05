"""Initial schema (Phase B baseline).

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-05 22:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -----------------------------------------------------------------
    # Enums (named so Alembic can manage them deterministically)
    # -----------------------------------------------------------------
    user_status = postgresql.ENUM(
        "active", "inactive", "on_leave", "pseudonymized",
        name="user_status",
    )
    user_type = postgresql.ENUM(
        "employee", "contractor",
        name="user_type",
    )
    role_name = postgresql.ENUM(
        "trainee", "manager", "content_author", "compliance_admin", "auditor",
        name="role_name",
    )
    question_type = postgresql.ENUM(
        "single_select", "true_false",
        name="question_type",
    )
    assignment_status = postgresql.ENUM(
        "assigned", "in_progress", "passed", "blocked", "cancelled", "expired",
        name="assignment_status",
    )
    attempt_outcome = postgresql.ENUM(
        "in_progress", "pass", "fail",
        name="attempt_outcome",
    )
    terminal_reason = postgresql.ENUM(
        "passed", "max_attempts_failed", "cancelled_by_admin", "expired_due_date",
        name="terminal_reason",
    )
    for enum in (
        user_status,
        user_type,
        role_name,
        question_type,
        assignment_status,
        attempt_outcome,
        terminal_reason,
    ):
        enum.create(op.get_bind(), checkfirst=True)

    # -----------------------------------------------------------------
    # tenant
    # -----------------------------------------------------------------
    op.create_table(
        "tenant",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("short_code", sa.String(50), nullable=False),
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
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_tenant_name"),
        sa.UniqueConstraint("short_code", name="uq_tenant_short_code"),
    )

    # -----------------------------------------------------------------
    # user_account (forward-declare for self-referential FK)
    # -----------------------------------------------------------------
    op.create_table(
        "user_account",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column(
            "user_type",
            postgresql.ENUM(name="user_type", create_type=False),
            nullable=False,
            server_default="employee",
        ),
        sa.Column("department", sa.String(200), nullable=True),
        sa.Column(
            "manager_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "user_account.user_id",
                ondelete="SET NULL",
                use_alter=True,
                name="fk_user_account_manager_user_id_user_account",
            ),
            nullable=True,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="user_status", create_type=False),
            nullable=False,
            server_default="active",
        ),
        sa.Column("sso_subject", sa.String(255), nullable=True),
        sa.Column("pseudonymized_at", sa.DateTime(timezone=True), nullable=True),
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
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "email", name="user_tenant_email_unique"
        ),
        sa.UniqueConstraint("sso_subject", name="uq_user_account_sso_subject"),
        sa.CheckConstraint(
            "(status = 'pseudonymized') = (pseudonymized_at IS NOT NULL)",
            name="ck_user_account_pseudonymized_at_consistent",
        ),
    )
    op.create_index("ix_user_account_tenant_id", "user_account", ["tenant_id"])
    op.create_index(
        "ix_user_account_manager_user_id", "user_account", ["manager_user_id"]
    )
    op.create_index("ix_user_status", "user_account", ["status"])

    # -----------------------------------------------------------------
    # role + user_role
    # -----------------------------------------------------------------
    op.create_table(
        "role",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "name",
            postgresql.ENUM(name="role_name", create_type=False),
            nullable=False,
        ),
        sa.Column("description", sa.String(500), nullable=False),
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
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_role_name"),
    )

    op.create_table(
        "user_role",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("role.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "granted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="SET NULL"),
            nullable=True,
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
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "role_id", name="user_role_unique"),
    )
    op.create_index("ix_user_role_user_id", "user_role", ["user_id"])
    op.create_index("ix_user_role_role_id", "user_role", ["role_id"])

    # -----------------------------------------------------------------
    # course
    # -----------------------------------------------------------------
    op.create_table(
        "course",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "author_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "cooldown_days", sa.Integer(), nullable=False, server_default="365"
        ),
        sa.Column(
            "pass_threshold_pct", sa.Integer(), nullable=False, server_default="80"
        ),
        sa.Column(
            "max_attempts", sa.Integer(), nullable=False, server_default="2"
        ),
        sa.Column(
            "framework_tags",
            postgresql.ARRAY(sa.String(50)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "topic_tags",
            postgresql.ARRAY(sa.String(50)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "current_version_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
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
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "pass_threshold_pct BETWEEN 0 AND 100",
            name="ck_course_pass_threshold_pct_range",
        ),
        sa.CheckConstraint(
            "cooldown_days >= 0", name="ck_course_cooldown_days_nonneg"
        ),
        sa.CheckConstraint(
            "max_attempts >= 1", name="ck_course_max_attempts_min"
        ),
    )
    op.create_index("ix_course_tenant_id", "course", ["tenant_id"])
    op.create_index("ix_course_author_user_id", "course", ["author_user_id"])
    op.create_index(
        "ix_course_framework_tags",
        "course",
        ["framework_tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_course_topic_tags",
        "course",
        ["topic_tags"],
        postgresql_using="gin",
    )

    # -----------------------------------------------------------------
    # course_version
    # -----------------------------------------------------------------
    op.create_table(
        "course_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "published_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("video_asset_id", sa.String(500), nullable=True),
        sa.Column(
            "min_watch_pct", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "is_material_change",
            sa.Boolean(),
            nullable=False,
            server_default="false",
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
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "course_id", "version_number", name="course_version_unique"
        ),
        sa.CheckConstraint(
            "version_number >= 1", name="ck_course_version_version_number_min"
        ),
        sa.CheckConstraint(
            "min_watch_pct BETWEEN 0 AND 100",
            name="ck_course_version_min_watch_pct_range",
        ),
    )
    op.create_index("ix_course_version_course_id", "course_version", ["course_id"])
    op.create_index(
        "ix_course_version_active",
        "course_version",
        ["course_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    # Now we can wire course.current_version_id -> course_version.id
    op.create_foreign_key(
        "fk_course_current_version_id_course_version",
        "course",
        "course_version",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
        use_alter=True,
    )

    # -----------------------------------------------------------------
    # question + answer_option
    # -----------------------------------------------------------------
    op.create_table(
        "question",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "course_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column(
            "question_type",
            postgresql.ENUM(name="question_type", create_type=False),
            nullable=False,
        ),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "display_order", sa.Integer(), nullable=False, server_default="0"
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
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("weight > 0", name="ck_question_weight_positive"),
    )
    op.create_index(
        "ix_question_course_version_id", "question", ["course_version_id"]
    )

    op.create_table(
        "answer_option",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("question.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("option_text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column(
            "display_order", sa.Integer(), nullable=False, server_default="0"
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
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "question_id", "display_order", name="answer_option_order_unique"
        ),
    )
    op.create_index(
        "ix_answer_option_question_id", "answer_option", ["question_id"]
    )

    # -----------------------------------------------------------------
    # assignment
    # -----------------------------------------------------------------
    op.create_table(
        "assignment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "course_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "assigned_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="assignment_status", create_type=False),
            nullable=False,
            server_default="assigned",
        ),
        sa.Column(
            "attempts_used", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "max_attempts", sa.Integer(), nullable=False, server_default="2"
        ),
        sa.Column(
            "cooldown_days", sa.Integer(), nullable=False, server_default="365"
        ),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "terminal_reason",
            postgresql.ENUM(name="terminal_reason", create_type=False),
            nullable=True,
        ),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
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
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempts_used >= 0 AND attempts_used <= max_attempts + 1",
            name="ck_assignment_attempts_used_range",
        ),
        sa.CheckConstraint(
            "cooldown_days >= 0", name="ck_assignment_cooldown_days_nonneg"
        ),
        sa.CheckConstraint(
            "(status IN ('passed','blocked','cancelled','expired')) "
            "= (terminal_at IS NOT NULL)",
            name="ck_assignment_terminal_at_consistent",
        ),
        sa.CheckConstraint(
            "(status IN ('passed','blocked')) = (cooldown_until IS NOT NULL)",
            name="ck_assignment_cooldown_until_consistent",
        ),
    )
    op.create_index("ix_assignment_tenant_id", "assignment", ["tenant_id"])
    op.create_index("ix_assignment_user_id", "assignment", ["user_id"])
    op.create_index("ix_assignment_course_id", "assignment", ["course_id"])
    op.create_index("ix_assignment_user_status", "assignment", ["user_id", "status"])
    op.create_index(
        "ix_assignment_course_status", "assignment", ["course_id", "status"]
    )
    op.create_index("ix_assignment_due_at", "assignment", ["due_at"])

    # -----------------------------------------------------------------
    # attempt + attempt_answer
    # -----------------------------------------------------------------
    op.create_table(
        "attempt",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assignment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assignment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score_pct", sa.Float(), nullable=True),
        sa.Column(
            "outcome",
            postgresql.ENUM(name="attempt_outcome", create_type=False),
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("total_active_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "attestation_accepted",
            sa.Boolean(),
            nullable=False,
            server_default="false",
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
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "assignment_id", "attempt_number", name="attempt_number_unique"
        ),
        sa.CheckConstraint(
            "attempt_number >= 1", name="ck_attempt_attempt_number_min"
        ),
        sa.CheckConstraint(
            "score_pct IS NULL OR (score_pct BETWEEN 0 AND 100)",
            name="ck_attempt_score_pct_range",
        ),
        sa.CheckConstraint(
            "(submitted_at IS NULL) = (outcome = 'in_progress')",
            name="ck_attempt_outcome_consistent_with_submission",
        ),
    )
    op.create_index("ix_attempt_assignment_id", "attempt", ["assignment_id"])

    op.create_table(
        "attempt_answer",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("attempt.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("question.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "selected_option_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
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
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "attempt_id", "question_id", name="attempt_answer_unique"
        ),
    )
    op.create_index(
        "ix_attempt_answer_attempt_id", "attempt_answer", ["attempt_id"]
    )

    # -----------------------------------------------------------------
    # certificate
    # -----------------------------------------------------------------
    op.create_table(
        "certificate",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "course_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "assignment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assignment.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verification_code", sa.String(32), nullable=False),
        sa.Column("pdf_object_key", sa.String(500), nullable=True),
        sa.Column("attestation_text_version", sa.String(50), nullable=False),
        sa.Column("attestation_ip", postgresql.INET(), nullable=True),
        sa.Column("attestation_user_agent", sa.Text(), nullable=True),
        sa.Column("attestation_timestamp", sa.DateTime(timezone=True), nullable=False),
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
            server_onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("assignment_id", name="uq_certificate_assignment_id"),
        sa.UniqueConstraint(
            "verification_code", name="uq_certificate_verification_code"
        ),
    )
    op.create_index("ix_certificate_tenant_id", "certificate", ["tenant_id"])
    op.create_index("ix_certificate_user_id", "certificate", ["user_id"])
    op.create_index(
        "ix_certificate_user_issued", "certificate", ["user_id", "issued_at"]
    )

    # -----------------------------------------------------------------
    # audit_log (append-only via trigger; no UPDATE or DELETE allowed)
    # -----------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column(
            "audit_id",
            sa.BigInteger(),
            sa.Identity(always=True),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_ip", postgresql.INET(), nullable=True),
        sa.Column("actor_user_agent", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("prev_audit_hash", sa.String(64), nullable=True),
        sa.Column("audit_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])
    op.create_index("ix_audit_log_actor_user_id", "audit_log", ["actor_user_id"])
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("ix_audit_event_type", "audit_log", ["event_type"])
    op.create_index("ix_audit_occurred_at", "audit_log", ["occurred_at"])

    # Append-only enforcement: reject UPDATE and DELETE on audit_log.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_immutable()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit_log is append-only (operation: %)', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_update
          BEFORE UPDATE ON audit_log
          FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_delete
          BEFORE DELETE ON audit_log
          FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
        """
    )


def downgrade() -> None:
    # Drop triggers and audit-log function first.
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log;")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS audit_log_immutable();")

    # Drop tables in reverse dependency order.
    op.drop_table("audit_log")
    op.drop_table("certificate")
    op.drop_table("attempt_answer")
    op.drop_table("attempt")
    op.drop_table("assignment")
    op.drop_constraint(
        "fk_course_current_version_id_course_version",
        "course",
        type_="foreignkey",
    )
    op.drop_table("answer_option")
    op.drop_table("question")
    op.drop_table("course_version")
    op.drop_table("course")
    op.drop_table("user_role")
    op.drop_table("role")
    op.drop_table("user_account")
    op.drop_table("tenant")

    # Drop enums.
    for name in (
        "terminal_reason",
        "attempt_outcome",
        "assignment_status",
        "question_type",
        "role_name",
        "user_type",
        "user_status",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name};")
