"""The application role cannot rewrite history (TICKETS/PR-1).

``SECURITY.md`` §3 requires that the role the application connects as holds no
UPDATE or DELETE on ``audit_log``, so the append-only guarantee does not rest on
the trigger alone. Migration ``0009`` issues those grants — but only when
``APP_DB_ROLE`` names a role that does not own the schema, because **in Postgres
an object's owner keeps its privileges regardless of REVOKE**.

That conditional is exactly why this file exists. A migration that silently
skips is indistinguishable from a migration that worked, and the ticket has been
open on the strength of "the code side is done". These tests build the real
two-role topology against a real Postgres and prove the boundary holds.

**The assertion that matters is the error code, not the failure.** An UPDATE on
``audit_log`` can be refused by two independent controls:

* the privilege system — ``InsufficientPrivilege``, SQLSTATE **42501**
* the ``audit_log_immutable()`` trigger from ``0001`` — ``RaiseException``,
  SQLSTATE **P0001**

Postgres checks privileges *before* firing triggers, so the two are
distinguishable, and only 42501 proves the REVOKE is real. A test that accepted
either would pass just as happily with no grants applied at all — which is the
state every deployment is in today.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import _db_url

pytestmark = pytest.mark.integration

#: A role that owns nothing — the whole point. Named for the test so a stray one
#: left behind by a crashed run is obvious.
APP_ROLE = "pramana_app_undertest"
APP_PASSWORD = "pr1-acceptance"

#: SQLSTATEs, spelled out because the distinction is the test.
INSUFFICIENT_PRIVILEGE = "42501"
RAISE_EXCEPTION = "P0001"


def _dsn(url: str) -> str:
    """SQLAlchemy URL -> plain libpq DSN for asyncpg."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _owner_conn() -> asyncpg.Connection:
    return await asyncpg.connect(_dsn(_db_url()))


@pytest_asyncio.fixture
async def tenant_id(db: AsyncSession) -> uuid.UUID:
    """A tenant for the audit rows' FK, created by the OWNER.

    Deliberately not created by the app role: ``0009`` grants it nothing on
    ``tenant``, and that is correct. Needing the owner here is a small proof
    that the app role's rights really are narrow.
    """
    owner = await _owner_conn()
    try:
        tid = uuid.uuid4()
        await owner.execute(
            "INSERT INTO tenant (id, name, short_code) VALUES ($1, $2, $3)",
            tid,
            f"PR1 {tid}",
            uuid.uuid4().hex[:12],
        )
        return tid
    finally:
        await owner.close()


@pytest_asyncio.fixture
async def app_role_conn(db: AsyncSession) -> AsyncIterator[asyncpg.Connection]:
    """A connection as a non-owning role carrying exactly migration 0009's grants.

    Depends on ``db`` so the schema exists first: the grants name tables, and
    ``create_all`` runs in that fixture.
    """
    owner = await _owner_conn()
    # A role left behind by a crashed run must not fail the next one.
    with contextlib.suppress(asyncpg.exceptions.UndefinedObjectError):
        await owner.execute(f"DROP OWNED BY {APP_ROLE} CASCADE")
    await owner.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
    await owner.execute(f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}'")
    await owner.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")

    # Exactly what 0009 applies, and nothing else.
    await owner.execute(f"GRANT SELECT, INSERT ON audit_log TO {APP_ROLE}")
    await owner.execute(f"REVOKE UPDATE, DELETE ON audit_log FROM {APP_ROLE}")
    await owner.execute(f"GRANT SELECT, INSERT ON audit_archive_segment TO {APP_ROLE}")
    # audit_id is a sequence-backed identity; INSERT is useless without it.
    await owner.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")

    dsn = _dsn(_db_url())
    app_dsn = dsn.replace("//pramana:pramana@", f"//{APP_ROLE}:{APP_PASSWORD}@")
    conn = await asyncpg.connect(app_dsn)
    try:
        yield conn
    finally:
        await conn.close()
        await owner.execute(f"DROP OWNED BY {APP_ROLE} CASCADE")
        await owner.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
        await owner.close()


async def _seed_row(conn: asyncpg.Connection, tenant_id: uuid.UUID) -> int:
    """Insert one audit row directly and return its id."""
    return await conn.fetchval(
        """
        INSERT INTO audit_log (tenant_id, entity_type, entity_id, event_type,
                               payload, occurred_at, audit_hash)
        VALUES ($1, 'test', 'e1', 'test.event', '{}'::jsonb, now(), $2)
        RETURNING audit_id
        """,
        tenant_id,
        uuid.uuid4().hex,
    )


class TestApplicationRoleCannotRewriteHistory:
    async def test_the_app_role_can_still_read_and_append(
        self, app_role_conn: asyncpg.Connection, tenant_id: uuid.UUID
    ) -> None:
        """The control must not break the thing the application actually does."""
        audit_id = await _seed_row(app_role_conn, tenant_id)
        assert audit_id is not None
        found = await app_role_conn.fetchval(
            "SELECT count(*) FROM audit_log WHERE audit_id = $1", audit_id
        )
        assert found == 1

    async def test_update_is_refused_by_privilege_not_by_trigger(
        self, app_role_conn: asyncpg.Connection, tenant_id: uuid.UUID
    ) -> None:
        """42501 — the REVOKE is real, independent of the append-only trigger."""
        audit_id = await _seed_row(app_role_conn, tenant_id)
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError) as exc:
            await app_role_conn.execute(
                "UPDATE audit_log SET event_type = 'tampered' WHERE audit_id = $1", audit_id
            )
        assert exc.value.sqlstate == INSUFFICIENT_PRIVILEGE
        assert exc.value.sqlstate != RAISE_EXCEPTION

    async def test_delete_is_refused_by_privilege_not_by_trigger(
        self, app_role_conn: asyncpg.Connection, tenant_id: uuid.UUID
    ) -> None:
        audit_id = await _seed_row(app_role_conn, tenant_id)
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError) as exc:
            await app_role_conn.execute("DELETE FROM audit_log WHERE audit_id = $1", audit_id)
        assert exc.value.sqlstate == INSUFFICIENT_PRIVILEGE

    async def test_the_row_survives_both_attempts(
        self, app_role_conn: asyncpg.Connection, tenant_id: uuid.UUID
    ) -> None:
        """Refusing the statement is only half of it; the evidence must remain."""
        audit_id = await _seed_row(app_role_conn, tenant_id)
        for stmt in (
            "UPDATE audit_log SET event_type = 'tampered' WHERE audit_id = $1",
            "DELETE FROM audit_log WHERE audit_id = $1",
        ):
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await app_role_conn.execute(stmt, audit_id)

        row = await app_role_conn.fetchrow(
            "SELECT event_type FROM audit_log WHERE audit_id = $1", audit_id
        )
        assert row is not None, "the audit row was deleted"
        assert row["event_type"] == "test.event", "the audit row was modified"

    async def test_truncate_is_also_refused(
        self, app_role_conn: asyncpg.Connection, tenant_id: uuid.UUID
    ) -> None:
        """TRUNCATE bypasses row triggers entirely, so only privilege stops it.

        This is the case the trigger genuinely cannot cover: ``audit_log_no_delete``
        is FOR EACH ROW, and TRUNCATE fires no row triggers. In a single-role
        deployment the audit table can be emptied in one statement.
        """
        await _seed_row(app_role_conn, tenant_id)
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError) as exc:
            await app_role_conn.execute("TRUNCATE audit_log")
        assert exc.value.sqlstate == INSUFFICIENT_PRIVILEGE


class TestTheOwnerIsNotConstrainedByGrants:
    """Why the two-role split is required, demonstrated rather than asserted.

    If this ever fails, the single-role warning in ``SECURITY.md`` §3 and the
    skip in migration ``0009`` have become wrong and both should be revisited.
    """

    async def test_revoking_from_the_owner_does_not_stop_the_owner(
        self, db: AsyncSession, tenant_id: uuid.UUID
    ) -> None:
        owner = await _owner_conn()
        try:
            current = await owner.fetchval("SELECT current_user")
            await owner.execute(f"REVOKE UPDATE, DELETE ON audit_log FROM {current}")
            audit_id = await _seed_row(owner, tenant_id)
            # No trigger here: integration schemas come from create_all, which
            # carries no raw DDL. So this is the privilege system alone, and it
            # permits the owner regardless of the REVOKE above.
            await owner.execute(
                "UPDATE audit_log SET event_type = 'owner-can' WHERE audit_id = $1", audit_id
            )
            changed = await owner.fetchval(
                "SELECT event_type FROM audit_log WHERE audit_id = $1", audit_id
            )
            assert changed == "owner-can"
        finally:
            await owner.close()


class TestTruncateIsBlockedForEveryone:
    """The hole migration ``0011`` closes, and the reason it needed closing.

    ``0001``'s append-only triggers are ``FOR EACH ROW``, and row triggers do not
    fire on TRUNCATE. Until ``0011`` the entire audit log could be erased in one
    statement by the owner — which, in the single-role topology every deployment
    actually runs, is the application's own role.
    """

    @staticmethod
    async def _install_0011(conn: asyncpg.Connection) -> None:
        """Apply 0011's DDL (integration schemas come from create_all, not Alembic)."""
        await conn.execute(
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
        await conn.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
        await conn.execute(
            """
            CREATE TRIGGER audit_log_no_truncate
              BEFORE TRUNCATE ON audit_log
              FOR EACH STATEMENT EXECUTE FUNCTION audit_no_truncate();
            """
        )

    async def test_the_owner_cannot_truncate_the_audit_log(
        self, db: AsyncSession, tenant_id: uuid.UUID
    ) -> None:
        """Blocked for the OWNER — the case grants can never cover."""
        owner = await _owner_conn()
        try:
            await self._install_0011(owner)
            await _seed_row(owner, tenant_id)
            before = await owner.fetchval("SELECT count(*) FROM audit_log")

            with pytest.raises(asyncpg.exceptions.RaiseError) as exc:
                await owner.execute("TRUNCATE audit_log")
            assert exc.value.sqlstate == RAISE_EXCEPTION
            assert "append-only evidence" in str(exc.value)

            after = await owner.fetchval("SELECT count(*) FROM audit_log")
            assert after == before, "rows were lost despite the refusal"
        finally:
            await owner.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
            await owner.close()

    async def test_without_0011_the_owner_can_truncate(
        self, db: AsyncSession, tenant_id: uuid.UUID
    ) -> None:
        """Pins the vulnerability, so the fix cannot be quietly reverted.

        If this ever fails, TRUNCATE became blocked by something else and 0011's
        rationale should be re-read rather than assumed.
        """
        owner = await _owner_conn()
        try:
            await owner.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
            await _seed_row(owner, tenant_id)
            assert await owner.fetchval("SELECT count(*) FROM audit_log") > 0
            await owner.execute("TRUNCATE audit_log")
            assert await owner.fetchval("SELECT count(*) FROM audit_log") == 0
        finally:
            await owner.close()
