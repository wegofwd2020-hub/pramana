"""``/content-requests`` — commission content from a regulation (US-PLATFORM-0003).

HTTP shell over :mod:`pramana.services.content_requests`. A POST builds a Package
Request, enforces clause resolvability against the definitions library, persists
the request as audit evidence, and pushes it to Mentible. Validation failures
(malformed request, unresolvable clause) surface as
:class:`~pramana.exceptions.ValidationError` → 422; a Mentible push failure as
:class:`~pramana.exceptions.ExternalServiceError`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from pramana.api.dependencies import ContentRequestService, get_content_request_service
from pramana.api.schemas import (
    ContentRequestCreate,
    ContentRequestOut,
    ContentRequestPage,
    Pagination,
)
from pramana.services.content_requests import parse_status

router = APIRouter(prefix="/content-requests", tags=["ContentRequests"])

Service = Annotated[ContentRequestService, Depends(get_content_request_service)]


@router.get("", response_model=ContentRequestPage, summary="List content (package) requests")
async def list_content_requests(
    service: Service,
    status_: Annotated[str | None, Query(alias="status")] = None,
    framework: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ContentRequestPage:
    parsed = parse_status(status_) if status_ is not None else None
    items, total = await service.list_requests(
        framework=framework, status=parsed, page=page, page_size=page_size
    )
    return ContentRequestPage(
        items=[ContentRequestOut.of(cr) for cr in items],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ContentRequestOut,
    summary="Commission content — create a Package Request and push to Mentible",
)
async def commission_content(body: ContentRequestCreate, service: Service) -> ContentRequestOut:
    cr = await service.commission(body.model_dump(exclude_none=True))
    return ContentRequestOut.of(cr)


@router.get(
    "/{request_id}",
    response_model=ContentRequestOut,
    summary="Get a content request (and its status)",
)
async def get_content_request(request_id: uuid.UUID, service: Service) -> ContentRequestOut:
    return ContentRequestOut.of(await service.get_request(request_id))
