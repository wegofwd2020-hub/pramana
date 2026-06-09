"""FastAPI dependency providers.

Kept separate from the routers so tests can override individual seams
(``app.dependency_overrides[...]``) without importing route internals.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Protocol

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.config import get_settings
from pramana.db.models.content import ContentDraft
from pramana.db.models.content_request import ContentRequest
from pramana.db.models.course import CourseVersion
from pramana.db.session import session_scope
from pramana.domain.consumable_package import SignatureVerifier
from pramana.domain.content_approval import utcnow
from pramana.domain.enums import ContentDraftStatus, ContentRequestStatus
from pramana.exceptions import AuthenticationError
from pramana.services import content_requests, content_review
from pramana.services.auth import (
    JwksKeySource,
    OidcJwtVerifier,
    Principal,
    TokenVerifier,
    resolve_principal,
)
from pramana.services.consumer_library import ingest_consumable_package
from pramana.services.mentible_client import (
    HttpMentibleClient,
    MentibleClient,
    NullMentibleClient,
)
from pramana.services.package_signing import HmacSignatureVerifier

__all__ = [
    "Principal",
    "get_content_request_service",
    "get_content_review_service",
    "get_db_session",
    "get_definitions_root",
    "get_mentible_client",
    "get_package_ingestor",
    "get_principal",
    "get_signature_verifier",
    "get_token_verifier",
]


def get_definitions_root() -> Path:
    """The definitions-library root directory (the "law" picker source)."""
    return Path(get_settings().definitions_root)


def get_mentible_client() -> MentibleClient:
    """The outbound Mentible client, chosen by configuration.

    A real HTTP client when ``mentible_request_url`` is set, else the no-op
    :class:`NullMentibleClient` so commissioning works without Mentible present.
    """
    url = get_settings().mentible_request_url
    return HttpMentibleClient(url) if url else NullMentibleClient()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session that commits on success, rolls back on error."""
    async with session_scope() as session:
        yield session


def get_signature_verifier() -> SignatureVerifier:
    """Build the package signature verifier from configured key custody."""
    secret = get_settings().mentible_package_hmac_secret.get_secret_value()
    return HmacSignatureVerifier(secret)


class PackageIngestor(Protocol):
    """The seam the ingestion route depends on.

    A protocol (not the bare service function) so the HTTP layer can be tested
    independently of the database: tests override :func:`get_package_ingestor`
    with a fake that returns a stub draft or raises a domain exception.
    """

    async def ingest(
        self,
        *,
        manifest: Mapping[str, Any],
        tenant_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> ContentDraft: ...


class _ServicePackageIngestor:
    """Default ingestor: binds a session + verifier and delegates to the service."""

    def __init__(self, session: AsyncSession, verifier: SignatureVerifier) -> None:
        self._session = session
        self._verifier = verifier

    async def ingest(
        self,
        *,
        manifest: Mapping[str, Any],
        tenant_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> ContentDraft:
        return await ingest_consumable_package(
            self._session,
            manifest=manifest,
            tenant_id=tenant_id,
            course_id=course_id,
            verifier=self._verifier,
            now=utcnow(),
        )


def get_package_ingestor(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    verifier: Annotated[SignatureVerifier, Depends(get_signature_verifier)],
) -> PackageIngestor:
    """Provide the default database-backed package ingestor."""
    return _ServicePackageIngestor(session, verifier)


# ---------------------------------------------------------------------------
# Authentication — OIDC bearer token → Principal
# ---------------------------------------------------------------------------
async def _httpx_get_json(url: str) -> Mapping[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data: Mapping[str, Any] = resp.json()
        return data


@lru_cache(maxsize=1)
def get_token_verifier() -> TokenVerifier:
    """Build the process-singleton OIDC verifier (JWKS cache persists across requests)."""
    s = get_settings()
    return OidcJwtVerifier(
        issuer=s.sso_issuer_url,
        audience=s.jwt_audience,
        algorithms=[s.jwt_algorithm],
        key_source=JwksKeySource(s.sso_issuer_url, http_get_json=_httpx_get_json),
    )


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if not header:
        raise AuthenticationError("missing Authorization header")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("expected an 'Authorization: Bearer <token>' header")
    return token


async def get_principal(
    request: Request,
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Principal:
    """Resolve the authenticated principal from the request's OIDC bearer token.

    Extracts the bearer token, verifies it (signature + ``iss``/``aud``/``exp``)
    against the issuer's JWKS, and maps the ``sub`` claim to a Pramana user.
    """
    token = _bearer_token(request)
    claims = await verifier.verify(token)
    return await resolve_principal(session, claims, now=utcnow())


# ---------------------------------------------------------------------------
# Content-review service seam
# ---------------------------------------------------------------------------
class ContentReviewService(Protocol):
    """The seam the ``/content-drafts`` routes depend on, so the HTTP layer is
    testable without a database (tests override :func:`get_content_review_service`)."""

    async def list_drafts(
        self,
        *,
        status: ContentDraftStatus | None,
        framework: str | None,
        quarantined: bool,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[ContentDraft], int]: ...

    async def get_draft(self, draft_id: uuid.UUID) -> ContentDraft: ...

    async def submit_for_review(self, draft_id: uuid.UUID) -> ContentDraft: ...

    async def approve(self, draft_id: uuid.UUID, *, attestation_text: str) -> ContentDraft: ...

    async def request_changes(self, draft_id: uuid.UUID, *, notes: str) -> ContentDraft: ...

    async def reject(self, draft_id: uuid.UUID, *, notes: str) -> ContentDraft: ...

    async def publish(self, draft_id: uuid.UUID, *, is_material_change: bool) -> CourseVersion: ...


class _DbContentReviewService:
    """Default review service: binds a session + principal to the service layer."""

    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self._s = session
        self._p = principal

    async def list_drafts(
        self,
        *,
        status: ContentDraftStatus | None,
        framework: str | None,
        quarantined: bool,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[ContentDraft], int]:
        return await content_review.list_drafts(
            self._s,
            tenant_id=self._p.tenant_id,
            status=status,
            framework=framework,
            quarantined=quarantined,
            page=page,
            page_size=page_size,
        )

    async def get_draft(self, draft_id: uuid.UUID) -> ContentDraft:
        return await content_review.get_draft(self._s, draft_id=draft_id)

    async def submit_for_review(self, draft_id: uuid.UUID) -> ContentDraft:
        return await content_review.submit_for_review(
            self._s,
            draft_id=draft_id,
            tenant_id=self._p.tenant_id,
            actor_user_id=self._p.user_id,
            now=utcnow(),
        )

    async def approve(self, draft_id: uuid.UUID, *, attestation_text: str) -> ContentDraft:
        return await content_review.approve_draft(
            self._s,
            draft_id=draft_id,
            tenant_id=self._p.tenant_id,
            approver_user_id=self._p.user_id,
            attestation_text=attestation_text,
            now=utcnow(),
        )

    async def request_changes(self, draft_id: uuid.UUID, *, notes: str) -> ContentDraft:
        return await content_review.request_changes(
            self._s,
            draft_id=draft_id,
            tenant_id=self._p.tenant_id,
            actor_user_id=self._p.user_id,
            notes=notes,
            now=utcnow(),
        )

    async def reject(self, draft_id: uuid.UUID, *, notes: str) -> ContentDraft:
        return await content_review.reject_draft(
            self._s,
            draft_id=draft_id,
            tenant_id=self._p.tenant_id,
            actor_user_id=self._p.user_id,
            notes=notes,
            now=utcnow(),
        )

    async def publish(self, draft_id: uuid.UUID, *, is_material_change: bool) -> CourseVersion:
        return await content_review.publish_draft(
            self._s,
            draft_id=draft_id,
            tenant_id=self._p.tenant_id,
            publisher_user_id=self._p.user_id,
            now=utcnow(),
            is_material_change=is_material_change,
        )


def get_content_review_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> ContentReviewService:
    """Provide the default database-backed content-review service."""
    return _DbContentReviewService(session, principal)


# ---------------------------------------------------------------------------
# Content-request (commission) service seam
# ---------------------------------------------------------------------------
class ContentRequestService(Protocol):
    """The seam the ``/content-requests`` + regenerate routes depend on."""

    async def commission(self, body: Mapping[str, Any]) -> ContentRequest: ...

    async def regenerate(
        self, draft_id: uuid.UUID, *, parameter_overrides: Mapping[str, Any] | None
    ) -> ContentRequest: ...

    async def list_requests(
        self,
        *,
        framework: str | None,
        status: ContentRequestStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[ContentRequest], int]: ...

    async def get_request(self, request_id: uuid.UUID) -> ContentRequest: ...


class _DbContentRequestService:
    """Default commission service: binds session, principal, library, and client."""

    def __init__(
        self,
        session: AsyncSession,
        principal: Principal,
        definitions_root: Path,
        mentible: MentibleClient,
    ) -> None:
        self._s = session
        self._p = principal
        self._root = definitions_root
        self._mentible = mentible

    async def commission(self, body: Mapping[str, Any]) -> ContentRequest:
        return await content_requests.commission_request(
            self._s,
            body=body,
            tenant_id=self._p.tenant_id,
            requested_by=self._p.user_id,
            definitions_root=self._root,
            mentible=self._mentible,
            now=utcnow(),
        )

    async def regenerate(
        self, draft_id: uuid.UUID, *, parameter_overrides: Mapping[str, Any] | None
    ) -> ContentRequest:
        return await content_requests.regenerate_from_draft(
            self._s,
            draft_id=draft_id,
            tenant_id=self._p.tenant_id,
            requested_by=self._p.user_id,
            parameter_overrides=parameter_overrides,
            definitions_root=self._root,
            mentible=self._mentible,
            now=utcnow(),
        )

    async def list_requests(
        self,
        *,
        framework: str | None,
        status: ContentRequestStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[ContentRequest], int]:
        return await content_requests.list_requests(
            self._s,
            tenant_id=self._p.tenant_id,
            framework=framework,
            status=status,
            page=page,
            page_size=page_size,
        )

    async def get_request(self, request_id: uuid.UUID) -> ContentRequest:
        return await content_requests.get_request(
            self._s, request_id=request_id, tenant_id=self._p.tenant_id
        )


def get_content_request_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    principal: Annotated[Principal, Depends(get_principal)],
    definitions_root: Annotated[Path, Depends(get_definitions_root)],
    mentible: Annotated[MentibleClient, Depends(get_mentible_client)],
) -> ContentRequestService:
    """Provide the default database-backed content-request (commission) service."""
    return _DbContentRequestService(session, principal, definitions_root, mentible)
