"""Tests for the pure quiz-scoring domain."""

from __future__ import annotations

import uuid

import pytest

from pramana.domain.scoring import GradedQuestion, grade_attempt


def _q(weight: float = 1.0, *, correct: list[uuid.UUID] | None = None) -> GradedQuestion:
    return GradedQuestion(
        question_id=uuid.uuid4(),
        weight=weight,
        correct_option_ids=frozenset(correct or [uuid.uuid4()]),
    )


class TestGradedQuestion:
    def test_rejects_nonpositive_weight(self) -> None:
        with pytest.raises(ValueError, match="weight must be positive"):
            GradedQuestion(uuid.uuid4(), 0.0, frozenset([uuid.uuid4()]))

    def test_rejects_no_correct_option(self) -> None:
        with pytest.raises(ValueError, match="no correct option"):
            GradedQuestion(uuid.uuid4(), 1.0, frozenset())


class TestGradeAttempt:
    def test_all_correct_is_100(self) -> None:
        opt_a, opt_b = uuid.uuid4(), uuid.uuid4()
        q1 = _q(correct=[opt_a])
        q2 = _q(correct=[opt_b])
        result = grade_attempt([q1, q2], {q1.question_id: [opt_a], q2.question_id: [opt_b]})
        assert result.score_pct == 100.0
        assert result.incorrect_question_ids == ()

    def test_all_wrong_is_0(self) -> None:
        correct, wrong = uuid.uuid4(), uuid.uuid4()
        q1 = _q(correct=[correct])
        result = grade_attempt([q1], {q1.question_id: [wrong]})
        assert result.score_pct == 0.0
        assert result.incorrect_question_ids == (q1.question_id,)

    def test_partial_uniform_weight(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        q1 = _q(correct=[a])
        q2 = _q(correct=[b])
        # q1 right, q2 wrong -> 50%
        result = grade_attempt([q1, q2], {q1.question_id: [a], q2.question_id: [uuid.uuid4()]})
        assert result.score_pct == 50.0
        assert result.incorrect_question_ids == (q2.question_id,)

    def test_weighted_score(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        q_heavy = _q(weight=3.0, correct=[a])
        q_light = _q(weight=1.0, correct=[b])
        # heavy right, light wrong -> 3/4 = 75%
        result = grade_attempt(
            [q_heavy, q_light],
            {q_heavy.question_id: [a], q_light.question_id: [uuid.uuid4()]},
        )
        assert result.score_pct == 75.0

    def test_unanswered_question_is_wrong(self) -> None:
        q1 = _q()
        result = grade_attempt([q1], {})  # no selection at all
        assert result.score_pct == 0.0
        assert result.incorrect_question_ids == (q1.question_id,)

    def test_extra_selected_option_is_wrong(self) -> None:
        correct, extra = uuid.uuid4(), uuid.uuid4()
        q1 = _q(correct=[correct])
        # selected the correct one AND an extra -> not an exact set match
        result = grade_attempt([q1], {q1.question_id: [correct, extra]})
        assert result.score_pct == 0.0

    def test_multiselect_requires_full_set(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        q_multi = _q(correct=[a, b])
        # only one of two correct -> wrong
        partial = grade_attempt([q_multi], {q_multi.question_id: [a]})
        assert partial.score_pct == 0.0
        # both correct, order/dupes irrelevant -> right
        full = grade_attempt([q_multi], {q_multi.question_id: [b, a, a]})
        assert full.score_pct == 100.0

    def test_per_question_preserves_order(self) -> None:
        qs = [_q() for _ in range(3)]
        result = grade_attempt(qs, {})
        assert [r.question_id for r in result.per_question] == [q.question_id for q in qs]

    def test_empty_quiz_raises(self) -> None:
        with pytest.raises(ValueError, match="no questions"):
            grade_attempt([], {})
