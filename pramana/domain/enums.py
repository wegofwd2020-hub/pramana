"""Domain-level enumerations.

These are pure value objects — no database or framework imports — so they
can be re-used by the persistence layer, the API layer, and the test suite
without coupling.
"""

from __future__ import annotations

from enum import StrEnum, auto


class AssignmentStatus(StrEnum):
    """Lifecycle state of a course assignment.

    See Section 7 of ``docs/02_resolved_decisions.md`` for the full state
    machine. Terminal states are :attr:`PASSED`, :attr:`BLOCKED`,
    :attr:`CANCELLED`, and :attr:`EXPIRED` — no transitions out of them are
    permitted.
    """

    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    @property
    def is_terminal(self) -> bool:
        """True if no transitions out of this state are permitted."""
        return self in _TERMINAL_STATES

    @property
    def is_active(self) -> bool:
        """True if the assignment counts as 'currently being worked on'."""
        return self == AssignmentStatus.IN_PROGRESS

    @property
    def started_cooldown(self) -> bool:
        """True if reaching this state begins the course re-assignment cooldown.

        Per FR8 / Section 4 of the resolved decisions doc, both ``PASSED`` and
        ``BLOCKED`` start the cooldown. ``CANCELLED`` and ``EXPIRED`` do not —
        the user remains eligible for immediate re-assignment in those cases.
        """
        return self in {AssignmentStatus.PASSED, AssignmentStatus.BLOCKED}


_TERMINAL_STATES: frozenset[AssignmentStatus] = frozenset(
    {
        AssignmentStatus.PASSED,
        AssignmentStatus.BLOCKED,
        AssignmentStatus.CANCELLED,
        AssignmentStatus.EXPIRED,
    }
)


class AttemptOutcome(StrEnum):
    """Outcome of a single quiz attempt."""

    IN_PROGRESS = "in_progress"
    PASS = "pass"
    FAIL = "fail"


class TerminalReason(StrEnum):
    """Why an assignment reached a terminal state.

    Captured on the assignment record at the moment of terminal transition;
    used by audit reporting and exception reports.
    """

    PASSED = "passed"
    MAX_ATTEMPTS_FAILED = "max_attempts_failed"
    CANCELLED_BY_ADMIN = "cancelled_by_admin"
    EXPIRED_DUE_DATE = "expired_due_date"


class TransitionEvent(StrEnum):
    """Events that drive state transitions on the assignment.

    Exposed as discriminated values so audit-log entries can name the
    triggering event without re-deriving it from the before/after states.
    """

    START_ATTEMPT = auto()
    SUBMIT_ATTEMPT = auto()
    CANCEL = auto()
    EXPIRE = auto()
