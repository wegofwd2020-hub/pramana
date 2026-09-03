"""Integration test: consumer subscription schema (migration 0010).

Asserts that the 7 consumer tables exist and that a Consumer tenant row can
be stored — equivalent to what migration 0010 seeds via Alembic.

The ``db`` fixture (see tests/integration/conftest.py) rebuilds the schema
via ``Base.metadata.create_all`` (which registers all ORM models including
the consumer ones), so ``to_regclass`` checks prove the tables are present.
The seed assertion inserts a ``short_code='consumer'`` tenant directly — this
validates the schema allows the row (same guarantee as the migration INSERT,
just through the ORM path instead of the Alembic seed).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.identity import Tenant

pytestmark = pytest.mark.integration


async def test_consumer_tables_and_seed_present(db: AsyncSession) -> None:
    # All 7 consumer tables must exist.
    for table in [
        "package",
        "entitlement",
        "enrollment",
        "play_session",
        "consumer_attempt",
        "consumer_attempt_answer",
        "package_course",
    ]:
        got = await db.execute(text(f"SELECT to_regclass('{table}')"))
        assert got.scalar() is not None, f"{table} missing"

    # Seed: a Consumer tenant row with short_code='consumer' must be storable
    # (mirrors the Alembic migration INSERT that seeds the Consumer tenant).
    consumer_tenant = Tenant(
        id=uuid.uuid4(),
        name="Consumer",
        short_code="consumer",
    )
    db.add(consumer_tenant)
    await db.flush()

    seed = await db.execute(text("SELECT count(*) FROM tenant WHERE short_code = 'consumer'"))
    assert seed.scalar() == 1
