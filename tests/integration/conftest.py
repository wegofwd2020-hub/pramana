"""Integration-test fixtures — real Postgres.

The learner-runtime services (assignments / player / certificates) issue many
sequential queries per call, so they are covered against a real database rather
than a hand-canned fake session. Requires a reachable Postgres; the URL comes
from ``DATABASE_URL`` (CI sets it), else a local scratch instance on port 55432.

Each test gets a freshly created schema (``create_all`` from the ORM metadata,
not Alembic) and a session; data is isolated by unique ids per test.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import pramana.db.models  # noqa: F401 — register every table on Base.metadata
from pramana.db.base import Base
from pramana.db.models.course import AnswerOption, Course, CourseVersion, Question
from pramana.db.models.identity import Tenant, User
from tests.conftest import _ensure_test_environment

_DEFAULT_URL = "postgresql+asyncpg://pramana:pramana@localhost:55432/pramana_test"


def _db_url() -> str:
    return os.getenv("DATABASE_URL") or _DEFAULT_URL


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[object]:
    _ensure_test_environment()
    # NullPool: connections are created on demand in the caller's event loop, so
    # the fixture loop (seeding) and the TestClient's own loop (HTTP requests)
    # never share a loop-bound asyncpg connection.
    eng = create_async_engine(_db_url(), future=True, poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def sessions(engine: object) -> async_sessionmaker[AsyncSession]:
    """A sessionmaker on the test engine (fresh session per request/assertion)."""
    return async_sessionmaker(engine, expire_on_commit=False)  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def db(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """A session for seeding and assertions (the test commits explicitly)."""
    async with sessions() as session:
        yield session


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SeededCourse:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    course_id: uuid.UUID
    course_version_id: uuid.UUID
    # question_id -> (correct_option_id, wrong_option_id)
    questions: dict[uuid.UUID, tuple[uuid.UUID, uuid.UUID]]


async def seed_course(
    session: AsyncSession,
    *,
    n_questions: int = 2,
    pass_threshold_pct: int = 80,
    max_attempts: int = 2,
    cooldown_days: int = 365,
    min_watch_pct: int = 0,
) -> SeededCourse:
    """Create a tenant, user, and a published course version with questions.

    Commits so that request-scoped sessions opened by the app can read it.
    """
    tenant = Tenant(
        id=uuid.uuid4(), name=f"Tenant {uuid.uuid4()}", short_code=uuid.uuid4().hex[:12]
    )
    user = User(user_id=uuid.uuid4(), tenant_id=tenant.id, email=f"{uuid.uuid4()}@example.com")
    course = Course(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        title="Compliance 101",
        pass_threshold_pct=pass_threshold_pct,
        max_attempts=max_attempts,
        cooldown_days=cooldown_days,
    )
    version = CourseVersion(
        id=uuid.uuid4(),
        course_id=course.id,
        version_number=1,
        min_watch_pct=min_watch_pct,
        is_active=True,
    )
    session.add_all([tenant, user, course, version])
    await session.flush()
    course.current_version_id = version.id

    questions: dict[uuid.UUID, tuple[uuid.UUID, uuid.UUID]] = {}
    for i in range(n_questions):
        q = Question(
            id=uuid.uuid4(),
            course_version_id=version.id,
            question_text=f"Q{i}?",
            question_type="single_select",
            weight=1.0,
            display_order=i,
        )
        correct = AnswerOption(
            id=uuid.uuid4(), question_id=q.id, option_text="right", is_correct=True, display_order=0
        )
        wrong = AnswerOption(
            id=uuid.uuid4(),
            question_id=q.id,
            option_text="wrong",
            is_correct=False,
            display_order=1,
        )
        session.add_all([q, correct, wrong])
        questions[q.id] = (correct.id, wrong.id)

    await session.commit()
    return SeededCourse(
        tenant_id=tenant.id,
        user_id=user.user_id,
        course_id=course.id,
        course_version_id=version.id,
        questions=questions,
    )
