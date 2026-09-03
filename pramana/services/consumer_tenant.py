"""Consumer-tenant bootstrap helper.

The ``tenant`` table contains one fixed row with ``short_code='consumer'`` that
represents the public consumer-facing store. Real deployments receive that row
from migration ``0010_consumer_subscription``; the integration suite builds its
schema from ORM metadata and never runs Alembic, so it calls
:func:`ensure_consumer_tenant` from its fixtures instead.

``tests/db/test_consumer_seed.py`` asserts that the two sources of truth agree
(same pattern as :mod:`pramana.services.roles` / migration ``0007``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.identity import Tenant

#: ``short_code`` of the one consumer-facing tenant seeded by migration 0010.
#: Mirrors ``CONSUMER_TENANT_SHORT_CODE`` in ``alembic/versions/0010_consumer_subscription.py``.
CONSUMER_TENANT_SHORT_CODE: str = "consumer"

#: Display name seeded for the consumer tenant.
#: Mirrors ``CONSUMER_TENANT_NAME`` in ``alembic/versions/0010_consumer_subscription.py``.
CONSUMER_TENANT_NAME: str = "Consumer"


async def ensure_consumer_tenant(session: AsyncSession) -> Tenant:
    """Insert the consumer tenant if absent and return it. Idempotent.

    Migration ``0010`` does this for real deployments; this serves the paths
    that never run Alembic — the integration suite fixtures.
    """
    existing = (
        await session.execute(select(Tenant).where(Tenant.short_code == CONSUMER_TENANT_SHORT_CODE))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    tenant = Tenant(
        id=uuid.uuid4(),
        name=CONSUMER_TENANT_NAME,
        short_code=CONSUMER_TENANT_SHORT_CODE,
    )
    session.add(tenant)
    await session.flush()
    return tenant
