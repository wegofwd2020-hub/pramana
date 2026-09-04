"""Enrollment service — per-(user, lesson) progress anchor.

Access is NOT granted here; enrollment is progress state. The router checks the
live entitlement before calling in.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.consumer import ConsumerAttempt, Enrollment, PlaySession
from pramana.domain.consumer.completion import derive_counters
from pramana.exceptions import NotFoundError


async def get_or_create_enrollment(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    entitlement_id: uuid.UUID,
    now: datetime,
) -> Enrollment:
    existing = (
        await session.execute(
            select(Enrollment).where(
                Enrollment.user_id == user_id, Enrollment.course_id == course_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.last_accessed_at = now
        return existing

    enrollment = Enrollment(
        tenant_id=tenant_id,
        user_id=user_id,
        course_id=course_id,
        entitlement_id=entitlement_id,
        first_accessed_at=now,
        last_accessed_at=now,
    )
    session.add(enrollment)
    await session.flush()
    return enrollment


async def recompute_counters(session: AsyncSession, *, enrollment_id: uuid.UUID) -> Enrollment:
    enrollment = await session.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("enrollment not found", context={"enrollment_id": str(enrollment_id)})

    num_views = (
        await session.execute(
            select(func.count())
            .select_from(PlaySession)
            .where(PlaySession.enrollment_id == enrollment_id)
        )
    ).scalar_one()
    scores: list[float] = [
        s
        for s in (
            await session.execute(
                select(ConsumerAttempt.score_pct).where(
                    ConsumerAttempt.enrollment_id == enrollment_id,
                    ConsumerAttempt.submitted_at.is_not(None),
                    ConsumerAttempt.score_pct.is_not(None),
                )
            )
        ).scalars()
        if s is not None
    ]
    counters = derive_counters(num_views=num_views, attempt_scores=scores)
    enrollment.view_count = counters.view_count
    enrollment.completion_count = counters.completion_count
    enrollment.best_score_pct = counters.best_score_pct
    return enrollment
