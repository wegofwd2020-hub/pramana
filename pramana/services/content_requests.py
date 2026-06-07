"""Content-request service — commission content and push it to Mentible.

The Create phase made operable (US-PLATFORM-0003): validate a Package Request
(structure + clause resolvability), persist it as an auditable artifact, and push
it to Mentible. Also drives ``regenerate`` (US-PLATFORM-0005): re-issuing a
request for an existing draft with optional parameter overrides.

Thin transactional shell over the pure :mod:`pramana.domain.package_request`
(validation) and :mod:`pramana.services.definitions_library` (clause resolution),
with the outbound push behind the :class:`~pramana.services.mentible_client.
MentibleClient` seam. The caller owns the transaction; a failed push raises so
the whole commission rolls back rather than leaving an unsent request.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.content import ContentDraft
from pramana.db.models.content_request import ContentRequest
from pramana.domain.enums import ContentRequestEvent, ContentRequestStatus
from pramana.domain.package_request import PackageRequest, build_package_request
from pramana.exceptions import (
    ExternalServiceError,
    InvalidStateTransitionError,
    NotFoundError,
)
from pramana.services import definitions_library as dl
from pramana.services.audit import append_audit
from pramana.services.mentible_client import MentibleClient


async def commission_request(
    session: AsyncSession,
    *,
    body: Mapping[str, Any],
    tenant_id: uuid.UUID,
    requested_by: uuid.UUID,
    definitions_root: Path,
    mentible: MentibleClient,
    now: datetime,
) -> ContentRequest:
    """Build, validate, persist, and push a commissioning request.

    Raises:
        ValidationError: The request is malformed or cites an unresolvable clause
            (AC4 — no definition, no request). Nothing is written.
        ExternalServiceError: Mentible rejected the push — the transaction rolls
            back, so no request is recorded.
    """
    request = build_package_request(body)
    dl.validate_request_clauses(definitions_root, request)

    cr = _new_request(request, tenant_id=tenant_id, requested_by=requested_by)
    session.add(cr)
    await session.flush()  # assign cr.id for audit + the push payload's request_id

    await _push(session, cr, mentible=mentible, event=ContentRequestEvent.COMMISSION, now=now)
    return cr


async def regenerate_from_draft(
    session: AsyncSession,
    *,
    draft_id: uuid.UUID,
    tenant_id: uuid.UUID,
    requested_by: uuid.UUID,
    parameter_overrides: Mapping[str, Any] | None,
    definitions_root: Path,
    mentible: MentibleClient,
    now: datetime,
) -> ContentRequest:
    """Re-issue a Package Request for ``draft_id``, optionally with overrides.

    The new request supersedes the draft (tracked via ``regenerated_from_draft_id``)
    and reuses the original commissioning spec when one exists, else reconstructs a
    spec from the draft. Does not touch the existing draft or any published version.

    Raises:
        NotFoundError: The draft does not exist in this tenant.
        ValidationError: The merged request is malformed or cites an unresolvable
            clause.
        ExternalServiceError: Mentible rejected the push.
    """
    draft = await session.get(ContentDraft, draft_id)
    if draft is None or draft.archived_at is not None or draft.tenant_id != tenant_id:
        raise NotFoundError("content draft not found", context={"draft_id": str(draft_id)})

    base_spec = await _originating_spec(session, draft, tenant_id=tenant_id)
    merged = {**base_spec, **dict(parameter_overrides or {})}
    request = build_package_request(merged)
    dl.validate_request_clauses(definitions_root, request)

    cr = _new_request(request, tenant_id=tenant_id, requested_by=requested_by)
    cr.regenerated_from_draft_id = draft_id
    if cr.course_id is None:
        cr.course_id = draft.course_id
    session.add(cr)
    await session.flush()

    await _push(session, cr, mentible=mentible, event=ContentRequestEvent.REGENERATE, now=now)
    return cr


async def list_requests(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    framework: str | None = None,
    status: ContentRequestStatus | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[Sequence[ContentRequest], int]:
    """Return a page of content requests for the tenant + the total count."""
    filters = [ContentRequest.tenant_id == tenant_id, ContentRequest.archived_at.is_(None)]
    if framework is not None:
        filters.append(ContentRequest.framework == framework)
    if status is not None:
        filters.append(ContentRequest.status == status.value)

    total = (
        await session.execute(select(func.count()).select_from(ContentRequest).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(ContentRequest)
                .where(*filters)
                .order_by(ContentRequest.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .scalars()
        .all()
    )
    return rows, total


async def get_request(
    session: AsyncSession, *, request_id: uuid.UUID, tenant_id: uuid.UUID
) -> ContentRequest:
    """Load one content request scoped to the tenant (404 otherwise)."""
    cr = await session.get(ContentRequest, request_id)
    if cr is None or cr.archived_at is not None or cr.tenant_id != tenant_id:
        raise NotFoundError("content request not found", context={"request_id": str(request_id)})
    return cr


def parse_status(value: str) -> ContentRequestStatus:
    """Parse a status query value, raising a domain error on an unknown value."""
    try:
        return ContentRequestStatus(value)
    except ValueError as exc:
        raise InvalidStateTransitionError(
            f"unknown content-request status {value!r}",
            context={"value": value},
        ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _new_request(
    request: PackageRequest, *, tenant_id: uuid.UUID, requested_by: uuid.UUID
) -> ContentRequest:
    request_id = uuid.uuid4()
    return ContentRequest(
        id=request_id,
        tenant_id=tenant_id,
        framework=request.framework,
        title=request.title,
        status=ContentRequestStatus.REQUESTED.value,
        requested_by=requested_by,
        spec=request.as_payload(request_id=request_id, requested_by=str(requested_by)),
        course_id=request.course_id,
    )


async def _push(
    session: AsyncSession,
    cr: ContentRequest,
    *,
    mentible: MentibleClient,
    event: ContentRequestEvent,
    now: datetime,
) -> None:
    """Push the request to Mentible and audit it; raise (rolling back) on failure."""
    try:
        result = await mentible.push_request(cr.spec)
    except ExternalServiceError:
        # Re-raised so the transaction rolls back — no half-sent request persists.
        raise
    if not result.accepted:
        raise ExternalServiceError(
            "Mentible did not accept the Package Request",
            context={"request_id": str(cr.id), "detail": result.detail},
        )
    if result.package_id is not None:
        cr.package_id = uuid.UUID(result.package_id)

    await append_audit(
        session,
        tenant_id=cr.tenant_id,
        actor_user_id=cr.requested_by,
        entity_type="content_request",
        entity_id=str(cr.id),
        event_type=f"content_request.{event.value}",
        payload={
            "framework": cr.framework,
            "title": cr.title,
            "course_id": str(cr.course_id) if cr.course_id else None,
            "regenerated_from_draft_id": (
                str(cr.regenerated_from_draft_id) if cr.regenerated_from_draft_id else None
            ),
            "package_id": str(cr.package_id) if cr.package_id else None,
        },
        occurred_at=now,
    )


async def _originating_spec(
    session: AsyncSession, draft: ContentDraft, *, tenant_id: uuid.UUID
) -> dict[str, Any]:
    """The spec to re-issue: the draft's originating request, else reconstructed."""
    origin = (
        await session.execute(
            select(ContentRequest)
            .where(
                ContentRequest.tenant_id == tenant_id,
                ContentRequest.draft_id == draft.id,
            )
            .order_by(ContentRequest.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if origin is not None:
        return dict(origin.spec)
    return _spec_from_draft(draft)


def _spec_from_draft(draft: ContentDraft) -> dict[str, Any]:
    """Reconstruct a minimal Package Request spec from an ingested draft.

    For drafts that arrived without an originating request (ingested directly),
    recover enough to re-commission: the cited clauses, title, and pass threshold.
    """
    citations = draft.source_citations or []
    framework = ""
    if citations and isinstance(citations[0], Mapping):
        framework = str(citations[0].get("framework") or "")
    quiz = (draft.body or {}).get("quiz") or {}
    threshold = quiz.get("pass_threshold_pct")
    return {
        "framework": framework,
        "title": draft.title,
        "course_id": str(draft.course_id) if draft.course_id else None,
        "source_definitions": [dict(c) for c in citations if isinstance(c, Mapping)],
        "assessment": {"pass_threshold_pct": threshold if isinstance(threshold, int) else 80},
    }
