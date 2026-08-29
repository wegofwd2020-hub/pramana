"""Certificate HTTP router.

Reads are tenant-scoped and default to the caller's own certificates. The
verification endpoint is deliberately **public and unauthenticated** — the
verification code is itself the credential — and returns only the minimal,
non-PII facts an external verifier needs.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.api.dependencies import (
    forbid_cross_user_read,
    get_db_session,
    get_pdf_renderer,
    get_principal,
    may_read_others,
)
from pramana.api.schemas import (
    CertificateOut,
    CertificatePage,
    CertificateVerification,
    Pagination,
)
from pramana.domain.assignment_state import utcnow
from pramana.domain.certificate_document import build_certificate_html
from pramana.exceptions import AuthorizationError
from pramana.services import certificate_pdf
from pramana.services import certificates as svc
from pramana.services.audit import append_audit
from pramana.services.auth import Principal

router = APIRouter(prefix="/certificates", tags=["certificates"])

Session = Annotated[AsyncSession, Depends(get_db_session)]
Caller = Annotated[Principal, Depends(get_principal)]
Renderer = Annotated[certificate_pdf.PdfRenderer, Depends(get_pdf_renderer)]


@router.get("", response_model=CertificatePage, dependencies=[Depends(forbid_cross_user_read)])
async def list_certificates(
    session: Session,
    caller: Caller,
    user_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CertificatePage:
    """List certificates — the caller's own by default, or a given user's (staff)."""
    rows, total = await svc.list_certificates(
        session,
        tenant_id=caller.tenant_id,
        user_id=user_id if user_id is not None else caller.user_id,
        page=page,
        page_size=page_size,
    )
    return CertificatePage(
        items=[CertificateOut.of(c) for c in rows],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.get("/verify/{verification_code}", response_model=CertificateVerification)
async def verify_certificate(verification_code: str, session: Session) -> CertificateVerification:
    """Publicly verify a certificate by its code (unauthenticated)."""
    cert = await svc.verify_by_code(session, verification_code=verification_code)
    if cert is None:
        return CertificateVerification(valid=False)
    return CertificateVerification(
        valid=True,
        certificate_id=cert.id,
        course_id=cert.course_id,
        course_version_id=cert.course_version_id,
        issued_at=getattr(cert, "issued_at", None),
        expires_at=cert.expires_at,
        expired=cert.expires_at < utcnow(),
    )


@router.get("/{certificate_id}", response_model=CertificateOut)
async def get_certificate(
    certificate_id: uuid.UUID, session: Session, caller: Caller
) -> CertificateOut:
    """Read one certificate — the caller's own, or any of them if staff."""
    cert = await svc.get_certificate(
        session, certificate_id=certificate_id, tenant_id=caller.tenant_id
    )
    if not may_read_others(caller) and cert.user_id != caller.user_id:
        raise AuthorizationError(
            "not your certificate", context={"certificate_id": str(certificate_id)}
        )
    return CertificateOut.of(cert)


@router.get("/{certificate_id}/pdf", response_model=None)
async def download_certificate_pdf(
    certificate_id: uuid.UUID, session: Session, caller: Caller, render: Renderer
) -> Response:
    """The certificate as a PDF, rendered on demand.

    Nothing is stored: every fact is immutable and pinned, so re-rendering is
    reproducible and there is no file that can drift from the record.

    A third party reading somebody else's certificate is evidence access and is
    audited as ``certificate.downloaded``. A learner fetching their own is not —
    logging routine self-service would bury the accesses that matter.
    """
    certificate = await certificate_pdf.load_certificate(
        session, certificate_id=certificate_id, tenant_id=caller.tenant_id
    )
    is_owner = certificate.user_id == caller.user_id
    if not is_owner and not may_read_others(caller):
        raise AuthorizationError(
            "not your certificate", context={"certificate_id": str(certificate_id)}
        )

    document = await certificate_pdf.build_certificate_document(session, certificate=certificate)
    pdf = render(build_certificate_html(document, now=utcnow()))

    if not is_owner:
        await append_audit(
            session,
            tenant_id=caller.tenant_id,
            actor_user_id=caller.user_id,
            entity_type="certificate",
            entity_id=str(certificate.id),
            event_type="certificate.downloaded",
            payload={"subject_user_id": str(certificate.user_id)},
            occurred_at=utcnow(),
        )

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{certificate_pdf.certificate_filename(certificate)}"'
            )
        },
    )
