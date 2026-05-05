"""Assignment state machine.

Pure domain module: no database, no HTTP, no I/O. Encodes the rules from
Section 4 (cooldown semantics) and Section 7 (state machine) of
``docs/02_resolved_decisions.md``.

The machine is implemented as a function over an immutable
:class:`AssignmentSnapshot`: each transition takes the current snapshot plus
an event and returns either a new snapshot or raises a
:class:`pramana.exceptions.DomainError`.

This separation makes the rules exhaustively testable with property-based
tests (see ``tests/domain/test_assignment_state.py``) without requiring a
running database.

Glossary
--------
**Snapshot**
    Immutable value object representing all the fields of an assignment that
    affect transition decisions.

**Transition**
    A function ``(snapshot, event_args) -> snapshot`` that may raise a
    :class:`DomainError` if the event is invalid in the current state.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Final

from pramana.domain.enums import (
    AssignmentStatus,
    AttemptOutcome,
    TerminalReason,
)
from pramana.exceptions import (
    ConcurrentAssignmentError,
    InvalidStateTransitionError,
    MaxAttemptsExceededError,
)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AssignmentSnapshot:
    """Immutable snapshot of assignment state.

    Attributes:
        status: Current lifecycle state.
        attempts_used: Number of attempts the user has begun (started, not
            necessarily submitted). Increments on each ``START_ATTEMPT``.
        max_attempts: Cap from the parent course (default 2).
        cooldown_days: Re-assignment cooldown for the parent course.
        terminal_at: When the assignment reached its current terminal state.
            ``None`` while the assignment is non-terminal.
        terminal_reason: Why the assignment reached a terminal state.
        cooldown_until: ``terminal_at + cooldown_days`` for terminal states
            that started the cooldown (``PASSED``/``BLOCKED``); ``None``
            otherwise.
    """

    status: AssignmentStatus
    attempts_used: int = 0
    max_attempts: int = 2
    cooldown_days: int = 365
    terminal_at: datetime | None = None
    terminal_reason: TerminalReason | None = None
    cooldown_until: datetime | None = None

    def __post_init__(self) -> None:
        if self.attempts_used < 0:
            raise ValueError("attempts_used must be non-negative")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.cooldown_days < 0:
            raise ValueError("cooldown_days must be non-negative")

        # Invariant: terminal_at is set iff status is terminal.
        if self.status.is_terminal and self.terminal_at is None:
            raise ValueError(
                f"status {self.status.value!r} is terminal but terminal_at is None"
            )
        if not self.status.is_terminal and self.terminal_at is not None:
            raise ValueError(
                f"status {self.status.value!r} is not terminal but terminal_at is set"
            )

        # Invariant: cooldown_until is set iff status started the cooldown.
        if self.status.started_cooldown and self.cooldown_until is None:
            raise ValueError(
                f"status {self.status.value!r} starts cooldown but cooldown_until is None"
            )
        if not self.status.started_cooldown and self.cooldown_until is not None:
            raise ValueError(
                f"status {self.status.value!r} does not start cooldown "
                "but cooldown_until is set"
            )

    @property
    def remaining_attempts(self) -> int:
        """Number of attempts the user may still start."""
        return max(0, self.max_attempts - self.attempts_used)


@dataclass(frozen=True, slots=True)
class AssignmentSubmissionResult:
    """Outcome of ``submit_attempt`` — both the new snapshot and per-attempt info."""

    snapshot: AssignmentSnapshot
    attempt_outcome: AttemptOutcome
    retry_available: bool


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_MAX_ATTEMPTS: Final[int] = 2


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------
def start_attempt(
    snapshot: AssignmentSnapshot,
    *,
    user_has_other_in_progress_assignment: bool,
) -> AssignmentSnapshot:
    """Begin a new attempt.

    Permitted only from :class:`AssignmentStatus.ASSIGNED`. The caller is
    responsible for telling us whether the user has *another* assignment
    already in progress (FR7).

    Args:
        snapshot: Current state.
        user_has_other_in_progress_assignment: True if another assignment for
            the same user is in :class:`AssignmentStatus.IN_PROGRESS`. Per
            FR7, only one in-progress assignment is permitted.

    Returns:
        New snapshot with ``status = IN_PROGRESS`` and ``attempts_used``
        incremented.

    Raises:
        InvalidStateTransitionError: The current status does not permit
            starting an attempt.
        ConcurrentAssignmentError: Another assignment is already in progress.
        MaxAttemptsExceededError: The attempt cap has been reached.
    """
    if snapshot.status is not AssignmentStatus.ASSIGNED:
        raise InvalidStateTransitionError(
            f"Cannot start attempt from status {snapshot.status.value!r}; "
            f"expected {AssignmentStatus.ASSIGNED.value!r}",
            context={"current_status": snapshot.status.value},
        )

    if user_has_other_in_progress_assignment:
        raise ConcurrentAssignmentError(
            "User already has another assignment in progress (FR7)."
        )

    if snapshot.attempts_used >= snapshot.max_attempts:
        raise MaxAttemptsExceededError(
            f"User has used {snapshot.attempts_used} of "
            f"{snapshot.max_attempts} attempts.",
            context={
                "attempts_used": snapshot.attempts_used,
                "max_attempts": snapshot.max_attempts,
            },
        )

    return replace(
        snapshot,
        status=AssignmentStatus.IN_PROGRESS,
        attempts_used=snapshot.attempts_used + 1,
    )


def submit_attempt(
    snapshot: AssignmentSnapshot,
    *,
    score_pct: float,
    pass_threshold_pct: float,
    now: datetime,
) -> AssignmentSubmissionResult:
    """Submit and score the in-progress attempt.

    Per Section 4 of the resolved decisions doc:

    * ``score_pct >= pass_threshold_pct`` → assignment transitions to ``PASSED``.
    * Otherwise, if ``attempts_used < max_attempts`` → assignment transitions
      back to ``ASSIGNED`` so the user can immediately start the next attempt
      (which will replay only the wrongly-answered questions).
    * Otherwise (max attempts exhausted) → assignment transitions to
      ``BLOCKED``; manager intervention is required.

    Both ``PASSED`` and ``BLOCKED`` start the cooldown timer (FR8 / Scenario B).

    Args:
        snapshot: Current state. Must be :class:`AssignmentStatus.IN_PROGRESS`.
        score_pct: Score as a percentage in ``[0, 100]``.
        pass_threshold_pct: Course-defined pass threshold.
        now: Reference timestamp used as ``terminal_at`` for terminal
            transitions. Must be timezone-aware.

    Returns:
        :class:`AssignmentSubmissionResult` with the new snapshot, the
        attempt outcome, and whether a retry is available.

    Raises:
        InvalidStateTransitionError: The assignment is not in progress, or
            ``now`` is naive, or score values are out of range.
    """
    if snapshot.status is not AssignmentStatus.IN_PROGRESS:
        raise InvalidStateTransitionError(
            f"Cannot submit from status {snapshot.status.value!r}; "
            f"expected {AssignmentStatus.IN_PROGRESS.value!r}",
            context={"current_status": snapshot.status.value},
        )
    if now.tzinfo is None:
        raise InvalidStateTransitionError("`now` must be timezone-aware")
    if not 0.0 <= score_pct <= 100.0:
        raise InvalidStateTransitionError(
            f"score_pct {score_pct} out of range [0, 100]"
        )
    if not 0.0 <= pass_threshold_pct <= 100.0:
        raise InvalidStateTransitionError(
            f"pass_threshold_pct {pass_threshold_pct} out of range [0, 100]"
        )

    passed = score_pct >= pass_threshold_pct

    if passed:
        cooldown_until = now + timedelta(days=snapshot.cooldown_days)
        new_snapshot = replace(
            snapshot,
            status=AssignmentStatus.PASSED,
            terminal_at=now,
            terminal_reason=TerminalReason.PASSED,
            cooldown_until=cooldown_until,
        )
        return AssignmentSubmissionResult(
            snapshot=new_snapshot,
            attempt_outcome=AttemptOutcome.PASS,
            retry_available=False,
        )

    # Failed attempt — branch on remaining attempts.
    if snapshot.attempts_used < snapshot.max_attempts:
        # Retry available; transition back to ASSIGNED for the next start_attempt.
        new_snapshot = replace(snapshot, status=AssignmentStatus.ASSIGNED)
        return AssignmentSubmissionResult(
            snapshot=new_snapshot,
            attempt_outcome=AttemptOutcome.FAIL,
            retry_available=True,
        )

    # Max attempts exhausted — terminal BLOCKED.
    cooldown_until = now + timedelta(days=snapshot.cooldown_days)
    new_snapshot = replace(
        snapshot,
        status=AssignmentStatus.BLOCKED,
        terminal_at=now,
        terminal_reason=TerminalReason.MAX_ATTEMPTS_FAILED,
        cooldown_until=cooldown_until,
    )
    return AssignmentSubmissionResult(
        snapshot=new_snapshot,
        attempt_outcome=AttemptOutcome.FAIL,
        retry_available=False,
    )


def cancel(
    snapshot: AssignmentSnapshot,
    *,
    now: datetime,
) -> AssignmentSnapshot:
    """Cancel a non-terminal assignment.

    Permitted from :class:`AssignmentStatus.ASSIGNED` or
    :class:`AssignmentStatus.IN_PROGRESS`. ``CANCELLED`` is terminal but does
    **not** start the course-level cooldown — the user remains eligible for
    immediate re-assignment.

    Args:
        snapshot: Current state.
        now: Reference timestamp; recorded as ``terminal_at``.

    Returns:
        New snapshot with ``status = CANCELLED``.

    Raises:
        InvalidStateTransitionError: The assignment is already terminal.
    """
    if snapshot.status.is_terminal:
        raise InvalidStateTransitionError(
            f"Cannot cancel terminal assignment (status={snapshot.status.value!r})",
            context={"current_status": snapshot.status.value},
        )
    if now.tzinfo is None:
        raise InvalidStateTransitionError("`now` must be timezone-aware")

    return replace(
        snapshot,
        status=AssignmentStatus.CANCELLED,
        terminal_at=now,
        terminal_reason=TerminalReason.CANCELLED_BY_ADMIN,
        cooldown_until=None,
    )


def expire(
    snapshot: AssignmentSnapshot,
    *,
    now: datetime,
) -> AssignmentSnapshot:
    """Mark an assignment as expired due to its due date passing.

    Like :func:`cancel`, ``EXPIRED`` is terminal but does not start the
    cooldown.

    Args:
        snapshot: Current state.
        now: Reference timestamp.

    Returns:
        New snapshot with ``status = EXPIRED``.

    Raises:
        InvalidStateTransitionError: The assignment is already terminal.
    """
    if snapshot.status.is_terminal:
        raise InvalidStateTransitionError(
            f"Cannot expire terminal assignment (status={snapshot.status.value!r})",
            context={"current_status": snapshot.status.value},
        )
    if now.tzinfo is None:
        raise InvalidStateTransitionError("`now` must be timezone-aware")

    return replace(
        snapshot,
        status=AssignmentStatus.EXPIRED,
        terminal_at=now,
        terminal_reason=TerminalReason.EXPIRED_DUE_DATE,
        cooldown_until=None,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def initial_snapshot(
    *,
    cooldown_days: int = 365,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> AssignmentSnapshot:
    """Construct a snapshot for a freshly created assignment."""
    return AssignmentSnapshot(
        status=AssignmentStatus.ASSIGNED,
        attempts_used=0,
        max_attempts=max_attempts,
        cooldown_days=cooldown_days,
    )


def is_within_cooldown(
    cooldown_until: datetime | None,
    *,
    now: datetime,
) -> bool:
    """Return True if ``now`` is before the cooldown expiry.

    Used by the assignment-creation guard to enforce FR8: a new assignment
    for the same course cannot be created while the previous one's cooldown
    is still active.
    """
    if cooldown_until is None:
        return False
    if now.tzinfo is None:
        raise ValueError("`now` must be timezone-aware")
    if cooldown_until.tzinfo is None:
        raise ValueError("`cooldown_until` must be timezone-aware")
    return now < cooldown_until


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(tz=timezone.utc)
