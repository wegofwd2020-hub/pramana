# tests/integration/test_consumer_enrollment.py
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.services.consumer import enrollment as enr
from tests.integration.conftest import consumer_setup

pytestmark = pytest.mark.integration

now = datetime(2026, 1, 1, tzinfo=UTC)


async def test_get_or_create_is_idempotent(db: AsyncSession) -> None:
    s = await consumer_setup(db)
    e1 = await enr.get_or_create_enrollment(
        db,
        tenant_id=s.tenant_id,
        user_id=s.user.user_id,
        course_id=s.course.id,
        entitlement_id=s.entitlement.id,
        now=now,
    )
    e2 = await enr.get_or_create_enrollment(
        db,
        tenant_id=s.tenant_id,
        user_id=s.user.user_id,
        course_id=s.course.id,
        entitlement_id=s.entitlement.id,
        now=now,
    )
    assert e1.id == e2.id


async def test_recompute_counters_matches_events(db: AsyncSession) -> None:
    from pramana.db.models.consumer import ConsumerAttempt, PlaySession

    s = await consumer_setup(db)
    e = await enr.get_or_create_enrollment(
        db,
        tenant_id=s.tenant_id,
        user_id=s.user.user_id,
        course_id=s.course.id,
        entitlement_id=s.entitlement.id,
        now=now,
    )

    db.add(
        PlaySession(
            tenant_id=s.tenant_id,
            enrollment_id=e.id,
            course_version_id=s.course.current_version_id,
            duration_seconds=10,
            max_watched_pct=100,
        )
    )
    db.add(
        ConsumerAttempt(
            tenant_id=s.tenant_id,
            enrollment_id=e.id,
            course_version_id=s.course.current_version_id,
            submitted_at=now,
            score_pct=100.0,
            is_all_correct=True,
            question_count=3,
            correct_count=3,
        )
    )
    db.add(
        ConsumerAttempt(
            tenant_id=s.tenant_id,
            enrollment_id=e.id,
            course_version_id=s.course.current_version_id,
            submitted_at=now,
            score_pct=66.7,
            is_all_correct=False,
            question_count=3,
            correct_count=2,
        )
    )
    await db.flush()

    got = await enr.recompute_counters(db, enrollment_id=e.id)
    assert got.view_count == 1
    assert got.completion_count == 1
    assert got.best_score_pct == 100.0
