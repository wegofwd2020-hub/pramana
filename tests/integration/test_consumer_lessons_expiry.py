"""Integration test: expired entitlement is rejected on GET /packages/{id}/lessons.

An entitlement whose expires_at is in the past but whose status is still
"active" must be treated as expired — the route should return 403.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pramana.api.app import create_app
from pramana.api.dependencies import get_db_session, get_principal
from pramana.db.models.consumer import Entitlement, Package, PackageCourse
from pramana.services.auth import Principal
from pramana.services.consumer import entitlements as ent
from pramana.services.consumer_tenant import ensure_consumer_tenant
from tests.integration.conftest import seed_course

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_PAST = _NOW - timedelta(days=1)


def _client(
    sessions: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
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


@pytest.mark.asyncio
async def test_expired_entitlement_cannot_list_lessons(
    db: AsyncSession,
    sessions: async_sessionmaker[AsyncSession],
    consumer_tenant: object,
) -> None:
    """An entitlement with expires_at in the past must yield 403 on lesson listing."""
    # Ensure the consumer tenant exists and get its id.
    await ensure_consumer_tenant(db)
    await db.flush()
    tenant_id = await ent.get_consumer_tenant_id(db)

    # Seed a published course (creates its own tenant internally).
    seeded = await seed_course(db)

    # Create a consumer user under the consumer tenant.
    user = await ent.create_consumer_user(
        db,
        tenant_id=tenant_id,
        email=f"{uuid.uuid4()}@expiry-test.example.com",
        first_name="Exp",
        last_name="Ired",
        now=_NOW,
    )

    # Create a fresh package containing that course — isolated from any
    # never-expiring entitlement that consumer_setup might have created.
    pkg = Package(
        tenant_id=tenant_id,
        slug=uuid.uuid4().hex[:12],
        title="Expiry Test Package",
        is_published=True,
    )
    db.add(pkg)
    await db.flush()
    db.add(PackageCourse(package_id=pkg.id, course_id=seeded.course_id))
    await db.flush()

    # Insert an entitlement that is status="active" but already expired.
    expired_ent = Entitlement(
        user_id=user.user_id,
        package_id=pkg.id,
        tenant_id=tenant_id,
        status="active",
        granted_at=_PAST,
        expires_at=_PAST,  # expired yesterday
    )
    db.add(expired_ent)
    await db.commit()

    client = _client(sessions, tenant_id=tenant_id, user_id=user.user_id)
    resp = client.get(f"/packages/{pkg.id}/lessons")
    assert resp.status_code == 403, resp.text
