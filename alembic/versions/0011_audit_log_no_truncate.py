"""Block TRUNCATE on the audit tables (TICKETS/PR-1).

``0001`` makes ``audit_log`` append-only with ``BEFORE UPDATE`` and
``BEFORE DELETE`` triggers declared ``FOR EACH ROW``. **Row-level triggers do not
fire on TRUNCATE.** Verified against Postgres 16 with exactly that trigger shape:

    UPDATE    blocked   (P0001)
    DELETE    blocked   (P0001)
    TRUNCATE  SUCCEEDED — every row gone

So the append-only guarantee had a hole wide enough to erase the whole audit log
in one statement, and the hash chain cannot help: it proves rows were not
*altered*, and an empty table has no chain to check. The WORM archive still holds
whatever was archived, but everything since the last segment is simply gone.

``0009`` is not the answer on its own. It revokes rights from ``APP_DB_ROLE``,
which is unset in every deployment to date (``SECURITY.md`` §3 records that the
two-role split has never been adopted), and an owner keeps its privileges
regardless of REVOKE. This trigger is deployment-independent: a ``FOR EACH
STATEMENT`` trigger fires for **everyone, including the owner**, so the control
holds in the single-role topology that is actually running.

It does not replace the two-role split — a superuser can still drop this trigger,
which is precisely what the app role must not be able to do. It closes the gap
that exists today rather than the one that exists after a migration nobody has
run.

Dropping the trigger deliberately (to rotate or repair the table) is a two-step
operation an operator must perform consciously, which is the intent.

Revision ID: 0011_audit_log_no_truncate
Revises: 0010_consumer_subscription
Create Date: 2026-09-08 19:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_audit_log_no_truncate"
down_revision: str | None = "0010_consumer_subscription"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The evidence tables. ``audit_archive_segment`` is included because losing the
#: segment manifests would break the "is a whole segment missing?" check that
#: makes the archive worth having.
_PROTECTED = ("audit_log", "audit_archive_segment")


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_no_truncate()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION
            'truncating % is not permitted: it is append-only evidence', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in _PROTECTED:
        op.execute(
            f"""
            CREATE TRIGGER {table}_no_truncate
              BEFORE TRUNCATE ON {table}
              FOR EACH STATEMENT EXECUTE FUNCTION audit_no_truncate();
            """
        )


def downgrade() -> None:
    for table in _PROTECTED:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table};")
    op.execute("DROP FUNCTION IF EXISTS audit_no_truncate();")
