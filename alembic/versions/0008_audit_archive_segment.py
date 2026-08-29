"""Track which audit ranges have been mirrored to WORM storage.

Bookkeeping for :mod:`pramana.services.audit_archive`. Two questions the bucket
answers badly: where the last run got to, so the next resumes instead of
re-reading the whole log, and whether the archive is complete — which a
compliance product should answer from its own database rather than a listing.

Not append-only: unlike ``audit_log`` this is derived state, and losing it costs
a re-scan, not evidence.

Revision ID: 0008_audit_archive_segment
Revises: 0007_seed_roles
Create Date: 2026-08-29 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_audit_archive_segment"
down_revision: str | None = "0007_seed_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_archive_segment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("first_audit_id", sa.BigInteger(), nullable=False),
        sa.Column("last_audit_id", sa.BigInteger(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("prev_audit_hash", sa.String(64), nullable=True),
        sa.Column("head_audit_hash", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_audit_archive_segment_last_audit_id",
        "audit_archive_segment",
        ["last_audit_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_archive_segment_last_audit_id", "audit_archive_segment")
    op.drop_table("audit_archive_segment")
