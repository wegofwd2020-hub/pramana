"""Add the missing user_account.manager_user_id self-referential FK.

Migration 0001 declared the manager self-FK inline with ``use_alter=True`` inside
``op.create_table``. Alembic does not post-process ``use_alter`` the way
``MetaData.create_all`` does, so the secondary ALTER was never emitted and the
constraint was silently absent — the column existed and was indexed, but
referential integrity was unenforced (a manager_user_id could point at a
non-existent user, and deleting a manager would not SET NULL on reports).

This adds the constraint after the fact, matching the model
(``User.manager_user_id`` → ``user_account.user_id``, ``ON DELETE SET NULL``).
Editing 0001 in place is avoided since it is already applied elsewhere; a fresh
database now gets the FK via this revision instead.

Revision ID: 0004_user_manager_fk
Revises: 0003_content_request
Create Date: 2026-06-07 13:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_user_manager_fk"
down_revision: str | None = "0003_content_request"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK = "fk_user_account_manager_user_id_user_account"


def upgrade() -> None:
    op.create_foreign_key(
        _FK,
        source_table="user_account",
        referent_table="user_account",
        local_cols=["manager_user_id"],
        remote_cols=["user_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(_FK, "user_account", type_="foreignkey")
