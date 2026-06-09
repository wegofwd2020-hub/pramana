"""Destructure an approved draft's quiz into question/answer specs.

Pure domain glue between a :class:`~pramana.db.models.content.ContentDraft`
``body`` (the verbatim training content an arrival was stored as — see
:mod:`pramana.domain.ingestion`) and the persistence layer. Given a draft body,
it projects the embedded quiz onto the exact field set the service uses to build
:class:`~pramana.db.models.course.Question` / ``AnswerOption`` rows at publish
time (Mentible ADR-011 §9.2, "materialise at publish").

No database, no I/O. The quiz body is *not* validated upstream beyond
"``questions`` is a non-empty list" (:func:`pramana.domain.consumable_package.
_parse_quiz`), so the per-question shape is validated **here** — a malformed quiz
that reached ``APPROVED`` raises :class:`~pramana.exceptions.ValidationError`
rather than producing a broken, ungradeable course version.

The contract shape (Mentible ADR-011 §4, ``quiz``)::

    {
        "pass_threshold_pct": 80,
        "questions": [{"prompt": "...", "options": ["A", "B", "C"], "answer_index": 0}],
    }
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeGuard

from pramana.domain.enums import QuestionType
from pramana.exceptions import ValidationError

_MIN_OPTIONS = 2
_TRUE_FALSE_OPTIONS = ("true", "false")


@dataclass(frozen=True, slots=True)
class AnswerOptionSpec:
    """One answer choice for a :class:`QuestionSpec`."""

    option_text: str
    is_correct: bool
    display_order: int


@dataclass(frozen=True, slots=True)
class QuestionSpec:
    """A quiz question projected from the draft body, ready to persist."""

    question_text: str
    question_type: QuestionType
    display_order: int
    options: tuple[AnswerOptionSpec, ...]
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class MaterializedQuiz:
    """The full quiz projected from a draft body.

    ``pass_threshold_pct`` is the threshold the quiz itself declares; the service
    propagates it onto the course so the published quiz governs its own grading.
    It is ``None`` for a hand-authored body that omitted one.
    """

    questions: tuple[QuestionSpec, ...]
    pass_threshold_pct: int | None


def materialize_quiz(body: Mapping[str, Any]) -> MaterializedQuiz:
    """Project a draft ``body`` onto persistable question/answer specs.

    Raises:
        ValidationError: The body has no quiz, an empty/malformed question list,
            a question missing its prompt, fewer than two options, or an
            ``answer_index`` that is absent or out of range.
    """
    quiz = body.get("quiz") if isinstance(body, Mapping) else None
    if not isinstance(quiz, Mapping):
        raise ValidationError(
            "draft body has no quiz to materialise", context={"field": "body.quiz"}
        )

    raw_questions = quiz.get("questions")
    if not _is_list(raw_questions) or len(raw_questions) == 0:
        raise ValidationError(
            "quiz.questions must be a non-empty list",
            context={"field": "quiz.questions"},
        )

    questions = tuple(_materialize_question(item, index=i) for i, item in enumerate(raw_questions))
    return MaterializedQuiz(
        questions=questions,
        pass_threshold_pct=_optional_threshold(quiz),
    )


def _materialize_question(item: Any, *, index: int) -> QuestionSpec:
    path = f"quiz.questions[{index}]"
    if not isinstance(item, Mapping):
        raise ValidationError(f"{path} must be an object", context={"field": path})

    prompt = item.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValidationError(
            f"{path}.prompt must be a non-empty string",
            context={"field": f"{path}.prompt"},
        )

    raw_options = item.get("options")
    if not _is_list(raw_options) or len(raw_options) < _MIN_OPTIONS:
        raise ValidationError(
            f"{path}.options must list at least {_MIN_OPTIONS} choices",
            context={"field": f"{path}.options"},
        )
    for j, opt in enumerate(raw_options):
        if not isinstance(opt, str) or not opt.strip():
            raise ValidationError(
                f"{path}.options[{j}] must be a non-empty string",
                context={"field": f"{path}.options[{j}]"},
            )

    answer_index = item.get("answer_index")
    # bool is an int subclass — reject it explicitly so True/False can't pose as 1/0.
    if not isinstance(answer_index, int) or isinstance(answer_index, bool):
        raise ValidationError(
            f"{path}.answer_index must be an integer",
            context={"field": f"{path}.answer_index"},
        )
    if not 0 <= answer_index < len(raw_options):
        raise ValidationError(
            f"{path}.answer_index {answer_index} out of range for {len(raw_options)} options",
            context={"field": f"{path}.answer_index", "value": answer_index},
        )

    options = tuple(
        AnswerOptionSpec(option_text=opt, is_correct=(j == answer_index), display_order=j)
        for j, opt in enumerate(raw_options)
    )
    return QuestionSpec(
        question_text=prompt,
        question_type=_infer_type(raw_options),
        display_order=index,
        options=options,
    )


def _infer_type(options: Sequence[str]) -> QuestionType:
    """A two-choice ``["True", "False"]`` quiz is true/false; everything else is
    single-select. The contract carries no explicit type, so it is inferred."""
    normalized = tuple(o.strip().lower() for o in options)
    if normalized == _TRUE_FALSE_OPTIONS:
        return QuestionType.TRUE_FALSE
    return QuestionType.SINGLE_SELECT


def _optional_threshold(quiz: Mapping[str, Any]) -> int | None:
    value = quiz.get("pass_threshold_pct")
    if value is None or isinstance(value, bool) or not isinstance(value, int):
        return None
    if not 0 <= value <= 100:
        return None
    return value


def _is_list(value: Any) -> TypeGuard[Sequence[Any]]:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes)
