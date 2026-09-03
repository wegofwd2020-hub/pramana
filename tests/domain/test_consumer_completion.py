from pramana.domain.consumer.completion import (
    EnrollmentCounters,
    derive_counters,
    is_all_correct,
)


def test_is_all_correct_only_at_100():
    assert is_all_correct(100.0) is True
    assert is_all_correct(99.9) is False
    assert is_all_correct(0.0) is False


def test_derive_counters_counts_perfect_scores_and_best():
    got = derive_counters(num_views=3, attempt_scores=[100.0, 80.0, 100.0, 60.0])
    assert got == EnrollmentCounters(view_count=3, completion_count=2, best_score_pct=100.0)


def test_derive_counters_empty_scores():
    got = derive_counters(num_views=0, attempt_scores=[])
    assert got == EnrollmentCounters(view_count=0, completion_count=0, best_score_pct=None)
