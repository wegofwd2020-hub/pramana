"""Authorization (RBAC) tests for the HTTP surface.

Authentication was already universal; these cover the *authorization* layer
added on top of it. The denial direction is tested exhaustively and table-driven
because that is the direction a forgotten gate breaks silently: an ungated route
keeps working in every manual test, and only an explicit "a roleless caller must
be refused" assertion catches it.

Service seams are overridden so no database is needed — a gate that refuses the
caller never reaches the service, and one that wrongly admits them returns the
fake's 200, which is exactly the failure we want to see.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pramana.api.app import create_app
from pramana.api.dependencies import (
    get_content_request_service,
    get_content_review_service,
    get_definitions_root,
    get_principal,
)
from pramana.db.models.course import CourseVersion
from pramana.db.models.identity import RoleName
from pramana.services.auth import Principal
from tests.api.test_content_drafts import FakeService as FakeReviewService
from tests.api.test_content_drafts import make_draft
from tests.api.test_content_requests import FakeService as FakeRequestService

TENANT = uuid.uuid4()
CALLER = uuid.uuid4()
OTHER_USER = uuid.uuid4()
DRAFT_ID = uuid.uuid4()
REQUEST_ID = uuid.uuid4()
ASSIGNMENT_ID = uuid.uuid4()


def build_client(*roles: str, tmp_path: Any = None) -> Iterator[TestClient]:
    """App with a principal holding exactly ``roles`` and both seams faked."""
    cv = CourseVersion(id=uuid.uuid4(), course_id=uuid.uuid4(), version_number=1, is_active=True)
    app = create_app()
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=CALLER, tenant_id=TENANT, roles=frozenset(roles)
    )
    app.dependency_overrides[get_content_review_service] = lambda: FakeReviewService(
        draft=make_draft(), cv=cv
    )
    app.dependency_overrides[get_content_request_service] = lambda: FakeRequestService()
    if tmp_path is not None:
        app.dependency_overrides[get_definitions_root] = lambda: tmp_path
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def client(*roles: str) -> TestClient:
    return next(build_client(*roles))


def _commission_body() -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# The gate table: (method, path, json_body, a role that grants access)
# ---------------------------------------------------------------------------
GATED: list[tuple[str, str, dict[str, Any] | None, str]] = [
    # Assignment administration — assigning and cancelling are privileged.
    (
        "POST",
        "/assignments",
        {"user_id": str(OTHER_USER), "course_id": str(uuid.uuid4())},
        RoleName.MANAGER,
    ),
    ("POST", f"/assignments/{ASSIGNMENT_ID}/cancel", None, RoleName.MANAGER),
    # Content review queue — reading is authoring/audit work.
    ("GET", "/content-drafts", None, RoleName.CONTENT_AUTHOR),
    ("GET", f"/content-drafts/{DRAFT_ID}", None, RoleName.CONTENT_AUTHOR),
    ("POST", f"/content-drafts/{DRAFT_ID}/submit-for-review", None, RoleName.CONTENT_AUTHOR),
    (
        "POST",
        f"/content-drafts/{DRAFT_ID}/regenerate",
        {"parameter_overrides": {}},
        RoleName.CONTENT_AUTHOR,
    ),
    # The approval gate itself — compliance_admin only.
    (
        "POST",
        f"/content-drafts/{DRAFT_ID}/approve",
        {"attestation_text": "I attest this content is accurate."},
        RoleName.COMPLIANCE_ADMIN,
    ),
    (
        "POST",
        f"/content-drafts/{DRAFT_ID}/request-changes",
        {"notes": "Fix clause citation."},
        RoleName.COMPLIANCE_ADMIN,
    ),
    (
        "POST",
        f"/content-drafts/{DRAFT_ID}/reject",
        {"notes": "Out of scope."},
        RoleName.COMPLIANCE_ADMIN,
    ),
    (
        "POST",
        f"/content-drafts/{DRAFT_ID}/publish",
        {"is_material_change": False},
        RoleName.COMPLIANCE_ADMIN,
    ),
    # Commissioning.
    ("GET", "/content-requests", None, RoleName.CONTENT_AUTHOR),
    ("POST", "/content-requests", _commission_body(), RoleName.CONTENT_AUTHOR),
    ("GET", f"/content-requests/{REQUEST_ID}", None, RoleName.CONTENT_AUTHOR),
]

IDS = [f"{m} {p.split('?')[0]}" for m, p, _, _ in GATED]


@pytest.mark.parametrize(("method", "path", "body", "role"), GATED, ids=IDS)
def test_roleless_caller_is_refused(
    method: str, path: str, body: dict[str, Any] | None, role: str
) -> None:
    """A caller holding no roles is refused every privileged route."""
    c = client()
    resp = c.request(method, path, json=body)
    assert resp.status_code == 403, f"{method} {path} admitted a roleless caller"


@pytest.mark.parametrize(("method", "path", "body", "role"), GATED, ids=IDS)
def test_granting_role_is_admitted(
    method: str, path: str, body: dict[str, Any] | None, role: str
) -> None:
    """The same route admits a caller holding the granting role."""
    c = client(role)
    resp = c.request(method, path, json=body)
    assert resp.status_code != 403, f"{method} {path} refused a caller holding {role}"


def test_trainee_role_does_not_grant_administration() -> None:
    """Holding *a* role is not holding the *right* role."""
    c = client(RoleName.TRAINEE)
    resp = c.post(f"/content-drafts/{DRAFT_ID}/approve", json={"attestation_text": "x"})
    assert resp.status_code == 403


def test_content_author_cannot_approve() -> None:
    """Approval is compliance_admin only — separation of duties is not the only guard."""
    c = client(RoleName.CONTENT_AUTHOR)
    resp = c.post(f"/content-drafts/{DRAFT_ID}/approve", json={"attestation_text": "x"})
    assert resp.status_code == 403


def test_auditor_may_read_the_review_queue_but_not_act() -> None:
    """Auditors see what was approved; they cannot approve, reject, or publish."""
    c = client(RoleName.AUDITOR)
    assert c.get("/content-drafts").status_code == 200
    assert c.post(f"/content-drafts/{DRAFT_ID}/publish", json={}).status_code == 403
    reject = c.post(f"/content-drafts/{DRAFT_ID}/reject", json={"notes": "no"})
    assert reject.status_code == 403


# ---------------------------------------------------------------------------
# Cross-user reads: scoped down, not refused, unless explicitly asking for
# someone else.
# ---------------------------------------------------------------------------
def test_listing_another_users_assignments_requires_a_role() -> None:
    c = client()
    assert c.get(f"/assignments?user_id={OTHER_USER}").status_code == 403


def test_listing_another_users_certificates_requires_a_role() -> None:
    c = client()
    assert c.get(f"/certificates?user_id={OTHER_USER}").status_code == 403


@pytest.mark.parametrize("role", [RoleName.MANAGER, RoleName.COMPLIANCE_ADMIN, RoleName.AUDITOR])
def test_staff_may_list_another_users_assignments(role: str) -> None:
    c = client(role)
    assert c.get(f"/assignments?user_id={OTHER_USER}").status_code != 403


# ---------------------------------------------------------------------------
# Routes that must stay open — regressions here are as bad as a missing gate.
# ---------------------------------------------------------------------------
def test_certificate_verification_stays_public() -> None:
    """The public verify-by-code endpoint must not acquire an auth requirement."""
    app = create_app()
    with TestClient(app) as c:
        resp = c.get("/certificates/verify/does-not-exist")
    assert resp.status_code not in (401, 403)


def test_own_assignments_need_no_role() -> None:
    c = client()
    assert c.get("/assignments/me").status_code != 403


def test_frameworks_need_no_role(tmp_path: Any) -> None:
    (tmp_path / "framework_sox.md").write_text(
        "# Framework Reference: SOX\n\n### Section 404\nText.\n", encoding="utf-8"
    )
    c = next(build_client(tmp_path=tmp_path))
    assert c.get("/frameworks").status_code == 200
