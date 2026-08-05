"""Inbound Mentible webhooks — the generation-progress boundary.

Mentible POSTs a signed progress event as it manufactures a commissioned
package: ``progress`` advances the request ``REQUESTED → GENERATING`` (with an
optional completion percent / ETA), ``failure`` moves it to ``FAILED``. This
closes the reporting gap between commissioning a request and its package
arriving — until this endpoint, a request sat at ``requested`` the whole time.

Machine-to-machine, like package ingestion: authenticated by an HMAC-SHA256
signature over the raw request body (header ``X-Mentible-Signature``) against a
dedicated webhook secret — **not** an OIDC user token. The heavy lifting is in
:mod:`pramana.services.content_requests`; this module verifies, parses, and
dispatches. Benign no-ops (unknown or already-progressed request) return 200 so
Mentible does not retry them.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import ValidationError as PydanticValidationError

from pramana.api.dependencies import (
    MentibleWebhookHandler,
    get_mentible_webhook_handler,
    get_webhook_signature_verifier,
)
from pramana.api.schemas import MentibleProgressResponse, MentibleProgressWebhook
from pramana.domain.consumable_package import SignatureVerifier
from pramana.exceptions import AuthenticationError, ValidationError

router = APIRouter(prefix="/webhooks/mentible", tags=["webhooks"])

_SIGNATURE_HEADER = "X-Mentible-Signature"


@router.post(
    "/progress",
    status_code=status.HTTP_200_OK,
    response_model=MentibleProgressResponse,
    summary="Ingest a Mentible generation-progress event",
)
async def mentible_progress(
    request: Request,
    verifier: Annotated[SignatureVerifier, Depends(get_webhook_signature_verifier)],
    handler: Annotated[MentibleWebhookHandler, Depends(get_mentible_webhook_handler)],
) -> MentibleProgressResponse:
    """Verify, parse, and apply a Mentible progress webhook.

    A 200 with ``applied: false`` means the event was a benign no-op (the request
    is unknown in the tenant, or already progressed past what the event reports)
    — deliberately not an error, so a duplicate or out-of-order delivery is safe.
    A bad signature is 401; a malformed body (post-signature) is 422.
    """
    raw = await request.body()
    signature = request.headers.get(_SIGNATURE_HEADER)
    if not signature or not verifier.verify(signed_payload=raw, signature=signature):
        raise AuthenticationError(
            "invalid or missing Mentible webhook signature",
            context={"header": _SIGNATURE_HEADER},
        )

    try:
        payload = MentibleProgressWebhook.model_validate_json(raw)
    except PydanticValidationError as exc:
        raise ValidationError(
            "malformed Mentible progress webhook body",
            context={"errors": exc.errors(include_url=False)},
        ) from exc

    applied, resulting_status = await handler.handle(payload)
    return MentibleProgressResponse(
        applied=applied, request_id=payload.request_id, status=resulting_status
    )
