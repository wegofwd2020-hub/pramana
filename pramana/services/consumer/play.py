# pramana/services/consumer/play.py
"""Play service — opens/closes a lesson view (the '# times viewed' event)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.consumer import Enrollment, PlaySession
from pramana.db.models.course import Course, CourseVersion
from pramana.exceptions import NotFoundError, ValidationError
from pramana.services.consumer.enrollment import get_or_create_enrollment
from pramana.services.player import AssetUrlSigner, null_asset_signer


@dataclass(frozen=True, slots=True)
class PlaySessionManifest:
    play_session_id: uuid.UUID
    enrollment_id: uuid.UUID
    course_version_id: uuid.UUID
    media_url: str | None
    media_kind: str
    min_watch_pct: int


async def start_view(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    entitlement_id: uuid.UUID,
    media_kind: str,
    now: datetime,
    sign_asset: AssetUrlSigner = null_asset_signer,
) -> PlaySessionManifest:
    course = await session.get(Course, course_id)
    if course is None or course.current_version_id is None:
        raise NotFoundError("course has no active version", context={"course_id": str(course_id)})
    version = await session.get(CourseVersion, course.current_version_id)
    if version is None:
        raise NotFoundError("course version not found")

    enrollment = await get_or_create_enrollment(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        course_id=course_id,
        entitlement_id=entitlement_id,
        now=now,
    )

    ps = PlaySession(
        tenant_id=tenant_id,
        enrollment_id=enrollment.id,
        course_version_id=version.id,
        media_kind=media_kind,
        started_at=now,
    )
    session.add(ps)
    await session.flush()
    return PlaySessionManifest(
        play_session_id=ps.id,
        enrollment_id=enrollment.id,
        course_version_id=version.id,
        media_url=sign_asset(version.video_asset_id),
        media_kind=media_kind,
        min_watch_pct=version.min_watch_pct,
    )


async def end_view(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    play_session_id: uuid.UUID,
    duration_seconds: int,
    max_watched_pct: int,
    now: datetime,
) -> None:
    if not (0 <= max_watched_pct <= 100):
        raise ValidationError("max_watched_pct out of range")
    ps = await session.get(PlaySession, play_session_id)
    if ps is None or ps.tenant_id != tenant_id:
        raise NotFoundError("play session not found")
    if ps.ended_at is not None:
        return  # idempotent: already closed, don't double-count
    ps.ended_at = now
    ps.duration_seconds = duration_seconds
    ps.max_watched_pct = max_watched_pct

    enrollment = await session.get(Enrollment, ps.enrollment_id)
    if enrollment is None:
        raise NotFoundError(
            "enrollment not found for play session",
            context={"play_session_id": str(play_session_id)},
        )
    enrollment.view_count += 1
    enrollment.last_accessed_at = now
