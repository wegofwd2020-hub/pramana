"""Unit tests for in-process quiz generation (ADR-013), no DB, no live API.

The LLM is a fake :class:`wegofwd_llm.Provider` returning canned text, so the
whole make-step — prompt → conformance loop → projection onto draft fields — is
exercised deterministically. The async DB shell (:func:`create_quiz_draft`) is
left for the integration-test phase, consistent with the repo's other services.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from wegofwd_llm import Capabilities, LLMRequest, LLMResponse, LLMSchemaError, Provider

from pramana.domain.content_generation import (
    GEN_ENGINE,
    QUIZ_PROMPT_VERSION,
    GeneratedQuiz,
    validate_quiz,
)
from pramana.domain.enums import ContentDraftStatus
from pramana.exceptions import ValidationError
from pramana.services.content_generation import generate_quiz_draft_fields

_NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)
_CITATION = "docs/frameworks/framework_sox.md#404"


def _valid_quiz_json(citation: str = _CITATION) -> str:
    return json.dumps(
        {
            "pass_threshold_pct": 80,
            "questions": [
                {
                    "prompt": "Who must assess internal controls under SOX 404?",
                    "options": ["Management", "External auditors only", "The SEC"],
                    "answer_index": 0,
                    "citation": citation,
                },
                {
                    "prompt": "SOX 404 requires controls to be documented.",
                    "options": ["True", "False"],
                    "answer_index": 0,
                    "citation": citation,
                },
            ],
        }
    )


class FakeProvider(Provider):
    """A scripted provider: returns each queued response in order."""

    provider_id = "anthropic"
    capabilities = Capabilities(tools=True)

    def __init__(self, responses: list[str], *, model: str = "claude-sonnet-4-6") -> None:
        self._responses = list(responses)
        self._model = model
        self.requests: list[LLMRequest] = []

    @property
    def model(self) -> str:
        return self._model

    def generate(self, req: LLMRequest) -> LLMResponse:
        self.requests.append(req)
        text = self._responses.pop(0)
        return LLMResponse(text=text, provider_id=self.provider_id, model=self._model)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------
def test_validate_quiz_accepts_valid_json() -> None:
    quiz = validate_quiz(_valid_quiz_json())
    assert isinstance(quiz, GeneratedQuiz)
    assert len(quiz.questions) == 2


def test_validate_quiz_strips_code_fence() -> None:
    fenced = f"```json\n{_valid_quiz_json()}\n```"
    assert len(validate_quiz(fenced).questions) == 2


def test_validate_quiz_rejects_non_json() -> None:
    with pytest.raises(ValidationError):
        validate_quiz("here is your quiz:")


def test_validate_quiz_rejects_answer_index_out_of_range() -> None:
    bad = json.dumps(
        {
            "pass_threshold_pct": 80,
            "questions": [
                {"prompt": "Q?", "options": ["a", "b"], "answer_index": 5, "citation": _CITATION}
            ],
        }
    )
    with pytest.raises(ValidationError):
        validate_quiz(bad)


def test_validate_quiz_requires_citation() -> None:
    bad = json.dumps(
        {
            "pass_threshold_pct": 80,
            "questions": [{"prompt": "Q?", "options": ["a", "b"], "answer_index": 0}],
        }
    )
    with pytest.raises(ValidationError):
        validate_quiz(bad)


# ---------------------------------------------------------------------------
# generate_quiz_draft_fields (make step)
# ---------------------------------------------------------------------------
def _generate(provider: Provider) -> object:
    return generate_quiz_draft_fields(
        provider,
        framework="sox",
        clause="404",
        clause_title="Management Assessment of Internal Controls",
        clause_text="Management must assess and report on internal controls...",
        citation_ref=_CITATION,
        tenant_id=uuid.uuid4(),
        course_id=uuid.uuid4(),
        title="SOX 404 quiz",
        generated_by_user_id=uuid.uuid4(),
        now=_NOW,
    )


def test_generate_produces_draft_fields_with_provenance() -> None:
    user_id = uuid.uuid4()
    provider = FakeProvider([_valid_quiz_json()])
    fields = generate_quiz_draft_fields(
        provider,
        framework="sox",
        clause="404",
        clause_title="Management Assessment of Internal Controls",
        clause_text="Management must assess and report on internal controls...",
        citation_ref=_CITATION,
        tenant_id=uuid.uuid4(),
        course_id=uuid.uuid4(),
        title="SOX 404 quiz",
        generated_by_user_id=user_id,
        now=_NOW,
    )

    # Lands as an un-approved DRAFT — never assignable until the gate clears.
    assert fields.status is ContentDraftStatus.DRAFT
    # Provenance is stamped: in-house engine, the provider's model/id, the version.
    assert fields.gen_engine == GEN_ENGINE
    assert fields.gen_provider == "anthropic"
    assert fields.gen_model == "claude-sonnet-4-6"
    assert fields.gen_prompt_version == QUIZ_PROMPT_VERSION
    assert fields.generated_at == _NOW
    # The triggering user is recorded — this is what arms separation-of-duties.
    assert fields.generated_by_user_id == user_id
    # Body is publish-shaped; the clause is traceable.
    assert fields.body["quiz"]["questions"][0]["answer_index"] == 0
    assert fields.source_citations == [{"framework": "sox", "clause": "404", "ref": _CITATION}]


def test_generate_passes_clause_text_into_the_prompt() -> None:
    provider = FakeProvider([_valid_quiz_json()])
    _generate(provider)
    sent = provider.requests[0].prompt
    assert "Management must assess and report on internal controls" in sent
    assert _CITATION in sent
    assert provider.requests[0].response_format == "json"


def test_generate_repairs_then_succeeds() -> None:
    # First response is junk; the conformance loop should repair and then accept.
    provider = FakeProvider(["not json at all", _valid_quiz_json()])
    fields = _generate(provider)
    assert fields.status is ContentDraftStatus.DRAFT  # type: ignore[attr-defined]
    assert len(provider.requests) == 2  # one initial + one repair


def test_generate_raises_when_never_valid() -> None:
    provider = FakeProvider(["nope", "still nope", "nope again", "and again"])
    with pytest.raises(LLMSchemaError):
        _generate(provider)


def test_as_model_kwargs_round_trips_for_orm() -> None:
    provider = FakeProvider([_valid_quiz_json()])
    fields = _generate(provider)
    kwargs = fields.as_model_kwargs()  # type: ignore[attr-defined]
    assert kwargs["status"] == ContentDraftStatus.DRAFT.value
    assert kwargs["gen_engine"] == GEN_ENGINE
    assert kwargs["generated_by_user_id"] is not None
    assert "quiz" in kwargs["body"]
