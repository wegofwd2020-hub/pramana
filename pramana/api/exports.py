"""``/exports`` — the auditor's CSV artifacts (US-SOX-0006).

Thin HTTP shell over :mod:`pramana.services.reporting`, which sources status from
the audit log rather than current state so a report answers "what was true during
the period" rather than "what is true now".

Every export appends an audit entry. ``US-SOX-0006`` AC3 requires that auditor
access to evidence be itself logged, and ``/audit/export`` already set that
precedent: reading the records is an event in the record.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.api.dependencies import get_db_session, get_pdf_renderer, require_roles
from pramana.db.models.identity import RoleName, User
from pramana.domain.assignment_state import utcnow
from pramana.domain.binder_document import (
    FRAMINGS,
    AttemptLine,
    BinderDocument,
    BinderItem,
    build_binder_html,
)
from pramana.exceptions import NotFoundError
from pramana.services import certificate_pdf, evidence, reporting
from pramana.services.audit import append_audit
from pramana.services.auth import Principal

router = APIRouter(prefix="/exports", tags=["Exports"])

_AUDITOR = require_roles(RoleName.AUDITOR, RoleName.COMPLIANCE_ADMIN)

Session = Annotated[AsyncSession, Depends(get_db_session)]
# Declared on each route as well as here: a route dependency resolves before the
# endpoint's own parameters, so an unauthorised caller is refused before the
# request opens a database session.
Auditor = Annotated[Principal, Depends(_AUDITOR)]
Renderer = Annotated[certificate_pdf.PdfRenderer, Depends(get_pdf_renderer)]


def _end_of(day: date | None) -> datetime:
    """Interpret a date parameter as the *end* of that day.

    A report "as of 2026-03-31" means through the close of the 31st. Treating the
    date as midnight would silently exclude everything that happened on the day
    the auditor named.
    """
    if day is None:
        return utcnow()
    return datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=UTC)


def _start_of(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


async def _record(
    session: AsyncSession, caller: Principal, *, report: str, row_count: int, **context: object
) -> None:
    await append_audit(
        session,
        tenant_id=caller.tenant_id,
        actor_user_id=caller.user_id,
        entity_type="export",
        entity_id=report,
        event_type=f"export.{report}",
        payload={"row_count": row_count, **context},
        occurred_at=utcnow(),
    )


def _csv(rows: list[dict[str, object]], columns: tuple[str, ...], filename: str) -> Response:
    return Response(
        content=reporting.rows_to_csv(rows, columns=columns),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/population", response_model=None, dependencies=[Depends(_AUDITOR)])
async def export_population(
    session: Session,
    auditor: Auditor,
    as_of: date | None = None,
    framework_tag: str | None = None,
) -> Response:
    """The in-scope population as CSV.

    In scope means *assigned*: users who held at least one assignment as of the
    date. The system can prove who the control actually covered; it has no HR
    notion of who ought to have been covered.

    ``user_status_current`` is named for what it is — user attributes are not
    historised, so that column is a present-day value even when ``as_of`` is not.
    """
    as_of_dt = _end_of(as_of)
    rows = await reporting.population(
        session,
        tenant_id=auditor.tenant_id,
        as_of=as_of_dt,
        framework_tag=framework_tag,
    )
    await _record(
        session,
        auditor,
        report="population",
        row_count=len(rows),
        as_of=as_of_dt.isoformat(),
        framework_tag=framework_tag,
    )
    return _csv(rows, reporting.POPULATION_COLUMNS, "population.csv")


@router.get("/training-matrix", response_model=None, dependencies=[Depends(_AUDITOR)])
async def export_training_matrix(
    session: Session,
    auditor: Auditor,
    period_start: Annotated[date, Query()],
    period_end: Annotated[date, Query()],
    framework_tag: str | None = None,
) -> Response:
    """Users against courses, with the status each held at ``period_end``.

    ``course_version_id`` is the version the learner was actually tested on, not
    the course's current version — a retired version stays represented.
    """
    start, end = _start_of(period_start), _end_of(period_end)
    rows = await reporting.training_matrix(
        session,
        tenant_id=auditor.tenant_id,
        period_start=start,
        period_end=end,
        framework_tag=framework_tag,
    )
    await _record(
        session,
        auditor,
        report="training_matrix",
        row_count=len(rows),
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        framework_tag=framework_tag,
    )
    return _csv(rows, reporting.MATRIX_COLUMNS, "training-matrix.csv")


@router.get("/exception-report", response_model=None, dependencies=[Depends(_AUDITOR)])
async def export_exception_report(
    session: Session,
    auditor: Auditor,
    as_of: date | None = None,
    framework_tag: str | None = None,
) -> Response:
    """Assignments overdue, blocked, or expired as of the date."""
    as_of_dt = _end_of(as_of)
    rows = await reporting.exception_report(
        session,
        tenant_id=auditor.tenant_id,
        as_of=as_of_dt,
        framework_tag=framework_tag,
    )
    await _record(
        session,
        auditor,
        report="exception_report",
        row_count=len(rows),
        as_of=as_of_dt.isoformat(),
        framework_tag=framework_tag,
    )
    return _csv(rows, reporting.EXCEPTION_COLUMNS, "exception-report.csv")


def _to_binder_item(ev: evidence.AssignmentEvidence) -> BinderItem:
    """Map one assignment's evidence onto what the binder renders."""
    cert = ev.certificate
    return BinderItem(
        course_title=ev.course_title,
        course_version_id=ev.assignment.course_version_id,
        course_version_number=ev.course_version_number,
        status=ev.assignment.status,
        assigned_at=ev.assignment.assigned_at,
        terminal_at=getattr(ev.assignment, "terminal_at", None),
        attempts=tuple(
            AttemptLine(
                attempt_number=a.attempt_number,
                outcome=a.outcome,
                score_pct=a.score_pct,
                submitted_at=getattr(a, "submitted_at", None),
            )
            for a in ev.attempts
        ),
        certificate_code=cert.verification_code if cert else None,
        certificate_issued_at=getattr(cert, "issued_at", None) if cert else None,
        attestation_text_version=cert.attestation_text_version if cert else None,
        attestation_timestamp=cert.attestation_timestamp if cert else None,
    )


@router.get(
    "/users/{user_id}/audit-binder",
    response_model=None,
    dependencies=[Depends(_AUDITOR)],
)
async def export_audit_binder(
    user_id: uuid.UUID,
    session: Session,
    auditor: Auditor,
    render: Renderer,
    period_start: Annotated[date, Query()],
    period_end: Annotated[date, Query()],
    framework: str = "sox",
) -> Response:
    """One person's evidence package as a PDF — the sample-testing artifact.

    The document states which citation it answers and, at the end, what it does
    *not* cover: every framework asks for evidence Pramana does not hold, and a
    binder that omits that silently implies a completeness it lacks.
    """
    framing = FRAMINGS.get(framework)
    if framing is None:
        raise NotFoundError(
            "unknown framework",
            context={"framework": framework, "known": sorted(FRAMINGS)},
        )

    start, end = _start_of(period_start), _end_of(period_end)
    binder = await evidence.build_evidence_binder(
        session,
        tenant_id=auditor.tenant_id,
        user_id=user_id,
        occurred_after=start,
        occurred_before=end,
    )
    subject = await session.get(User, user_id)
    document = BinderDocument(
        subject_name=certificate_pdf.display_name(subject) if subject else binder.user_email,
        subject_email=binder.user_email,
        framing=framing,
        period_start=start,
        period_end=end,
        generated_at=utcnow(),
        items=tuple(_to_binder_item(i) for i in binder.items),
    )
    pdf = render(build_binder_html(document))

    await _record(
        session,
        auditor,
        report="audit_binder",
        row_count=len(document.items),
        subject_user_id=str(user_id),
        framework=framework,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="audit-binder-{framework}-{user_id}.pdf"'
            )
        },
    )
