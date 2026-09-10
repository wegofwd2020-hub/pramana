"""``attach_course_video`` against a real Postgres schema.

``pramana/services/video_generation.py`` has no test at all for its async DB
shell — the unit tests in ``tests/test_video_generation.py`` explicitly defer
it ("left for the integration-test phase"). This file closes that gap for the
one line that matters most: the transcript is the learner's *only* access to
what an unnarrated pilot video says (see
``TICKETS/VIDEO-1-pilot-lesson-videos.md``'s accept­ance-gap note), so the
line that writes it — ``patch["video"]["transcript"] = "\\n".join(lines)`` —
needs a test that would fail if it were ever deleted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from wegofwd_video import VideoCapabilities, VideoProvider, VideoRequest, VideoResult

from pramana.db.models.content import ContentDraft
from pramana.db.models.course import Course
from pramana.db.models.identity import Tenant, User
from pramana.domain.enums import ContentDraftStatus
from pramana.services.video_generation import attach_course_video

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


class _FakeVideoProvider(VideoProvider):
    """A scripted provider returning one canned asset.

    ``provider_id="veo"`` so the capability check in
    ``generate_video_result`` resolves the real veo limits from the registry
    (mirrors ``tests/test_video_generation.py``'s fake).
    """

    provider_id = "veo"
    capabilities = VideoCapabilities(
        max_duration_s=60, resolutions=("720p", "1080p", "4k"), native_audio=True
    )

    @property
    def model(self) -> str:
        return "veo-3.1"

    def generate(self, req: VideoRequest) -> VideoResult:
        return VideoResult(
            provider_id="veo",
            model="veo-3.1",
            asset_bytes=b"\x00\x01mp4",
            duration_s=req.target_duration_s,
            resolution=req.resolution,
            has_audio=True,
            c2pa_signed=True,
            watermark="SynthID",
        )


async def _tenant_course_user(db: AsyncSession) -> tuple[Tenant, Course, User]:
    tenant = Tenant(id=uuid.uuid4(), name="T", short_code=uuid.uuid4().hex[:12])
    db.add(tenant)
    await db.flush()
    course = Course(id=uuid.uuid4(), tenant_id=tenant.id, title="Compliance 101")
    db.add(course)
    user = User(user_id=uuid.uuid4(), tenant_id=tenant.id, email=f"{uuid.uuid4()}@e.example")
    db.add(user)
    await db.flush()
    return tenant, course, user


class TestAttachCourseVideoWritesTheTranscript:
    async def test_the_narration_lines_are_written_to_the_body_transcript(
        self, db: AsyncSession
    ) -> None:
        tenant, course, generator = await _tenant_course_user(db)
        draft = ContentDraft(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            course_id=course.id,
            title="ICFR awareness",
            status=ContentDraftStatus.DRAFT.value,
            body={"modules": [{"heading": "x", "content": "seed"}]},
            generated_by_user_id=generator.user_id,
        )
        db.add(draft)
        await db.flush()

        lines = [
            "Every internal control has a named owner.",
            "Evidence is recorded when the control runs.",
        ]
        stored: dict[str, bytes] = {}

        def fake_upload(data: bytes, key: str) -> str:
            stored[key] = data
            return key

        updated = await attach_course_video(
            db,
            provider=_FakeVideoProvider(),
            upload=fake_upload,
            draft_id=draft.id,
            tenant_id=tenant.id,
            generated_by_user_id=generator.user_id,
            now=NOW,
            narration_lines=lines,
        )

        assert updated.body["video"]["transcript"] == "\n".join(lines)
        await db.commit()

        # Re-read from the database rather than trusting the in-memory object.
        reread = await db.get(ContentDraft, draft.id)
        assert reread is not None
        assert reread.body["video"]["transcript"] == "\n".join(lines)
