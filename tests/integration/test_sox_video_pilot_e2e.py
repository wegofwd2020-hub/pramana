"""The SOX pilot loop, end to end, against a real Postgres.

Each stage is covered on its own elsewhere. What this pins is that they
compose: a draft with generated footage cannot reach a learner without both
attestations, and once it does, the published version carries the attested
asset and the audit trail names both attestations by different actors.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.audit import AuditLog
from pramana.db.models.content import ContentDraft
from pramana.db.models.course import Course
from pramana.db.models.identity import Tenant, User
from pramana.domain.enums import ContentDraftStatus, ContentEvent
from pramana.exceptions import InvalidStateTransitionError
from pramana.services import content_review

pytestmark = pytest.mark.integration


GENERATOR_ID = uuid.uuid4()
APPROVER_ID = uuid.uuid4()
ATTESTER_ID = uuid.uuid4()
NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

# A minimal but real quiz. materialize_quiz (pramana/domain/publication.py)
# requires quiz.questions to be a non-empty list, with each question carrying
# a prompt, >= 2 options, and an in-range answer_index — an empty questions
# list raises ValidationError at publish time, which would mask the video
# gate this file exists to prove. See task-7-report.md for why this departs
# from the brief's literal `{"questions": []}`.
VIDEO_BODY: dict[str, Any] = {
    "video": {"asset_ref": "s3://audit/sox-pilot.mp4", "min_watch_pct": 80},
    "quiz": {
        "pass_threshold_pct": 80,
        "questions": [
            {
                "prompt": "An auditor asks for evidence a control operated. What do you show them?",
                "options": [
                    "The signed approval and the date it was recorded",
                    "Nothing — controls are confidential",
                    "A verbal assurance that it happened",
                ],
                "answer_index": 0,
            },
        ],
    },
}
ASSET_HASH = "sha256:9f2c0b1e"


async def _seed_draft(
    db: AsyncSession, *, body: dict[str, Any], generated_by_user_id: uuid.UUID
) -> ContentDraft:
    """Seed a Tenant, a Course, the three fixed actor Users, and a ContentDraft.

    Mirrors ``_draft``/``_user`` in
    ``tests/integration/test_video_attestation_constraints.py``.
    ``content_draft.course_id`` is NOT NULL with an FK to ``course``, and the
    users table is ``user_account``, not ``user``.

    Every test in this file drives the same three fixed actor ids
    (generator/approver/attester) so the separation-of-duties checks are
    exercised consistently, but each test gets its own freshly created schema
    (see the ``engine`` fixture in ``tests/integration/conftest.py``) — so
    those ids must be (re-)seeded as real ``User`` rows on every call rather
    than once at import time.
    """
    tenant = Tenant(id=uuid.uuid4(), name="T", short_code=uuid.uuid4().hex[:12])
    db.add(tenant)
    await db.flush()
    course = Course(id=uuid.uuid4(), tenant_id=tenant.id, title="Compliance 101")
    db.add(course)
    await db.flush()
    for actor_id in (GENERATOR_ID, APPROVER_ID, ATTESTER_ID):
        db.add(User(user_id=actor_id, tenant_id=tenant.id, email=f"{actor_id}@e.example"))
    await db.flush()
    draft = ContentDraft(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        course_id=course.id,
        title="ICFR awareness — SOX pilot",
        status=ContentDraftStatus.DRAFT.value,
        body=body,
        generated_by_user_id=generated_by_user_id,
    )
    db.add(draft)
    await db.flush()
    return draft


async def _approved_video_draft(
    db: AsyncSession, *, generator: uuid.UUID, approver: uuid.UUID, now: datetime
) -> ContentDraft:
    """A draft carrying footage, script-approved but not yet attested."""
    draft = await _seed_draft(db, body=VIDEO_BODY, generated_by_user_id=generator)
    await content_review.submit_for_review(
        db,
        draft_id=draft.id,
        tenant_id=draft.tenant_id,
        actor_user_id=generator,
        now=now,
    )
    await content_review.approve_draft(
        db,
        draft_id=draft.id,
        tenant_id=draft.tenant_id,
        approver_user_id=approver,
        attestation_text="Claims verified against the cited sections.",
        now=now,
    )
    await db.commit()
    return draft


class TestSoxVideoPilotEndToEnd:
    async def test_unattested_video_never_reaches_a_learner(self, db: AsyncSession) -> None:
        """The whole point of the second gate, proved through the real stack."""
        draft = await _approved_video_draft(
            db, generator=GENERATOR_ID, approver=APPROVER_ID, now=NOW
        )
        with pytest.raises(InvalidStateTransitionError):
            await content_review.publish_draft(
                db,
                draft_id=draft.id,
                tenant_id=draft.tenant_id,
                publisher_user_id=APPROVER_ID,
                now=NOW,
            )
        await db.rollback()
        refreshed = await db.get(ContentDraft, draft.id)
        assert refreshed is not None
        assert refreshed.status == ContentDraftStatus.APPROVED.value
        assert refreshed.published_course_version_id is None

    async def test_attested_video_publishes_and_certifies(self, db: AsyncSession) -> None:
        """draft -> video -> approve -> attest -> publish."""
        draft = await _approved_video_draft(
            db, generator=GENERATOR_ID, approver=APPROVER_ID, now=NOW
        )
        await content_review.attest_draft_video(
            db,
            draft_id=draft.id,
            tenant_id=draft.tenant_id,
            actor_user_id=ATTESTER_ID,
            video_asset_hash=ASSET_HASH,
            attestation_text="Footage matches the approved script.",
            now=NOW,
        )
        version = await content_review.publish_draft(
            db,
            draft_id=draft.id,
            tenant_id=draft.tenant_id,
            publisher_user_id=APPROVER_ID,
            now=NOW,
        )
        await db.commit()
        # publish_draft returns the new CourseVersion, not the draft. Assert the
        # draft reached PUBLISHED by re-reading it.
        assert version is not None
        refreshed = await db.get(ContentDraft, draft.id)
        assert refreshed is not None
        assert refreshed.status == ContentDraftStatus.PUBLISHED.value
        assert refreshed.published_course_version_id == version.id

    async def test_the_published_version_carries_the_attested_asset(self, db: AsyncSession) -> None:
        draft = await _approved_video_draft(
            db, generator=GENERATOR_ID, approver=APPROVER_ID, now=NOW
        )
        await content_review.attest_draft_video(
            db,
            draft_id=draft.id,
            tenant_id=draft.tenant_id,
            actor_user_id=ATTESTER_ID,
            video_asset_hash=ASSET_HASH,
            attestation_text="ok",
            now=NOW,
        )
        version = await content_review.publish_draft(
            db,
            draft_id=draft.id,
            tenant_id=draft.tenant_id,
            publisher_user_id=APPROVER_ID,
            now=NOW,
        )
        await db.commit()
        assert version.video_asset_id == VIDEO_BODY["video"]["asset_ref"]
        assert version.min_watch_pct == VIDEO_BODY["video"]["min_watch_pct"]

    async def test_both_attestations_are_in_the_audit_trail(self, db: AsyncSession) -> None:
        """APPROVE and ATTEST_VIDEO both appear, recorded to different actors."""
        draft = await _approved_video_draft(
            db, generator=GENERATOR_ID, approver=APPROVER_ID, now=NOW
        )
        await content_review.attest_draft_video(
            db,
            draft_id=draft.id,
            tenant_id=draft.tenant_id,
            actor_user_id=ATTESTER_ID,
            video_asset_hash=ASSET_HASH,
            attestation_text="ok",
            now=NOW,
        )
        await db.commit()
        rows = (
            (
                await db.execute(
                    select(AuditLog)
                    .where(AuditLog.entity_id == str(draft.id))
                    .order_by(AuditLog.audit_id.asc())
                )
            )
            .scalars()
            .all()
        )
        by_event = {r.event_type: r.actor_user_id for r in rows}
        # append_audit (pramana/services/content_review.py::_audit) stamps the
        # event type as "content_draft.<ContentEvent value>", not the bare
        # ContentEvent value — see task-7-report.md.
        approve_event = f"content_draft.{ContentEvent.APPROVE.value}"
        attest_event = f"content_draft.{ContentEvent.ATTEST_VIDEO.value}"
        assert approve_event in by_event
        assert attest_event in by_event
        assert by_event[approve_event] != by_event[attest_event]
