"""Render a certificate to PDF, on demand.

Nothing is stored. Every fact on a certificate is immutable and pinned — the
course *version* tested on, the score, the issue and expiry dates, the
verification code, the attestation accepted — so re-rendering always produces the
same document. Storing it would buy a cache and cost the question of what to do
when the file and the row disagree; the row is the evidence and the endpoint at
``/certificates/verify/{code}`` is what a third party should trust.

``Certificate.pdf_object_key`` is therefore unused. It is left in place rather
than dropped in case a deployment later wants a durable copy.

The renderer is injected, matching the object-storage seams: WeasyPrint needs
system libraries (pango, cairo) that a test environment has no reason to carry,
so tests pass a fake and the real import happens lazily inside the factory.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.assignment import Attempt, Certificate
from pramana.db.models.course import Course, CourseVersion
from pramana.db.models.identity import User
from pramana.domain.certificate_document import CertificateDocument
from pramana.exceptions import NotFoundError, PramanaError

if TYPE_CHECKING:  # pragma: no cover
    pass

#: ``html -> pdf bytes``.
PdfRenderer = Callable[[str], bytes]


def build_weasyprint_renderer() -> PdfRenderer:
    """A renderer backed by WeasyPrint, imported lazily.

    Lazy because WeasyPrint pulls in native libraries at import time. Deferring
    it means a deployment that never renders a certificate — and every test —
    does not need them present.
    """

    def _render(html: str) -> bytes:
        try:
            from weasyprint import HTML  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on deploy extras
            raise PramanaError(
                "certificate rendering requires weasyprint and its native "
                "dependencies (pango, cairo)"
            ) from exc
        return bytes(HTML(string=html).write_pdf())

    return _render


async def build_certificate_document(
    session: AsyncSession, *, certificate: Certificate
) -> CertificateDocument:
    """Gather the pinned facts a certificate displays.

    The score lives on the attempt rather than the certificate, so it is read
    from the highest-numbered attempt on the assignment — the one that produced
    the pass.
    """
    user = await session.get(User, certificate.user_id)
    course = await session.get(Course, certificate.course_id)
    version = await session.get(CourseVersion, certificate.course_version_id)
    if user is None or course is None or version is None:
        raise NotFoundError(
            "certificate references a missing record",
            context={"certificate_id": str(certificate.id)},
        )

    score = (
        await session.execute(
            select(Attempt.score_pct)
            .where(Attempt.assignment_id == certificate.assignment_id)
            .order_by(Attempt.attempt_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    return CertificateDocument(
        learner_name=_display_name(user),
        learner_email=user.email,
        course_title=course.title,
        course_version_id=version.id,
        course_version_number=version.version_number,
        score_pct=float(score or 0.0),
        issued_at=certificate.issued_at,
        expires_at=certificate.expires_at,
        verification_code=certificate.verification_code,
        attestation_text_version=certificate.attestation_text_version,
    )


def _display_name(user: User) -> str:
    """The learner's name, falling back to the email local part.

    Names are optional on a user record — a certificate still has to name
    somebody, and an empty line reads as a rendering bug.
    """
    parts = [p for p in (user.first_name, user.last_name) if p]
    return " ".join(parts) if parts else user.email.split("@")[0]


def certificate_filename(certificate: Certificate) -> str:
    """Download filename, keyed by the verification code so it is checkable."""
    return f"certificate-{certificate.verification_code}.pdf"


async def load_certificate(
    session: AsyncSession, *, certificate_id: uuid.UUID, tenant_id: uuid.UUID
) -> Certificate:
    """Load a certificate scoped to the tenant (404 otherwise)."""
    certificate = await session.get(Certificate, certificate_id)
    if certificate is None or certificate.tenant_id != tenant_id:
        raise NotFoundError(
            "certificate not found", context={"certificate_id": str(certificate_id)}
        )
    return certificate
