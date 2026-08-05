"""Assignment service — the learner runtime's take-the-quiz loop.

Transactional shell over the pure state machine
(:mod:`pramana.domain.assignment_state`) and grader
(:mod:`pramana.domain.scoring`). Drives an assignment through
``assign → (watch) → attempt → submit → pass/fail/block``, persisting each
transition, appending audit entries, and issuing a certificate on ``PASSED``.

Design notes:

- **Version pinning.** An assignment snapshots ``course_version_id`` at creation
  so publishing a new version never changes what a learner is tested on. Grading
  and the certificate both use that pinned version.
- **Retry carry-forward.** A failed attempt with retries left returns the
  assignment to ``ASSIGNED``; the next attempt replays only the wrongly-answered
  questions. The service carries the previous attempt's *correct* answers forward
  and grades the union server-side, so the score reflects the whole quiz and the
  client cannot inflate it by omitting questions.
- **Ownership.** Learner actions (start/submit/watch) require the acting user to
  be the assignee; creation and cancellation are privileged (manager) actions and
  are authorised at the router.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pramana.db.models.assignment import Assignment, Attempt, AttemptAnswer, Certificate
from pramana.db.models.course import Course, CourseVersion, Question
from pramana.domain import assignment_state as fsm
from pramana.domain.assignment_state import AssignmentSnapshot
from pramana.domain.enums import AssignmentStatus, TerminalReason, TransitionEvent
from pramana.domain.scoring import GradedQuestion, GradeResult, grade_attempt
from pramana.exceptions import (
    AuthorizationError,
    ConflictError,
    CooldownActiveError,
    InvalidStateTransitionError,
    NotFoundError,
    ValidationError,
)
from pramana.services import certificates
from pramana.services.audit import append_audit


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Attestation:
    """The SOX honesty attestation captured when a learner submits an attempt."""

    text_version: str
    accepted: bool
    ip: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class AttemptSubmission:
    """Result of :func:`submit_attempt`."""

    attempt: Attempt
    snapshot: AssignmentSnapshot
    grade: GradeResult
    retry_available: bool
    certificate: Certificate | None


# ---------------------------------------------------------------------------
# Create / read
# ---------------------------------------------------------------------------
async def create_assignment(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    assigned_by_user_id: uuid.UUID | None,
    due_at: datetime | None,
    now: datetime,
) -> Assignment:
    """Assign the course's active version to a user.

    Snapshots ``max_attempts``/``cooldown_days`` and the active
    ``course_version_id`` from the course. Enforces one active assignment per
    (user, course) and the FR8 cooldown after a terminal ``PASSED``/``BLOCKED``.

    Raises:
        NotFoundError: The course does not exist in this tenant.
        ValidationError: The course has no active published version.
        ConflictError: The user already has an active assignment for the course.
        CooldownActiveError: A prior terminal assignment is still in cooldown.
    """
    course = await session.get(Course, course_id)
    if course is None or course.tenant_id != tenant_id:
        raise NotFoundError("course not found", context={"course_id": str(course_id)})
    if course.current_version_id is None:
        raise ValidationError(
            "course has no active published version", context={"course_id": str(course_id)}
        )

    recent = await _latest_assignment_for_course(
        session, tenant_id=tenant_id, user_id=user_id, course_id=course_id
    )
    if recent is not None:
        if not AssignmentStatus(recent.status).is_terminal:
            raise ConflictError(
                "user already has an active assignment for this course",
                context={"assignment_id": str(recent.id)},
            )
        cooldown_until = recent.cooldown_until
        if cooldown_until is not None and fsm.is_within_cooldown(cooldown_until, now=now):
            raise CooldownActiveError(
                "a prior assignment for this course is still in its cooldown window",
                context={"cooldown_until": cooldown_until.isoformat()},
            )

    assignment = Assignment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        course_id=course_id,
        course_version_id=course.current_version_id,
        assigned_at=now,
        assigned_by_user_id=assigned_by_user_id,
        due_at=due_at,
        status=AssignmentStatus.ASSIGNED.value,
        attempts_used=0,
        max_attempts=course.max_attempts,
        cooldown_days=course.cooldown_days,
        watched_pct=0,
    )
    session.add(assignment)
    await _audit(session, assignment, TransitionEvent.CREATE, now=now)
    return assignment


async def get_assignment(
    session: AsyncSession, *, assignment_id: uuid.UUID, tenant_id: uuid.UUID
) -> Assignment:
    """Load one assignment scoped to the tenant (404 otherwise)."""
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None or assignment.tenant_id != tenant_id:
        raise NotFoundError("assignment not found", context={"assignment_id": str(assignment_id)})
    return assignment


async def list_assignments(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    status: AssignmentStatus | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[Sequence[Assignment], int]:
    """Return a page of assignments for the tenant (optionally filtered) + total."""
    filters: list[Any] = [Assignment.tenant_id == tenant_id]
    if user_id is not None:
        filters.append(Assignment.user_id == user_id)
    if status is not None:
        filters.append(Assignment.status == status.value)

    total = (
        await session.execute(select(func.count()).select_from(Assignment).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(Assignment)
                .where(*filters)
                .order_by(Assignment.assigned_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .scalars()
        .all()
    )
    return rows, total


# ---------------------------------------------------------------------------
# Attempt loop
# ---------------------------------------------------------------------------
async def start_attempt(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    tenant_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    now: datetime,
) -> Attempt:
    """Begin (or resume) an attempt: ``ASSIGNED → IN_PROGRESS``.

    Idempotent: if an in-progress attempt already exists, it is returned
    unchanged. Enforces the watch-gate (``watched_pct >= min_watch_pct``), FR7
    (no other in-progress assignment for the user), and the attempt cap.

    Raises:
        AuthorizationError: The acting user is not the assignee.
        ValidationError: The quiz is still locked by the watch requirement.
        InvalidStateTransitionError / ConcurrentAssignmentError /
        MaxAttemptsExceededError: from the domain state machine.
    """
    assignment = await _load_owned(
        session, assignment_id=assignment_id, tenant_id=tenant_id, acting_user_id=acting_user_id
    )

    existing = await _in_progress_attempt(session, assignment.id)
    if existing is not None:
        return existing

    version = await session.get(CourseVersion, assignment.course_version_id)
    if version is not None and assignment.watched_pct < version.min_watch_pct:
        raise ValidationError(
            "quiz is locked until the watch requirement is met",
            context={
                "watched_pct": assignment.watched_pct,
                "min_watch_pct": version.min_watch_pct,
            },
        )

    other_in_progress = await _has_other_in_progress(
        session, tenant_id=tenant_id, user_id=acting_user_id, exclude_assignment_id=assignment.id
    )
    new_snapshot = fsm.start_attempt(
        _snapshot(assignment), user_has_other_in_progress_assignment=other_in_progress
    )
    _apply(assignment, new_snapshot)

    attempt = Attempt(
        id=uuid.uuid4(),
        assignment_id=assignment.id,
        attempt_number=assignment.attempts_used,
        started_at=now,
        outcome="in_progress",
    )
    session.add(attempt)
    await _audit(
        session,
        assignment,
        TransitionEvent.START_ATTEMPT,
        now=now,
        extra={"attempt_number": attempt.attempt_number},
    )
    return attempt


async def submit_attempt(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    tenant_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    answers: Mapping[uuid.UUID, Sequence[uuid.UUID]],
    attestation: Attestation,
    now: datetime,
) -> AttemptSubmission:
    """Grade and submit the in-progress attempt.

    Grades the union of the submitted answers with the previous attempt's
    correct answers (retry carry-forward), drives the state machine against the
    course pass threshold, persists the attempt + per-question answers, and — on
    ``PASSED`` — issues a certificate pinned to the played version.

    Raises:
        AuthorizationError: The acting user is not the assignee.
        InvalidStateTransitionError: No in-progress attempt to submit.
        ValidationError: The honesty attestation was not accepted.
    """
    assignment = await _load_owned(
        session, assignment_id=assignment_id, tenant_id=tenant_id, acting_user_id=acting_user_id
    )
    attempt = await _in_progress_attempt(session, assignment.id)
    if attempt is None:
        raise InvalidStateTransitionError(
            "no in-progress attempt to submit", context={"assignment_id": str(assignment.id)}
        )
    if not attestation.accepted:
        raise ValidationError("the honesty attestation must be accepted to submit")

    graded, questions = await _load_graded_questions(session, assignment.course_version_id)
    merged = await _merge_carried_forward(
        session, assignment_id=assignment.id, current_attempt_id=attempt.id, submitted=answers
    )
    grade = grade_attempt(graded, merged)

    course = await session.get(Course, assignment.course_id)
    threshold = float(course.pass_threshold_pct) if course is not None else 80.0
    result = fsm.submit_attempt(
        _snapshot(assignment), score_pct=grade.score_pct, pass_threshold_pct=threshold, now=now
    )
    _apply(assignment, result.snapshot)

    attempt.score_pct = grade.score_pct
    attempt.outcome = result.attempt_outcome.value
    attempt.submitted_at = now
    attempt.attestation_accepted = True
    _write_answers(session, attempt, grade=grade, selections=merged, questions=questions, now=now)

    await _audit(
        session,
        assignment,
        TransitionEvent.SUBMIT_ATTEMPT,
        now=now,
        extra={
            "attempt_number": attempt.attempt_number,
            "score_pct": grade.score_pct,
            "outcome": result.attempt_outcome.value,
            "retry_available": result.retry_available,
        },
    )

    certificate: Certificate | None = None
    if result.snapshot.status is AssignmentStatus.PASSED:
        certificate = await certificates.issue_certificate(
            session,
            assignment=assignment,
            attestation_text_version=attestation.text_version,
            attestation_timestamp=now,
            attestation_ip=attestation.ip,
            attestation_user_agent=attestation.user_agent,
            now=now,
        )

    return AttemptSubmission(
        attempt=attempt,
        snapshot=result.snapshot,
        grade=grade,
        retry_available=result.retry_available,
        certificate=certificate,
    )


# ---------------------------------------------------------------------------
# Terminal transitions (privileged / system)
# ---------------------------------------------------------------------------
async def cancel_assignment(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    now: datetime,
) -> Assignment:
    """Cancel a non-terminal assignment (privileged). Does not start cooldown."""
    assignment = await get_assignment(session, assignment_id=assignment_id, tenant_id=tenant_id)
    _apply(assignment, fsm.cancel(_snapshot(assignment), now=now))
    await _audit(session, assignment, TransitionEvent.CANCEL, now=now, actor_user_id=actor_user_id)
    return assignment


async def expire_assignment(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    tenant_id: uuid.UUID,
    now: datetime,
) -> Assignment:
    """Expire a non-terminal assignment past its due date (system). No cooldown."""
    assignment = await get_assignment(session, assignment_id=assignment_id, tenant_id=tenant_id)
    _apply(assignment, fsm.expire(_snapshot(assignment), now=now))
    await _audit(session, assignment, TransitionEvent.EXPIRE, now=now)
    return assignment


# ---------------------------------------------------------------------------
# Helpers — snapshot <-> model
# ---------------------------------------------------------------------------
def _snapshot(a: Assignment) -> AssignmentSnapshot:
    return AssignmentSnapshot(
        status=AssignmentStatus(a.status),
        attempts_used=a.attempts_used,
        max_attempts=a.max_attempts,
        cooldown_days=a.cooldown_days,
        terminal_at=a.terminal_at,
        terminal_reason=TerminalReason(a.terminal_reason) if a.terminal_reason else None,
        cooldown_until=a.cooldown_until,
    )


def _apply(a: Assignment, snapshot: AssignmentSnapshot) -> None:
    a.status = snapshot.status.value
    a.attempts_used = snapshot.attempts_used
    a.terminal_at = snapshot.terminal_at
    a.terminal_reason = snapshot.terminal_reason.value if snapshot.terminal_reason else None
    a.cooldown_until = snapshot.cooldown_until


async def _audit(
    session: AsyncSession,
    a: Assignment,
    event: TransitionEvent,
    *,
    now: datetime,
    actor_user_id: uuid.UUID | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "status": a.status,
        "attempts_used": a.attempts_used,
        "course_version_id": str(a.course_version_id),
    }
    if extra:
        payload.update(extra)
    await append_audit(
        session,
        tenant_id=a.tenant_id,
        actor_user_id=actor_user_id if actor_user_id is not None else a.user_id,
        entity_type="assignment",
        entity_id=str(a.id),
        event_type=f"assignment.{event.value}",
        payload=payload,
        occurred_at=now,
    )


# ---------------------------------------------------------------------------
# Helpers — queries
# ---------------------------------------------------------------------------
async def _load_owned(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    tenant_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> Assignment:
    """Load an assignment and assert the acting user is its assignee."""
    assignment = await get_assignment(session, assignment_id=assignment_id, tenant_id=tenant_id)
    if assignment.user_id != acting_user_id:
        raise AuthorizationError(
            "not your assignment", context={"assignment_id": str(assignment_id)}
        )
    return assignment


async def _in_progress_attempt(session: AsyncSession, assignment_id: uuid.UUID) -> Attempt | None:
    return (
        await session.execute(
            select(Attempt)
            .where(Attempt.assignment_id == assignment_id, Attempt.outcome == "in_progress")
            .order_by(Attempt.attempt_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _has_other_in_progress(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    exclude_assignment_id: uuid.UUID,
) -> bool:
    count = (
        await session.execute(
            select(func.count())
            .select_from(Assignment)
            .where(
                Assignment.tenant_id == tenant_id,
                Assignment.user_id == user_id,
                Assignment.status == AssignmentStatus.IN_PROGRESS.value,
                Assignment.id != exclude_assignment_id,
            )
        )
    ).scalar_one()
    return count > 0


async def _latest_assignment_for_course(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
) -> Assignment | None:
    return (
        await session.execute(
            select(Assignment)
            .where(
                Assignment.tenant_id == tenant_id,
                Assignment.user_id == user_id,
                Assignment.course_id == course_id,
            )
            .order_by(Assignment.assigned_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _load_graded_questions(
    session: AsyncSession, course_version_id: uuid.UUID
) -> tuple[list[GradedQuestion], dict[uuid.UUID, Question]]:
    """Load the version's questions + options as grader inputs."""
    rows = (
        (
            await session.execute(
                select(Question)
                .where(Question.course_version_id == course_version_id)
                .options(selectinload(Question.options))
                .order_by(Question.display_order)
            )
        )
        .scalars()
        .all()
    )
    graded: list[GradedQuestion] = []
    by_id: dict[uuid.UUID, Question] = {}
    for q in rows:
        correct = frozenset(o.id for o in q.options if o.is_correct)
        graded.append(GradedQuestion(question_id=q.id, weight=q.weight, correct_option_ids=correct))
        by_id[q.id] = q
    return graded, by_id


async def _merge_carried_forward(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    current_attempt_id: uuid.UUID,
    submitted: Mapping[uuid.UUID, Sequence[uuid.UUID]],
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Merge the previous attempt's correct answers under the submitted ones.

    The submitted answers win for any question the learner re-answered; the rest
    are carried forward from the most recent submitted attempt's correct answers.
    """
    merged: dict[uuid.UUID, list[uuid.UUID]] = {}
    prev = (
        await session.execute(
            select(Attempt)
            .where(
                Attempt.assignment_id == assignment_id,
                Attempt.id != current_attempt_id,
                Attempt.submitted_at.is_not(None),
            )
            .order_by(Attempt.attempt_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if prev is not None:
        prev_answers = (
            (
                await session.execute(
                    select(AttemptAnswer).where(
                        AttemptAnswer.attempt_id == prev.id,
                        AttemptAnswer.is_correct.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        for ans in prev_answers:
            merged[ans.question_id] = list(ans.selected_option_ids)
    for qid, opts in submitted.items():
        merged[qid] = list(opts)
    return merged


def _write_answers(
    session: AsyncSession,
    attempt: Attempt,
    *,
    grade: GradeResult,
    selections: Mapping[uuid.UUID, Sequence[uuid.UUID]],
    questions: Mapping[uuid.UUID, Question],
    now: datetime,
) -> None:
    """Persist one AttemptAnswer per graded question."""
    correct_by_q = {r.question_id: r.is_correct for r in grade.per_question}
    for qid in questions:
        session.add(
            AttemptAnswer(
                id=uuid.uuid4(),
                attempt_id=attempt.id,
                question_id=qid,
                selected_option_ids=list(selections.get(qid, ())),
                is_correct=correct_by_q.get(qid, False),
                answered_at=now,
            )
        )
