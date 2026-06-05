"""FastAPI dependency providers.

Kept separate from the routers so tests can override individual seams
(``app.dependency_overrides[...]``) without importing route internals.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.config import get_settings
from pramana.db.models.content import ContentDraft
from pramana.db.models.course import CourseVersion
from pramana.db.session import session_scope
from pramana.domain.consumable_package import SignatureVerifier
from pramana.domain.content_approval import utcnow
from pramana.domain.enums import ContentDraftStatus
from pramana.exceptions import AuthenticationError
from pramana.services import content_review
from pramana.services.consumer_library import ingest_consumable_package
from pramana.services.package_signing import HmacSignatureVerifier


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
# Current principal (user + tenant)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller: their ``user_id`` and ``tenant_id``."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID


def get_principal() -> Principal:
    """Resolve the authenticated principal from the request.

    Auth (OIDC/JWT → ``user_id``) is not wired yet, so this raises by default;
    tests override it. Real deployment will map the JWT ``sub`` claim to a Pramana
    user and tenant here.
    """
    raise AuthenticationError("authentication is not configured")


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
