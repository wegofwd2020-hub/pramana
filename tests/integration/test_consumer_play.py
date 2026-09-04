# tests/integration/test_consumer_play.py
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.services.consumer import play
from tests.integration.conftest import consumer_setup

pytestmark = pytest.mark.integration

now = datetime(2026, 1, 1, tzinfo=UTC)


async def test_start_then_end_view_bumps_view_count_once(
    db: AsyncSession, consumer_tenant: object
) -> None:
    s = await consumer_setup(db)
    manifest = await play.start_view(
        db,
        tenant_id=s.tenant_id,
        user_id=s.user.user_id,
        course_id=s.course.id,
        entitlement_id=s.entitlement.id,
        media_kind="video",
        now=now,
    )
    assert manifest.course_version_id == s.course.current_version_id

    await play.end_view(
        db,
        tenant_id=s.tenant_id,
        user_id=s.user.user_id,
        play_session_id=manifest.play_session_id,
        duration_seconds=42,
        max_watched_pct=100,
        now=now,
    )
    # ending the same session again must not double-count
    await play.end_view(
        db,
        tenant_id=s.tenant_id,
        user_id=s.user.user_id,
        play_session_id=manifest.play_session_id,
        duration_seconds=42,
        max_watched_pct=100,
        now=now,
    )

    from sqlalchemy import select

    from pramana.db.models.consumer import Enrollment

    enr = (
        await db.execute(select(Enrollment).where(Enrollment.id == manifest.enrollment_id))
    ).scalar_one()
    assert enr.view_count == 1
