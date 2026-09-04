"""Pydantic request/response schemas for the HTTP API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

if TYPE_CHECKING:
    from pramana.db.models.assignment import Assignment, Attempt, Certificate
    from pramana.db.models.audit import AuditLog
    from pramana.db.models.content import ContentDraft
    from pramana.db.models.content_request import ContentRequest
    from pramana.db.models.course import CourseVersion
    from pramana.services.definitions_library import ClauseInfo, FrameworkInfo


class IngestPackageRequest(BaseModel):
    """Body of a consumable-package push (Mentible ADR-011 §6).

    ``tenant_id`` and ``course_id`` say *where* the package lands in Pramana
    (Mentible does not know Pramana's ids — they are supplied by the operator /
    drop configuration). ``manifest`` is the raw ADR-011 manifest, validated and
    integrity-checked downstream in the domain.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: uuid.UUID
    course_id: uuid.UUID
    manifest: dict[str, Any] = Field(
        description="The full Consumable Package manifest (ADR-011 §4)."
    )


class IngestPackageResponse(BaseModel):
    """Result of a successful ingestion: an untrusted ``RECEIVED`` draft."""

    draft_id: uuid.UUID
    status: str
    package_id: uuid.UUID
    package_version: int


# ---------------------------------------------------------------------------
# Content-draft review queue
# ---------------------------------------------------------------------------
def _framework_of(draft: ContentDraft) -> str | None:
    citations = draft.source_citations or []
    if citations and isinstance(citations[0], dict):
        return citations[0].get("framework")
    return None


class ContentDraftOut(BaseModel):
    """A content draft as shown in the review queue."""

    draft_id: uuid.UUID
    course_id: uuid.UUID | None
    status: str
    title: str
    framework: str | None
    package_id: uuid.UUID | None
    package_version: int | None
    verified: bool = Field(
        description="Signature + content_hash verified on ingest (stored drafts are verified)."
    )
    created_at: datetime | None

    @classmethod
    def of(cls, draft: ContentDraft) -> ContentDraftOut:
        return cls(
            draft_id=draft.id,
            course_id=draft.course_id,
            status=draft.status,
            title=draft.title,
            framework=_framework_of(draft),
            package_id=draft.package_id,
            package_version=draft.package_version,
            # Only verified packages are persisted (ADR-011 §6), so a stored draft
            # is verified iff it came from a package at all.
            verified=draft.package_id is not None,
            created_at=getattr(draft, "created_at", None),
        )


class ContentDraftDetail(ContentDraftOut):
    """Full review payload: content body, provenance, citations, verification."""

    provenance: dict[str, Any] | None
    source_citations: list[Any] | None
    modules: list[Any] | None
    quiz: dict[str, Any] | None
    artifacts: list[Any] | None
    assets: list[Any] | None
    review_notes: str | None

    @classmethod
    def of(cls, draft: ContentDraft) -> ContentDraftDetail:
        body = draft.body or {}
        provenance = {
            "engine": draft.gen_engine,
            "model": draft.gen_model,
            "provider": draft.gen_provider,
            "prompt_version": draft.gen_prompt_version,
            "generated_at": draft.generated_at.isoformat() if draft.generated_at else None,
        }
        return cls(
            draft_id=draft.id,
            course_id=draft.course_id,
            status=draft.status,
            title=draft.title,
            framework=_framework_of(draft),
            package_id=draft.package_id,
            package_version=draft.package_version,
            verified=draft.package_id is not None,
            created_at=getattr(draft, "created_at", None),
            provenance=provenance,
            source_citations=draft.source_citations,
            modules=body.get("modules"),
            quiz=body.get("quiz"),
            artifacts=body.get("artifacts"),
            assets=body.get("assets"),
            review_notes=draft.review_notes,
        )


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int


class ContentDraftPage(BaseModel):
    items: list[ContentDraftOut]
    pagination: Pagination


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attestation_text: str = Field(
        min_length=1,
        description="The approver's accuracy attestation, captured as audit evidence.",
    )


class ReviewNotesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str = Field(min_length=1)


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_material_change: bool = False


# ---------------------------------------------------------------------------
# Frameworks (the "law" picker — definitions-library feed)
# ---------------------------------------------------------------------------
class FrameworkOut(BaseModel):
    """A framework in the definitions library."""

    code: str
    name: str
    doc: str

    @classmethod
    def of(cls, fw: FrameworkInfo) -> FrameworkOut:
        return cls(code=fw.code, name=fw.name, doc=fw.doc)


class FrameworkClauseOut(BaseModel):
    """A citable clause anchor within a framework doc."""

    clause: str
    title: str
    ref: str

    @classmethod
    def of(cls, c: ClauseInfo) -> FrameworkClauseOut:
        return cls(clause=c.clause, title=c.title, ref=c.ref)


# ---------------------------------------------------------------------------
# Content requests (Create phase — commission content → Mentible)
# ---------------------------------------------------------------------------
class ContentRequestCreate(BaseModel):
    """Body of a commissioning request (the Package Request spec, US-PLATFORM-0003).

    Top-level fields are typed; the nested ``scope``/``assessment``/``constraints``/
    ``source_definitions`` are validated authoritatively by the pure
    :mod:`pramana.domain.package_request`, so they are accepted as raw structures
    here to keep a single source of validation truth.
    """

    model_config = ConfigDict(extra="forbid")

    framework: str
    title: str
    course_id: uuid.UUID | None = None
    scope: dict[str, Any] | None = None
    source_definitions: list[dict[str, Any]] = Field(min_length=1)
    learning_objectives: list[str] | None = None
    assessment: dict[str, Any]
    constraints: dict[str, Any] | None = None
    deliverables: list[str] | None = None
    visuals: list[str] | None = None
    satisfies_stories: list[str] | None = None


class RegenerateRequest(BaseModel):
    """Body of a draft regeneration (US-PLATFORM-0005)."""

    model_config = ConfigDict(extra="forbid")

    notes: str | None = None
    parameter_overrides: dict[str, Any] | None = Field(
        default=None,
        description="Partial Package Request fields to change; unspecified reuse the original.",
    )


class ContentRequestOut(BaseModel):
    """A content request and its lifecycle status."""

    request_id: uuid.UUID
    framework: str
    title: str
    status: str
    requested_by: uuid.UUID
    course_id: uuid.UUID | None
    package_id: uuid.UUID | None
    draft_id: uuid.UUID | None
    progress_pct: int | None
    progress_eta: datetime | None
    failure_reason: str | None
    created_at: datetime | None

    @classmethod
    def of(cls, cr: ContentRequest) -> ContentRequestOut:
        return cls(
            request_id=cr.id,
            framework=cr.framework,
            title=cr.title,
            status=cr.status,
            requested_by=cr.requested_by,
            course_id=cr.course_id,
            package_id=cr.package_id,
            draft_id=cr.draft_id,
            progress_pct=cr.progress_pct,
            progress_eta=cr.progress_eta,
            failure_reason=cr.failure_reason,
            created_at=getattr(cr, "created_at", None),
        )


class ContentRequestPage(BaseModel):
    items: list[ContentRequestOut]
    pagination: Pagination


# ---------------------------------------------------------------------------
# Mentible progress webhook (inbound, machine-to-machine, HMAC-signed)
# ---------------------------------------------------------------------------
class MentibleProgressWebhook(BaseModel):
    """Body of an inbound Mentible generation-progress webhook.

    Keyed by the ``request_id`` Pramana stamped into the pushed Package Request
    (and that Mentible echoes). ``tenant_id`` scopes the lookup. ``event`` selects
    the transition: ``progress`` advances ``REQUESTED → GENERATING`` (with an
    optional ``progress_pct``/``eta``); ``failure`` moves the request to
    ``FAILED`` with an optional ``detail`` recorded as the failure reason.
    """

    model_config = ConfigDict(extra="forbid")

    request_id: uuid.UUID
    tenant_id: uuid.UUID
    event: Literal["progress", "failure"]
    progress_pct: Annotated[int, Field(ge=0, le=100)] | None = None
    eta: datetime | None = None
    detail: str | None = None


class MentibleProgressResponse(BaseModel):
    """Result of a webhook: the request's resulting status, or ``ignored``.

    ``applied`` is ``False`` when the event was a no-op (unknown request, or one
    already past the point the event describes) — always a 200 so Mentible does
    not retry a benign no-op.
    """

    applied: bool
    request_id: uuid.UUID
    status: str | None = None


# ---------------------------------------------------------------------------
# Learner runtime — assignments
# ---------------------------------------------------------------------------
class AssignmentCreate(BaseModel):
    """Body to assign a course's active version to a user (privileged)."""

    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    course_id: uuid.UUID
    due_at: datetime | None = None


class AssignmentOut(BaseModel):
    """An assignment and its lifecycle state."""

    assignment_id: uuid.UUID
    user_id: uuid.UUID
    course_id: uuid.UUID
    course_version_id: uuid.UUID
    status: str
    attempts_used: int
    max_attempts: int
    remaining_attempts: int
    watched_pct: int
    due_at: datetime | None
    terminal_at: datetime | None
    cooldown_until: datetime | None
    assigned_at: datetime | None

    @classmethod
    def of(cls, a: Assignment) -> AssignmentOut:
        return cls(
            assignment_id=a.id,
            user_id=a.user_id,
            course_id=a.course_id,
            course_version_id=a.course_version_id,
            status=a.status,
            attempts_used=a.attempts_used,
            max_attempts=a.max_attempts,
            remaining_attempts=max(0, a.max_attempts - a.attempts_used),
            watched_pct=a.watched_pct,
            due_at=a.due_at,
            terminal_at=a.terminal_at,
            cooldown_until=a.cooldown_until,
            assigned_at=getattr(a, "assigned_at", None),
        )


class AssignmentPage(BaseModel):
    items: list[AssignmentOut]
    pagination: Pagination


class AttemptOut(BaseModel):
    """A quiz attempt."""

    attempt_id: uuid.UUID
    assignment_id: uuid.UUID
    attempt_number: int
    outcome: str
    score_pct: float | None
    started_at: datetime | None
    submitted_at: datetime | None

    @classmethod
    def of(cls, at: Attempt) -> AttemptOut:
        return cls(
            attempt_id=at.id,
            assignment_id=at.assignment_id,
            attempt_number=at.attempt_number,
            outcome=at.outcome,
            score_pct=at.score_pct,
            started_at=getattr(at, "started_at", None),
            submitted_at=at.submitted_at,
        )


class SubmittedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: uuid.UUID
    selected_option_ids: list[uuid.UUID] = Field(default_factory=list)


class AttestationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_version: str = Field(min_length=1)
    accepted: bool


class AttemptSubmitRequest(BaseModel):
    """Body to submit the in-progress attempt: per-question answers + attestation."""

    model_config = ConfigDict(extra="forbid")
    answers: list[SubmittedAnswer] = Field(default_factory=list)
    attestation: AttestationInput


class SubmissionResultOut(BaseModel):
    """Outcome of submitting an attempt."""

    assignment_id: uuid.UUID
    status: str
    outcome: str
    score_pct: float
    retry_available: bool
    remaining_attempts: int
    certificate_id: uuid.UUID | None


# ---------------------------------------------------------------------------
# Learner runtime — player / watch-gate
# ---------------------------------------------------------------------------
class PlayerManifestOut(BaseModel):
    assignment_id: uuid.UUID
    course_version_id: uuid.UUID
    status: str
    video_url: str | None
    min_watch_pct: int
    watched_pct: int
    quiz_unlocked: bool


class ProgressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    watched_pct: Annotated[int, Field(ge=0, le=100)]


class WatchProgressOut(BaseModel):
    assignment_id: uuid.UUID
    watched_pct: int
    min_watch_pct: int
    quiz_unlocked: bool


# ---------------------------------------------------------------------------
# Learner runtime — certificates
# ---------------------------------------------------------------------------
class CertificateOut(BaseModel):
    certificate_id: uuid.UUID
    user_id: uuid.UUID
    course_id: uuid.UUID
    course_version_id: uuid.UUID
    assignment_id: uuid.UUID
    issued_at: datetime | None
    expires_at: datetime
    verification_code: str
    #: Always true: the PDF is rendered on demand from the certificate's pinned
    #: facts, so there is no state in which one is unavailable. Kept so existing
    #: clients do not break, but it no longer reflects stored-file presence.
    pdf_available: bool = True

    @classmethod
    def of(cls, c: Certificate) -> CertificateOut:
        return cls(
            certificate_id=c.id,
            user_id=c.user_id,
            course_id=c.course_id,
            course_version_id=c.course_version_id,
            assignment_id=c.assignment_id,
            issued_at=getattr(c, "issued_at", None),
            expires_at=c.expires_at,
            verification_code=c.verification_code,
            pdf_available=True,
        )


class CertificatePage(BaseModel):
    items: list[CertificateOut]
    pagination: Pagination


# ---------------------------------------------------------------------------
# Role administration
# ---------------------------------------------------------------------------
class RoleGrantRequest(BaseModel):
    """The role to grant. Validated against the fixed set in the service."""

    model_config = ConfigDict(extra="forbid")
    role: str = Field(min_length=1, description="One of the fixed role names.")


class UserRolesOut(BaseModel):
    """A user's current roles, after any change."""

    user_id: uuid.UUID
    roles: list[str]


class CertificateVerification(BaseModel):
    """Public verification result — minimal, no PII beyond the pinned refs."""

    valid: bool
    certificate_id: uuid.UUID | None = None
    course_id: uuid.UUID | None = None
    course_version_id: uuid.UUID | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    expired: bool = False


# ---------------------------------------------------------------------------
# Audit — verification, search, export
# ---------------------------------------------------------------------------
class AuditLogOut(BaseModel):
    """One audit-log entry, including the chain hashes (re-verifiable)."""

    audit_id: int
    tenant_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    entity_type: str
    entity_id: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    prev_audit_hash: str | None
    audit_hash: str

    @classmethod
    def of(cls, r: AuditLog) -> AuditLogOut:
        return cls(
            audit_id=r.audit_id,
            tenant_id=r.tenant_id,
            actor_user_id=r.actor_user_id,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            event_type=r.event_type,
            payload=r.payload,
            occurred_at=r.occurred_at,
            prev_audit_hash=r.prev_audit_hash,
            audit_hash=r.audit_hash,
        )


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    pagination: Pagination


class ChainBreakOut(BaseModel):
    audit_id: int
    reason: str
    expected: str | None
    found: str | None


class ChainVerificationOut(BaseModel):
    """Result of verifying the audit chain."""

    ok: bool
    total: int
    first_break: ChainBreakOut | None = None


# ---------------------------------------------------------------------------
# Evidence binder (per-user auditor export)
# ---------------------------------------------------------------------------
class EvidenceAttemptOut(BaseModel):
    attempt_number: int
    outcome: str
    score_pct: float | None
    submitted_at: datetime | None


class AssignmentEvidenceOut(BaseModel):
    assignment_id: uuid.UUID
    course_id: uuid.UUID
    course_title: str
    course_version_id: uuid.UUID
    course_version_number: int
    status: str
    assigned_at: datetime | None
    terminal_at: datetime | None
    attempts: list[EvidenceAttemptOut]
    certificate: CertificateOut | None


class EvidenceBinderOut(BaseModel):
    user_id: uuid.UUID
    user_email: str
    items: list[AssignmentEvidenceOut]


class CourseVersionOut(BaseModel):
    """Minimal view of a published course version."""

    version_id: uuid.UUID
    course_id: uuid.UUID
    version_number: int
    is_active: bool

    @classmethod
    def of(cls, cv: CourseVersion) -> CourseVersionOut:
        return cls(
            version_id=cv.id,
            course_id=cv.course_id,
            version_number=cv.version_number,
            is_active=cv.is_active,
        )


# ---------------------------------------------------------------------------
# Consumer admin — create consumer account + grant/revoke package access
# ---------------------------------------------------------------------------
class ConsumerGrantIn(BaseModel):
    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    package_id: uuid.UUID


class EntitlementOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    package_id: uuid.UUID
    status: str
    model_config = ConfigDict(from_attributes=True)


class ConsumerGrantOut(BaseModel):
    user_id: uuid.UUID
    entitlement: EntitlementOut


# ---------------------------------------------------------------------------
# Consumer catalog — my packages, lesson list, views, quiz
# ---------------------------------------------------------------------------
class MyPackageOut(BaseModel):
    package_id: uuid.UUID = Field(validation_alias="id")
    slug: str
    title: str
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class LessonListItemOut(BaseModel):
    course_id: uuid.UUID
    title: str
    display_order: int
    view_count: int
    completion_count: int
    best_score_pct: float | None


class StartViewIn(BaseModel):
    media_kind: str = "video"


class PlaySessionOut(BaseModel):
    play_session_id: uuid.UUID
    course_version_id: uuid.UUID
    media_url: str | None
    media_kind: str
    min_watch_pct: int


class EndViewIn(BaseModel):
    duration_seconds: int = Field(ge=0)
    max_watched_pct: int = Field(ge=0, le=100)


class QuizOptionOut(BaseModel):
    option_id: uuid.UUID
    option_text: str


class QuizQuestionOut(BaseModel):
    question_id: uuid.UUID
    question_text: str
    question_type: str
    options: list[QuizOptionOut]


class QuizFormOut(BaseModel):
    attempt_id: uuid.UUID
    course_version_id: uuid.UUID
    questions: list[QuizQuestionOut]


class SubmitQuizIn(BaseModel):
    answers: dict[uuid.UUID, list[uuid.UUID]]


class QuizResultOut(BaseModel):
    attempt_id: uuid.UUID
    score_pct: float
    is_all_correct: bool
    correct_count: int
    question_count: int
