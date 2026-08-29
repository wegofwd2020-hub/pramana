"""``/exports`` — the auditor's CSV artifacts (US-SOX-0006).

Thin HTTP shell over :mod:`pramana.services.reporting`, which sources status from
the audit log rather than current state so a report answers "what was true during
the period" rather than "what is true now".

Every export appends an audit entry. ``US-SOX-0006`` AC3 requires that auditor
access to evidence be itself logged, and ``/audit/export`` already set that
precedent: reading the records is an event in the record.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.api.dependencies import get_db_session, require_roles
from pramana.db.models.identity import RoleName
from pramana.domain.assignment_state import utcnow
from pramana.services import reporting
from pramana.services.audit import append_audit
from pramana.services.auth import Principal

router = APIRouter(prefix="/exports", tags=["Exports"])

_AUDITOR = require_roles(RoleName.AUDITOR, RoleName.COMPLIANCE_ADMIN)

Session = Annotated[AsyncSession, Depends(get_db_session)]
# Declared on each route as well as here: a route dependency resolves before the
# endpoint's own parameters, so an unauthorised caller is refused before the
# request opens a database session.
Auditor = Annotated[Principal, Depends(_AUDITOR)]


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
