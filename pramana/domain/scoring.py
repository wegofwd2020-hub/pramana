"""Quiz scoring — pure domain.

No database, no HTTP, no I/O. Grades a set of answered questions against their
canonical correct options and produces a weighted percentage score. The
assignment state machine (:mod:`pramana.domain.assignment_state`) deliberately
takes ``score_pct`` as an *input*; this module is where that number comes from,
kept separate so grading is exhaustively testable on its own.

A question is correct iff the learner's selected option set is *exactly* the
set of correct options — no missing correct options, no extra wrong ones. This
holds for single-select, true/false, and (future) multi-select uniformly. The
overall score is the weight of correct questions over total weight, as a
percentage in ``[0, 100]``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class GradedQuestion:
    """A question reduced to what grading needs: its id, weight, correct set."""

    question_id: UUID
    weight: float
    correct_option_ids: frozenset[UUID]

    def __post_init__(self) -> None:
        if self.weight <= 0:
            raise ValueError("question weight must be positive")
        if not self.correct_option_ids:
            raise ValueError(f"question {self.question_id} has no correct option; cannot grade")


@dataclass(frozen=True, slots=True)
class QuestionResult:
    """Per-question grading outcome."""

    question_id: UUID
    is_correct: bool


@dataclass(frozen=True, slots=True)
class GradeResult:
    """Overall grade: the percentage and the per-question breakdown."""

    score_pct: float
    per_question: tuple[QuestionResult, ...]

    @property
    def incorrect_question_ids(self) -> tuple[UUID, ...]:
        """The questions answered wrongly — the retry replays exactly these."""
        return tuple(r.question_id for r in self.per_question if not r.is_correct)


def grade_attempt(
    questions: Sequence[GradedQuestion],
    selected_by_question: Mapping[UUID, Iterable[UUID]],
) -> GradeResult:
    """Grade a full quiz attempt.

    Args:
        questions: Every question in the attempt's quiz. Must be non-empty.
        selected_by_question: The option ids the learner selected per question.
            A question absent from the map (or with an empty selection) is
            treated as answered wrongly. Selections are compared as sets, so
            duplicates and order do not matter.

    Returns:
        :class:`GradeResult` with the weighted ``score_pct`` in ``[0, 100]`` and
        one :class:`QuestionResult` per question, in the input order.

    Raises:
        ValueError: ``questions`` is empty (a quiz must have questions).
    """
    if not questions:
        raise ValueError("cannot grade an attempt with no questions")

    results: list[QuestionResult] = []
    correct_weight = 0.0
    total_weight = 0.0
    for q in questions:
        selected = frozenset(selected_by_question.get(q.question_id, ()))
        is_correct = selected == q.correct_option_ids
        results.append(QuestionResult(question_id=q.question_id, is_correct=is_correct))
        total_weight += q.weight
        if is_correct:
            correct_weight += q.weight

    score_pct = 100.0 * correct_weight / total_weight
    return GradeResult(score_pct=score_pct, per_question=tuple(results))
