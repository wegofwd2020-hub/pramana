"""Map a verified Consumable Package to a content-draft record.

Pure domain glue between :mod:`pramana.domain.consumable_package` (the handoff
contract) and the persistence layer. Given a parsed, integrity-verified
:class:`~pramana.domain.consumable_package.ConsumablePackage`, it produces the
exact field set used to create a ``RECEIVED`` ``ContentDraft`` (Mentible
ADR-011 §9 item 2, "manifest → domain mapping").

No database, no I/O — the service layer takes :class:`IngestedDraftFields` and
constructs the ORM row. Keeping the mapping pure means it is exhaustively
testable and the ingestion service stays a thin transactional shell.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pramana.domain.consumable_package import ConsumablePackage
from pramana.domain.enums import ContentDraftStatus


@dataclass(frozen=True, slots=True)
class IngestedDraftFields:
    """The field set for a content draft created from an ingested package.

    Mirrors the writable columns of :class:`~pramana.db.models.content.
    ContentDraft` for an arrival, so the service can do
    ``ContentDraft(**fields.as_model_kwargs())`` without re-deriving anything.
    """

    tenant_id: uuid.UUID
    course_id: uuid.UUID
    status: ContentDraftStatus
    title: str
    body: dict[str, Any]
    source_citations: list[dict[str, Any]]
    gen_engine: str
    gen_model: str
    gen_provider: str
    gen_prompt_version: str
    generated_at: datetime
    package_id: uuid.UUID
    package_version: int
    package_content_hash: str
    signature: str

    def as_model_kwargs(self) -> dict[str, Any]:
        """Return kwargs for constructing a ``ContentDraft`` row.

        ``status`` is emitted as its string value (the column stores the enum
        value); the generator is an external engine, so ``generated_by_user_id``
        is deliberately absent (left ``NULL``).
        """
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
            "package_id": self.package_id,
            "package_version": self.package_version,
            "package_content_hash": self.package_content_hash,
            "signature": self.signature,
        }


def package_to_draft_fields(
    package: ConsumablePackage,
    *,
    tenant_id: uuid.UUID,
    course_id: uuid.UUID,
) -> IngestedDraftFields:
    """Project a verified package onto draft fields for the given course.

    The training content (``modules`` + ``quiz``) and the delivery references
    (``assets`` + ``artifacts``) are stored verbatim on ``body``; the quiz is
    destructured into ``Question`` / ``AnswerOption`` at publish time by
    :func:`pramana.domain.publication.materialize_quiz`. ``source_definitions``
    become the draft's ``source_citations`` so a reviewer can trace each claim to
    its originating clause.
    """
    body: dict[str, Any] = {
        "modules": [dict(m) for m in package.modules],
        "quiz": dict(package.quiz),
        "assets": [dict(a) for a in package.assets],
        "artifacts": [dict(a) for a in package.artifacts],
    }
    source_citations = [
        {"framework": sd.framework, "clause": sd.clause, "ref": sd.ref}
        for sd in package.source_definitions
    ]
    return IngestedDraftFields(
        tenant_id=tenant_id,
        course_id=course_id,
        status=ContentDraftStatus.RECEIVED,
        title=package.title,
        body=body,
        source_citations=source_citations,
        gen_engine=package.provenance.engine,
        gen_model=package.provenance.model,
        gen_provider=package.provenance.provider,
        gen_prompt_version=package.provenance.prompt_version,
        generated_at=package.provenance.generated_at,
        package_id=package.package_id,
        package_version=package.package_version,
        package_content_hash=package.declared_content_hash,
        signature=package.signature,
    )
