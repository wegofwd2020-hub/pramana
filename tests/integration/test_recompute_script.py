# tests/integration/test_recompute_script.py
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.recompute_enrollment_counters import recompute_all
from tests.integration.conftest import consumer_setup

pytestmark = pytest.mark.integration

now = datetime(2026, 1, 1, tzinfo=UTC)


async def test_recompute_all_fixes_drift(db: AsyncSession, consumer_tenant: object) -> None:
    s = await consumer_setup(db)
    from pramana.db.models.consumer import Enrollment, PlaySession

    e = Enrollment(
        tenant_id=s.tenant_id,
        user_id=s.user.user_id,
        course_id=s.course.id,
        entitlement_id=s.entitlement.id,
        first_accessed_at=now,
        last_accessed_at=now,
        view_count=99,  # deliberately wrong
    )
    db.add(e)
    await db.flush()
    db.add(
        PlaySession(
            tenant_id=s.tenant_id,
            enrollment_id=e.id,
            course_version_id=s.course.current_version_id,
        )
    )
    await db.flush()

    drifted = await recompute_all(db, dry_run=False)
    await db.commit()
    await db.refresh(e)
    assert e.view_count == 1
    assert any(d["enrollment_id"] == e.id for d in drifted)
