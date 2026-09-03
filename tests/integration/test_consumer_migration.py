"""Integration test: consumer subscription schema (migration 0010).

Two concerns are verified here:

1. **Schema** — all 7 consumer tables exist after the migration runs.
2. **Seed** — the migration's ``INSERT INTO tenant`` actually fires and produces
   the ``short_code='consumer'`` row (not just that the ORM *could* insert one).

The ``db`` fixture rebuilds the schema via ``Base.metadata.create_all`` (ORM
path), which is correct for table-existence checks because it registers every
consumer model.  But ``create_all`` never runs the migration's SQL seed INSERT,
so ``test_migration_seed_insert`` drives Alembic directly against the scratch DB
to confirm the real upgrade path works end-to-end.

.. note::
   The Alembic round-trip test must run against a clean DB.  The ``engine``
   fixture calls ``drop_all`` at teardown, which clobbers ``alembic_version``.
   The seed test therefore uses its own engine scope and stamps ``base`` before
   running upgrades to avoid the stale-version-pointer failure documented in the
   Task 2 report.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import pramana.db.models  # noqa: F401 — register every table on Base.metadata
from pramana.db.base import Base
from tests.conftest import _ensure_test_environment

pytestmark = pytest.mark.integration

_DEFAULT_URL = "postgresql+asyncpg://pramana:pramana@localhost:55432/pramana_test"


def _db_url() -> str:
    return os.getenv("DATABASE_URL") or _DEFAULT_URL


# ---------------------------------------------------------------------------
# Schema-existence test (ORM / create_all path)
# ---------------------------------------------------------------------------


async def test_consumer_tables_present(db: AsyncSession) -> None:
    """All 7 consumer tables exist in the ORM-built schema."""
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
        assert got.scalar() is not None, f"{table} missing from ORM schema"


# ---------------------------------------------------------------------------
# Seed-INSERT test — runs the real Alembic migration
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def alembic_engine():
    """A scratch engine for the Alembic round-trip.

    Drops and recreates the entire schema so the migration chain can run from
    scratch, independent of the ORM-based ``engine`` fixture.
    """
    _ensure_test_environment()
    eng = create_async_engine(_db_url(), future=True, poolclass=NullPool)
    async with eng.begin() as conn:
        # Wipe everything so no stale alembic_version remains.
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    yield eng
    # Teardown: drop all again so ORM fixtures in the same pytest session start clean.
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    await eng.dispose()


def _run_alembic(*args: str) -> None:
    """Run an alembic sub-command against the scratch DB.

    ``env.py`` reads ``DATABASE_URL`` via ``get_settings()``, so we inject the
    asyncpg URL directly — no driver conversion needed.
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = _db_url()
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")


async def test_migration_seed_insert(alembic_engine) -> None:  # type: ignore[no-untyped-def]
    """The migration's seed INSERT fires and the consumer tenant row exists.

    This test runs the full Alembic upgrade chain (0001→0010) so the seed SQL
    in ``upgrade()`` actually executes.  The prior implementation inserted the
    row via the ORM, which would pass even if the migration SQL were broken.
    """
    # Run the full migration chain from scratch.
    _run_alembic("upgrade", "head")

    # Verify the seed INSERT in migration 0010 produced the consumer tenant row.
    session_factory = async_sessionmaker(alembic_engine, expire_on_commit=False)
    async with session_factory() as session:
        count = (
            await session.execute(text("SELECT count(*) FROM tenant WHERE short_code = 'consumer'"))
        ).scalar()
        assert count == 1, (
            "Migration 0010 seed INSERT did not produce a tenant row with "
            "short_code='consumer'.  The upgrade() SQL may be broken."
        )

    # Confirm round-trip: downgrade removes the row, upgrade restores it.
    _run_alembic("downgrade", "-1")
    async with session_factory() as session:
        count_after_down = (
            await session.execute(text("SELECT count(*) FROM tenant WHERE short_code = 'consumer'"))
        ).scalar()
        assert count_after_down == 0, "Downgrade did not remove the consumer tenant row."

    _run_alembic("upgrade", "head")
    async with session_factory() as session:
        count_after_up = (
            await session.execute(text("SELECT count(*) FROM tenant WHERE short_code = 'consumer'"))
        ).scalar()
        assert count_after_up == 1, "Re-upgrade did not restore the consumer tenant row."
