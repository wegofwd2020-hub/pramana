"""Pydantic request/response schemas for the HTTP API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
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
            created_at=getattr(cr, "created_at", None),
        )


class ContentRequestPage(BaseModel):
    items: list[ContentRequestOut]
    pagination: Pagination


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
