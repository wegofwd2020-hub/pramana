"""Integration test: GET /me/packages returns 200 + correct body.

Covers the bug where MyPackageOut.package_id failed to map from Package.id
(ORM primary key is `id`, not `package_id`), causing a 500 on every call.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pramana.api.app import create_app
from pramana.api.dependencies import get_db_session, get_principal
from pramana.db.models.identity import Tenant
from pramana.services.auth import Principal
from tests.integration.conftest import consumer_setup

pytestmark = pytest.mark.integration


def _make_client(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
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
        user_id=user_id, tenant_id=tenant_id, roles=frozenset()
    )
    return TestClient(app)


async def test_my_packages_returns_granted_package(
    db: AsyncSession,
    sessions: async_sessionmaker[AsyncSession],
    consumer_tenant: Tenant,
) -> None:
    """GET /me/packages returns 200 with the package the user holds an entitlement for."""
    setup = await consumer_setup(db)

    client = _make_client(
        sessions,
        user_id=setup.user.user_id,
        tenant_id=setup.tenant_id,
    )

    resp = client.get("/me/packages")
    assert resp.status_code == 200, f"GET /me/packages failed: {resp.text}"

    data = resp.json()
    assert isinstance(data, list), f"Expected list, got: {type(data)}"
    assert len(data) == 1, f"Expected 1 package, got {len(data)}: {data}"

    item = data[0]
    # Verify the ORM id maps correctly to the JSON key package_id (the bug).
    assert "package_id" in item, f"Missing 'package_id' key in response: {item}"
    assert uuid.UUID(item["package_id"]) == setup.entitlement.package_id, (
        f"package_id mismatch: got {item['package_id']}"
    )
    assert "slug" in item, f"Missing 'slug' key in response: {item}"
    assert "title" in item, f"Missing 'title' key in response: {item}"
    assert item["title"] == "Test Package", f"Unexpected title: {item['title']}"
