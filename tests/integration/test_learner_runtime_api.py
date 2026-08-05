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
from pramana.services.auth import Principal
from tests.integration.conftest import seed_course

pytestmark = pytest.mark.integration


def _client(
    sessions: async_sessionmaker[AsyncSession], *, tenant_id: uuid.UUID, user_id: uuid.UUID
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
        user_id=user_id, tenant_id=tenant_id
    )
    return TestClient(app)


def _attest() -> dict:
    return {"text_version": "v1", "accepted": True}


async def test_full_flow_over_http(
    db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    seed = await seed_course(db, n_questions=2)
    client = _client(sessions, tenant_id=seed.tenant_id, user_id=seed.user_id)

    # assign
    resp = client.post(
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
    resp = client.post(
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


async def test_double_assign_conflicts_over_http(
    db: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    seed = await seed_course(db)
    client = _client(sessions, tenant_id=seed.tenant_id, user_id=seed.user_id)
    payload = {"user_id": str(seed.user_id), "course_id": str(seed.course_id)}
    assert client.post("/assignments", json=payload).status_code == 201
    assert client.post("/assignments", json=payload).status_code == 409
