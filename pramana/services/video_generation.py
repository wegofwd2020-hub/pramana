"""In-process video generation for a course draft (ADR-013 / ADR-026).

Pramana drafts a compliance **video** to accompany a course's quiz, via the shared
``wegofwd-video`` seam. The make-or-derive split mirrors
:mod:`pramana.services.content_generation`:

* :func:`generate_video_result` is the **make** step — capability-check the brief
  against the provider, then drive the injected ``wegofwd_video.VideoProvider``.
  No database, no storage; fully unit-testable with a fake provider.
* :func:`attach_course_video` is the thin **transactional shell** — build the brief
  from an existing ``DRAFT`` content draft, generate, persist the asset via the
  injected uploader, patch ``body["video"]`` onto the draft, and append the audit
  entry with the shared provenance stamp. The caller owns the transaction.

The video is a *drafting aid only* (ADR-013): it attaches to a ``DRAFT`` and is
**never assignable** until a different human approves the draft. At publish,
:func:`pramana.domain.publication.materialize_video` copies the asset key onto the
immutable course version.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from wegofwd_video import (
    VideoBrief,
    VideoProvider,
    VideoRequest,
    VideoResult,
    assert_brief_within_capabilities,
    provenance,
)

from pramana.db.models.content import ContentDraft
from pramana.domain.enums import ContentDraftStatus, ContentEvent
from pramana.domain.video_generation import (
    build_video_brief,
    video_to_body_patch,
)
from pramana.exceptions import NotFoundError, ValidationError
from pramana.services.audit import append_audit
from pramana.services.storage import VideoUploader, video_asset_key

_DEFAULT_RESOLUTION = "1080p"
_DEFAULT_ASPECT_RATIO = "16:9"


def generate_video_result(
    provider: VideoProvider,
    brief: VideoBrief,
    *,
    resolution: str = _DEFAULT_RESOLUTION,
    aspect_ratio: str = _DEFAULT_ASPECT_RATIO,
    seed: int | None = None,
) -> VideoResult:
    """Generate one video from a brief (no database, no storage).

    Fails fast if the brief exceeds the provider/model's limits *before* any
    dispatch, then runs the (blocking) provider call.

    Raises:
        wegofwd_video.VideoCapabilityError: The brief asks for more than the
            provider supports (resolution / aspect / duration / ingredients).
        wegofwd_video.VideoError: An auth / transport / provider failure (key-free).
    """
    duration_s = sum(shot.duration_s for shot in brief.shots)
    assert_brief_within_capabilities(
        provider.provider_id,
        resolution=resolution,
        aspect=aspect_ratio,
        duration_s=duration_s,
        ingredients=len(brief.ingredients),
    )
    req = VideoRequest(
        brief=brief,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
        target_duration_s=duration_s,
        seed=seed,
    )
    return provider.generate(req)


async def attach_course_video(
    session: AsyncSession,
    *,
    provider: VideoProvider,
    upload: VideoUploader,
    draft_id: uuid.UUID,
    tenant_id: uuid.UUID,
    generated_by_user_id: uuid.UUID,
    now: datetime,
    narration_lines: Sequence[str] | None = None,
    resolution: str = _DEFAULT_RESOLUTION,
    aspect_ratio: str = _DEFAULT_ASPECT_RATIO,
    min_watch_pct: int = 0,
    seed: int | None = None,
) -> ContentDraft:
    """Generate a video for a ``DRAFT`` draft and attach it to ``body["video"]``.

    Narration defaults to the draft's clause citation title(s) unless
    ``narration_lines`` is supplied. The asset is persisted via ``upload`` and the
    returned storage key is stored on the draft; the shared provenance stamp is
    written to both the body and the audit trail.

    Raises:
        NotFoundError: ``draft_id`` is not in this tenant.
        ValidationError: The draft is not in ``DRAFT`` status, or there is no
            narration to build a brief from.
        wegofwd_video.VideoError: Generation failed (capability / transport).
    """
    draft = await session.get(ContentDraft, draft_id)
    if draft is None or draft.tenant_id != tenant_id:
        raise NotFoundError(
            "content draft not found in tenant",
            context={"draft_id": str(draft_id), "tenant_id": str(tenant_id)},
        )
    if draft.status != ContentDraftStatus.DRAFT.value:
        raise ValidationError(
            "video can only be attached to a DRAFT draft",
            context={"draft_id": str(draft_id), "status": draft.status},
        )

    lines = list(narration_lines) if narration_lines else _narration_from_draft(draft)
    clause_title = draft.title
    brief = build_video_brief(clause_title=clause_title, narration_lines=lines)

    result = generate_video_result(
        provider, brief, resolution=resolution, aspect_ratio=aspect_ratio, seed=seed
    )

    key = video_asset_key(course_id=draft.course_id, draft_id=draft.id)
    if result.asset_bytes is not None:
        asset_ref = upload(result.asset_bytes, key)
    elif result.asset_uri:
        asset_ref = result.asset_uri  # provider returned a fetchable URI; store as-is
    else:
        raise ValidationError("provider returned neither asset bytes nor a URI")

    prov = provenance(provider.provider_id, provider.model, seed=seed)
    patch = video_to_body_patch(
        result, asset_ref=asset_ref, provenance=prov, min_watch_pct=min_watch_pct
    )
    # Reassign body so SQLAlchemy detects the JSONB change (in-place mutation of a
    # mutable column is not tracked).
    draft.body = {**draft.body, **patch}

    await append_audit(
        session,
        tenant_id=tenant_id,
        entity_type="content_draft",
        entity_id=str(draft.id),
        event_type=f"content_draft.{ContentEvent.GENERATE.value}",
        payload={
            "stage": "video",
            "asset_ref": asset_ref,
            "generated_by_user_id": str(generated_by_user_id),
            "provenance": prov,
        },
        occurred_at=now,
        actor_user_id=generated_by_user_id,
    )
    return draft


def _narration_from_draft(draft: ContentDraft) -> list[str]:
    """Derive narration lines from a draft when the caller supplies none.

    First slice: use the draft's lesson ``modules`` content if present, else fall
    back to the draft title. Keeps the make-step honest — it narrates only content
    already in the draft, inventing nothing.
    """
    modules = draft.body.get("modules") if isinstance(draft.body, dict) else None
    if isinstance(modules, list):
        lines = [
            m["content"]
            for m in modules
            if isinstance(m, dict) and isinstance(m.get("content"), str) and m["content"].strip()
        ]
        if lines:
            return lines
    return [draft.title]
