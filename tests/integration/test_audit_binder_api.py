"""HTTP tests for the per-user audit binder PDF."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pramana.api.app import create_app
from pramana.api.dependencies import get_db_session, get_pdf_renderer, get_principal
from pramana.db.models.audit import AuditLog
from pramana.db.models.identity import RoleName, User
from pramana.services import assignments as assign_svc
from pramana.services.auth import Principal
from tests.integration.conftest import seed_course

pytestmark = pytest.mark.integration

T1 = datetime(2026, 3, 1, tzinfo=UTC)
T3 = datetime(2026, 5, 1, tzinfo=UTC)
PERIOD = "period_start=2026-01-01&period_end=2026-12-31"


class SpyRenderer:
    def __init__(self) -> None:
        self.html: str | None = None

    def __call__(self, html: str) -> bytes:
        self.html = html
        return b"%PDF-1.7 binder"


def _client(
    sessions: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    renderer: SpyRenderer,
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
    app.dependency_overrides[get_pdf_renderer] = lambda: renderer
    return TestClient(app)


async def _auditor(db: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    user = User(user_id=uuid.uuid4(), tenant_id=tenant_id, email=f"{uuid.uuid4()}@x.com")
    db.add(user)
    await db.commit()
    return user.user_id


async def _earn(db: AsyncSession, seed: object) -> None:
    a = await assign_svc.create_assignment(
        db,
        tenant_id=seed.tenant_id,  # type: ignore[attr-defined]
        user_id=seed.user_id,  # type: ignore[attr-defined]
        course_id=seed.course_id,  # type: ignore[attr-defined]
        assigned_by_user_id=None,
        due_at=None,
        now=T1,
    )
    await db.flush()
    await assign_svc.start_attempt(
        db,
        assignment_id=a.id,
        tenant_id=seed.tenant_id,  # type: ignore[attr-defined]
        acting_user_id=seed.user_id,  # type: ignore[attr-defined]
        now=T1,
    )
    await assign_svc.submit_attempt(
        db,
        assignment_id=a.id,
        tenant_id=seed.tenant_id,  # type: ignore[attr-defined]
        acting_user_id=seed.user_id,  # type: ignore[attr-defined]
        answers={
            qid: [c]
            for qid, (c, _w) in seed.questions.items()  # type: ignore[attr-defined]
        },
        attestation=assign_svc.Attestation(text_version="v1", accepted=True),
        now=T3,
    )
    await db.commit()


class TestBinder:
    async def test_returns_a_pdf(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db, n_questions=2)
        await _earn(db, seed)
        spy = SpyRenderer()

        resp = _client(
            sessions,
            tenant_id=seed.tenant_id,
            user_id=await _auditor(db, seed.tenant_id),
            renderer=spy,
        ).get(f"/exports/users/{seed.user_id}/audit-binder?{PERIOD}")

        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"
        assert "audit-binder-sox" in resp.headers["content-disposition"]

    async def test_the_document_carries_the_evidence(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """Attestation in particular — SOX §6.3 asks for it by name."""
        seed = await seed_course(db, n_questions=2)
        await _earn(db, seed)
        spy = SpyRenderer()

        _client(
            sessions,
            tenant_id=seed.tenant_id,
            user_id=await _auditor(db, seed.tenant_id),
            renderer=spy,
        ).get(f"/exports/users/{seed.user_id}/audit-binder?{PERIOD}")

        assert spy.html is not None
        assert str(seed.course_version_id) in spy.html
        assert "v1" in spy.html
        assert "404" in spy.html
        assert "Not covered by this binder" in spy.html

    async def test_framework_selects_the_framing(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db, n_questions=2)
        await _earn(db, seed)
        spy = SpyRenderer()

        _client(
            sessions,
            tenant_id=seed.tenant_id,
            user_id=await _auditor(db, seed.tenant_id),
            renderer=spy,
        ).get(f"/exports/users/{seed.user_id}/audit-binder?{PERIOD}&framework=hipaa")

        assert spy.html is not None
        assert "164.530(b)" in spy.html

    async def test_an_unknown_framework_is_rejected(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db, n_questions=2)
        resp = _client(
            sessions,
            tenant_id=seed.tenant_id,
            user_id=await _auditor(db, seed.tenant_id),
            renderer=SpyRenderer(),
        ).get(f"/exports/users/{seed.user_id}/audit-binder?{PERIOD}&framework=wizardry")
        assert resp.status_code == 404

    async def test_a_period_is_required(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db, n_questions=2)
        resp = _client(
            sessions,
            tenant_id=seed.tenant_id,
            user_id=await _auditor(db, seed.tenant_id),
            renderer=SpyRenderer(),
        ).get(f"/exports/users/{seed.user_id}/audit-binder")
        assert resp.status_code == 422


class TestTenantIsolation:
    async def test_a_user_in_another_tenant_is_not_found(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """An auditor must not be able to bind a subject outside their tenant.

        Regression guard: the binder is assembled before the subject's display
        name is looked up, so this pins the refusal at the boundary rather than
        relying on the ordering of two statements staying as it is.
        """
        mine = await seed_course(db, n_questions=2)
        theirs = await seed_course(db, n_questions=2)
        await _earn(db, theirs)

        resp = _client(
            sessions,
            tenant_id=mine.tenant_id,
            user_id=await _auditor(db, mine.tenant_id),
            renderer=SpyRenderer(),
        ).get(f"/exports/users/{theirs.user_id}/audit-binder?{PERIOD}")

        assert resp.status_code == 404

    async def test_no_cross_tenant_binder_is_audited(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """A refused request must not leave an export event naming the subject."""
        mine = await seed_course(db, n_questions=2)
        theirs = await seed_course(db, n_questions=2)

        _client(
            sessions,
            tenant_id=mine.tenant_id,
            user_id=await _auditor(db, mine.tenant_id),
            renderer=SpyRenderer(),
        ).get(f"/exports/users/{theirs.user_id}/audit-binder?{PERIOD}")

        events = (
            (await db.execute(select(AuditLog).where(AuditLog.event_type == "export.audit_binder")))
            .scalars()
            .all()
        )
        assert events == []


class TestAuthorizationAndAudit:
    async def test_a_roleless_caller_is_refused(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db, n_questions=2)
        resp = _client(
            sessions,
            tenant_id=seed.tenant_id,
            user_id=await _auditor(db, seed.tenant_id),
            renderer=SpyRenderer(),
            roles=frozenset(),
        ).get(f"/exports/users/{seed.user_id}/audit-binder?{PERIOD}")
        assert resp.status_code == 403

    async def test_producing_a_binder_is_audited(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db, n_questions=2)
        await _earn(db, seed)
        auditor = await _auditor(db, seed.tenant_id)

        _client(sessions, tenant_id=seed.tenant_id, user_id=auditor, renderer=SpyRenderer()).get(
            f"/exports/users/{seed.user_id}/audit-binder?{PERIOD}"
        )

        events = (
            (await db.execute(select(AuditLog).where(AuditLog.event_type == "export.audit_binder")))
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].payload["subject_user_id"] == str(seed.user_id)
        assert events[0].payload["framework"] == "sox"
