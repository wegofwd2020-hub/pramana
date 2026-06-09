"""In-process generation of quiz items from a clause (ADR-013, first slice).

Pure domain: the output schema + validator, the compliance-register prompt, and
the projection onto draft fields. No database and no network — the LLM call is
driven by the service layer through an injected ``wegofwd_llm.Provider``, exactly
as the ingestion path injects a ``SignatureVerifier``. That keeps the real logic
(prompt, schema conformance, mapping) exhaustively unit-testable with a fake
provider, and the async service a thin transactional shell.

ADR-013 lets Pramana draft a *defined, text-first* class of compliance content
in-process; this covers **quiz / assessment items drafted against a framework
clause**. The output is **never assignable**: it is projected onto a ``DRAFT``
:class:`~pramana.db.models.content.ContentDraft` and must pass the human-approval
gate (:mod:`pramana.domain.content_approval`). The triggering user is recorded as
the generator, so separation of duties is enforced at approval (the approver may
not be that user).

The generated ``quiz`` body is shaped to the publish contract
(:func:`pramana.domain.publication.materialize_quiz`): ``{pass_threshold_pct,
questions: [{prompt, options, answer_index}]}``. Each question additionally
carries a ``citation`` (the clause it tests) — Pramana's "every claim cited" rule
(ADR-011 §4); ``materialize_quiz`` ignores the extra field.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as SchemaError

from pramana.domain.enums import ContentDraftStatus
from pramana.exceptions import ValidationError

# Version of THIS generator's prompt + output contract. Bump on a material change
# so a draft's provenance records which generator produced it (drift detection).
QUIZ_PROMPT_VERSION = "pramana-quiz-2026-06"

# gen_engine stamped on in-house drafts (vs "mentible" on an ingested package).
GEN_ENGINE = "pramana"

_MIN_OPTIONS = 2
_DEFAULT_QUESTION_COUNT = 5


# ---------------------------------------------------------------------------
# Output schema (validates the model's JSON before it becomes a draft)
# ---------------------------------------------------------------------------
class GeneratedQuestion(BaseModel):
    """One drafted question, in the publish-contract shape plus a ``citation``."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    options: list[str] = Field(min_length=_MIN_OPTIONS)
    answer_index: int = Field(ge=0)
    citation: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> GeneratedQuestion:
        if any(not o.strip() for o in self.options):
            raise ValueError("every option must be a non-empty string")
        if self.answer_index >= len(self.options):
            raise ValueError(
                f"answer_index {self.answer_index} is out of range for {len(self.options)} options"
            )
        return self


class GeneratedQuiz(BaseModel):
    """The drafted quiz — a non-empty list of questions and a pass threshold."""

    model_config = ConfigDict(extra="forbid")

    pass_threshold_pct: int = Field(ge=0, le=100)
    questions: list[GeneratedQuestion] = Field(min_length=1)


def validate_quiz(text: str) -> GeneratedQuiz:
    """Parse + validate a model response into a :class:`GeneratedQuiz`.

    Suitable as the ``validate`` callable for
    :func:`wegofwd_llm.generate_validated`: it returns the parsed quiz on success
    and **raises on invalid**, so the conformance loop feeds the error back to the
    model for repair. Tolerates a `````json`` fence the model may add.

    Raises:
        ValidationError: The response is not valid JSON, or fails the schema.
    """
    payload = _strip_fences(text)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "model response is not valid JSON", context={"error": str(exc)}
        ) from exc
    try:
        return GeneratedQuiz.model_validate(data)
    except SchemaError as exc:
        raise ValidationError(
            "quiz failed schema validation",
            context={"errors": exc.errors(include_url=False)},
        ) from exc


def _strip_fences(text: str) -> str:
    """Drop a leading/trailing Markdown code fence if the model wrapped the JSON."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1] if "\n" in stripped else ""
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[: -len("```")]
    return stripped.strip()


# ---------------------------------------------------------------------------
# Prompt (compliance register — Pramana-owned, ADR-013 §7)
# ---------------------------------------------------------------------------
def build_quiz_prompt(
    *,
    framework: str,
    clause_title: str,
    clause_text: str,
    citation_ref: str,
    n_questions: int = _DEFAULT_QUESTION_COUNT,
    pass_threshold_pct: int = 80,
) -> str:
    """Construct the generation prompt for quiz items on one clause.

    The clause's own prose is the *only* permitted source — the model must ground
    every question in it rather than its parametric memory, because the output is
    compliance evidence. Each question must cite ``citation_ref``.
    """
    return (
        "You are drafting assessment questions for mandatory compliance training. "
        "Accuracy is non-negotiable: every question and its correct answer MUST be "
        "supported by the clause text provided below. Do NOT use outside knowledge, "
        "do NOT invent requirements, and do NOT cover material the clause does not state.\n\n"
        f"Framework: {framework}\n"
        f"Clause: {clause_title}\n"
        f"Citation ref (use verbatim for every question's `citation`): {citation_ref}\n\n"
        "--- CLAUSE TEXT (the only source of truth) ---\n"
        f"{clause_text}\n"
        "--- END CLAUSE TEXT ---\n\n"
        f"Write exactly {n_questions} single-select multiple-choice questions that test "
        "understanding of this clause. Each question has 3-4 plausible options with exactly "
        "one correct answer. Keep stems clear and unambiguous.\n\n"
        "Return ONLY a JSON object (no prose, no Markdown fences) of the form:\n"
        "{\n"
        f'  "pass_threshold_pct": {pass_threshold_pct},\n'
        '  "questions": [\n'
        '    {"prompt": "<question>", "options": ["<a>", "<b>", "<c>"], '
        '"answer_index": <0-based index of the correct option>, '
        f'"citation": "{citation_ref}"}}\n'
        "  ]\n"
        "}"
    )


# ---------------------------------------------------------------------------
# Projection onto draft fields (mirrors domain.ingestion.IngestedDraftFields)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class GeneratedDraftFields:
    """Field set for a ``DRAFT`` content draft produced by in-process generation.

    Mirrors the writable columns of :class:`~pramana.db.models.content.
    ContentDraft` so the service can do ``ContentDraft(**fields.as_model_kwargs())``.
    Unlike an ingested package, ``generated_by_user_id`` IS set — the in-house
    generator is a Pramana user, and recording them is what makes the
    separation-of-duties check at approval meaningful.
    """

    tenant_id: uuid.UUID
    course_id: uuid.UUID
    title: str
    body: dict[str, Any]
    source_citations: list[dict[str, Any]]
    gen_model: str
    gen_provider: str
    gen_prompt_version: str
    generated_at: datetime
    generated_by_user_id: uuid.UUID
    status: ContentDraftStatus = ContentDraftStatus.DRAFT
    gen_engine: str = GEN_ENGINE

    def as_model_kwargs(self) -> dict[str, Any]:
        """Return kwargs for constructing a ``ContentDraft`` row (status as its
        string value; ``generated_by_user_id`` retained for separation of duties)."""
        return {
            "tenant_id": self.tenant_id,
            "course_id": self.course_id,
            "status": self.status.value,
            "title": self.title,
            "body": self.body,
            "source_citations": self.source_citations,
            "gen_engine": self.gen_engine,
            "gen_model": self.gen_model,
            "gen_provider": self.gen_provider,
            "gen_prompt_version": self.gen_prompt_version,
            "generated_at": self.generated_at,
            "generated_by_user_id": self.generated_by_user_id,
        }


def quiz_to_draft_fields(
    quiz: GeneratedQuiz,
    *,
    tenant_id: uuid.UUID,
    course_id: uuid.UUID,
    title: str,
    framework: str,
    clause: str,
    citation_ref: str,
    provider_id: str,
    model: str,
    generated_by_user_id: uuid.UUID,
    now: datetime,
) -> GeneratedDraftFields:
    """Project a validated quiz onto draft fields for the given course.

    The quiz is stored verbatim on ``body.quiz`` (publishable via
    :func:`pramana.domain.publication.materialize_quiz`); the clause it was drafted
    from becomes the draft's single ``source_citations`` entry so a reviewer can
    trace it back to the regulation.
    """
    return GeneratedDraftFields(
        tenant_id=tenant_id,
        course_id=course_id,
        title=title,
        body={"quiz": quiz.model_dump()},
        source_citations=[{"framework": framework, "clause": clause, "ref": citation_ref}],
        gen_model=model,
        gen_provider=provider_id,
        gen_prompt_version=QUIZ_PROMPT_VERSION,
        generated_at=now,
        generated_by_user_id=generated_by_user_id,
    )
