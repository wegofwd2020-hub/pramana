import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from pramana.api.app import create_app
from pramana.api.dependencies import get_principal
from pramana.services.auth import Principal


@pytest.mark.asyncio
async def test_create_and_grant_requires_compliance_admin(monkeypatch):
    app = create_app()

    # A caller lacking compliance_admin is forbidden.
    weak = Principal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=frozenset())
    app.dependency_overrides[get_principal] = lambda: weak
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(
            "/admin/consumers",
            json={
                "email": "a@example.com",
                "first_name": "A",
                "last_name": "B",
                "package_id": str(uuid.uuid4()),
            },
        )
    assert r.status_code == 403
