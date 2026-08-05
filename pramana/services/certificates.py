"""Certificate service — issue and verify completion certificates.

A certificate is issued automatically when an assignment reaches ``PASSED``
(driven from :mod:`pramana.services.assignments`). It is **evidence**: pinned to
the exact ``CourseVersion`` the learner was tested on, carrying the SOX
attestation captured at submission, and expiring at the recertification horizon
(issued + the course's cooldown window). PDF rendering is out of scope here —
``pdf_object_key`` stays null; a later slice renders and uploads it.

Verification is public-by-code: the ``verification_code`` is itself the
credential, so :func:`verify_by_code` is intentionally not tenant-scoped. All
other reads are tenant-scoped like the rest of the API.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.assignment import Assignment, Certificate
from pramana.domain.enums import CertificateEvent
from pramana.exceptions import NotFoundError
from pramana.services.audit import append_audit

# 16 bytes -> 32 hex chars, matching Certificate.verification_code String(32).
_CODE_BYTES = 16


async def issue_certificate(
    session: AsyncSession,
    *,
    assignment: Assignment,
    attestation_text_version: str,
    attestation_timestamp: datetime,
    attestation_ip: str | None,
    attestation_user_agent: str | None,
    now: datetime,
) -> Certificate:
    """Issue a certificate for a just-passed assignment.

    Pins the certificate to the assignment's played ``course_version_id`` and
    sets ``expires_at`` to ``now + cooldown_days`` (the recertification horizon).
    Appends a ``certificate.issue`` audit entry. Not committed — the caller owns
    the transaction. The assignment↔certificate uniqueness is enforced by the
    schema, so a double-issue raises at flush.
    """
    cert = Certificate(
        id=uuid.uuid4(),
        tenant_id=assignment.tenant_id,
        user_id=assignment.user_id,
        course_id=assignment.course_id,
        course_version_id=assignment.course_version_id,
        assignment_id=assignment.id,
        issued_at=now,
        expires_at=now + timedelta(days=assignment.cooldown_days),
        verification_code=secrets.token_hex(_CODE_BYTES),
        attestation_text_version=attestation_text_version,
        attestation_ip=attestation_ip,
        attestation_user_agent=attestation_user_agent,
        attestation_timestamp=attestation_timestamp,
    )
    session.add(cert)
    await append_audit(
        session,
        tenant_id=cert.tenant_id,
        actor_user_id=cert.user_id,
        entity_type="certificate",
        entity_id=str(cert.id),
        event_type=f"certificate.{CertificateEvent.ISSUE.value}",
        payload={
            "assignment_id": str(cert.assignment_id),
            "course_version_id": str(cert.course_version_id),
            "expires_at": cert.expires_at.isoformat(),
        },
        occurred_at=now,
    )
    return cert


async def get_certificate(
    session: AsyncSession, *, certificate_id: uuid.UUID, tenant_id: uuid.UUID
) -> Certificate:
    """Load one certificate scoped to the tenant (404 otherwise)."""
    cert = await session.get(Certificate, certificate_id)
    if cert is None or cert.tenant_id != tenant_id:
        raise NotFoundError(
            "certificate not found", context={"certificate_id": str(certificate_id)}
        )
    return cert


async def list_certificates(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[Sequence[Certificate], int]:
    """Return a page of certificates for the tenant (optionally one user) + total."""
    filters = [Certificate.tenant_id == tenant_id]
    if user_id is not None:
        filters.append(Certificate.user_id == user_id)

    total = (
        await session.execute(select(func.count()).select_from(Certificate).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(Certificate)
                .where(*filters)
                .order_by(Certificate.issued_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .scalars()
        .all()
    )
    return rows, total


async def verify_by_code(session: AsyncSession, *, verification_code: str) -> Certificate | None:
    """Resolve a certificate by its public verification code (not tenant-scoped).

    The code is the credential, so verification is deliberately cross-tenant and
    unauthenticated. Returns ``None`` when the code matches nothing.
    """
    return (
        await session.execute(
            select(Certificate).where(Certificate.verification_code == verification_code)
        )
    ).scalar_one_or_none()
