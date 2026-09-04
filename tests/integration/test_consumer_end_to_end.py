"""End-to-end integration test: admin grants package → consumer views lesson → passes quiz.

Drives the real ASGI app via TestClient against a scratch Postgres.
Proves that Tasks 1-11 compose correctly without modifying any production code.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pramana.api.app import create_app
from pramana.api.dependencies import get_db_session, get_principal
from pramana.db.models.consumer import Package, PackageCourse
from pramana.db.models.identity import RoleName, Tenant, User
from pramana.services.auth import Principal
from tests.integration.conftest import seed_course

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeededPackage:
    package_id: uuid.UUID
    course_id: uuid.UUID
    # question_id -> [correct_option_id]
    correct_options: dict[uuid.UUID, list[uuid.UUID]]


async def _seed_admin_user(db: AsyncSession, *, tenant: Tenant) -> User:
    """Insert a real user_account row for the admin (FK needed for granted_by_user_id)."""
    user = User(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=f"{uuid.uuid4()}@admin.example.com",
    )
    db.add(user)
    await db.commit()
    return user


async def _seed_package_with_lesson(db: AsyncSession, *, consumer_tenant: Tenant) -> SeededPackage:
    """Seed a Package under the consumer tenant with one published course.

    Reuses seed_course (which creates its own tenant + published CourseVersion
    with graded questions).  Inserts Package + PackageCourse under the consumer
    tenant and commits so the app's request-scoped sessions can read it.
    """
    seeded = await seed_course(db, n_questions=2)

    pkg = Package(
        tenant_id=consumer_tenant.id,
        slug=uuid.uuid4().hex[:12],
        title="E2E Test Package",
        is_published=True,
    )
    db.add(pkg)
    await db.flush()

    pc = PackageCourse(package_id=pkg.id, course_id=seeded.course_id)
    db.add(pc)
    await db.commit()

    correct_options = {qid: [correct] for qid, (correct, _wrong) in seeded.questions.items()}
    return SeededPackage(
        package_id=pkg.id,
        course_id=seeded.course_id,
        correct_options=correct_options,
    )


def _make_client(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    roles: frozenset[str] = frozenset(),
) -> TestClient:
    """Build a TestClient wired to the scratch DB with an injected Principal."""
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


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


async def test_grant_then_view_then_perfect_quiz(
    db: AsyncSession,
    sessions: async_sessionmaker[AsyncSession],
    consumer_tenant: Tenant,
) -> None:
    """Full consumer flow: admin creates+grants → learner views → passes quiz → progress updated."""

    # -----------------------------------------------------------------------
    # Seed
    # -----------------------------------------------------------------------
    pkg = await _seed_package_with_lesson(db, consumer_tenant=consumer_tenant)
    admin_user = await _seed_admin_user(db, tenant=consumer_tenant)

    # -----------------------------------------------------------------------
    # Step 1: Admin creates a consumer account and grants the package.
    # The admin_user.user_id satisfies the FK on entitlement.granted_by_user_id.
    # COMPLIANCE_ADMIN role is injected in the Principal (no UserRole row needed).
    # -----------------------------------------------------------------------
    admin_client = _make_client(
        sessions,
        user_id=admin_user.user_id,
        tenant_id=consumer_tenant.id,
        roles=frozenset({RoleName.COMPLIANCE_ADMIN}),
    )
    resp = admin_client.post(
        "/admin/consumers",
        json={
            "email": f"{uuid.uuid4()}@learner.example.com",
            "first_name": "Lee",
            "last_name": "Roy",
            "package_id": str(pkg.package_id),
        },
    )
    assert resp.status_code == 201, f"POST /admin/consumers failed: {resp.text}"
    consumer_user_id = uuid.UUID(resp.json()["user_id"])

    # -----------------------------------------------------------------------
    # Step 2: Switch to consumer principal (no roles — entitlement-gated).
    # -----------------------------------------------------------------------
    consumer_client = _make_client(
        sessions,
        user_id=consumer_user_id,
        tenant_id=consumer_tenant.id,
    )

    # Lessons visible with zeroed progress.
    resp = consumer_client.get(f"/packages/{pkg.package_id}/lessons")
    assert resp.status_code == 200, f"GET /packages/.../lessons failed: {resp.text}"
    lessons = resp.json()
    assert len(lessons) == 1
    assert lessons[0]["view_count"] == 0
    assert lessons[0]["completion_count"] == 0

    # -----------------------------------------------------------------------
    # Step 3: Start a view session.
    # -----------------------------------------------------------------------
    resp = consumer_client.post(
        f"/lessons/{pkg.course_id}/views",
        json={"media_kind": "video"},
    )
    assert resp.status_code == 201, f"POST /lessons/.../views failed: {resp.text}"
    play_session_id = resp.json()["play_session_id"]

    # -----------------------------------------------------------------------
    # Step 4: End the view session (watched 100%).
    # -----------------------------------------------------------------------
    resp = consumer_client.post(
        f"/lessons/{pkg.course_id}/views/{play_session_id}/end",
        json={"duration_seconds": 30, "max_watched_pct": 100},
    )
    assert resp.status_code == 204, f"POST /lessons/.../views/.../end failed: {resp.text}"

    # -----------------------------------------------------------------------
    # Step 5: Start quiz.
    # -----------------------------------------------------------------------
    resp = consumer_client.post(f"/lessons/{pkg.course_id}/quiz/start")
    assert resp.status_code == 201, f"POST /lessons/.../quiz/start failed: {resp.text}"
    form = resp.json()
    attempt_id = form["attempt_id"]

    # Build perfect answers: question_id_str -> [correct_option_id_str]
    answers: dict[str, list[str]] = {}
    for q in form["questions"]:
        qid = uuid.UUID(q["question_id"])
        correct_ids = [str(oid) for oid in pkg.correct_options[qid]]
        answers[q["question_id"]] = correct_ids

    # -----------------------------------------------------------------------
    # Step 6: Submit all-correct answers.
    # -----------------------------------------------------------------------
    resp = consumer_client.post(
        f"/lessons/{pkg.course_id}/quiz/{attempt_id}/submit",
        json={"answers": answers},
    )
    assert resp.status_code == 200, f"POST .../quiz/.../submit failed: {resp.text}"
    result = resp.json()
    assert result["is_all_correct"] is True, f"Expected all correct, got: {result}"

    # -----------------------------------------------------------------------
    # Step 7: Progress now shows 1 view + 1 completion.
    # -----------------------------------------------------------------------
    resp = consumer_client.get(f"/packages/{pkg.package_id}/lessons")
    assert resp.status_code == 200, f"GET /packages/.../lessons (after) failed: {resp.text}"
    item = resp.json()[0]
    assert item["view_count"] == 1, f"Expected view_count=1, got {item['view_count']}"
    assert item["completion_count"] == 1, (
        f"Expected completion_count=1, got {item['completion_count']}"
    )
