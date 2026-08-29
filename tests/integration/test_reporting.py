"""Auditor exports, sourced from history rather than current state.

The distinguishing test here is :meth:`TestAsOfIsHistorical.test_matrix_reflects_
the_date_not_today`. Built off ``assignment.status`` these reports would look
correct in every happy-path test and be quietly wrong for the only question an
auditor actually asks — *what was true during the period* — so the suite has to
pin that difference explicitly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.audit import AuditLog
from pramana.db.models.course import Course
from pramana.services import assignments as assign_svc
from pramana.services import reporting as svc
from tests.integration.conftest import seed_course

pytestmark = pytest.mark.integration

T1 = datetime(2026, 3, 1, tzinfo=UTC)  # assigned
T2 = datetime(2026, 4, 1, tzinfo=UTC)  # attempt started
T3 = datetime(2026, 5, 1, tzinfo=UTC)  # passed
LATER = datetime(2026, 6, 1, tzinfo=UTC)


async def _tag_course(db: AsyncSession, course_id: uuid.UUID, *tags: str) -> None:
    course = await db.get(Course, course_id)
    assert course is not None
    course.framework_tags = list(tags)
    await db.flush()


async def _drive_to_pass(db: AsyncSession, seed: object) -> uuid.UUID:
    """Assign at T1, start at T2, pass at T3 — a trail with distinct timestamps."""
    assignment = await assign_svc.create_assignment(
        db,
        tenant_id=seed.tenant_id,  # type: ignore[attr-defined]
        user_id=seed.user_id,  # type: ignore[attr-defined]
        course_id=seed.course_id,  # type: ignore[attr-defined]
        assigned_by_user_id=None,
        due_at=None,
        now=T1,
    )
    await db.flush()
    await assign_svc.start_attempt(
        db,
        assignment_id=assignment.id,
        tenant_id=seed.tenant_id,  # type: ignore[attr-defined]
        acting_user_id=seed.user_id,  # type: ignore[attr-defined]
        now=T2,
    )
    answers = {
        qid: [correct]
        for qid, (correct, _wrong) in seed.questions.items()  # type: ignore[attr-defined]
    }
    await assign_svc.submit_attempt(
        db,
        assignment_id=assignment.id,
        tenant_id=seed.tenant_id,  # type: ignore[attr-defined]
        acting_user_id=seed.user_id,  # type: ignore[attr-defined]
        answers=answers,
        attestation=assign_svc.Attestation(text_version="v1", accepted=True),
        now=T3,
    )
    await db.commit()
    return assignment.id


class TestAsOfIsHistorical:
    async def test_matrix_reflects_the_date_not_today(self, db: AsyncSession) -> None:
        """The same assignment reads differently depending on the as-of date."""
        seed = await seed_course(db, n_questions=2)
        await _drive_to_pass(db, seed)

        mid = await svc.training_matrix(
            db, tenant_id=seed.tenant_id, period_start=T1, period_end=T2
        )
        end = await svc.training_matrix(
            db, tenant_id=seed.tenant_id, period_start=T1, period_end=LATER
        )

        assert mid[0]["status"] == "in_progress"
        assert end[0]["status"] == "passed"

    async def test_before_assignment_the_user_is_absent(self, db: AsyncSession) -> None:
        seed = await seed_course(db, n_questions=2)
        await _drive_to_pass(db, seed)

        before = await svc.training_matrix(
            db,
            tenant_id=seed.tenant_id,
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period_end=datetime(2026, 2, 1, tzinfo=UTC),
        )
        assert before == []

    async def test_the_pinned_course_version_is_reported(self, db: AsyncSession) -> None:
        """A retired version must still be the one the record shows."""
        seed = await seed_course(db, n_questions=2)
        await _drive_to_pass(db, seed)

        rows = await svc.training_matrix(
            db, tenant_id=seed.tenant_id, period_start=T1, period_end=LATER
        )
        assert rows[0]["course_version_id"] == str(seed.course_version_id)


class TestPopulation:
    async def test_lists_users_with_an_assignment_in_the_period(self, db: AsyncSession) -> None:
        seed = await seed_course(db, n_questions=2)
        await _drive_to_pass(db, seed)

        rows = await svc.population(db, tenant_id=seed.tenant_id, as_of=LATER)
        assert [r["user_id"] for r in rows] == [str(seed.user_id)]
        assert rows[0]["courses_passed"] == 1

    async def test_column_name_marks_status_as_current_value(self, db: AsyncSession) -> None:
        """The caveat rides in the column name, where a reader will see it."""
        seed = await seed_course(db, n_questions=2)
        await _drive_to_pass(db, seed)
        rows = await svc.population(db, tenant_id=seed.tenant_id, as_of=LATER)
        assert "user_status_current" in rows[0]
        assert "user_status" not in rows[0]

    async def test_framework_tag_filters(self, db: AsyncSession) -> None:
        seed = await seed_course(db, n_questions=2)
        await _tag_course(db, seed.course_id, "sox")
        await _drive_to_pass(db, seed)

        assert await svc.population(db, tenant_id=seed.tenant_id, as_of=LATER, framework_tag="sox")
        assert (
            await svc.population(db, tenant_id=seed.tenant_id, as_of=LATER, framework_tag="hipaa")
            == []
        )


class TestExceptionReport:
    async def test_overdue_assignment_is_reported(self, db: AsyncSession) -> None:
        seed = await seed_course(db, n_questions=2)
        await assign_svc.create_assignment(
            db,
            tenant_id=seed.tenant_id,
            user_id=seed.user_id,
            course_id=seed.course_id,
            assigned_by_user_id=None,
            due_at=datetime(2026, 4, 1, tzinfo=UTC),
            now=T1,
        )
        await db.commit()

        rows = await svc.exception_report(db, tenant_id=seed.tenant_id, as_of=LATER)
        assert len(rows) == 1
        assert rows[0]["reason"] == "overdue"

    async def test_a_passed_assignment_is_not_an_exception(self, db: AsyncSession) -> None:
        seed = await seed_course(db, n_questions=2)
        await _drive_to_pass(db, seed)
        assert await svc.exception_report(db, tenant_id=seed.tenant_id, as_of=LATER) == []


class TestTenantScoping:
    async def test_another_tenants_rows_are_excluded(self, db: AsyncSession) -> None:
        mine = await seed_course(db, n_questions=2)
        theirs = await seed_course(db, n_questions=2)
        await _drive_to_pass(db, mine)
        await _drive_to_pass(db, theirs)

        rows = await svc.population(db, tenant_id=mine.tenant_id, as_of=LATER)
        assert [r["user_id"] for r in rows] == [str(mine.user_id)]


class TestAuditTrailUnaffected:
    async def test_reporting_reads_only(self, db: AsyncSession) -> None:
        """Building a report must not itself append to the chain."""
        seed = await seed_course(db, n_questions=2)
        await _drive_to_pass(db, seed)
        before = (await db.execute(select(AuditLog))).scalars().all()

        await svc.population(db, tenant_id=seed.tenant_id, as_of=LATER)
        await svc.training_matrix(db, tenant_id=seed.tenant_id, period_start=T1, period_end=LATER)
        after = (await db.execute(select(AuditLog))).scalars().all()
        assert len(before) == len(after)
