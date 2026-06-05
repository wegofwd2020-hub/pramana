"""HTTP-layer tests for the /content-drafts review queue.

The review-service seam is overridden, so these exercise routing, schema
validation, and exception -> status-code mapping without a database.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

from fastapi.testclient import TestClient

from pramana.api.app import create_app
from pramana.api.dependencies import get_content_review_service
from pramana.db.models.content import ContentDraft
from pramana.db.models.course import CourseVersion
from pramana.exceptions import (
    InvalidStateTransitionError,
    NotFoundError,
    SeparationOfDutiesError,
)


def make_draft(status: str = "received") -> ContentDraft:
    d = ContentDraft(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        course_id=uuid.uuid4(),
        status=status,
        title="FCPA Anti-Bribery",
        body={"modules": [{"heading": "x"}], "quiz": {"questions": [1]}},
        source_citations=[{"framework": "fcpa", "clause": "anti-bribery"}],
        package_id=uuid.uuid4(),
        package_version=1,
    )
    d.gen_engine = "mentible"
    d.review_notes = None
    return d


class FakeService:
    def __init__(self, *, draft=None, items=None, total=0, cv=None, raises=None):
        self.draft = draft or make_draft()
        self.items = items if items is not None else [self.draft]
        self.total = total
        self.cv = cv
        self.raises = raises

    def _maybe_raise(self):
        if self.raises is not None:
            raise self.raises

    async def list_drafts(self, **kw):
        self._maybe_raise()
        return self.items, self.total

    async def get_draft(self, draft_id):
        self._maybe_raise()
        return self.draft

    async def submit_for_review(self, draft_id):
        self._maybe_raise()
        return self.draft

    async def approve(self, draft_id, *, attestation_text):
        self._maybe_raise()
        return self.draft

    async def request_changes(self, draft_id, *, notes):
        self._maybe_raise()
        return self.draft

    async def reject(self, draft_id, *, notes):
        self._maybe_raise()
        return self.draft

    async def publish(self, draft_id, *, is_material_change):
        self._maybe_raise()
        return self.cv


def client(service: FakeService) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_content_review_service] = lambda: service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_list_queue() -> None:
    draft = make_draft("in_review")
    c = next(client(FakeService(draft=draft, items=[draft], total=1)))
    resp = c.get("/content-drafts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["status"] == "in_review"
    assert body["items"][0]["framework"] == "fcpa"
    assert body["items"][0]["verified"] is True


def test_list_rejects_bad_status() -> None:
    c = next(client(FakeService()))
    resp = c.get("/content-drafts", params={"status": "bogus"})
    assert resp.status_code == 409  # InvalidStateTransitionError


def test_get_draft_detail() -> None:
    draft = make_draft("in_review")
    c = next(client(FakeService(draft=draft)))
    resp = c.get(f"/content-drafts/{draft.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["modules"] == draft.body["modules"]
    assert body["provenance"]["engine"] == "mentible"


def test_get_draft_404() -> None:
    c = next(client(FakeService(raises=NotFoundError("nope"))))
    resp = c.get(f"/content-drafts/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_submit_for_review() -> None:
    c = next(client(FakeService(draft=make_draft("in_review"))))
    resp = c.post(f"/content-drafts/{uuid.uuid4()}/submit-for-review")
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_review"


def test_approve() -> None:
    c = next(client(FakeService(draft=make_draft("approved"))))
    resp = c.post(
        f"/content-drafts/{uuid.uuid4()}/approve",
        json={"attestation_text": "I attest this is accurate."},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_approve_separation_of_duties_is_409() -> None:
    c = next(client(FakeService(raises=SeparationOfDutiesError("approver == generator"))))
    resp = c.post(
        f"/content-drafts/{uuid.uuid4()}/approve",
        json={"attestation_text": "x"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "separation_of_duties"


def test_approve_requires_attestation() -> None:
    c = next(client(FakeService()))
    resp = c.post(f"/content-drafts/{uuid.uuid4()}/approve", json={})
    assert resp.status_code == 422  # missing attestation_text


def test_request_changes() -> None:
    c = next(client(FakeService(draft=make_draft("draft"))))
    resp = c.post(
        f"/content-drafts/{uuid.uuid4()}/request-changes",
        json={"notes": "Fix the citation."},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"


def test_reject() -> None:
    c = next(client(FakeService(draft=make_draft("rejected"))))
    resp = c.post(f"/content-drafts/{uuid.uuid4()}/reject", json={"notes": "Inaccurate."})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_invalid_transition_is_409() -> None:
    c = next(client(FakeService(raises=InvalidStateTransitionError("not in review"))))
    resp = c.post(f"/content-drafts/{uuid.uuid4()}/reject", json={"notes": "x"})
    assert resp.status_code == 409


def test_publish_returns_course_version() -> None:
    cv = CourseVersion(id=uuid.uuid4(), course_id=uuid.uuid4(), version_number=1, is_active=True)
    c = next(client(FakeService(cv=cv)))
    resp = c.post(f"/content-drafts/{uuid.uuid4()}/publish", json={})
    assert resp.status_code == 201
    body = resp.json()
    assert body["version_number"] == 1
    assert body["is_active"] is True
