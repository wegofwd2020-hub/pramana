# tests/integration/test_consumer_entitlements.py
"""Integration tests for the consumer entitlements service."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.services.consumer import entitlements as ent

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_grant_is_idempotent_and_gates_by_course(
    db: AsyncSession,
    consumer_tenant: object,
) -> None:
    from pramana.db.models.consumer import Package, PackageCourse
    from tests.integration.conftest import seed_course

    tenant_id = await ent.get_consumer_tenant_id(db)

    # seed_course creates its own tenant + published course; we only need the course_id
    seeded = await seed_course(db)

    user = await ent.create_consumer_user(
        db,
        tenant_id=tenant_id,
        email="a@example.com",
        first_name="Ann",
        last_name="Lee",
        now=_NOW,
    )

    # A package under the consumer tenant containing the seeded course
    pkg = Package(tenant_id=tenant_id, slug="sox", title="SOX", is_published=True)
    db.add(pkg)
    await db.flush()
    db.add(PackageCourse(package_id=pkg.id, course_id=seeded.course_id))
    await db.flush()

    # No entitlement yet → gate is closed
    assert (
        await ent.has_active_entitlement_for_course(
            db,
            tenant_id=tenant_id,
            user_id=user.user_id,
            course_id=seeded.course_id,
            now=_NOW,
        )
        is False
    )

    # Grant once
    e1 = await ent.grant_package(
        db,
        tenant_id=tenant_id,
        user_id=user.user_id,
        package_id=pkg.id,
        granted_by_user_id=None,
        now=_NOW,
    )
    # Grant again → idempotent, same object
    e2 = await ent.grant_package(
        db,
        tenant_id=tenant_id,
        user_id=user.user_id,
        package_id=pkg.id,
        granted_by_user_id=None,
        now=_NOW,
    )
    assert e1.id == e2.id

    # Gate is now open
    assert (
        await ent.has_active_entitlement_for_course(
            db,
            tenant_id=tenant_id,
            user_id=user.user_id,
            course_id=seeded.course_id,
            now=_NOW,
        )
        is True
    )

    # Revoke → gate closes again
    await ent.revoke_entitlement(
        db,
        tenant_id=tenant_id,
        entitlement_id=e1.id,
        revoked_by_user_id=None,
        now=_NOW,
    )
    assert (
        await ent.has_active_entitlement_for_course(
            db,
            tenant_id=tenant_id,
            user_id=user.user_id,
            course_id=seeded.course_id,
            now=_NOW,
        )
        is False
    )
