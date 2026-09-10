"""Publish-time transcript stamping, against a real Postgres schema.

The unit-level service tests (``tests/services/test_content_review.py``) mock
the session, so ``session.add(course_version)`` never reaches a real table —
they prove the *code path* assigns ``transcript``, not that the column exists
with a compatible type or that a real ``publish_draft`` write actually
persists it. This file closes that gap: it drives the real service functions
(``submit_for_review`` -> ``approve_draft`` -> ``attach``-equivalent video
block -> ``attest_draft_video`` -> ``publish_draft``) against the scratch
database and reads the resulting ``CourseVersion`` row back after commit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.content import ContentDraft
from pramana.db.models.course import Course, CourseVersion
from pramana.db.models.identity import Tenant, User
from pramana.services import content_review as cr

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

_QUIZ = {
    "pass_threshold_pct": 80,
    "questions": [{"prompt": "Q1?", "options": ["a", "b", "c"], "answer_index": 0}],
}


async def _tenant_course(db: AsyncSession) -> tuple[Tenant, Course]:
    tenant = Tenant(id=uuid.uuid4(), name="T", short_code=uuid.uuid4().hex[:12])
    db.add(tenant)
    await db.flush()
    course = Course(id=uuid.uuid4(), tenant_id=tenant.id, title="Compliance 101")
    db.add(course)
    await db.flush()
    return tenant, course


async def _user(db: AsyncSession, tenant: Tenant) -> User:
    user = User(user_id=uuid.uuid4(), tenant_id=tenant.id, email=f"{uuid.uuid4()}@e.example")
    db.add(user)
    await db.flush()
    return user


class TestPublishStampsTranscriptOnRealSchema:
    async def test_the_transcript_survives_a_real_publish_and_round_trip(
        self, db: AsyncSession
    ) -> None:
        tenant, course = await _tenant_course(db)
        generator = await _user(db, tenant)
        approver = await _user(db, tenant)
        attester = await _user(db, tenant)
        publisher = await _user(db, tenant)

        transcript = "Every control has an owner."
        draft = ContentDraft(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            course_id=course.id,
            title="ICFR awareness",
            status="draft",
            body={
                "modules": [{"heading": "x"}],
                "quiz": _QUIZ,
                "video": {
                    "asset_ref": "video/course/draft.mp4",
                    "min_watch_pct": 80,
                    "transcript": transcript,
                },
            },
            generated_by_user_id=generator.user_id,
        )
        db.add(draft)
        await db.flush()

        await cr.submit_for_review(
            db, draft_id=draft.id, tenant_id=tenant.id, actor_user_id=generator.user_id, now=NOW
        )
        await cr.approve_draft(
            db,
            draft_id=draft.id,
            tenant_id=tenant.id,
            approver_user_id=approver.user_id,
            attestation_text="Script is accurate.",
            now=NOW,
        )
        await cr.attest_draft_video(
            db,
            draft_id=draft.id,
            tenant_id=tenant.id,
            actor_user_id=attester.user_id,
            video_asset_hash="sha256:" + "b" * 64,
            attestation_text="Footage matches the approved script.",
            now=NOW,
        )
        version = await cr.publish_draft(
            db,
            draft_id=draft.id,
            tenant_id=tenant.id,
            publisher_user_id=publisher.user_id,
            now=NOW,
        )
        assert version.transcript == transcript
        await db.commit()

        # The point of this test: re-read the row from the database rather than
        # trusting the in-memory object the service handed back.
        reread = await db.get(CourseVersion, version.id)
        assert reread is not None
        assert reread.transcript == transcript

    async def test_a_quiz_only_publish_leaves_the_transcript_null(self, db: AsyncSession) -> None:
        tenant, course = await _tenant_course(db)
        generator = await _user(db, tenant)
        approver = await _user(db, tenant)
        publisher = await _user(db, tenant)

        draft = ContentDraft(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            course_id=course.id,
            title="ICFR awareness",
            status="draft",
            body={"modules": [{"heading": "x"}], "quiz": _QUIZ},
            generated_by_user_id=generator.user_id,
        )
        db.add(draft)
        await db.flush()

        await cr.submit_for_review(
            db, draft_id=draft.id, tenant_id=tenant.id, actor_user_id=generator.user_id, now=NOW
        )
        await cr.approve_draft(
            db,
            draft_id=draft.id,
            tenant_id=tenant.id,
            approver_user_id=approver.user_id,
            attestation_text="Script is accurate.",
            now=NOW,
        )
        version = await cr.publish_draft(
            db,
            draft_id=draft.id,
            tenant_id=tenant.id,
            publisher_user_id=publisher.user_id,
            now=NOW,
        )
        assert version.transcript is None
        await db.commit()

        reread = await db.get(CourseVersion, version.id)
        assert reread is not None
        assert reread.transcript is None
