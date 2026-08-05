"""Integration tests for audit verification, search, export, evidence (real PG).

Generates real audit history by running the assignment flow, then verifies the
chain, searches/exports it, and builds an evidence binder. Tampering is
simulated with a raw UPDATE — possible here only because the integration schema
is built from ORM metadata (no ``audit_log_no_update`` trigger); the point is
that the verifier catches what the trigger would otherwise have prevented.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pramana.api.app import create_app
from pramana.api.dependencies import get_db_session, get_principal
from pramana.db.models.audit import AuditLog
from pramana.db.models.identity import RoleName
from pramana.services import assignments as asvc
from pramana.services import audit_query
from pramana.services.auth import Principal
from tests.integration.conftest import SeededCourse, seed_course

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


async def _run_pass_flow(db: AsyncSession, seed: SeededCourse) -> uuid.UUID:
    """Assign + pass, generating a run of audit entries. Returns assignment id."""
    a = await asvc.create_assignment(
        db,
        tenant_id=seed.tenant_id,
        user_id=seed.user_id,
        course_id=seed.course_id,
        assigned_by_user_id=None,
        due_at=None,
        now=NOW,
    )
    await db.commit()
    await asvc.start_attempt(
        db, assignment_id=a.id, tenant_id=seed.tenant_id, acting_user_id=seed.user_id, now=NOW
    )
    await db.commit()
    answers = {qid: [c] for qid, (c, _w) in seed.questions.items()}
    await asvc.submit_attempt(
        db,
        assignment_id=a.id,
        tenant_id=seed.tenant_id,
        acting_user_id=seed.user_id,
        answers=answers,
        attestation=asvc.Attestation("v1", accepted=True),
        now=NOW,
    )
    await db.commit()
    return a.id


class TestVerifyService:
    async def test_valid_chain_verifies(self, db: AsyncSession) -> None:
        seed = await seed_course(db)
        await _run_pass_flow(db, seed)
        result = await audit_query.verify_stored_chain(db)
        assert result.ok is True
        assert result.total >= 3  # create + start + submit + certificate.issue

    async def test_tampered_row_is_detected(self, db: AsyncSession) -> None:
        seed = await seed_course(db)
        await _run_pass_flow(db, seed)
        target = (await db.execute(select(func.min(AuditLog.audit_id)))).scalar_one()
        await db.execute(
            text(
                "UPDATE audit_log SET payload = '{\"tampered\": true}'::jsonb WHERE audit_id = :i"
            ),
            {"i": target},
        )
        await db.commit()
        result = await audit_query.verify_stored_chain(db)
        assert result.ok is False
        assert result.first_break is not None
        assert result.first_break.audit_id == target
        assert result.first_break.reason == "hash_mismatch"


def _client(
    sessions: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: frozenset[str],
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


class TestAuditApi:
    async def test_auditor_can_verify_and_search(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db)
        await _run_pass_flow(db, seed)
        client = _client(
            sessions,
            tenant_id=seed.tenant_id,
            user_id=seed.user_id,
            roles=frozenset([RoleName.AUDITOR]),
        )

        verify = client.get("/audit/verify")
        assert verify.status_code == 200
        assert verify.json()["ok"] is True

        search = client.get("/audit", params={"entity_type": "assignment"})
        assert search.status_code == 200
        assert search.json()["pagination"]["total"] >= 1

    async def test_non_auditor_is_forbidden(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db)
        client = _client(
            sessions,
            tenant_id=seed.tenant_id,
            user_id=seed.user_id,
            roles=frozenset([RoleName.TRAINEE]),
        )
        assert client.get("/audit/verify").status_code == 403

    async def test_export_csv_includes_hashes_and_is_audited(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db)
        await _run_pass_flow(db, seed)
        client = _client(
            sessions,
            tenant_id=seed.tenant_id,
            user_id=seed.user_id,
            roles=frozenset([RoleName.COMPLIANCE_ADMIN]),
        )
        resp = client.get("/audit/export", params={"format": "csv"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "audit_hash" in resp.text.splitlines()[0]

        # the export itself was recorded
        exported = (
            await db.execute(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.event_type == "audit.exported")
            )
        ).scalar_one()
        assert exported == 1

    async def test_evidence_binder(
        self, db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        seed = await seed_course(db)
        await _run_pass_flow(db, seed)
        client = _client(
            sessions,
            tenant_id=seed.tenant_id,
            user_id=seed.user_id,
            roles=frozenset([RoleName.AUDITOR]),
        )
        resp = client.get(f"/evidence/{seed.user_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == str(seed.user_id)
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["status"] == "passed"
        assert item["certificate"] is not None
        assert len(item["attempts"]) == 1
        assert item["attempts"][0]["outcome"] == "pass"
