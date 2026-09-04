# tests/integration/test_consumer_quiz.py
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.consumer import Enrollment
from pramana.services.consumer import quiz
from tests.integration.conftest import consumer_setup

pytestmark = pytest.mark.integration

now = datetime(2026, 1, 1, tzinfo=UTC)


async def test_perfect_submission_counts_a_completion(
    db: AsyncSession, consumer_tenant: object
) -> None:
    s = await consumer_setup(db)  # course has a version with graded questions
    form = await quiz.start_quiz(
        db,
        tenant_id=s.tenant_id,
        user_id=s.user.user_id,
        course_id=s.course.id,
        entitlement_id=s.entitlement.id,
        now=now,
    )
    assert form.questions  # non-empty
    # answer every question with its correct option(s) — consumer_setup exposes them
    answers = {q.question_id: s.correct_options[q.question_id] for q in form.questions}

    result = await quiz.submit_quiz(
        db,
        tenant_id=s.tenant_id,
        user_id=s.user.user_id,
        attempt_id=form.attempt_id,
        answers=answers,
        now=now,
    )
    assert result.is_all_correct is True
    assert result.score_pct == 100.0

    enr = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.user_id == s.user.user_id,
                Enrollment.course_id == s.course.id,
            )
        )
    ).scalar_one()
    assert enr.completion_count == 1
    assert enr.best_score_pct == 100.0


async def test_options_do_not_leak_correctness(db: AsyncSession, consumer_tenant: object) -> None:
    s = await consumer_setup(db)
    form = await quiz.start_quiz(
        db,
        tenant_id=s.tenant_id,
        user_id=s.user.user_id,
        course_id=s.course.id,
        entitlement_id=s.entitlement.id,
        now=now,
    )
    for q in form.questions:
        for opt in q.options:
            assert not hasattr(opt, "is_correct")
