"""Add generation-progress columns to content_request (Mentible progress webhook).

The Mentible progress webhook drives a commissioned request through
``REQUESTED → GENERATING`` and reports completion percent + ETA while the
package is being manufactured (and ``→ FAILED`` if generation is abandoned).
The ``generating``/``failed`` enum values already exist (0003); this only adds
the two nullable progress columns and a 0–100 range check on the percent.

Revision ID: 0005_content_request_progress
Revises: 0004_user_manager_fk
Create Date: 2026-08-05 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_content_request_progress"
down_revision: str | None = "0004_user_manager_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The naming convention (db/base.py) is applied by alembic on *both* create and
# drop, expanding this suffix to the full ``ck_content_request_progress_pct_range``.
# Pass the suffix (not the resolved name) to both, or it double-prefixes.
_CK = "progress_pct_range"


def upgrade() -> None:
    op.add_column(
        "content_request",
        sa.Column(
            "progress_pct",
            sa.SmallInteger(),
            nullable=True,
            comment="Generation completion percent (0-100), last reported by Mentible.",
        ),
    )
    op.add_column(
        "content_request",
        sa.Column(
            "progress_eta",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Estimated generation-completion time, last reported by Mentible.",
        ),
    )
    op.create_check_constraint(
        _CK,
        "content_request",
        "progress_pct IS NULL OR (progress_pct >= 0 AND progress_pct <= 100)",
    )


def downgrade() -> None:
    op.drop_constraint(_CK, "content_request", type_="check")
    op.drop_column("content_request", "progress_eta")
    op.drop_column("content_request", "progress_pct")
