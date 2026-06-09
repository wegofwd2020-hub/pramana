"""HTTP-layer tests for /content-requests (commission surface).

The commission-service seam is overridden, so these exercise routing, schema
validation, and exception -> status mapping without a database or Mentible.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

from fastapi.testclient import TestClient

from pramana.api.app import create_app
from pramana.api.dependencies import get_content_request_service
from pramana.db.models.content_request import ContentRequest
from pramana.exceptions import ExternalServiceError, NotFoundError, ValidationError


def make_request(status: str = "requested") -> ContentRequest:
    cr = ContentRequest(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        framework="fcpa",
        title="FCPA Anti-Bribery",
        status=status,
        requested_by=uuid.uuid4(),
        spec={},
    )
    cr.course_id = None
    cr.package_id = None
    cr.draft_id = None
    return cr


def _body() -> dict:
    return {
        "framework": "fcpa",
        "title": "FCPA Anti-Bribery",
        "source_definitions": [
            {
                "framework": "fcpa",
                "clause": "anti-bribery",
                "ref": "docs/frameworks/framework_fcpa.md#anti-bribery",
            }
        ],
        "assessment": {"pass_threshold_pct": 80},
    }


class FakeService:
    def __init__(self, *, cr=None, items=None, total=0, raises=None):
        self.cr = cr or make_request()
        self.items = items if items is not None else [self.cr]
        self.total = total
        self.raises = raises

    def _maybe_raise(self):
        if self.raises is not None:
            raise self.raises

    async def commission(self, body):
        self._maybe_raise()
        return self.cr

    async def regenerate(self, draft_id, *, parameter_overrides):
        self._maybe_raise()
        return self.cr

    async def list_requests(self, **kw):
        self._maybe_raise()
        return self.items, self.total

    async def get_request(self, request_id):
        self._maybe_raise()
        return self.cr


def client(service: FakeService) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_content_request_service] = lambda: service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_commission_returns_202() -> None:
    cr = make_request()
    c = next(client(FakeService(cr=cr)))
    resp = c.post("/content-requests", json=_body())
    assert resp.status_code == 202
    body = resp.json()
    assert body["request_id"] == str(cr.id)
    assert body["status"] == "requested"
    assert body["framework"] == "fcpa"


def test_commission_unresolvable_clause_is_422() -> None:
    c = next(client(FakeService(raises=ValidationError("clause does not resolve"))))
    resp = c.post("/content-requests", json=_body())
    assert resp.status_code == 422


def test_commission_missing_required_field_is_422() -> None:
    c = next(client(FakeService()))
    resp = c.post("/content-requests", json={"framework": "fcpa"})
    assert resp.status_code == 422


def test_commission_push_failure_is_502() -> None:
    c = next(client(FakeService(raises=ExternalServiceError("mentible down"))))
    resp = c.post("/content-requests", json=_body())
    assert resp.status_code == 502


def test_list_requests() -> None:
    cr = make_request("generating")
    c = next(client(FakeService(cr=cr, items=[cr], total=1)))
    resp = c.get("/content-requests")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["status"] == "generating"


def test_list_rejects_bad_status() -> None:
    c = next(client(FakeService()))
    resp = c.get("/content-requests", params={"status": "bogus"})
    assert resp.status_code == 409


def test_get_request() -> None:
    cr = make_request()
    c = next(client(FakeService(cr=cr)))
    resp = c.get(f"/content-requests/{cr.id}")
    assert resp.status_code == 200
    assert resp.json()["request_id"] == str(cr.id)


def test_get_request_404() -> None:
    c = next(client(FakeService(raises=NotFoundError("nope"))))
    resp = c.get(f"/content-requests/{uuid.uuid4()}")
    assert resp.status_code == 404
