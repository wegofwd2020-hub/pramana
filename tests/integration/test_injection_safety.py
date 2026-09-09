"""Hostile input reaches the database as data, never as syntax.

``tests/test_no_string_built_sql.py`` proves no query is assembled from
strings. This proves the consequence against a real Postgres: caller-supplied
values land in ``WHERE`` clauses and columns as bound parameters, so a payload
that would end a statement and start another simply fails to match anything.

:func:`~pramana.services.audit_query.search_audit` is the target because it is
the widest caller-controlled surface in the codebase — an auditor supplies
``entity_type``, ``entity_id`` and ``event_type`` as free text and they go
straight into the filter list.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.audit import AuditLog
from pramana.db.models.identity import Tenant
from pramana.db.session import session_scope
from pramana.exceptions import DatabaseError
from pramana.services.audit import append_audit
from pramana.services.audit_query import search_audit

pytestmark = pytest.mark.integration

#: Payloads that end the current statement, comment out the rest, or flip a
#: predicate — the shapes that work when a query is built by concatenation.
HOSTILE = [
    pytest.param("'; DROP TABLE audit_log; --", id="drop-table"),
    pytest.param("' OR '1'='1", id="tautology"),
    pytest.param('" OR 1=1 --', id="double-quote-tautology"),
    pytest.param("'; DELETE FROM audit_log WHERE 't'='t", id="delete-all"),
    pytest.param("1; SELECT pg_sleep(10)", id="stacked-sleep"),
    pytest.param("%", id="like-wildcard"),
    pytest.param("_", id="like-single-wildcard"),
    pytest.param("\\", id="backslash"),
]

#: Not an injection vector — Postgres refuses a NUL byte in UTF8 text even as a
#: bound parameter — but it is the cheapest way for a caller to provoke a real
#: driver error, which is the path that used to leak the statement and every
#: bound value into the response body.
NUL_PAYLOAD = "\x00truncated"


async def _seed_entry(session: AsyncSession, tenant_id: uuid.UUID, **overrides) -> None:
    fields = {
        "entity_type": "course",
        "entity_id": "c-1",
        "event_type": "course.published",
    }
    fields.update(overrides)
    await append_audit(
        session,
        tenant_id=tenant_id,
        payload={"k": "v"},
        occurred_at=datetime.now(UTC),
        **fields,
    )
    await session.commit()


@pytest.fixture
async def tenant_id(db: AsyncSession) -> uuid.UUID:
    tenant = Tenant(id=uuid.uuid4(), name="Injection Co", short_code=uuid.uuid4().hex[:12])
    db.add(tenant)
    await db.commit()
    return tenant.id


class TestHostileFiltersAreInertData:
    @pytest.mark.parametrize("payload", HOSTILE)
    async def test_hostile_filter_matches_nothing_and_changes_nothing(
        self, db: AsyncSession, tenant_id: uuid.UUID, payload: str
    ) -> None:
        """The payload is compared against the column, not executed."""
        await _seed_entry(db, tenant_id)
        before = (await db.execute(select(func.count()).select_from(AuditLog))).scalar_one()

        rows, total = await search_audit(db, tenant_id=tenant_id, entity_type=payload)

        assert rows == [] and total == 0
        after = (await db.execute(select(func.count()).select_from(AuditLog))).scalar_one()
        assert after == before, "the filter modified data — it was executed, not bound"

    async def test_a_tautology_does_not_widen_the_tenant_scope(
        self, db: AsyncSession, tenant_id: uuid.UUID
    ) -> None:
        """The classic payload: make the WHERE always true and read everyone's rows.

        Tenant isolation is enforced in the same filter list, so if the payload
        were syntax rather than data this would return the other tenant's entry.
        """
        other = Tenant(id=uuid.uuid4(), name="Other Co", short_code=uuid.uuid4().hex[:12])
        db.add(other)
        await db.commit()
        await _seed_entry(db, tenant_id)
        await _seed_entry(db, other.id, entity_id="secret-of-other-tenant")

        rows, total = await search_audit(db, tenant_id=tenant_id, entity_id="' OR '1'='1")

        assert total == 0
        assert all(r.entity_id != "secret-of-other-tenant" for r in rows)

    async def test_the_table_still_exists_after_every_payload(
        self, db: AsyncSession, tenant_id: uuid.UUID
    ) -> None:
        """A dropped table would make later assertions error rather than fail."""
        for param in HOSTILE:
            await search_audit(db, tenant_id=tenant_id, event_type=param.values[0])
        assert (
            await db.execute(select(func.count()).select_from(AuditLog))
        ).scalar_one() is not None


class TestARealDriverErrorIsRedacted:
    """The other half of PR-4, proved with a genuine failure rather than a fake.

    ``tests/db/test_session_error_redaction.py`` synthesises an
    ``IntegrityError``. This provokes one from the actual driver and checks what
    a caller would be told.
    """

    async def test_nul_byte_yields_an_opaque_error_with_an_incident_id(
        self, sessions, tenant_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("pramana.db.session.get_sessionmaker", lambda: sessions)

        with pytest.raises(DatabaseError) as ei:
            async with session_scope() as session:
                await search_audit(session, tenant_id=tenant_id, event_type=NUL_PAYLOAD)

        message = ei.value.message
        assert "[SQL:" not in message
        assert "[parameters:" not in message
        assert "audit_log" not in message
        assert str(tenant_id) not in message
        assert isinstance(ei.value.incident_id, uuid.UUID)


class TestHostileValuesRoundTripVerbatim:
    @pytest.mark.parametrize("payload", HOSTILE)
    async def test_stored_hostile_text_comes_back_byte_for_byte(
        self, db: AsyncSession, tenant_id: uuid.UUID, payload: str
    ) -> None:
        """Storage must neither execute the payload nor quietly mangle it.

        Silent escaping would be its own bug: an auditor's evidence must read
        back exactly as written.
        """
        await _seed_entry(db, tenant_id, entity_id=payload)

        rows, total = await search_audit(db, tenant_id=tenant_id, entity_id=payload)

        assert total == 1
        assert rows[0].entity_id == payload
