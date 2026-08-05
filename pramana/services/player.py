"""Course-player service — asset manifest + watch-gate (US-PLATFORM-0002).

The player presents a pinned ``CourseVersion``'s video/deck and enforces the
watch requirement before the quiz unlocks. This module is the read/update side
of that: build the manifest an assignee's player needs, and record watch
progress. The quiz-unlock decision (``watched_pct >= min_watch_pct``) lives here
and is re-checked authoritatively in
:func:`pramana.services.assignments.start_attempt` — the client is never trusted
to have unlocked itself.

Asset URLs are produced through an :data:`AssetUrlSigner` seam so the manifest is
testable without S3/boto3; the default is a pass-through, and a deployment wires
a presigning signer.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.assignment import Assignment
from pramana.db.models.course import CourseVersion
from pramana.domain.enums import TransitionEvent
from pramana.exceptions import AuthorizationError, NotFoundError, ValidationError
from pramana.services import assignments as assignments_service
from pramana.services.audit import append_audit

# (object_key | None) -> a fetchable URL | None. Default: identity (return the key).
AssetUrlSigner = Callable[[str | None], str | None]


def null_asset_signer(object_key: str | None) -> str | None:
    """Pass-through signer: surfaces the raw object key (no presigning)."""
    return object_key


@dataclass(frozen=True, slots=True)
class PlayerManifest:
    """What the player needs to render an assigned course."""

    assignment_id: uuid.UUID
    course_version_id: uuid.UUID
    status: str
    video_url: str | None
    min_watch_pct: int
    watched_pct: int
    quiz_unlocked: bool


@dataclass(frozen=True, slots=True)
class WatchProgress:
    """The learner's watch state after an update."""

    assignment_id: uuid.UUID
    watched_pct: int
    min_watch_pct: int
    quiz_unlocked: bool


async def get_player_manifest(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    tenant_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    sign_asset: AssetUrlSigner = null_asset_signer,
) -> PlayerManifest:
    """Build the player manifest for the assignee's pinned course version."""
    assignment = await _load_owned(
        session, assignment_id=assignment_id, tenant_id=tenant_id, acting_user_id=acting_user_id
    )
    version = await session.get(CourseVersion, assignment.course_version_id)
    if version is None:
        raise NotFoundError(
            "course version not found",
            context={"course_version_id": str(assignment.course_version_id)},
        )
    return PlayerManifest(
        assignment_id=assignment.id,
        course_version_id=version.id,
        status=assignment.status,
        video_url=sign_asset(version.video_asset_id),
        min_watch_pct=version.min_watch_pct,
        watched_pct=assignment.watched_pct,
        quiz_unlocked=assignment.watched_pct >= version.min_watch_pct,
    )


async def record_progress(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    tenant_id: uuid.UUID,
    acting_user_id: uuid.UUID,
    watched_pct: int,
    now: datetime,
) -> WatchProgress:
    """Record the learner's furthest watched position (monotonic upsert).

    ``watched_pct`` only ever advances — a lower report is ignored — so scrubbing
    backward or an out-of-order client update never revokes an unlocked quiz.

    Raises:
        AuthorizationError: The acting user is not the assignee.
        ValidationError: ``watched_pct`` is out of ``[0, 100]``.
    """
    if not 0 <= watched_pct <= 100:
        raise ValidationError(
            "watched_pct must be between 0 and 100", context={"watched_pct": watched_pct}
        )
    assignment = await _load_owned(
        session, assignment_id=assignment_id, tenant_id=tenant_id, acting_user_id=acting_user_id
    )
    version = await session.get(CourseVersion, assignment.course_version_id)
    min_watch_pct = version.min_watch_pct if version is not None else 0

    new_pct = max(assignment.watched_pct, watched_pct)
    if new_pct != assignment.watched_pct:
        assignment.watched_pct = new_pct
        await append_audit(
            session,
            tenant_id=assignment.tenant_id,
            actor_user_id=assignment.user_id,
            entity_type="assignment",
            entity_id=str(assignment.id),
            event_type=f"assignment.{TransitionEvent.RECORD_PROGRESS.value}",
            payload={"watched_pct": new_pct},
            occurred_at=now,
        )
    return WatchProgress(
        assignment_id=assignment.id,
        watched_pct=assignment.watched_pct,
        min_watch_pct=min_watch_pct,
        quiz_unlocked=assignment.watched_pct >= min_watch_pct,
    )


async def _load_owned(
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    tenant_id: uuid.UUID,
    acting_user_id: uuid.UUID,
) -> Assignment:
    assignment = await assignments_service.get_assignment(
        session, assignment_id=assignment_id, tenant_id=tenant_id
    )
    if assignment.user_id != acting_user_id:
        raise AuthorizationError(
            "not your assignment", context={"assignment_id": str(assignment_id)}
        )
    return assignment
