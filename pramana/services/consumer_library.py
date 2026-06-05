"""``consumer_library`` ingestion — Pramana's side of the Mentible handoff.

Mentible ADR-011 §6-§7: Mentible pushes a signed Consumable Package; Pramana
**verifies signature + content_hash**, and on success records it as an
*untrusted* ``RECEIVED`` content draft — never silently published. The human
approval gate (:mod:`pramana.domain.content_approval`) sits downstream,
unchanged.

The pure work — parse, verify, map — is :func:`verify_and_map` (no I/O, fully
unit-testable). :func:`ingest_consumable_package` is the thin transactional
shell: idempotency check, course lookup, persist the draft, append the audit
entry. The caller owns the transaction (commit/rollback).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.content import ContentDraft
from pramana.db.models.course import Course
from pramana.domain.consumable_package import (
    SignatureVerifier,
    parse_manifest,
    verify_package,
)
from pramana.domain.enums import ContentEvent
from pramana.domain.ingestion import IngestedDraftFields, package_to_draft_fields
from pramana.exceptions import DuplicatePackageError, NotFoundError
from pramana.services.audit import append_audit


def verify_and_map(
    manifest: Mapping[str, Any],
    *,
    tenant_id: uuid.UUID,
    course_id: uuid.UUID,
    verifier: SignatureVerifier,
) -> IngestedDraftFields:
    """Parse, integrity-verify, and project a manifest onto draft fields.

    Pure: no database, no clock. The two failure modes are surfaced as
    distinct exceptions so the boundary can react correctly:

    Raises:
        PackageValidationError: The manifest is structurally invalid.
        PackageIntegrityError: Signature or content_hash failed — quarantine.
    """
    package = parse_manifest(manifest)
    verify_package(package, verifier)
    return package_to_draft_fields(package, tenant_id=tenant_id, course_id=course_id)


async def ingest_consumable_package(
    session: AsyncSession,
    *,
    manifest: Mapping[str, Any],
    tenant_id: uuid.UUID,
    course_id: uuid.UUID,
    verifier: SignatureVerifier,
    now: datetime,
) -> ContentDraft:
    """Ingest one pushed Consumable Package into a ``RECEIVED`` draft.

    Idempotent on ``(tenant_id, package_id, package_version)``: a re-push of an
    already-received package raises :class:`DuplicatePackageError` rather than
    creating a second draft.

    Raises:
        PackageValidationError: Malformed manifest (before any DB write).
        PackageIntegrityError: Signature / content_hash mismatch — quarantined.
        NotFoundError: ``course_id`` does not exist in this tenant.
        DuplicatePackageError: This package/version was already ingested.
    """
    fields = verify_and_map(manifest, tenant_id=tenant_id, course_id=course_id, verifier=verifier)

    course = (
        await session.execute(
            select(Course.id).where(Course.id == course_id, Course.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if course is None:
        raise NotFoundError(
            "course not found in tenant",
            context={"course_id": str(course_id), "tenant_id": str(tenant_id)},
        )

    existing = (
        await session.execute(
            select(ContentDraft.id).where(
                ContentDraft.tenant_id == tenant_id,
                ContentDraft.package_id == fields.package_id,
                ContentDraft.package_version == fields.package_version,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicatePackageError(
            "package already ingested",
            context={
                "package_id": str(fields.package_id),
                "package_version": fields.package_version,
                "existing_draft_id": str(existing),
            },
        )

    draft = ContentDraft(**fields.as_model_kwargs())
    session.add(draft)
    await session.flush()  # assign draft.id for the audit entry

    await append_audit(
        session,
        tenant_id=tenant_id,
        entity_type="content_draft",
        entity_id=str(draft.id),
        event_type=f"content_draft.{ContentEvent.RECEIVE.value}",
        payload={
            "package_id": str(fields.package_id),
            "package_version": fields.package_version,
            "content_hash": fields.package_content_hash,
            "engine": fields.gen_engine,
            "model": fields.gen_model,
            "provider": fields.gen_provider,
            "prompt_version": fields.gen_prompt_version,
        },
        occurred_at=now,
    )
    return draft
