"""HTTP-layer tests for the consumer_library ingestion endpoint.

The ingestor seam is overridden, so these exercise routing, schema validation,
and the exception → status-code mapping without a database.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from pramana.api.app import create_app
from pramana.api.dependencies import get_package_ingestor
from pramana.db.models.content import ContentDraft
from pramana.exceptions import (
    DuplicatePackageError,
    NotFoundError,
    PackageIntegrityError,
    PackageValidationError,
)
from tests.support import make_signed_manifest

ENDPOINT = "/consumer-library/packages"


class _FakeIngestor:
    """Stands in for the DB-backed ingestor; returns a draft or raises."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises
        self.calls: list[dict] = []

    async def ingest(self, *, manifest, tenant_id, course_id) -> ContentDraft:
        self.calls.append({"manifest": manifest, "tenant_id": tenant_id, "course_id": course_id})
        if self._raises is not None:
            raise self._raises
        draft = ContentDraft(
            tenant_id=tenant_id,
            course_id=course_id,
            status="received",
            title=manifest["title"],
            body={},
            package_id=uuid.UUID(manifest["package_id"]),
            package_version=manifest["package_version"],
        )
        draft.id = uuid.uuid4()
        return draft


def _client(ingestor: _FakeIngestor) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_package_ingestor] = lambda: ingestor
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _body(**overrides) -> dict:
    body = {
        "tenant_id": str(uuid.uuid4()),
        "course_id": str(uuid.uuid4()),
        "manifest": make_signed_manifest(),
    }
    body.update(overrides)
    return body


def test_health() -> None:
    ingestor = _FakeIngestor()
    client = next(_client(ingestor))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_successful_ingest_returns_201_with_received_draft() -> None:
    ingestor = _FakeIngestor()
    client = next(_client(ingestor))
    body = _body()

    resp = client.post(ENDPOINT, json=body)

    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "received"
    assert data["package_id"] == body["manifest"]["package_id"]
    assert data["package_version"] == 1
    assert uuid.UUID(data["draft_id"])
    # the route forwarded the manifest + ids to the service seam
    assert ingestor.calls[0]["course_id"] == uuid.UUID(body["course_id"])


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_code"),
    [
        (PackageValidationError("bad manifest"), 422, "package_validation_error"),
        (PackageIntegrityError("quarantine"), 422, "package_integrity_error"),
        (DuplicatePackageError("dup"), 409, "duplicate_package"),
        (NotFoundError("no course"), 404, "not_found"),
    ],
)
def test_domain_errors_map_to_status_codes(
    exc: Exception, expected_status: int, expected_code: str
) -> None:
    client = next(_client(_FakeIngestor(raises=exc)))
    resp = client.post(ENDPOINT, json=_body())
    assert resp.status_code == expected_status
    assert resp.json()["error"]["code"] == expected_code


def test_malformed_request_body_is_422() -> None:
    client = next(_client(_FakeIngestor()))
    body = _body()
    del body["course_id"]
    resp = client.post(ENDPOINT, json=body)
    assert resp.status_code == 422


def test_unknown_body_fields_rejected() -> None:
    client = next(_client(_FakeIngestor()))
    resp = client.post(ENDPOINT, json=_body(surprise="nope"))
    assert resp.status_code == 422
