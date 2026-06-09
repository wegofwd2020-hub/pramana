"""In-process quiz generation (ADR-013) — Pramana drafts assessment items itself.

The make-or-derive split mirrors :mod:`pramana.services.consumer_library`:

* :func:`generate_quiz_draft_fields` is the **make** step — it drives the injected
  ``wegofwd_llm.Provider`` through the validate→repair conformance loop and
  projects the result onto :class:`~pramana.domain.content_generation.
  GeneratedDraftFields`. No database; fully unit-testable with a fake provider.
* :func:`create_quiz_draft` is the thin **transactional shell** — resolve the
  clause text from the definitions library, generate, persist a ``DRAFT``
  :class:`~pramana.db.models.content.ContentDraft`, and append the audit entry.
  The caller owns the transaction.

The drafted content is a *drafting aid only* (ADR-013 D4): it lands as ``DRAFT``
with the triggering user recorded as the generator, and is **never assignable**
until a different human approves it through
:mod:`pramana.domain.content_approval`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from wegofwd_llm import LLMRequest, Provider, generate_validated, provenance

from pramana.db.models.content import ContentDraft
from pramana.db.models.course import Course
from pramana.domain.content_generation import (
    GeneratedDraftFields,
    build_quiz_prompt,
    quiz_to_draft_fields,
    validate_quiz,
)
from pramana.domain.enums import ContentEvent
from pramana.exceptions import NotFoundError
from pramana.services import definitions_library
from pramana.services.audit import append_audit

_DEFAULT_QUESTION_COUNT = 5
_DEFAULT_PASS_THRESHOLD_PCT = 80


def generate_quiz_draft_fields(
    provider: Provider,
    *,
    framework: str,
    clause: str,
    clause_title: str,
    clause_text: str,
    citation_ref: str,
    tenant_id: uuid.UUID,
    course_id: uuid.UUID,
    title: str,
    generated_by_user_id: uuid.UUID,
    now: datetime,
    n_questions: int = _DEFAULT_QUESTION_COUNT,
    pass_threshold_pct: int = _DEFAULT_PASS_THRESHOLD_PCT,
    max_tokens: int = 4096,
) -> GeneratedDraftFields:
    """Generate + validate a quiz and project it onto draft fields (no I/O on the
    database). The provider call is schema-guarded by the conformance loop, so a
    returned value is always a structurally valid quiz.

    Raises:
        wegofwd_llm.LLMSchemaError: The provider could not produce a schema-valid
            quiz within the repair budget.
        wegofwd_llm.LLMError: An auth / rate-limit / transport failure (key-free).
    """
    req = LLMRequest(
        prompt=build_quiz_prompt(
            framework=framework,
            clause_title=clause_title,
            clause_text=clause_text,
            citation_ref=citation_ref,
            n_questions=n_questions,
            pass_threshold_pct=pass_threshold_pct,
        ),
        max_tokens=max_tokens,
        response_format="json",
    )
    result = generate_validated(provider, req, validate_quiz)
    return quiz_to_draft_fields(
        result.parsed,
        tenant_id=tenant_id,
        course_id=course_id,
        title=title,
        framework=framework,
        clause=clause,
        citation_ref=citation_ref,
        provider_id=provider.provider_id,
        model=provider.model,
        generated_by_user_id=generated_by_user_id,
        now=now,
    )


async def create_quiz_draft(
    session: AsyncSession,
    *,
    provider: Provider,
    tenant_id: uuid.UUID,
    course_id: uuid.UUID,
    framework: str,
    clause: str,
    generated_by_user_id: uuid.UUID,
    definitions_root: str,
    now: datetime,
    title: str | None = None,
    n_questions: int = _DEFAULT_QUESTION_COUNT,
    pass_threshold_pct: int = _DEFAULT_PASS_THRESHOLD_PCT,
    max_tokens: int = 4096,
) -> ContentDraft:
    """Draft a quiz for ``course_id`` from one framework clause and persist it as
    a ``DRAFT`` content draft (never assignable until approved).

    Resolves the clause against the definitions library first — *no definition, no
    generation* (mirrors the Package Request's AC4). The caller owns the
    transaction (commit/rollback).

    Raises:
        NotFoundError: The framework/clause does not resolve, or ``course_id`` is
            not in this tenant.
        wegofwd_llm.LLMError: Generation failed (schema or transport) — key-free.
    """
    root = Path(definitions_root)
    clauses = definitions_library.list_clauses(root, framework)
    info = next((c for c in clauses if c.clause == clause), None)
    if info is None:
        raise NotFoundError(
            "clause not found in definitions library",
            context={"framework": framework, "clause": clause},
        )
    text = definitions_library.clause_text(root, framework=framework, clause=clause, ref=info.ref)

    course = (
        await session.execute(
            select(Course.id).where(Course.id == course_id, Course.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if course is None:
        raise NotFoundError(
            "course not found in tenant",
            context={"course_id": str(course_id), "tenant_id": str(tenant_id)},
        )

    fields = generate_quiz_draft_fields(
        provider,
        framework=framework,
        clause=clause,
        clause_title=info.title,
        clause_text=text,
        citation_ref=info.ref,
        tenant_id=tenant_id,
        course_id=course_id,
        title=title or f"{framework.upper()} — {info.title} — quiz",
        generated_by_user_id=generated_by_user_id,
        now=now,
        n_questions=n_questions,
        pass_threshold_pct=pass_threshold_pct,
        max_tokens=max_tokens,
    )

    draft = ContentDraft(**fields.as_model_kwargs())
    session.add(draft)
    await session.flush()  # assign draft.id for the audit entry

    await append_audit(
        session,
        tenant_id=tenant_id,
        entity_type="content_draft",
        entity_id=str(draft.id),
        event_type=f"content_draft.{ContentEvent.GENERATE.value}",
        payload={
            "framework": framework,
            "clause": clause,
            "citation_ref": info.ref,
            "generated_by_user_id": str(generated_by_user_id),
            # The shared cross-product provenance stamp (ADR-012 D6).
            "provenance": provenance(provider.provider_id, provider.model),
        },
        occurred_at=now,
        actor_user_id=generated_by_user_id,
    )
    return draft
