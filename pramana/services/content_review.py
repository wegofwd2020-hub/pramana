"""Content-draft review & approval service — the human gate.

Thin transactional orchestration over the pure
:mod:`pramana.domain.content_approval` state machine: load a draft, apply a
transition, persist the new state + evidence, and append an audit entry. This is
the service behind the ``/content-drafts`` review queue (US-PLATFORM-0004) and
every framework's ``*-0005`` approval story.

The decision *rules* (which transitions are legal, separation of duties, freezing
approval evidence) live in the domain and are exhaustively unit-tested there; this
module only reads/writes the ORM around them and emits audit events.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.content import ContentDraft
from pramana.db.models.course import AnswerOption, Course, CourseVersion, Question
from pramana.domain import content_approval as ca
from pramana.domain.consumable_package import canonical_json, compute_content_hash
from pramana.domain.enums import ContentDraftStatus, ContentEvent, ContentRequestStatus
from pramana.domain.publication import QuestionSpec, materialize_quiz
from pramana.exceptions import InvalidStateTransitionError, NotFoundError
from pramana.services import content_requests
from pramana.services.audit import append_audit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _snapshot(draft: ContentDraft) -> ca.ContentDraftSnapshot:
    """Project an ORM draft onto the immutable domain snapshot."""
    return ca.ContentDraftSnapshot(
        status=ContentDraftStatus(draft.status),
        has_content=bool(draft.body),
        generated_by_user_id=draft.generated_by_user_id,
        approved_by_user_id=draft.approved_by_user_id,
        approved_at=draft.approved_at,
        content_hash=draft.content_hash,
        published_course_version_id=draft.published_course_version_id,
    )


def _add_question(session: AsyncSession, course_version_id: uuid.UUID, spec: QuestionSpec) -> None:
    """Persist a :class:`QuestionSpec` and its options under a course version."""
    question_id = uuid.uuid4()
    session.add(
        Question(
            id=question_id,
            course_version_id=course_version_id,
            question_text=spec.question_text,
            question_type=spec.question_type.value,
            weight=spec.weight,
            display_order=spec.display_order,
        )
    )
    for opt in spec.options:
        session.add(
            AnswerOption(
                id=uuid.uuid4(),
                question_id=question_id,
                option_text=opt.option_text,
                is_correct=opt.is_correct,
                display_order=opt.display_order,
            )
        )


async def _load(session: AsyncSession, draft_id: uuid.UUID) -> ContentDraft:
    draft = await session.get(ContentDraft, draft_id)
    if draft is None or draft.archived_at is not None:
        raise NotFoundError("content draft not found", context={"draft_id": str(draft_id)})
    return draft


async def _audit(
    session: AsyncSession,
    draft: ContentDraft,
    event: ContentEvent,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    now: datetime,
    extra: dict[str, Any] | None = None,
) -> None:
    await append_audit(
        session,
        tenant_id=tenant_id,
        entity_type="content_draft",
        entity_id=str(draft.id),
        event_type=f"content_draft.{event.value}",
        payload={"status": draft.status, **(extra or {})},
        occurred_at=now,
        actor_user_id=actor_user_id,
    )


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
async def list_drafts(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    status: ContentDraftStatus | None = None,
    framework: str | None = None,
    quarantined: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> tuple[Sequence[ContentDraft], int]:
    """Return a page of drafts for the review queue and the total count.

    ``quarantined`` returns an empty page: in the current model a package that
    fails verification is rejected at ingestion (ADR-011 §6) and never persisted,
    so there is no stored quarantined draft to list (persisting quarantined
    packages is a follow-up).
    """
    if quarantined:
        return [], 0

    conds: list[ColumnElement[bool]] = [
        ContentDraft.tenant_id == tenant_id,
        ContentDraft.archived_at.is_(None),
    ]
    if status is not None:
        conds.append(ContentDraft.status == status.value)
    if framework is not None:
        # JSONB containment: any source-citation entry names this framework.
        conds.append(ContentDraft.source_citations.contains([{"framework": framework}]))

    total = (
        await session.execute(select(func.count()).select_from(ContentDraft).where(*conds))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(ContentDraft)
                .where(*conds)
                .order_by(ContentDraft.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .scalars()
        .all()
    )
    return rows, int(total)


async def get_draft(session: AsyncSession, *, draft_id: uuid.UUID) -> ContentDraft:
    """Load a single draft (404 if missing/archived)."""
    return await _load(session, draft_id)


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------
async def submit_for_review(
    session: AsyncSession,
    *,
    draft_id: uuid.UUID,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    now: datetime,
) -> ContentDraft:
    """``RECEIVED``/``DRAFT`` → ``IN_REVIEW``."""
    draft = await _load(session, draft_id)
    new = ca.submit_for_review(_snapshot(draft))
    draft.status = new.status.value
    await _audit(
        session,
        draft,
        ContentEvent.SUBMIT_FOR_REVIEW,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        now=now,
    )
    await content_requests.advance_for_draft(
        session,
        draft_id=draft_id,
        tenant_id=tenant_id,
        status=ContentRequestStatus.IN_REVIEW,
        now=now,
    )
    return draft


async def approve_draft(
    session: AsyncSession,
    *,
    draft_id: uuid.UUID,
    tenant_id: uuid.UUID,
    approver_user_id: uuid.UUID,
    attestation_text: str,
    now: datetime,
) -> ContentDraft:
    """``IN_REVIEW`` → ``APPROVED``: freeze content + record attestation.

    Separation of duties (approver ≠ generator) is enforced by the domain.
    """
    draft = await _load(session, draft_id)
    content_hash = compute_content_hash(canonical_json(draft.body))
    new = ca.approve(
        _snapshot(draft),
        approver_user_id=approver_user_id,
        content_hash=content_hash,
        now=now,
    )
    draft.status = new.status.value
    draft.approved_by_user_id = new.approved_by_user_id
    draft.approved_at = new.approved_at
    draft.content_hash = new.content_hash
    draft.attestation_text = attestation_text
    await _audit(
        session,
        draft,
        ContentEvent.APPROVE,
        tenant_id=tenant_id,
        actor_user_id=approver_user_id,
        now=now,
        extra={"content_hash": content_hash},
    )
    return draft


async def request_changes(
    session: AsyncSession,
    *,
    draft_id: uuid.UUID,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    notes: str,
    now: datetime,
) -> ContentDraft:
    """``IN_REVIEW`` → ``DRAFT`` with reviewer notes."""
    draft = await _load(session, draft_id)
    new = ca.request_changes(_snapshot(draft))
    draft.status = new.status.value
    draft.review_notes = notes
    await _audit(
        session,
        draft,
        ContentEvent.REQUEST_CHANGES,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        now=now,
    )
    return draft


async def reject_draft(
    session: AsyncSession,
    *,
    draft_id: uuid.UUID,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    notes: str,
    now: datetime,
) -> ContentDraft:
    """``IN_REVIEW`` → ``REJECTED`` (terminal) with reviewer notes."""
    draft = await _load(session, draft_id)
    new = ca.reject(_snapshot(draft))
    draft.status = new.status.value
    draft.review_notes = notes
    await _audit(
        session,
        draft,
        ContentEvent.REJECT,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        now=now,
    )
    return draft


async def publish_draft(
    session: AsyncSession,
    *,
    draft_id: uuid.UUID,
    tenant_id: uuid.UUID,
    publisher_user_id: uuid.UUID,
    now: datetime,
    is_material_change: bool = False,
) -> CourseVersion:
    """``APPROVED`` → ``PUBLISHED``: materialise an immutable course version.

    Creates the next :class:`CourseVersion` for the draft's course, destructures
    the draft's quiz into the version's ``Question`` / ``AnswerOption`` rows
    (ADR-011 §9.2) so the published content is assignable and gradeable, makes it
    the active version (deactivating the previous one), and links the draft to
    it. The quiz's own ``pass_threshold_pct`` is propagated onto the course.

    Raises:
        ValidationError: The draft's quiz body is malformed — no question is
            materialised and nothing is written.
    """
    draft = await _load(session, draft_id)
    course_version_id = uuid.uuid4()
    # Validates APPROVED *before* any DB write (raises otherwise).
    new = ca.publish(_snapshot(draft), course_version_id=course_version_id)
    # Validate + project the quiz before any mutation, same as the state check.
    quiz = materialize_quiz(draft.body)

    next_version = (
        (
            await session.execute(
                select(func.max(CourseVersion.version_number)).where(
                    CourseVersion.course_id == draft.course_id
                )
            )
        ).scalar_one_or_none()
        or 0
    ) + 1
    await session.execute(
        update(CourseVersion)
        .where(
            CourseVersion.course_id == draft.course_id,
            CourseVersion.is_active.is_(True),
        )
        .values(is_active=False)
    )
    course_version = CourseVersion(
        id=course_version_id,
        course_id=draft.course_id,
        version_number=next_version,
        published_by_user_id=publisher_user_id,
        is_active=True,
        is_material_change=is_material_change,
    )
    session.add(course_version)
    for spec in quiz.questions:
        _add_question(session, course_version_id, spec)

    # Propagate the quiz's declared threshold onto the (mutable) course metadata
    # so the published quiz governs its own grading.
    if quiz.pass_threshold_pct is not None:
        await session.execute(
            update(Course)
            .where(Course.id == draft.course_id)
            .values(pass_threshold_pct=quiz.pass_threshold_pct)
        )

    draft.status = new.status.value
    draft.published_course_version_id = course_version_id
    await _audit(
        session,
        draft,
        ContentEvent.PUBLISH,
        tenant_id=tenant_id,
        actor_user_id=publisher_user_id,
        now=now,
        extra={"course_version_id": str(course_version_id), "version_number": next_version},
    )
    await content_requests.advance_for_draft(
        session,
        draft_id=draft_id,
        tenant_id=tenant_id,
        status=ContentRequestStatus.PUBLISHED,
        now=now,
    )
    return course_version


def parse_status(value: str) -> ContentDraftStatus:
    """Parse a status query value, raising a domain error on an unknown value."""
    try:
        return ContentDraftStatus(value)
    except ValueError as exc:
        raise InvalidStateTransitionError(
            f"unknown content-draft status {value!r}",
            context={"value": value},
        ) from exc
