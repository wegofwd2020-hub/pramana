"""Quiz service — consumer quiz sitting. Reuses the pure grader (domain.scoring).

Consumer rules: unlimited attempts, no cooldown, always the full active-version
question set. A completion is a submission at 100%.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pramana.db.models.consumer import ConsumerAttempt, ConsumerAttemptAnswer, Enrollment
from pramana.db.models.course import Course, Question
from pramana.domain.consumer.completion import is_all_correct
from pramana.domain.scoring import GradedQuestion, grade_attempt
from pramana.exceptions import NotFoundError, ValidationError
from pramana.services.consumer.enrollment import get_or_create_enrollment


@dataclass(frozen=True, slots=True)
class QuizOption:
    option_id: uuid.UUID
    option_text: str


@dataclass(frozen=True, slots=True)
class QuizQuestion:
    question_id: uuid.UUID
    question_text: str
    question_type: str
    options: tuple[QuizOption, ...]


@dataclass(frozen=True, slots=True)
class QuizForm:
    attempt_id: uuid.UUID
    course_version_id: uuid.UUID
    questions: tuple[QuizQuestion, ...]


@dataclass(frozen=True, slots=True)
class QuizResult:
    attempt_id: uuid.UUID
    score_pct: float
    is_all_correct: bool
    correct_count: int
    question_count: int


async def _load_version_questions(
    session: AsyncSession, course_version_id: uuid.UUID
) -> list[Question]:
    return list(
        (
            await session.execute(
                select(Question)
                .where(Question.course_version_id == course_version_id)
                .options(selectinload(Question.options))
                .order_by(Question.display_order)
            )
        ).scalars()
    )


async def start_quiz(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    entitlement_id: uuid.UUID,
    now: datetime,
) -> QuizForm:
    course = await session.get(Course, course_id)
    if course is None or course.current_version_id is None:
        raise NotFoundError("course has no active version", context={"course_id": str(course_id)})
    questions = await _load_version_questions(session, course.current_version_id)
    if not questions:
        raise ValidationError("course version has no questions")

    enrollment = await get_or_create_enrollment(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        course_id=course_id,
        entitlement_id=entitlement_id,
        now=now,
    )

    attempt = ConsumerAttempt(
        tenant_id=tenant_id,
        enrollment_id=enrollment.id,
        course_version_id=course.current_version_id,
        started_at=now,
        question_count=len(questions),
    )
    session.add(attempt)
    await session.flush()

    return QuizForm(
        attempt_id=attempt.id,
        course_version_id=course.current_version_id,
        questions=tuple(
            QuizQuestion(
                question_id=q.id,
                question_text=q.question_text,
                question_type=q.question_type,
                options=tuple(
                    QuizOption(option_id=o.id, option_text=o.option_text) for o in q.options
                ),
            )
            for q in questions
        ),
    )


async def submit_quiz(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    attempt_id: uuid.UUID,
    answers: Mapping[uuid.UUID, list[uuid.UUID]],
    now: datetime,
) -> QuizResult:
    attempt = await session.get(ConsumerAttempt, attempt_id)
    if attempt is None or attempt.tenant_id != tenant_id:
        raise NotFoundError("attempt not found", context={"attempt_id": str(attempt_id)})

    enrollment = await session.get(Enrollment, attempt.enrollment_id)
    if enrollment is None or enrollment.user_id != user_id:
        raise NotFoundError("attempt not found", context={"attempt_id": str(attempt_id)})

    if attempt.submitted_at is not None:
        raise ValidationError("attempt already submitted")

    questions = await _load_version_questions(session, attempt.course_version_id)
    graded = [
        GradedQuestion(
            question_id=q.id,
            weight=q.weight,
            correct_option_ids=frozenset(o.id for o in q.options if o.is_correct),
        )
        for q in questions
    ]
    result = grade_attempt(graded, dict(answers.items()))

    correct_ids = {r.question_id for r in result.per_question if r.is_correct}
    for q in questions:
        session.add(
            ConsumerAttemptAnswer(
                consumer_attempt_id=attempt.id,
                question_id=q.id,
                selected_option_ids=list(answers.get(q.id, [])),
                is_correct=q.id in correct_ids,
                answered_at=now,
            )
        )

    attempt.submitted_at = now
    attempt.score_pct = result.score_pct
    attempt.correct_count = len(correct_ids)
    attempt.is_all_correct = is_all_correct(result.score_pct)

    if attempt.is_all_correct:
        enrollment.completion_count += 1
    if enrollment.best_score_pct is None or result.score_pct > enrollment.best_score_pct:
        enrollment.best_score_pct = result.score_pct
    enrollment.last_accessed_at = now

    return QuizResult(
        attempt_id=attempt.id,
        score_pct=result.score_pct,
        is_all_correct=attempt.is_all_correct,
        correct_count=len(correct_ids),
        question_count=len(questions),
    )
