"""Evidence binder — the auditor's per-user training record (US-FCPA-0006).

Bundles, for one user, everything an auditor needs to answer "who was trained on
what, when, and did they pass?" — assignments, every attempt and score, the
**exact content version** trained on, the certificate, and the attestation. The
assignment / attempt / certificate rows are themselves version-pinned evidence
(they snapshot ``course_version_id``), so a superseded version is still
faithfully represented for users trained on it.

Read-only; tenant-scoped. The shared ``Auditor`` role covers every framework, so
this is deliberately framework-agnostic — a SOX or HIPAA binder is the same
query with a different downstream template (templates are a later refinement).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pramana.db.models.assignment import Assignment, Attempt, Certificate
from pramana.db.models.course import Course, CourseVersion
from pramana.db.models.identity import User
from pramana.exceptions import NotFoundError


@dataclass(frozen=True, slots=True)
class AssignmentEvidence:
    """One assignment's full evidence: the assignment, its attempts, certificate."""

    assignment: Assignment
    attempts: Sequence[Attempt]
    certificate: Certificate | None
    course_title: str
    course_version_number: int


@dataclass(frozen=True, slots=True)
class EvidenceBinder:
    """A user's complete training-evidence binder."""

    user_id: uuid.UUID
    user_email: str
    items: Sequence[AssignmentEvidence]


async def build_evidence_binder(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
) -> EvidenceBinder:
    """Assemble the evidence binder for one user (optionally within a period).

    Raises:
        NotFoundError: The user does not exist in this tenant.
    """
    user = await session.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise NotFoundError("user not found", context={"user_id": str(user_id)})

    filters = [Assignment.tenant_id == tenant_id, Assignment.user_id == user_id]
    if occurred_after is not None:
        filters.append(Assignment.assigned_at >= occurred_after)
    if occurred_before is not None:
        filters.append(Assignment.assigned_at <= occurred_before)

    assignments = (
        (
            await session.execute(
                select(Assignment)
                .where(*filters)
                .order_by(Assignment.assigned_at.asc())
                .options(
                    selectinload(Assignment.attempts),
                    selectinload(Assignment.certificate),
                )
            )
        )
        .scalars()
        .all()
    )

    items: list[AssignmentEvidence] = []
    for a in assignments:
        version = await session.get(CourseVersion, a.course_version_id)
        course = await session.get(Course, a.course_id)
        attempts = sorted(a.attempts, key=lambda at: at.attempt_number)
        items.append(
            AssignmentEvidence(
                assignment=a,
                attempts=attempts,
                certificate=a.certificate,
                course_title=course.title if course is not None else "",
                course_version_number=version.version_number if version is not None else 0,
            )
        )

    return EvidenceBinder(user_id=user_id, user_email=user.email, items=items)
