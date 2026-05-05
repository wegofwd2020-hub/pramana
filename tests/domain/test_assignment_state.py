"""Tests for :mod:`pramana.domain.assignment_state`.

The state machine is a pure-function module, which lets us drive it with
:mod:`hypothesis` to verify invariants exhaustively rather than relying on
hand-crafted examples alone. The hand-crafted examples that *are* present
correspond directly to the worked flows in Section 4.4 of
``docs/02_resolved_decisions.md``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, strategies as st

from pramana.domain.assignment_state import (
    DEFAULT_MAX_ATTEMPTS,
    AssignmentSnapshot,
    AssignmentSubmissionResult,
    cancel,
    expire,
    initial_snapshot,
    is_within_cooldown,
    start_attempt,
    submit_attempt,
)
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
# Mock data — fixtures used by both example tests and property tests
# ---------------------------------------------------------------------------
NOW = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=30)
COOLDOWN_DAYS = 365
PASS_THRESHOLD = 80.0


@pytest.fixture
def fresh_snapshot() -> AssignmentSnapshot:
    """A freshly assigned course, no attempts started yet."""
    return initial_snapshot(cooldown_days=COOLDOWN_DAYS, max_attempts=2)


@pytest.fixture
def in_progress_snapshot(fresh_snapshot: AssignmentSnapshot) -> AssignmentSnapshot:
    """An assignment with one attempt currently underway."""
    return start_attempt(fresh_snapshot, user_has_other_in_progress_assignment=False)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------
tz_aware_datetimes = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)

scores = st.floats(
    min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
)

cooldown_days_strategy = st.integers(min_value=0, max_value=3650)
max_attempts_strategy = st.integers(min_value=1, max_value=5)


# ===========================================================================
# AssignmentSnapshot — invariants enforced in __post_init__
# ===========================================================================
class TestSnapshotInvariants:
    """The dataclass enforces consistency between status and timestamp fields."""

    def test_initial_snapshot_is_valid(self) -> None:
        """A freshly assigned snapshot has no terminal_at or cooldown."""
        snap = initial_snapshot()
        assert snap.status is AssignmentStatus.ASSIGNED
        assert snap.attempts_used == 0
        assert snap.terminal_at is None
        assert snap.cooldown_until is None

    def test_terminal_status_without_terminal_at_rejected(self) -> None:
        """A terminal status must come with a terminal_at timestamp."""
        with pytest.raises(ValueError, match="terminal_at is None"):
            AssignmentSnapshot(status=AssignmentStatus.PASSED)

    def test_non_terminal_status_with_terminal_at_rejected(self) -> None:
        """A non-terminal status must not carry a terminal_at."""
        with pytest.raises(ValueError, match="not terminal but terminal_at is set"):
            AssignmentSnapshot(status=AssignmentStatus.ASSIGNED, terminal_at=NOW)

    def test_passed_without_cooldown_until_rejected(self) -> None:
        """A status that starts cooldown must have cooldown_until populated."""
        with pytest.raises(ValueError, match="cooldown_until is None"):
            AssignmentSnapshot(status=AssignmentStatus.PASSED, terminal_at=NOW)

    def test_cancelled_with_cooldown_until_rejected(self) -> None:
        """CANCELLED must not carry a cooldown_until — it doesn't start cooldown."""
        with pytest.raises(ValueError, match="does not start cooldown"):
            AssignmentSnapshot(
                status=AssignmentStatus.CANCELLED,
                terminal_at=NOW,
                cooldown_until=LATER,
            )

    def test_negative_attempts_rejected(self) -> None:
        with pytest.raises(ValueError, match="attempts_used must be non-negative"):
            AssignmentSnapshot(status=AssignmentStatus.ASSIGNED, attempts_used=-1)

    def test_zero_max_attempts_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_attempts must be >= 1"):
            AssignmentSnapshot(
                status=AssignmentStatus.ASSIGNED, max_attempts=0
            )

    def test_negative_cooldown_rejected(self) -> None:
        with pytest.raises(ValueError, match="cooldown_days must be non-negative"):
            AssignmentSnapshot(
                status=AssignmentStatus.ASSIGNED, cooldown_days=-1
            )

    def test_remaining_attempts_property(self) -> None:
        """remaining_attempts = max(0, max_attempts - attempts_used)."""
        snap = initial_snapshot(max_attempts=3)
        assert snap.remaining_attempts == 3
        snap = AssignmentSnapshot(
            status=AssignmentStatus.ASSIGNED, max_attempts=3, attempts_used=2
        )
        assert snap.remaining_attempts == 1
        snap = AssignmentSnapshot(
            status=AssignmentStatus.ASSIGNED, max_attempts=3, attempts_used=10
        )
        assert snap.remaining_attempts == 0


# ===========================================================================
# start_attempt
# ===========================================================================
class TestStartAttempt:
    """Behaviour of the ASSIGNED → IN_PROGRESS transition."""

    def test_starts_from_assigned(
        self, fresh_snapshot: AssignmentSnapshot
    ) -> None:
        result = start_attempt(
            fresh_snapshot, user_has_other_in_progress_assignment=False
        )
        assert result.status is AssignmentStatus.IN_PROGRESS
        assert result.attempts_used == 1

    def test_increments_attempts_used(
        self, fresh_snapshot: AssignmentSnapshot
    ) -> None:
        result = start_attempt(
            fresh_snapshot, user_has_other_in_progress_assignment=False
        )
        assert result.attempts_used == fresh_snapshot.attempts_used + 1

    def test_blocks_on_concurrent_assignment(
        self, fresh_snapshot: AssignmentSnapshot
    ) -> None:
        with pytest.raises(ConcurrentAssignmentError):
            start_attempt(
                fresh_snapshot, user_has_other_in_progress_assignment=True
            )

    def test_rejects_when_already_in_progress(
        self, in_progress_snapshot: AssignmentSnapshot
    ) -> None:
        with pytest.raises(InvalidStateTransitionError):
            start_attempt(
                in_progress_snapshot,
                user_has_other_in_progress_assignment=False,
            )

    @pytest.mark.parametrize(
        "terminal_status",
        [
            AssignmentStatus.PASSED,
            AssignmentStatus.BLOCKED,
            AssignmentStatus.CANCELLED,
            AssignmentStatus.EXPIRED,
        ],
    )
    def test_rejects_from_terminal_states(
        self, terminal_status: AssignmentStatus
    ) -> None:
        kwargs: dict = {
            "status": terminal_status,
            "terminal_at": NOW,
            "terminal_reason": TerminalReason.PASSED,
        }
        if terminal_status.started_cooldown:
            kwargs["cooldown_until"] = LATER
        snap = AssignmentSnapshot(**kwargs)
        with pytest.raises(InvalidStateTransitionError):
            start_attempt(snap, user_has_other_in_progress_assignment=False)

    def test_rejects_when_max_attempts_reached(self) -> None:
        """Not reachable in normal flow, but defended against."""
        snap = AssignmentSnapshot(
            status=AssignmentStatus.ASSIGNED,
            attempts_used=2,
            max_attempts=2,
        )
        with pytest.raises(MaxAttemptsExceededError):
            start_attempt(snap, user_has_other_in_progress_assignment=False)


# ===========================================================================
# submit_attempt — Section 4 cooldown semantics
# ===========================================================================
class TestSubmitAttempt:
    """Submission branches into PASSED, retry-eligible FAIL, or BLOCKED."""

    def test_pass_first_attempt(
        self, in_progress_snapshot: AssignmentSnapshot
    ) -> None:
        """Flow A from Section 4.4: pass on first try."""
        result = submit_attempt(
            in_progress_snapshot,
            score_pct=85.0,
            pass_threshold_pct=PASS_THRESHOLD,
            now=NOW,
        )
        assert isinstance(result, AssignmentSubmissionResult)
        assert result.snapshot.status is AssignmentStatus.PASSED
        assert result.snapshot.terminal_at == NOW
        assert result.snapshot.terminal_reason is TerminalReason.PASSED
        assert result.snapshot.cooldown_until == NOW + timedelta(days=COOLDOWN_DAYS)
        assert result.attempt_outcome is AttemptOutcome.PASS
        assert result.retry_available is False

    def test_pass_at_exact_threshold(
        self, in_progress_snapshot: AssignmentSnapshot
    ) -> None:
        """Score equal to threshold counts as a pass."""
        result = submit_attempt(
            in_progress_snapshot,
            score_pct=PASS_THRESHOLD,
            pass_threshold_pct=PASS_THRESHOLD,
            now=NOW,
        )
        assert result.snapshot.status is AssignmentStatus.PASSED

    def test_fail_with_retry_available(
        self, in_progress_snapshot: AssignmentSnapshot
    ) -> None:
        """Flow B from Section 4.4: fail first attempt, retry available."""
        result = submit_attempt(
            in_progress_snapshot,
            score_pct=60.0,
            pass_threshold_pct=PASS_THRESHOLD,
            now=NOW,
        )
        # Goes back to ASSIGNED so the user can immediately start the next attempt.
        assert result.snapshot.status is AssignmentStatus.ASSIGNED
        assert result.snapshot.terminal_at is None
        assert result.snapshot.cooldown_until is None
        # attempts_used preserved (it was bumped on start).
        assert result.snapshot.attempts_used == 1
        assert result.attempt_outcome is AttemptOutcome.FAIL
        assert result.retry_available is True

    def test_fail_max_attempts_reached_blocks(
        self, fresh_snapshot: AssignmentSnapshot
    ) -> None:
        """Flow C from Section 4.4: fail second attempt → BLOCKED."""
        # Simulate having burned attempt 1 (failed) and started attempt 2.
        after_first_attempt = AssignmentSnapshot(
            status=AssignmentStatus.IN_PROGRESS,
            attempts_used=2,
            max_attempts=2,
            cooldown_days=COOLDOWN_DAYS,
        )
        result = submit_attempt(
            after_first_attempt,
            score_pct=50.0,
            pass_threshold_pct=PASS_THRESHOLD,
            now=NOW,
        )
        assert result.snapshot.status is AssignmentStatus.BLOCKED
        assert result.snapshot.terminal_reason is TerminalReason.MAX_ATTEMPTS_FAILED
        assert result.snapshot.cooldown_until == NOW + timedelta(days=COOLDOWN_DAYS)
        assert result.attempt_outcome is AttemptOutcome.FAIL
        assert result.retry_available is False

    def test_rejects_submit_from_assigned(
        self, fresh_snapshot: AssignmentSnapshot
    ) -> None:
        with pytest.raises(InvalidStateTransitionError):
            submit_attempt(
                fresh_snapshot,
                score_pct=90.0,
                pass_threshold_pct=PASS_THRESHOLD,
                now=NOW,
            )

    def test_rejects_naive_datetime(
        self, in_progress_snapshot: AssignmentSnapshot
    ) -> None:
        naive = datetime(2026, 5, 5, 12, 0, 0)  # no tzinfo
        with pytest.raises(InvalidStateTransitionError, match="timezone-aware"):
            submit_attempt(
                in_progress_snapshot,
                score_pct=90.0,
                pass_threshold_pct=PASS_THRESHOLD,
                now=naive,
            )

    @pytest.mark.parametrize("score", [-0.1, 100.5, 200.0, -50.0])
    def test_rejects_score_out_of_range(
        self, in_progress_snapshot: AssignmentSnapshot, score: float
    ) -> None:
        with pytest.raises(InvalidStateTransitionError, match="out of range"):
            submit_attempt(
                in_progress_snapshot,
                score_pct=score,
                pass_threshold_pct=PASS_THRESHOLD,
                now=NOW,
            )


# ===========================================================================
# cancel and expire
# ===========================================================================
class TestCancelAndExpire:
    """Both go terminal but neither starts cooldown."""

    def test_cancel_from_assigned(
        self, fresh_snapshot: AssignmentSnapshot
    ) -> None:
        result = cancel(fresh_snapshot, now=NOW)
        assert result.status is AssignmentStatus.CANCELLED
        assert result.terminal_at == NOW
        assert result.terminal_reason is TerminalReason.CANCELLED_BY_ADMIN
        assert result.cooldown_until is None

    def test_cancel_from_in_progress(
        self, in_progress_snapshot: AssignmentSnapshot
    ) -> None:
        result = cancel(in_progress_snapshot, now=NOW)
        assert result.status is AssignmentStatus.CANCELLED
        assert result.cooldown_until is None

    def test_expire_from_assigned(
        self, fresh_snapshot: AssignmentSnapshot
    ) -> None:
        result = expire(fresh_snapshot, now=NOW)
        assert result.status is AssignmentStatus.EXPIRED
        assert result.terminal_reason is TerminalReason.EXPIRED_DUE_DATE
        assert result.cooldown_until is None

    @pytest.mark.parametrize(
        "terminal_status",
        [
            AssignmentStatus.PASSED,
            AssignmentStatus.BLOCKED,
            AssignmentStatus.CANCELLED,
            AssignmentStatus.EXPIRED,
        ],
    )
    def test_cancel_rejected_from_terminal(
        self, terminal_status: AssignmentStatus
    ) -> None:
        kwargs: dict = {
            "status": terminal_status,
            "terminal_at": NOW,
            "terminal_reason": TerminalReason.PASSED,
        }
        if terminal_status.started_cooldown:
            kwargs["cooldown_until"] = LATER
        snap = AssignmentSnapshot(**kwargs)
        with pytest.raises(InvalidStateTransitionError):
            cancel(snap, now=LATER)

    def test_cancel_rejects_naive_datetime(
        self, fresh_snapshot: AssignmentSnapshot
    ) -> None:
        with pytest.raises(InvalidStateTransitionError, match="timezone-aware"):
            cancel(fresh_snapshot, now=datetime(2026, 5, 5))


# ===========================================================================
# is_within_cooldown
# ===========================================================================
class TestIsWithinCooldown:
    def test_none_cooldown_returns_false(self) -> None:
        assert is_within_cooldown(None, now=NOW) is False

    def test_now_before_cooldown_returns_true(self) -> None:
        cooldown_until = NOW + timedelta(days=10)
        assert is_within_cooldown(cooldown_until, now=NOW) is True

    def test_now_after_cooldown_returns_false(self) -> None:
        cooldown_until = NOW - timedelta(days=10)
        assert is_within_cooldown(cooldown_until, now=NOW) is False

    def test_naive_now_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            is_within_cooldown(LATER, now=datetime(2026, 5, 5))


# ===========================================================================
# Property-based tests
# ===========================================================================
class TestStateMachineProperties:
    """Properties that must hold across all reachable snapshots."""

    @given(
        score=scores,
        threshold=scores,
        cooldown=cooldown_days_strategy,
        now=tz_aware_datetimes,
    )
    def test_terminal_states_set_terminal_at(
        self,
        score: float,
        threshold: float,
        cooldown: int,
        now: datetime,
    ) -> None:
        """Any path that reaches a terminal state populates terminal_at."""
        snap = AssignmentSnapshot(
            status=AssignmentStatus.IN_PROGRESS,
            attempts_used=2,
            max_attempts=2,
            cooldown_days=cooldown,
        )
        result = submit_attempt(
            snap, score_pct=score, pass_threshold_pct=threshold, now=now
        )
        if result.snapshot.status.is_terminal:
            assert result.snapshot.terminal_at == now
            assert result.snapshot.terminal_reason is not None

    @given(
        score=scores,
        threshold=scores,
        cooldown=cooldown_days_strategy,
        now=tz_aware_datetimes,
    )
    def test_cooldown_consistent_with_terminal_at(
        self,
        score: float,
        threshold: float,
        cooldown: int,
        now: datetime,
    ) -> None:
        """For statuses that start cooldown, cooldown_until == terminal_at + cooldown_days."""
        snap = AssignmentSnapshot(
            status=AssignmentStatus.IN_PROGRESS,
            attempts_used=2,
            max_attempts=2,
            cooldown_days=cooldown,
        )
        result = submit_attempt(
            snap, score_pct=score, pass_threshold_pct=threshold, now=now
        )
        if result.snapshot.status.started_cooldown:
            assert result.snapshot.terminal_at is not None
            assert result.snapshot.cooldown_until == (
                result.snapshot.terminal_at + timedelta(days=cooldown)
            )

    @given(
        max_attempts=max_attempts_strategy,
        cooldown=cooldown_days_strategy,
    )
    def test_attempts_used_monotonically_increases(
        self,
        max_attempts: int,
        cooldown: int,
    ) -> None:
        """start_attempt only ever increases attempts_used by 1; submit never decreases it."""
        snap = initial_snapshot(cooldown_days=cooldown, max_attempts=max_attempts)
        prev = snap.attempts_used
        for _ in range(max_attempts):
            snap = start_attempt(
                snap, user_has_other_in_progress_assignment=False
            )
            assert snap.attempts_used == prev + 1
            prev = snap.attempts_used
            # Fail intentionally to walk through the loop.
            result = submit_attempt(
                snap,
                score_pct=0.0,
                pass_threshold_pct=PASS_THRESHOLD,
                now=NOW,
            )
            assert result.snapshot.attempts_used >= prev
            snap = result.snapshot
            if snap.status.is_terminal:
                break

    @given(
        score=scores,
        threshold=scores,
        cooldown=cooldown_days_strategy,
    )
    def test_terminal_states_are_absorbing(
        self,
        score: float,
        threshold: float,
        cooldown: int,
    ) -> None:
        """Once terminal, no transition is permitted."""
        # Build a PASSED snapshot via the legitimate path.
        snap = AssignmentSnapshot(
            status=AssignmentStatus.IN_PROGRESS,
            attempts_used=1,
            max_attempts=2,
            cooldown_days=cooldown,
        )
        result = submit_attempt(
            snap, score_pct=100.0, pass_threshold_pct=PASS_THRESHOLD, now=NOW
        )
        assert result.snapshot.status is AssignmentStatus.PASSED

        terminal = result.snapshot

        with pytest.raises(InvalidStateTransitionError):
            start_attempt(terminal, user_has_other_in_progress_assignment=False)
        with pytest.raises(InvalidStateTransitionError):
            submit_attempt(
                terminal,
                score_pct=score,
                pass_threshold_pct=threshold,
                now=LATER,
            )
        with pytest.raises(InvalidStateTransitionError):
            cancel(terminal, now=LATER)
        with pytest.raises(InvalidStateTransitionError):
            expire(terminal, now=LATER)


# ===========================================================================
# Worked-example flows from Section 4.4 of the resolved decisions doc
# ===========================================================================
class TestWorkedFlowsFromSpec:
    """End-to-end traces of the three documented user flows."""

    def test_flow_a_pass_first_attempt(self) -> None:
        """Trainee starts → submits at 90% → PASSED, cooldown 365d, certificate eligible."""
        snap = initial_snapshot(cooldown_days=COOLDOWN_DAYS, max_attempts=2)
        snap = start_attempt(snap, user_has_other_in_progress_assignment=False)
        result = submit_attempt(
            snap,
            score_pct=90.0,
            pass_threshold_pct=PASS_THRESHOLD,
            now=NOW,
        )

        assert result.snapshot.status is AssignmentStatus.PASSED
        assert result.snapshot.attempts_used == 1
        assert result.snapshot.cooldown_until == NOW + timedelta(days=COOLDOWN_DAYS)
        assert result.retry_available is False

    def test_flow_b_fail_then_pass(self) -> None:
        """Fail first attempt at 60%, pass second at 85% → PASSED."""
        snap = initial_snapshot(cooldown_days=COOLDOWN_DAYS, max_attempts=2)

        # Attempt 1 — fail.
        snap = start_attempt(snap, user_has_other_in_progress_assignment=False)
        first_result = submit_attempt(
            snap,
            score_pct=60.0,
            pass_threshold_pct=PASS_THRESHOLD,
            now=NOW,
        )
        assert first_result.snapshot.status is AssignmentStatus.ASSIGNED
        assert first_result.retry_available is True
        assert first_result.snapshot.attempts_used == 1

        # Attempt 2 — pass.
        snap = start_attempt(
            first_result.snapshot,
            user_has_other_in_progress_assignment=False,
        )
        assert snap.attempts_used == 2

        second_result = submit_attempt(
            snap,
            score_pct=85.0,
            pass_threshold_pct=PASS_THRESHOLD,
            now=LATER,
        )
        assert second_result.snapshot.status is AssignmentStatus.PASSED
        assert second_result.snapshot.terminal_at == LATER

    def test_flow_c_fail_both_attempts_blocks(self) -> None:
        """Fail attempt 1 at 50%, fail attempt 2 at 70% → BLOCKED."""
        snap = initial_snapshot(cooldown_days=COOLDOWN_DAYS, max_attempts=2)

        # Attempt 1 — fail.
        snap = start_attempt(snap, user_has_other_in_progress_assignment=False)
        first = submit_attempt(
            snap,
            score_pct=50.0,
            pass_threshold_pct=PASS_THRESHOLD,
            now=NOW,
        )
        assert first.snapshot.status is AssignmentStatus.ASSIGNED
        assert first.retry_available is True

        # Attempt 2 — fail.
        snap = start_attempt(
            first.snapshot, user_has_other_in_progress_assignment=False
        )
        second = submit_attempt(
            snap,
            score_pct=70.0,
            pass_threshold_pct=PASS_THRESHOLD,
            now=LATER,
        )
        assert second.snapshot.status is AssignmentStatus.BLOCKED
        assert second.snapshot.terminal_reason is TerminalReason.MAX_ATTEMPTS_FAILED
        assert second.snapshot.cooldown_until == LATER + timedelta(
            days=COOLDOWN_DAYS
        )
        assert second.retry_available is False


# ===========================================================================
# Default constants
# ===========================================================================
def test_default_max_attempts_constant() -> None:
    """The default max-attempts value matches the resolved decisions (2)."""
    assert DEFAULT_MAX_ATTEMPTS == 2
