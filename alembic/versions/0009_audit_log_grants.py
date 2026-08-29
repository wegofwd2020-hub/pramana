"""Narrow the application role's rights on ``audit_log`` (TICKETS/PR-1).

``SECURITY.md`` §3 requires that the application role hold no UPDATE or DELETE on
the audit table, so the append-only guarantee does not rest on the triggers
alone. There is a limit on what a migration can do about that, and it is worth
stating plainly rather than pretending the ticket is closed by running this.

In Postgres, **an object's owner keeps its privileges regardless of REVOKE.** If
the application connects as the same role that owns the schema — which is the
default single-role deployment, and what every environment here does today —
revoking from it achieves nothing. The control genuinely requires two roles: an
owner that runs migrations, and a lower-privilege role the application connects
as. That is a deployment topology, not a schema change.

So this migration applies the grants when ``APP_DB_ROLE`` names a separate role
and skips cleanly when it does not. The triggers from ``0001`` and the hash
chain remain the defences that always apply.

Revision ID: 0009_audit_log_grants
Revises: 0008_audit_archive_segment
Create Date: 2026-08-29 00:00:00
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from alembic import op

from pramana.config import get_settings

# revision identifiers, used by Alembic.
revision: str = "0009_audit_log_grants"
down_revision: str | None = "0008_audit_archive_segment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Role names cannot be bound as parameters in GRANT/REVOKE, so the identifier is
#: interpolated. Restrict it to what a plain identifier can contain rather than
#: trusting configuration to be well formed.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _app_role() -> str | None:
    role = get_settings().app_db_role.strip()
    if not role:
        return None
    if not _IDENTIFIER.match(role):
        raise ValueError(
            f"APP_DB_ROLE {role!r} is not a plain SQL identifier; refusing to "
            f"interpolate it into a GRANT statement"
        )
    return role


def upgrade() -> None:
    role = _app_role()
    if role is None:
        print("APP_DB_ROLE is unset — skipping audit_log grants (single-role deploy).")
        return
    op.execute(f"GRANT SELECT, INSERT ON audit_log TO {role};")
    op.execute(f"REVOKE UPDATE, DELETE ON audit_log FROM {role};")
    # The archive bookkeeping is ordinary derived state, not evidence.
    op.execute(f"GRANT SELECT, INSERT ON audit_archive_segment TO {role};")


def downgrade() -> None:
    role = _app_role()
    if role is None:
        return
    op.execute(f"GRANT UPDATE, DELETE ON audit_log TO {role};")
