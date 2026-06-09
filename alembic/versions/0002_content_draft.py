"""Content-authoring: content_draft table (AI-drafted, human-approved content).

Adds the approval-workflow table upstream of course_version (see
docs/03_ai_drafted_human_approved_content.md). On approval + publish a draft
materialises into the existing immutable course_version; the draft records which
version it produced.

Revision ID: 0002_content_draft
Revises: 0001_initial
Create Date: 2026-06-05 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_content_draft"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    content_draft_status = postgresql.ENUM(
        "draft",
        "received",
        "in_review",
        "approved",
        "published",
        "rejected",
        name="content_draft_status",
    )
    content_draft_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "content_draft",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="content_draft_status", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", postgresql.JSONB(), nullable=False),
        sa.Column("source_citations", postgresql.JSONB(), nullable=True),
        # Provenance
        sa.Column("gen_engine", sa.String(60), nullable=True),
        sa.Column("gen_model", sa.String(120), nullable=True),
        sa.Column("gen_provider", sa.String(60), nullable=True),
        sa.Column("gen_prompt_version", sa.String(60), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "generated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Ingestion (Mentible Consumable Package, ADR-011)
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("package_version", sa.Integer(), nullable=True),
        sa.Column("package_content_hash", sa.String(128), nullable=True),
        sa.Column("signature", sa.Text(), nullable=True),
        # Review / approval evidence
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_account.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attestation_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(128), nullable=True),
        # Published output
        sa.Column(
            "published_course_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_version.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Mixins
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(approved_by_user_id IS NULL) = (approved_at IS NULL)",
            name="ck_content_draft_approval_pair",
        ),
        sa.CheckConstraint(
            "approved_by_user_id IS NULL "
            "OR generated_by_user_id IS NULL "
            "OR approved_by_user_id <> generated_by_user_id",
            name="ck_content_draft_separation_of_duties",
        ),
        sa.CheckConstraint(
            "(package_id IS NULL) = (package_version IS NULL)",
            name="ck_content_draft_package_ref_pair",
        ),
    )
    op.create_index("ix_content_draft_tenant_id", "content_draft", ["tenant_id"])
    op.create_index("ix_content_draft_course_id", "content_draft", ["course_id"])
    op.create_index("ix_content_draft_status", "content_draft", ["status"])
    op.create_index(
        "ix_content_draft_generated_by_user_id",
        "content_draft",
        ["generated_by_user_id"],
    )
    op.create_index(
        "ix_content_draft_course_status", "content_draft", ["course_id", "status"]
    )
    # Ingestion idempotency: one draft per delivered (tenant, package_id, version).
    # Partial so locally-authored drafts (NULL package_id) don't collide.
    op.create_index(
        "uq_content_draft_package",
        "content_draft",
        ["tenant_id", "package_id", "package_version"],
        unique=True,
        postgresql_where=sa.text("package_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_content_draft_package", table_name="content_draft")
    op.drop_index("ix_content_draft_course_status", table_name="content_draft")
    op.drop_index("ix_content_draft_generated_by_user_id", table_name="content_draft")
    op.drop_index("ix_content_draft_status", table_name="content_draft")
    op.drop_index("ix_content_draft_course_id", table_name="content_draft")
    op.drop_index("ix_content_draft_tenant_id", table_name="content_draft")
    op.drop_table("content_draft")
    postgresql.ENUM(name="content_draft_status").drop(op.get_bind(), checkfirst=True)
