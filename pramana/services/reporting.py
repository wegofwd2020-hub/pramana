"""Auditor exports — the §404 artifacts, sourced from history.

``US-SOX-0006`` names the four things a §404 assessment needs: the population
list, the training matrix, sample evidence packages, and the exception report.
The evidence packages exist already (``/evidence/{user_id}``); this module is the
other three.

**The design constraint is where the data comes from.** Reading
``assignment.status`` would answer "what is true now". An auditor is asking "what
was true during the period", and those diverge the moment anything changes after
the period ends — a course version retired, an assignment cancelled, a user
reassigned. So status is read from the audit log: for each assignment, the last
``assignment.*`` entry at or before the as-of date.

Identity is joined from the ``assignment`` row, which is safe precisely because
those columns are immutable — ``user_id``, ``course_id`` and ``course_version_id``
are fixed at creation and never updated. The mutable field is the one the log
supplies.

**A limit worth knowing before you rely on a report.** User attributes —
employment status, department — are *not* historised. Nothing in the system
records their changes, and no code path mutates them today. So ``as_of`` is
genuinely point-in-time for training state, and current-value for the person. The
population export names that column ``user_status_current`` so a reader meets the
caveat in the file rather than in a document they may never see.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, String, cast, func, select
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.assignment import Assignment
from pramana.db.models.audit import AuditLog
from pramana.db.models.course import Course
from pramana.db.models.identity import User
from pramana.domain.enums import AssignmentStatus

Row = dict[str, Any]

#: Statuses that mean the learner is done and owes nothing further.
_SETTLED = {AssignmentStatus.PASSED.value}


def _status_as_of(as_of: datetime) -> Select[tuple[str, str, str, datetime]]:
    """Latest recorded status per assignment at or before ``as_of``.

    ``DISTINCT ON`` with ``audit_id DESC`` picks the most recent entry per
    assignment. Ordering by ``audit_id`` rather than ``occurred_at`` matters:
    ids are database-assigned and monotonic, so two events sharing a timestamp
    still resolve deterministically to the one that actually happened last.
    """
    return (
        select(
            AuditLog.entity_id.label("assignment_id"),
            AuditLog.payload["status"].astext.label("status"),
            AuditLog.payload["course_version_id"].astext.label("course_version_id"),
            AuditLog.occurred_at.label("occurred_at"),
        )
        .where(AuditLog.entity_type == "assignment", AuditLog.occurred_at <= as_of)
        .distinct(AuditLog.entity_id)
        .order_by(AuditLog.entity_id, AuditLog.audit_id.desc())
    )


def _joined(as_of: datetime, tenant_id: uuid.UUID, framework_tag: str | None) -> Select[Any]:
    """Historical status joined to the immutable identity of its assignment."""
    hist = _status_as_of(as_of).subquery()
    stmt = (
        select(
            hist.c.assignment_id,
            hist.c.status,
            hist.c.course_version_id,
            hist.c.occurred_at,
            Assignment.user_id,
            Assignment.course_id,
            Assignment.due_at,
            User.email,
            User.department,
            User.status.label("user_status_current"),
            Course.title.label("course_title"),
        )
        .join(Assignment, Assignment.id == func.cast(hist.c.assignment_id, Assignment.id.type))
        .join(User, User.user_id == Assignment.user_id)
        .join(Course, Course.id == Assignment.course_id)
        .where(Assignment.tenant_id == tenant_id)
    )
    if framework_tag is not None:
        # The column is mapped as a generic ARRAY, which has no containment
        # operator. Casting to the Postgres type gives `@>`, which the GIN index
        # on framework_tags can actually serve.
        stmt = stmt.where(cast(Course.framework_tags, PG_ARRAY(String)).contains([framework_tag]))
    return stmt


async def training_matrix(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    period_start: datetime,
    period_end: datetime,
    framework_tag: str | None = None,
) -> list[Row]:
    """One row per (user, course) with its status as of ``period_end``.

    Assignments created after the period are excluded; an assignment created
    before it and still running is included with the status it held then.
    """
    stmt = _joined(period_end, tenant_id, framework_tag).where(
        Assignment.assigned_at >= period_start
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "user_id": str(r.user_id),
            "user_email": r.email,
            "course_id": str(r.course_id),
            "course_title": r.course_title,
            "course_version_id": r.course_version_id,
            "status": r.status,
            "status_as_of": r.occurred_at.isoformat(),
        }
        for r in rows
    ]


async def population(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    as_of: datetime,
    framework_tag: str | None = None,
) -> list[Row]:
    """Users who held at least one assignment as of ``as_of``.

    "In-scope" is defined as *assigned* rather than as an HR notion of who ought
    to have been: the system knows who the control actually covered, and can
    prove it from the log.
    """
    rows = (await session.execute(_joined(as_of, tenant_id, framework_tag))).all()

    by_user: dict[str, Row] = {}
    for r in rows:
        entry = by_user.setdefault(
            str(r.user_id),
            {
                "user_id": str(r.user_id),
                "user_email": r.email,
                "department": r.department or "",
                "user_status_current": r.user_status_current,
                "courses_assigned": 0,
                "courses_passed": 0,
                "as_of": as_of.isoformat(),
            },
        )
        entry["courses_assigned"] += 1
        if r.status in _SETTLED:
            entry["courses_passed"] += 1
    return sorted(by_user.values(), key=lambda e: e["user_email"])


async def exception_report(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    as_of: datetime,
    framework_tag: str | None = None,
) -> list[Row]:
    """Assignments needing attention as of ``as_of``: overdue, blocked, expired.

    Overdue is derived rather than stored — an assignment past its due date that
    had not settled by ``as_of``. Blocked and expired are terminal states the
    machine records directly.
    """
    rows = (await session.execute(_joined(as_of, tenant_id, framework_tag))).all()

    out: list[Row] = []
    for r in rows:
        reason: str | None = None
        if r.status == AssignmentStatus.BLOCKED.value:
            reason = "blocked"
        elif r.status == AssignmentStatus.EXPIRED.value:
            reason = "expired"
        elif r.due_at is not None and r.due_at <= as_of and r.status not in _SETTLED:
            reason = "overdue"
        if reason is None:
            continue
        out.append(
            {
                "user_id": str(r.user_id),
                "user_email": r.email,
                "course_id": str(r.course_id),
                "course_title": r.course_title,
                "status": r.status,
                "due_at": r.due_at.isoformat() if r.due_at else "",
                "reason": reason,
                "as_of": as_of.isoformat(),
            }
        )
    return out


def rows_to_csv(rows: Sequence[Mapping[str, Any]], *, columns: Sequence[str]) -> str:
    """Render rows as CSV.

    ``columns`` is passed explicitly rather than inferred from the first row so
    an empty report still emits its header — a downstream parser handed a
    zero-byte file cannot tell "no exceptions" from "the export broke".
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(columns), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


POPULATION_COLUMNS = (
    "user_id",
    "user_email",
    "department",
    "user_status_current",
    "courses_assigned",
    "courses_passed",
    "as_of",
)

MATRIX_COLUMNS = (
    "user_id",
    "user_email",
    "course_id",
    "course_title",
    "course_version_id",
    "status",
    "status_as_of",
)

EXCEPTION_COLUMNS = (
    "user_id",
    "user_email",
    "course_id",
    "course_title",
    "status",
    "due_at",
    "reason",
    "as_of",
)

__all__ = [
    "EXCEPTION_COLUMNS",
    "MATRIX_COLUMNS",
    "POPULATION_COLUMNS",
    "exception_report",
    "population",
    "rows_to_csv",
    "training_matrix",
]
