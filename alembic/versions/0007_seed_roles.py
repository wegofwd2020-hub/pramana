"""Seed the five fixed roles.

The ``role`` table shipped empty. Once every privileged route was gated on a
role, that left a fresh deployment deadlocked: no roles means no grants, which
means no principal holds anything, which means every administrative route —
including the one that grants roles — refuses everyone. This migration seeds the
reference data so a deployment starts in a usable state.

The list is duplicated in ``pramana.services.roles.ROLE_DESCRIPTIONS`` because
the integration suite builds its schema from the ORM metadata and never runs
Alembic. ``tests/db/test_role_seed.py`` asserts the two agree and that both
cover :class:`~pramana.db.models.identity.RoleName`.

Deliberately frozen: a migration is a historical record, so it hardcodes the set
as of today rather than importing the enum. A sixth role is a new migration.

Revision ID: 0007_seed_roles
Revises: 0006_assignment_watch_progress
Create Date: 2026-08-29 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_seed_roles"
down_revision: str | None = "0006_assignment_watch_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (name, description) for every fixed role. Names must match ``RoleName``.
SEEDED_ROLES: tuple[tuple[str, str], ...] = (
    ("trainee", "Completes assigned training and reads their own records."),
    ("manager", "Assigns and cancels training; reads records across users."),
    (
        "content_author",
        "Commissions content, submits drafts for review, and regenerates them.",
    ),
    (
        "compliance_admin",
        "Approves, rejects, and publishes content; administers role grants.",
    ),
    (
        "auditor",
        "Reads and verifies the audit chain and exports evidence; read-only.",
    ),
)


def upgrade() -> None:
    """Insert the fixed roles, skipping any a deployment already created."""
    for name, description in SEEDED_ROLES:
        op.execute(
            f"""
            INSERT INTO role (id, name, description, created_at, updated_at)
            VALUES (gen_random_uuid(), '{name}', '{description}', now(), now())
            ON CONFLICT (name) DO NOTHING;
            """
        )


def downgrade() -> None:
    """Remove the seeded roles.

    ``user_role.role_id`` is ``ON DELETE RESTRICT``, so this fails loudly if any
    role is still granted rather than silently dropping someone's access.
    """
    names = ", ".join(f"'{name}'" for name, _description in SEEDED_ROLES)
    op.execute(f"DELETE FROM role WHERE name IN ({names});")
