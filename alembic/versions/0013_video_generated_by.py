"""Record who produced the footage, and bar them from attesting it.

Gate 2 asks whether generated footage depicts the approved script. Its whole
substance is that the person who produced the bytes does not sign off on them —
but the check compared the attester against ``generated_by_user_id``, which is
the *script's* author. ``attach_course_video`` takes a producer id and writes it
only to the audit payload, so the producer was unconstrained: render the footage,
then attest your own render.

This adds the column the check actually needs, plus a CHECK so the rule holds
against any code holding a session, not only against the domain layer.

The column is nullable and the CHECK carries the same null escape as its two
siblings: drafts created before this migration record no producer, and must
stay attestable rather than being retro-blocked.

Revision ID: 0013_video_generated_by
Revises: 0012_video_attestation
Create Date: 2026-09-10 11:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0013_video_generated_by"
down_revision: str | None = "0012_video_attestation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "content_draft"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("video_generated_by_user_id", PG_UUID(as_uuid=True), nullable=True),
    )
    # None: the metadata naming convention generates the FK name.
    op.create_foreign_key(
        None,
        _TABLE,
        "user_account",
        ["video_generated_by_user_id"],
        ["user_id"],
        ondelete="RESTRICT",
    )
    # SUFFIX ONLY — the convention prefixes ck_content_draft_.
    op.create_check_constraint(
        "video_producer_separation_of_duties",
        _TABLE,
        "video_attested_by_user_id IS NULL "
        "OR video_generated_by_user_id IS NULL "
        "OR video_attested_by_user_id <> video_generated_by_user_id",
    )


def downgrade() -> None:
    # Dropping the column takes its CHECK and FK with it.
    op.drop_column(_TABLE, "video_generated_by_user_id")
