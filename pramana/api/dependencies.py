"""FastAPI dependency providers.

Kept separate from the routers so tests can override individual seams
(``app.dependency_overrides[...]``) without importing route internals.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping
from typing import Annotated, Any, Protocol

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.config import get_settings
from pramana.db.models.content import ContentDraft
from pramana.db.session import session_scope
from pramana.domain.consumable_package import SignatureVerifier
from pramana.domain.content_approval import utcnow
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
