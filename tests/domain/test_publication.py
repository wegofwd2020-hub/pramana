"""Tests for the publish-time quiz materialization (pure domain)."""

from __future__ import annotations

from typing import Any

import pytest

from pramana.domain.enums import QuestionType
from pramana.domain.publication import materialize_quiz
from pramana.exceptions import ValidationError


def _body(**quiz_overrides: Any) -> dict[str, Any]:
    quiz: dict[str, Any] = {
        "pass_threshold_pct": 80,
        "questions": [
            {
                "prompt": "Who attests to internal controls under §404?",
                "options": ["Management", "Auditors", "The SEC"],
                "answer_index": 0,
            }
        ],
    }
    quiz.update(quiz_overrides)
    return {"modules": [{"heading": "x"}], "quiz": quiz}


class TestHappyPath:
    def test_projects_questions_and_options(self) -> None:
        result = materialize_quiz(_body())
        assert result.pass_threshold_pct == 80
        assert len(result.questions) == 1
        q = result.questions[0]
        assert q.question_text == "Who attests to internal controls under §404?"
        assert q.question_type is QuestionType.SINGLE_SELECT
        assert q.display_order == 0
        assert q.weight == 1.0
        assert [o.option_text for o in q.options] == ["Management", "Auditors", "The SEC"]
        assert [o.is_correct for o in q.options] == [True, False, False]
        assert [o.display_order for o in q.options] == [0, 1, 2]

    def test_marks_correct_option_by_answer_index(self) -> None:
        result = materialize_quiz(
            _body(questions=[{"prompt": "p", "options": ["a", "b", "c"], "answer_index": 2}])
        )
        assert [o.is_correct for o in result.questions[0].options] == [False, False, True]

    def test_preserves_question_order(self) -> None:
        result = materialize_quiz(
            _body(
                questions=[
                    {"prompt": "first", "options": ["a", "b"], "answer_index": 0},
                    {"prompt": "second", "options": ["a", "b"], "answer_index": 1},
                ]
            )
        )
        assert [q.display_order for q in result.questions] == [0, 1]
        assert [q.question_text for q in result.questions] == ["first", "second"]

    def test_infers_true_false_type(self) -> None:
        result = materialize_quiz(
            _body(questions=[{"prompt": "p", "options": ["True", "False"], "answer_index": 0}])
        )
        assert result.questions[0].question_type is QuestionType.TRUE_FALSE

    def test_two_non_boolean_options_stay_single_select(self) -> None:
        result = materialize_quiz(
            _body(questions=[{"prompt": "p", "options": ["Yes", "No"], "answer_index": 0}])
        )
        assert result.questions[0].question_type is QuestionType.SINGLE_SELECT

    def test_threshold_absent_is_none(self) -> None:
        body = _body()
        del body["quiz"]["pass_threshold_pct"]
        assert materialize_quiz(body).pass_threshold_pct is None


class TestRejection:
    def test_no_quiz(self) -> None:
        with pytest.raises(ValidationError):
            materialize_quiz({"modules": []})

    def test_empty_questions(self) -> None:
        with pytest.raises(ValidationError):
            materialize_quiz(_body(questions=[]))

    def test_questions_not_a_list(self) -> None:
        with pytest.raises(ValidationError):
            materialize_quiz(_body(questions={"prompt": "p"}))

    def test_question_not_an_object(self) -> None:
        with pytest.raises(ValidationError):
            materialize_quiz(_body(questions=[1]))

    def test_missing_prompt(self) -> None:
        with pytest.raises(ValidationError):
            materialize_quiz(_body(questions=[{"options": ["a", "b"], "answer_index": 0}]))

    def test_blank_prompt(self) -> None:
        with pytest.raises(ValidationError):
            materialize_quiz(
                _body(questions=[{"prompt": "  ", "options": ["a", "b"], "answer_index": 0}])
            )

    def test_too_few_options(self) -> None:
        with pytest.raises(ValidationError):
            materialize_quiz(_body(questions=[{"prompt": "p", "options": ["a"], "answer_index": 0}]))

    def test_blank_option(self) -> None:
        with pytest.raises(ValidationError):
            materialize_quiz(
                _body(questions=[{"prompt": "p", "options": ["a", ""], "answer_index": 0}])
            )

    def test_missing_answer_index(self) -> None:
        with pytest.raises(ValidationError):
            materialize_quiz(_body(questions=[{"prompt": "p", "options": ["a", "b"]}]))

    def test_answer_index_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            materialize_quiz(
                _body(questions=[{"prompt": "p", "options": ["a", "b"], "answer_index": 2}])
            )

    def test_answer_index_bool_rejected(self) -> None:
        with pytest.raises(ValidationError):
            materialize_quiz(
                _body(questions=[{"prompt": "p", "options": ["a", "b"], "answer_index": True}])
            )
