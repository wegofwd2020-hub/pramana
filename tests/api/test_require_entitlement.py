# tests/api/test_require_entitlement.py
import uuid

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from pramana.api.dependencies import (
    get_db_session,
    get_entitlement_checker,
    get_principal,
    require_course_entitlement,
)
from pramana.api.errors import register_exception_handlers
from pramana.services.auth import Principal


def _app_with_gate(has_entitlement: bool) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/lessons/{course_id}/probe", dependencies=[Depends(require_course_entitlement)])
    async def probe(course_id: uuid.UUID) -> dict:
        return {"ok": True}

    fake = Principal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())
    app.dependency_overrides[get_principal] = lambda: fake

    async def checker(*args, **kwargs) -> bool:
        return has_entitlement

    app.dependency_overrides[get_entitlement_checker] = lambda: checker
    # override the DB session dependency — the checker ignores it but the gate depends on it
    app.dependency_overrides[get_db_session] = lambda: None
    return app


@pytest.mark.asyncio
async def test_gate_allows_when_entitled():
    app = _app_with_gate(True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/lessons/{uuid.uuid4()}/probe")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_gate_forbids_when_not_entitled():
    app = _app_with_gate(False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/lessons/{uuid.uuid4()}/probe")
    assert r.status_code == 403
