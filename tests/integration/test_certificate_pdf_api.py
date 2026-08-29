"""Downloading a certificate as PDF.

The renderer is injected, so these never import WeasyPrint — what is asserted is
the authorization, the response shape, and *what HTML the renderer was handed*,
which is the part that carries the facts.
"""

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


class SpyRenderer:
    """Captures the HTML it was asked to render; returns recognisable bytes."""

    def __init__(self) -> None:
        self.html: str | None = None

    def __call__(self, html: str) -> bytes:
        self.html = html
        return b"%PDF-1.7 fake"


def _client(
    sessions: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    renderer: SpyRenderer,
    roles: frozenset[str] = frozenset(),
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


async def _another_user(db: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    user = User(user_id=uuid.uuid4(), tenant_id=tenant_id, email=f"{uuid.uuid4()}@x.com")
    db.add(user)
    await db.commit()
    return user.user_id


async def _earn_certificate(db: AsyncSession, seed: object) -> uuid.UUID:
    assignment = await assign_svc.create_assignment(
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
        assignment_id=assignment.id,
        tenant_id=seed.tenant_id,  # type: ignore[attr-defined]
        acting_user_id=seed.user_id,  # type: ignore[attr-defined]
        now=T1,
    )
    result = await assign_svc.submit_attempt(
        db,
        assignment_id=assignment.id,
        tenant_id=seed.tenant_id,  # type: ignore[attr-defined]
        acting_user_id=seed.user_id,  # type: ignore[attr-defined]
        answers={
            qid: [correct]
            for qid, (correct, _w) in seed.questions.items()  # type: ignore[attr-defined]
        },
        attestation=assign_svc.Attestation(text_version="v1", accepted=True),
        now=T3,
    )
    await db.commit()
    assert result.certificate is not None
    return result.certificate.id


class TestDownload:
    async def test_owner_gets_a_pdf_with_a_download_name(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db, n_questions=2)
        cert_id = await _earn_certificate(db, seed)
        spy = SpyRenderer()

        resp = _client(sessions, tenant_id=seed.tenant_id, user_id=seed.user_id, renderer=spy).get(
            f"/certificates/{cert_id}/pdf"
        )

        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"
        assert "certificate-" in resp.headers["content-disposition"]
        assert resp.content == b"%PDF-1.7 fake"

    async def test_the_rendered_html_names_the_pinned_version(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """The document must describe the version tested on, not the course."""
        seed = await seed_course(db, n_questions=2)
        cert_id = await _earn_certificate(db, seed)
        spy = SpyRenderer()

        _client(sessions, tenant_id=seed.tenant_id, user_id=seed.user_id, renderer=spy).get(
            f"/certificates/{cert_id}/pdf"
        )

        assert spy.html is not None
        assert str(seed.course_version_id) in spy.html

    async def test_a_missing_certificate_is_404(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db, n_questions=2)
        client = _client(
            sessions, tenant_id=seed.tenant_id, user_id=seed.user_id, renderer=SpyRenderer()
        )
        assert client.get(f"/certificates/{uuid.uuid4()}/pdf").status_code == 404


class TestAuthorization:
    async def test_a_stranger_is_refused(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db, n_questions=2)
        cert_id = await _earn_certificate(db, seed)
        stranger = await _another_user(db, seed.tenant_id)

        resp = _client(
            sessions, tenant_id=seed.tenant_id, user_id=stranger, renderer=SpyRenderer()
        ).get(f"/certificates/{cert_id}/pdf")

        assert resp.status_code == 403

    async def test_an_auditor_may_download_anyones(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db, n_questions=2)
        cert_id = await _earn_certificate(db, seed)
        auditor = await _another_user(db, seed.tenant_id)

        resp = _client(
            sessions,
            tenant_id=seed.tenant_id,
            user_id=auditor,
            renderer=SpyRenderer(),
            roles=frozenset({RoleName.AUDITOR}),
        ).get(f"/certificates/{cert_id}/pdf")

        assert resp.status_code == 200


class TestAuditing:
    async def _downloads(self, db: AsyncSession) -> list[AuditLog]:
        return list(
            (
                await db.execute(
                    select(AuditLog).where(AuditLog.event_type == "certificate.downloaded")
                )
            )
            .scalars()
            .all()
        )

    async def test_third_party_download_is_audited(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """Reading somebody else's certificate is evidence access."""
        seed = await seed_course(db, n_questions=2)
        cert_id = await _earn_certificate(db, seed)
        auditor = await _another_user(db, seed.tenant_id)

        _client(
            sessions,
            tenant_id=seed.tenant_id,
            user_id=auditor,
            renderer=SpyRenderer(),
            roles=frozenset({RoleName.AUDITOR}),
        ).get(f"/certificates/{cert_id}/pdf")

        events = await self._downloads(db)
        assert len(events) == 1
        assert events[0].actor_user_id == auditor
        assert events[0].payload["subject_user_id"] == str(seed.user_id)

    async def test_self_download_is_not_audited(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """Routine self-service would bury the accesses that matter."""
        seed = await seed_course(db, n_questions=2)
        cert_id = await _earn_certificate(db, seed)

        _client(
            sessions, tenant_id=seed.tenant_id, user_id=seed.user_id, renderer=SpyRenderer()
        ).get(f"/certificates/{cert_id}/pdf")

        assert await self._downloads(db) == []
