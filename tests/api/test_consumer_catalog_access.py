"""Entitlement-gating tests for the consumer catalog router (Task 11).

The denial path is tested here (unit, no DB).
The entitled happy path is covered by the integration test (Task 12).
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from pramana.api.app import create_app
from pramana.api.dependencies import get_db_session, get_entitlement_checker, get_principal
from pramana.services.auth import Principal


def _client_app(entitled: bool):
    app = create_app()
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4()
    )
    app.dependency_overrides[get_db_session] = lambda: None

    async def checker(*a, **k):
        return entitled

    app.dependency_overrides[get_entitlement_checker] = lambda: checker
    return app


@pytest.mark.asyncio
async def test_view_start_forbidden_without_entitlement():
    app = _client_app(entitled=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(f"/lessons/{uuid.uuid4()}/views", json={"media_kind": "video"})
    assert r.status_code == 403
