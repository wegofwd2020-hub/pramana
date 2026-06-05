"""``consumer_library`` HTTP router — the Mentible package ingestion endpoint.

One-way push (Mentible ADR-011 §6): Mentible POSTs a signed Consumable Package;
Pramana verifies it and records an untrusted ``RECEIVED`` draft. The heavy
lifting lives in :mod:`pramana.services.consumer_library`; this module is just
the HTTP shell. Integrity / validation / conflict failures are raised as
:class:`~pramana.exceptions.PramanaError` subclasses and mapped to status codes
by the handlers in :mod:`pramana.api.errors`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from pramana.api.dependencies import PackageIngestor, get_package_ingestor
from pramana.api.schemas import IngestPackageRequest, IngestPackageResponse

router = APIRouter(prefix="/consumer-library", tags=["consumer_library"])


@router.post(
    "/packages",
    status_code=status.HTTP_201_CREATED,
    response_model=IngestPackageResponse,
    summary="Ingest a pushed Mentible Consumable Package",
)
async def ingest_package(
    body: IngestPackageRequest,
    ingestor: Annotated[PackageIngestor, Depends(get_package_ingestor)],
) -> IngestPackageResponse:
    """Accept, verify, and record a Consumable Package as a ``RECEIVED`` draft.

    A 201 means the package passed signature + ``content_hash`` verification and
    is queued for human review — **not** that it is published. Verification
    failures quarantine the package (422); a re-pushed package is a 409.
    """
    draft = await ingestor.ingest(
        manifest=body.manifest,
        tenant_id=body.tenant_id,
        course_id=body.course_id,
    )
    return IngestPackageResponse(
        draft_id=draft.id,
        status=draft.status,
        package_id=draft.package_id,
        package_version=draft.package_version,
    )
