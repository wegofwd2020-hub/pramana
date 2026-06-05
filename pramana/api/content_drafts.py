"""``/content-drafts`` — the human review & approval gate (US-PLATFORM-0004).

HTTP shell over :mod:`pramana.services.content_review`, which drives the pure
:mod:`pramana.domain.content_approval` state machine. State-machine and
separation-of-duties errors are raised as :class:`~pramana.exceptions.PramanaError`
subclasses and mapped to status codes by :mod:`pramana.api.errors` (invalid
transition / SoD → 409, not found → 404, validation → 422).

``regenerate`` is intentionally not implemented here: it re-issues a Package
Request to Mentible (US-PLATFORM-0005), which depends on the content-requests
surface (US-PLATFORM-0003) that is not built yet.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from pramana.api.dependencies import ContentReviewService, get_content_review_service
from pramana.api.schemas import (
    ApproveRequest,
    ContentDraftDetail,
    ContentDraftOut,
    ContentDraftPage,
    CourseVersionOut,
    Pagination,
    PublishRequest,
    ReviewNotesRequest,
)
from pramana.services.content_review import parse_status

router = APIRouter(prefix="/content-drafts", tags=["ContentDrafts"])

Service = Annotated[ContentReviewService, Depends(get_content_review_service)]


@router.get("", response_model=ContentDraftPage, summary="List content drafts (review queue)")
async def list_content_drafts(
    service: Service,
    status_: Annotated[str | None, Query(alias="status")] = None,
    framework: str | None = None,
    quarantined: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ContentDraftPage:
    parsed = parse_status(status_) if status_ is not None else None
    items, total = await service.list_drafts(
        status=parsed,
        framework=framework,
        quarantined=quarantined,
        page=page,
        page_size=page_size,
    )
    return ContentDraftPage(
        items=[ContentDraftOut.of(d) for d in items],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.get(
    "/{draft_id}",
    response_model=ContentDraftDetail,
    summary="Get a draft for review (preview payload)",
)
async def get_content_draft(draft_id: uuid.UUID, service: Service) -> ContentDraftDetail:
    return ContentDraftDetail.of(await service.get_draft(draft_id))


@router.post(
    "/{draft_id}/submit-for-review",
    response_model=ContentDraftOut,
    summary="Open a draft for review",
)
async def submit_for_review(draft_id: uuid.UUID, service: Service) -> ContentDraftOut:
    return ContentDraftOut.of(await service.submit_for_review(draft_id))


@router.post(
    "/{draft_id}/approve",
    response_model=ContentDraftOut,
    summary="Approve a draft (attestation + separation of duties)",
)
async def approve(draft_id: uuid.UUID, body: ApproveRequest, service: Service) -> ContentDraftOut:
    return ContentDraftOut.of(
        await service.approve(draft_id, attestation_text=body.attestation_text)
    )


@router.post(
    "/{draft_id}/request-changes",
    response_model=ContentDraftOut,
    summary="Request changes on a draft",
)
async def request_changes(
    draft_id: uuid.UUID, body: ReviewNotesRequest, service: Service
) -> ContentDraftOut:
    return ContentDraftOut.of(await service.request_changes(draft_id, notes=body.notes))


@router.post(
    "/{draft_id}/reject",
    response_model=ContentDraftOut,
    summary="Reject a draft (terminal)",
)
async def reject(
    draft_id: uuid.UUID, body: ReviewNotesRequest, service: Service
) -> ContentDraftOut:
    return ContentDraftOut.of(await service.reject(draft_id, notes=body.notes))


@router.post(
    "/{draft_id}/publish",
    status_code=status.HTTP_201_CREATED,
    response_model=CourseVersionOut,
    summary="Publish an approved draft to an immutable course version",
)
async def publish(
    draft_id: uuid.UUID, service: Service, body: PublishRequest | None = None
) -> CourseVersionOut:
    body = body or PublishRequest()
    cv = await service.publish(draft_id, is_material_change=body.is_material_change)
    return CourseVersionOut.of(cv)
