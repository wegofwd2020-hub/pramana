"""HTTP-level tests for the auditor CSV exports."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pramana.api.app import create_app
from pramana.api.dependencies import get_db_session, get_principal
from pramana.db.models.audit import AuditLog
from pramana.db.models.identity import RoleName, User
from pramana.services import assignments as assign_svc
from pramana.services.auth import Principal
from tests.integration.conftest import seed_course

pytestmark = pytest.mark.integration

T1 = datetime(2026, 3, 1, tzinfo=UTC)
T3 = datetime(2026, 5, 1, tzinfo=UTC)


async def _auditor_user(db: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """A real user row — audit_log.actor_user_id carries a foreign key."""
    user = User(user_id=uuid.uuid4(), tenant_id=tenant_id, email=f"{uuid.uuid4()}@x.com")
    db.add(user)
    await db.commit()
    return user.user_id


def _client(
    sessions: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: frozenset[str] = frozenset({RoleName.AUDITOR}),
) -> TestClient:
    app = create_app()

    async def _override_session():
        async with sessions() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_session
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=user_id, tenant_id=tenant_id, roles=roles
    )
    return TestClient(app)


def _rows(body: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(body)))


async def _assign(db: AsyncSession, seed: object, *, now: datetime = T1) -> None:
    await assign_svc.create_assignment(
        db,
        tenant_id=seed.tenant_id,  # type: ignore[attr-defined]
        user_id=seed.user_id,  # type: ignore[attr-defined]
        course_id=seed.course_id,  # type: ignore[attr-defined]
        assigned_by_user_id=None,
        due_at=None,
        now=now,
    )
    await db.commit()


class TestCsvResponses:
    async def test_population_returns_csv_with_a_download_name(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db, n_questions=2)
        await _assign(db, seed)

        resp = _client(
            sessions, tenant_id=seed.tenant_id, user_id=await _auditor_user(db, seed.tenant_id)
        ).get("/exports/population")

        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")
        assert "population.csv" in resp.headers["content-disposition"]
        rows = _rows(resp.text)
        assert rows[0]["user_email"]
        assert rows[0]["courses_assigned"] == "1"

    async def test_empty_report_still_has_a_header_row(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """A zero-byte file cannot be told apart from a broken export."""
        seed = await seed_course(db, n_questions=2)

        resp = _client(
            sessions, tenant_id=seed.tenant_id, user_id=await _auditor_user(db, seed.tenant_id)
        ).get("/exports/exception-report")

        assert resp.status_code == 200
        assert resp.text.strip() == ",".join(
            [
                "user_id",
                "user_email",
                "course_id",
                "course_title",
                "status",
                "due_at",
                "reason",
                "as_of",
            ]
        )

    async def test_training_matrix_requires_a_period(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db, n_questions=2)
        client = _client(
            sessions, tenant_id=seed.tenant_id, user_id=await _auditor_user(db, seed.tenant_id)
        )
        assert client.get("/exports/training-matrix").status_code == 422


class TestAsOfBoundary:
    async def test_as_of_includes_the_named_day(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """`as_of=2026-03-01` must include what happened *during* the 1st.

        Treating the date as midnight would silently drop the day the auditor
        asked about — an off-by-one that reads as "no training happened".
        """
        seed = await seed_course(db, n_questions=2)
        await _assign(db, seed, now=datetime(2026, 3, 1, 14, 30, tzinfo=UTC))

        client = _client(
            sessions, tenant_id=seed.tenant_id, user_id=await _auditor_user(db, seed.tenant_id)
        )
        same_day = client.get("/exports/population?as_of=2026-03-01")
        day_before = client.get("/exports/population?as_of=2026-02-28")

        assert len(_rows(same_day.text)) == 1
        assert len(_rows(day_before.text)) == 0


class TestExportIsAudited:
    async def test_running_an_export_appends_an_audit_entry(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """US-SOX-0006 AC3: auditor access to evidence is itself logged."""
        seed = await seed_course(db, n_questions=2)
        await _assign(db, seed)

        _client(
            sessions, tenant_id=seed.tenant_id, user_id=await _auditor_user(db, seed.tenant_id)
        ).get("/exports/population")

        events = (
            (await db.execute(select(AuditLog).where(AuditLog.event_type == "export.population")))
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].payload["row_count"] == 1
        assert events[0].actor_user_id is not None
