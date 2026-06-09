"""Create phase: content_request table (commission content → Mentible).

Adds the Package Request record (US-PLATFORM-0003): the spec an author submits
to commission content, pushed to Mentible and tracked until the manufactured
package is ingested as a content_draft and published.

Revision ID: 0003_content_request
Revises: 0002_content_draft
Create Date: 2026-06-07 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_content_request"
down_revision: str | None = "0002_content_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    content_request_status = postgresql.ENUM(
        "requested",
        "generating",
        "received",
        "in_review",
        "published",
        "failed",
        name="content_request_status",
    )
    content_request_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "content_request",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("framework", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="content_request_status", create_type=False),
            nullable=False,
            server_default="requested",
        ),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("spec", postgresql.JSONB(), nullable=False),
        sa.Column(
            "course_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_draft.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "regenerated_from_draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_draft.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
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
    )
    op.create_index("ix_content_request_tenant_id", "content_request", ["tenant_id"])
    op.create_index("ix_content_request_framework", "content_request", ["framework"])
    op.create_index("ix_content_request_status", "content_request", ["status"])
    op.create_index("ix_content_request_course_id", "content_request", ["course_id"])
    op.create_index(
        "ix_content_request_tenant_status", "content_request", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_content_request_tenant_framework",
        "content_request",
        ["tenant_id", "framework"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_request_tenant_framework", table_name="content_request")
    op.drop_index("ix_content_request_tenant_status", table_name="content_request")
    op.drop_index("ix_content_request_course_id", table_name="content_request")
    op.drop_index("ix_content_request_status", table_name="content_request")
    op.drop_index("ix_content_request_framework", table_name="content_request")
    op.drop_index("ix_content_request_tenant_id", table_name="content_request")
    op.drop_table("content_request")
    postgresql.ENUM(name="content_request_status").drop(op.get_bind(), checkfirst=True)
