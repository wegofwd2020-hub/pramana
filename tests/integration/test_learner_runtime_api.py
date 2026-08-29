"""HTTP-layer integration tests for the learner runtime (real Postgres).

Drives the routers through TestClient against a real DB: the app's session
dependency is overridden to the test engine, and the principal is injected as
the seeded assignee. Exercises routing, schema, auth/status mapping, and the
public certificate-verification path end-to-end.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pramana.api.app import create_app
from pramana.api.dependencies import get_db_session, get_principal
from pramana.db.models.identity import RoleName, User
from pramana.services.auth import Principal
from tests.integration.conftest import seed_course

pytestmark = pytest.mark.integration


def _client(
    sessions: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
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
    return TestClient(app)


async def _another_user(db: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """Insert a second user in the tenant.

    Real rows, not invented UUIDs: ``assignment.assigned_by_user_id`` carries a
    foreign key to ``user_account``.
    """
    user = User(user_id=uuid.uuid4(), tenant_id=tenant_id, email=f"{uuid.uuid4()}@example.com")
    db.add(user)
    await db.commit()
    return user.user_id


async def _staff_client(
    db: AsyncSession, sessions: async_sessionmaker[AsyncSession], *, tenant_id: uuid.UUID
) -> TestClient:
    """A manager, who may assign and cancel training for other people."""
    return _client(
        sessions,
        tenant_id=tenant_id,
        user_id=await _another_user(db, tenant_id),
        roles=frozenset({RoleName.MANAGER}),
    )


def _attest() -> dict:
    return {"text_version": "v1", "accepted": True}


async def test_full_flow_over_http(
    db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    seed = await seed_course(db, n_questions=2)
    client = _client(sessions, tenant_id=seed.tenant_id, user_id=seed.user_id)
    staff = await _staff_client(db, sessions, tenant_id=seed.tenant_id)

    # a manager assigns; the learner does everything after this
    resp = staff.post(
        "/assignments", json={"user_id": str(seed.user_id), "course_id": str(seed.course_id)}
    )
    assert resp.status_code == 201, resp.text
    assignment_id = resp.json()["assignment_id"]

    # it shows up in /me
    mine = client.get("/assignments/me")
    assert mine.status_code == 200
    assert any(a["assignment_id"] == assignment_id for a in mine.json()["items"])

    # start attempt
    resp = client.post(f"/assignments/{assignment_id}/attempts")
    assert resp.status_code == 201, resp.text
    assert resp.json()["attempt_number"] == 1

    # submit all-correct -> pass + certificate
    answers = [
        {"question_id": str(qid), "selected_option_ids": [str(correct)]}
        for qid, (correct, _wrong) in seed.questions.items()
    ]
    resp = client.post(
        f"/assignments/{assignment_id}/submit",
        json={"answers": answers, "attestation": _attest()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "passed"
    assert body["score_pct"] == 100.0
    cert_id = body["certificate_id"]
    assert cert_id is not None

    # fetch the certificate, then verify it publicly (no auth needed for verify)
    cert = client.get(f"/certificates/{cert_id}")
    assert cert.status_code == 200
    code = cert.json()["verification_code"]

    verify = client.get(f"/certificates/verify/{code}")
    assert verify.status_code == 200
    assert verify.json()["valid"] is True
    assert verify.json()["certificate_id"] == cert_id


async def test_watch_gate_over_http(
    db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    seed = await seed_course(db, min_watch_pct=50)
    client = _client(sessions, tenant_id=seed.tenant_id, user_id=seed.user_id)
    staff = await _staff_client(db, sessions, tenant_id=seed.tenant_id)
    resp = staff.post(
        "/assignments", json={"user_id": str(seed.user_id), "course_id": str(seed.course_id)}
    )
    assignment_id = resp.json()["assignment_id"]

    # locked -> 422
    locked = client.post(f"/assignments/{assignment_id}/attempts")
    assert locked.status_code == 422

    # player manifest reports locked
    manifest = client.get(f"/assignments/{assignment_id}/player")
    assert manifest.status_code == 200
    assert manifest.json()["quiz_unlocked"] is False

    # watch to threshold -> unlocked
    prog = client.post(f"/assignments/{assignment_id}/progress", json={"watched_pct": 50})
    assert prog.status_code == 200
    assert prog.json()["quiz_unlocked"] is True

    # now the attempt starts
    started = client.post(f"/assignments/{assignment_id}/attempts")
    assert started.status_code == 201


async def test_verify_unknown_code_is_invalid(
    db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    seed = await seed_course(db)
    client = _client(sessions, tenant_id=seed.tenant_id, user_id=seed.user_id)
    resp = client.get(f"/certificates/verify/{uuid.uuid4().hex}")
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


async def test_another_tenant_member_cannot_read_your_assignment(
    db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Tenant membership is not permission to read a colleague's training record."""
    seed = await seed_course(db)
    staff = await _staff_client(db, sessions, tenant_id=seed.tenant_id)
    assignment_id = staff.post(
        "/assignments", json={"user_id": str(seed.user_id), "course_id": str(seed.course_id)}
    ).json()["assignment_id"]

    stranger = _client(
        sessions, tenant_id=seed.tenant_id, user_id=await _another_user(db, seed.tenant_id)
    )
    assert stranger.get(f"/assignments/{assignment_id}").status_code == 403

    owner = _client(sessions, tenant_id=seed.tenant_id, user_id=seed.user_id)
    assert owner.get(f"/assignments/{assignment_id}").status_code == 200


async def test_auditor_may_read_anyones_assignment(
    db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    seed = await seed_course(db)
    staff = await _staff_client(db, sessions, tenant_id=seed.tenant_id)
    assignment_id = staff.post(
        "/assignments", json={"user_id": str(seed.user_id), "course_id": str(seed.course_id)}
    ).json()["assignment_id"]

    auditor = _client(
        sessions,
        tenant_id=seed.tenant_id,
        user_id=await _another_user(db, seed.tenant_id),
        roles=frozenset({RoleName.AUDITOR}),
    )
    assert auditor.get(f"/assignments/{assignment_id}").status_code == 200


async def test_stranger_cannot_read_your_certificate(
    db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A certificate is evidence about a named person; strangers get 403."""
    seed = await seed_course(db, n_questions=2)
    staff = await _staff_client(db, sessions, tenant_id=seed.tenant_id)
    client = _client(sessions, tenant_id=seed.tenant_id, user_id=seed.user_id)
    assignment_id = staff.post(
        "/assignments", json={"user_id": str(seed.user_id), "course_id": str(seed.course_id)}
    ).json()["assignment_id"]
    client.post(f"/assignments/{assignment_id}/attempts")
    answers = [
        {"question_id": str(qid), "selected_option_ids": [str(correct)]}
        for qid, (correct, _wrong) in seed.questions.items()
    ]
    cert_id = client.post(
        f"/assignments/{assignment_id}/submit",
        json={"answers": answers, "attestation": _attest()},
    ).json()["certificate_id"]

    stranger = _client(
        sessions, tenant_id=seed.tenant_id, user_id=await _another_user(db, seed.tenant_id)
    )
    assert stranger.get(f"/certificates/{cert_id}").status_code == 403
    assert client.get(f"/certificates/{cert_id}").status_code == 200


async def test_double_assign_conflicts_over_http(
    db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    seed = await seed_course(db)
    staff = await _staff_client(db, sessions, tenant_id=seed.tenant_id)
    payload = {"user_id": str(seed.user_id), "course_id": str(seed.course_id)}
    assert staff.post("/assignments", json=payload).status_code == 201
    assert staff.post("/assignments", json=payload).status_code == 409
