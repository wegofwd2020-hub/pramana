"""Add watched_pct to assignment (course-player watch-gate).

The learner runtime's player (US-PLATFORM-0002) tracks the furthest watched
position of the pinned CourseVersion so the quiz can be gated on
``min_watch_pct`` and watch progress resumes on return. One nullable-free
SmallInteger column with a 0-100 range check; monotonic updates are enforced
in the service, not the schema.

Revision ID: 0006_assignment_watch_progress
Revises: 0005_content_request_progress
Create Date: 2026-08-05 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_assignment_watch_progress"
down_revision: str | None = "0005_content_request_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Suffix only — the naming convention (db/base.py) prefixes ``ck_assignment_``
# on both create and drop.
_CK = "watched_pct_range"


def upgrade() -> None:
    op.add_column(
        "assignment",
        sa.Column(
            "watched_pct",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(_CK, "assignment", "watched_pct BETWEEN 0 AND 100")


def downgrade() -> None:
    op.drop_constraint(_CK, "assignment", type_="check")
    op.drop_column("assignment", "watched_pct")
