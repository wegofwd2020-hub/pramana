"""Consumable-package ingestion: RECEIVED state + package columns on content_draft.

Pramana's side of the Mentible ADR-011 handoff contract. Adds the ``received``
lifecycle value (the entry state for an ingested package) and the columns that
record a delivered package on the draft: engine provenance, the package
id/version (idempotency key), the manifest content hash, and the signature.

See docs/03_ai_drafted_human_approved_content.md §5 and Mentible ADR-011
(StudyBuddy_SelfLearner/docs/adr/ADR-011-pramana-compliance-integration.md).

Revision ID: 0003_consumable_package_ingestion
Revises: 0002_content_draft
Create Date: 2026-06-05 13:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_consumable_package_ingestion"
down_revision: str | None = "0002_content_draft"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Extend the lifecycle enum with the ingestion entry state. PG 12+ allows
    #    ADD VALUE inside a transaction as long as the value is not *used* in the
    #    same transaction (we only define it here).
    op.execute("ALTER TYPE content_draft_status ADD VALUE IF NOT EXISTS 'received'")

    # 2. Provenance + ingestion columns.
    op.add_column(
        "content_draft",
        sa.Column("gen_engine", sa.String(60), nullable=True),
    )
    op.add_column(
        "content_draft",
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "content_draft",
        sa.Column("package_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "content_draft",
        sa.Column("package_content_hash", sa.String(128), nullable=True),
    )
    op.add_column(
        "content_draft",
        sa.Column("signature", sa.Text(), nullable=True),
    )

    # 3. package_id / package_version are present together or absent together.
    op.create_check_constraint(
        "ck_content_draft_package_ref_pair",
        "content_draft",
        "(package_id IS NULL) = (package_version IS NULL)",
    )

    # 4. Ingestion idempotency: one draft per delivered (tenant, package, version).
    #    Partial so non-ingested drafts (NULL package_id) never collide.
    op.create_index(
        "uq_content_draft_package",
        "content_draft",
        ["tenant_id", "package_id", "package_version"],
        unique=True,
        postgresql_where=sa.text("package_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_content_draft_package", table_name="content_draft")
    op.drop_constraint(
        "ck_content_draft_package_ref_pair", "content_draft", type_="check"
    )
    op.drop_column("content_draft", "signature")
    op.drop_column("content_draft", "package_content_hash")
    op.drop_column("content_draft", "package_version")
    op.drop_column("content_draft", "package_id")
    op.drop_column("content_draft", "gen_engine")
    # Note: PostgreSQL cannot drop a value from an enum type, so the 'received'
    # value added in upgrade() is intentionally left in place on downgrade.
