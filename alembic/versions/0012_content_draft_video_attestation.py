"""Fidelity attestation over a draft's rendered video (SOX video pilot).

Approval already freezes the *body* — ``content_hash``, ``approved_by_user_id``,
``approved_at`` — and attests that each claim is accurate and cites its section.
That says nothing about whether generated footage depicts what was approved,
which is a different question and the one that catches hallucinated on-screen
text or a person performing the wrong action.

These four columns hold the second answer. They cannot reuse the approval
columns: those hold one approver and one hash, so writing the video sign-off
there would destroy the evidence that the script was approved separately.

The CHECKs mirror the script gate, including its null-generator escape —
``generated_by_user_id`` is nullable, and without that clause a draft with no
recorded generator could never be attested. The third CHECK has no counterpart
above and is deliberate: an attestation naming no artefact attests to nothing.

Revision ID: 0012_video_attestation
Revises: 0011_audit_log_no_truncate
Create Date: 2026-09-09 17:00:00

Note on the revision id: ``alembic_version.version_num`` is ``VARCHAR(32)``
(Alembic's own default, not something this repo's migrations manage). The
brief's literal id, ``0012_content_draft_video_attestation``, is 36
characters and does not fit — ``alembic upgrade head`` fails with
``StringDataRightTruncationError`` writing that row. Shortened to
``0012_video_attestation`` (22 chars), verified to fit and to round-trip
in both directions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0012_video_attestation"
down_revision: str | None = "0011_audit_log_no_truncate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "content_draft"


def upgrade() -> None:
    # The learner-facing transcript. Narration is out of scope for the pilot, so
    # without this the footage reaches a learner silent and wordless.
    op.add_column("course_version", sa.Column("transcript", sa.Text(), nullable=True))
    op.add_column(_TABLE, sa.Column("video_asset_hash", sa.Text(), nullable=True))
    op.add_column(
        _TABLE,
        sa.Column("video_attested_by_user_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        _TABLE, sa.Column("video_attested_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(_TABLE, sa.Column("video_attestation_text", sa.Text(), nullable=True))
    # None: the metadata naming convention generates the FK name. Passing an
    # explicit one risks double-prefixing, same as the CHECKs below.
    op.create_foreign_key(
        None,
        _TABLE,
        "user_account",
        ["video_attested_by_user_id"],
        ["user_id"],
        ondelete="RESTRICT",
    )
    # SUFFIX ONLY — the naming convention prefixes ck_content_draft_. Passing a
    # pre-prefixed name yields ck_content_draft_ck_content_draft_... See how
    # 0010 does it: op.create_check_constraint("view_count_nonneg", ...).
    op.create_check_constraint(
        "video_attestation_pair",
        _TABLE,
        "(video_attested_by_user_id IS NULL) = (video_attested_at IS NULL)",
    )
    op.create_check_constraint(
        "video_separation_of_duties",
        _TABLE,
        "video_attested_by_user_id IS NULL "
        "OR generated_by_user_id IS NULL "
        "OR video_attested_by_user_id <> generated_by_user_id",
    )
    op.create_check_constraint(
        "video_attestation_needs_asset",
        _TABLE,
        "video_attested_at IS NULL OR video_asset_hash IS NOT NULL",
    )


def downgrade() -> None:
    # No explicit constraint drops: Postgres drops a CHECK or FK automatically
    # with the column it references, which also sidesteps having to name them.
    op.drop_column(_TABLE, "video_attestation_text")
    op.drop_column(_TABLE, "video_attested_at")
    op.drop_column(_TABLE, "video_attested_by_user_id")
    op.drop_column(_TABLE, "video_asset_hash")
    op.drop_column("course_version", "transcript")
