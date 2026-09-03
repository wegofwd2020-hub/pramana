"""Consumer completion rule + counter derivation — pure, no I/O.

A consumer 'completion' is a single quiz attempt at a perfect score. This is
deliberately a stricter bar than the B2B pass threshold (which lives in
pramana.config.Settings.default_pass_threshold_pct).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

_PERFECT_SCORE = 100.0


def is_all_correct(score_pct: float) -> bool:
    """True iff every question was answered correctly (a perfect score)."""
    return score_pct >= _PERFECT_SCORE


@dataclass(frozen=True, slots=True)
class EnrollmentCounters:
    view_count: int
    completion_count: int
    best_score_pct: float | None


def derive_counters(*, num_views: int, attempt_scores: Sequence[float]) -> EnrollmentCounters:
    """Reduce raw event history to the denormalized enrollment counters."""
    completion_count = sum(1 for s in attempt_scores if is_all_correct(s))
    best = max(attempt_scores) if attempt_scores else None
    return EnrollmentCounters(
        view_count=num_views, completion_count=completion_count, best_score_pct=best
    )
