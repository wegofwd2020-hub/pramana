"""Tests for the content-draft review/approval service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pramana.db.models.audit import AuditLog
from pramana.db.models.content import ContentDraft
from pramana.db.models.course import AnswerOption, Question
from pramana.domain.enums import ContentDraftStatus, ContentEvent
from pramana.exceptions import (
    InvalidStateTransitionError,
    NotFoundError,
    SeparationOfDutiesError,
    ValidationError,
)
from pramana.services import content_review as cr

NOW = datetime(2026, 6, 5, 14, 0, tzinfo=UTC)
TENANT = uuid.uuid4()


def make_draft(status: str = "received", **kw) -> ContentDraft:
    d = ContentDraft(
        id=kw.get("id", uuid.uuid4()),
        tenant_id=kw.get("tenant_id", TENANT),
        course_id=kw.get("course_id", uuid.uuid4()),
        status=status,
        title="FCPA Anti-Bribery",
        body=kw.get(
            "body",
            {
                "modules": [{"heading": "x"}],
                "quiz": {
                    "pass_threshold_pct": 80,
                    "questions": [{"prompt": "Q1?", "options": ["a", "b", "c"], "answer_index": 0}],
                },
            },
        ),
        source_citations=kw.get(
            "source_citations", [{"framework": "fcpa", "clause": "anti-bribery"}]
        ),
        generated_by_user_id=kw.get("generated_by_user_id"),
        package_id=kw.get("package_id", uuid.uuid4()),
        package_version=kw.get("package_version", 1),
    )
    d.approved_by_user_id = kw.get("approved_by_user_id")
    d.approved_at = kw.get("approved_at")
    d.content_hash = kw.get("content_hash")
    d.published_course_version_id = kw.get("published_course_version_id")
    d.archived_at = None
    d.review_notes = None
    d.attestation_text = None
    return d


def _approved_draft_with_video(*, generated_by_user_id: uuid.UUID | None = None) -> ContentDraft:
    """Build an APPROVED draft carrying a video block that has not yet been attested.

    Mirrors what ``submit_for_review`` + ``approve_draft`` would leave behind;
    built directly at the target state via ``make_draft``, matching this file's
    existing pattern (see ``TestPublish``) rather than driving a mocked session
    through both prior transitions.
    """
    return make_draft(
        status="approved",
        generated_by_user_id=generated_by_user_id,
        approved_by_user_id=uuid.uuid4(),
        approved_at=NOW,
        content_hash="sha256:" + "a" * 64,
        body={
            "modules": [{"heading": "x"}],
            "quiz": {
                "pass_threshold_pct": 80,
                "questions": [{"prompt": "Q1?", "options": ["a", "b", "c"], "answer_index": 0}],
            },
            "video": {"asset_ref": "video/course/draft.mp4", "min_watch_pct": 0},
        },
    )


def _result(*, scalar=None, rows=()) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalar_one.return_value = scalar if scalar is not None else 0
    r.scalars.return_value.all.return_value = list(rows)
    return r


def fake_session(*, get=None, execute=None) -> AsyncMock:
    s = AsyncMock()
    s.get = AsyncMock(return_value=get)
    if execute is not None:
        s.execute = AsyncMock(side_effect=execute)
    else:
        s.execute = AsyncMock(return_value=_result())
    s.add = MagicMock()
    return s


# --- snapshot mapping ----------------------------------------------------
def test_snapshot_maps_orm_to_domain() -> None:
    draft = make_draft(status="in_review")
    snap = cr._snapshot(draft)
    assert snap.status is ContentDraftStatus.IN_REVIEW
    assert snap.has_content is True
    assert snap.generated_by_user_id is None


# --- transitions ---------------------------------------------------------
class TestTransitions:
    async def test_submit_for_review(self) -> None:
        draft = make_draft(status="received")
        session = fake_session(get=draft)
        out = await cr.submit_for_review(
            session, draft_id=draft.id, tenant_id=TENANT, actor_user_id=uuid.uuid4(), now=NOW
        )
        assert out.status == "in_review"
        session.add.assert_called_once()  # audit entry

    async def test_submit_advances_linked_request(self) -> None:
        from pramana.db.models.content_request import ContentRequest

        draft = make_draft(status="received")
        req = ContentRequest(
            id=uuid.uuid4(),
            tenant_id=TENANT,
            framework="fcpa",
            title="t",
            status="received",
            requested_by=uuid.uuid4(),
            spec={},
        )
        req.draft_id = draft.id
        # execute: draft-audit head, advance-select(req), advance-audit head
        session = fake_session(get=draft, execute=[_result(), _result(scalar=req), _result()])
        await cr.submit_for_review(
            session, draft_id=draft.id, tenant_id=TENANT, actor_user_id=uuid.uuid4(), now=NOW
        )
        assert req.status == "in_review"

    async def test_submit_from_wrong_state_raises(self) -> None:
        draft = make_draft(
            status="approved",
            approved_by_user_id=uuid.uuid4(),
            approved_at=NOW,
            content_hash="sha256:" + "a" * 64,
        )
        session = fake_session(get=draft)
        with pytest.raises(InvalidStateTransitionError):
            await cr.submit_for_review(
                session, draft_id=draft.id, tenant_id=TENANT, actor_user_id=None, now=NOW
            )

    async def test_approve_freezes_hash_and_records_attestation(self) -> None:
        draft = make_draft(status="in_review")
        session = fake_session(get=draft)
        approver = uuid.uuid4()
        out = await cr.approve_draft(
            session,
            draft_id=draft.id,
            tenant_id=TENANT,
            approver_user_id=approver,
            attestation_text="I attest this is accurate.",
            now=NOW,
        )
        assert out.status == "approved"
        assert out.approved_by_user_id == approver
        assert out.approved_at == NOW
        assert out.content_hash.startswith("sha256:")
        assert out.attestation_text == "I attest this is accurate."

    async def test_approve_separation_of_duties(self) -> None:
        generator = uuid.uuid4()
        draft = make_draft(status="in_review", generated_by_user_id=generator)
        session = fake_session(get=draft)
        with pytest.raises(SeparationOfDutiesError):
            await cr.approve_draft(
                session,
                draft_id=draft.id,
                tenant_id=TENANT,
                approver_user_id=generator,
                attestation_text="x",
                now=NOW,
            )

    async def test_request_changes_records_notes(self) -> None:
        draft = make_draft(status="in_review")
        session = fake_session(get=draft)
        out = await cr.request_changes(
            session,
            draft_id=draft.id,
            tenant_id=TENANT,
            actor_user_id=None,
            notes="Fix the §404 citation.",
            now=NOW,
        )
        assert out.status == "draft"
        assert out.review_notes == "Fix the §404 citation."

    async def test_reject_is_terminal(self) -> None:
        draft = make_draft(status="in_review")
        session = fake_session(get=draft)
        out = await cr.reject_draft(
            session,
            draft_id=draft.id,
            tenant_id=TENANT,
            actor_user_id=None,
            notes="Inaccurate.",
            now=NOW,
        )
        assert out.status == "rejected"

    async def test_get_draft_not_found(self) -> None:
        session = fake_session(get=None)
        with pytest.raises(NotFoundError):
            await cr.get_draft(session, draft_id=uuid.uuid4())

    async def test_archived_draft_is_not_found(self) -> None:
        draft = make_draft()
        draft.archived_at = NOW
        session = fake_session(get=draft)
        with pytest.raises(NotFoundError):
            await cr.get_draft(session, draft_id=draft.id)


# --- publish -------------------------------------------------------------
class TestPublish:
    async def test_publish_creates_active_course_version(self) -> None:
        draft = make_draft(
            status="approved",
            approved_by_user_id=uuid.uuid4(),
            approved_at=NOW,
            content_hash="sha256:" + "a" * 64,
        )
        # execute: max-version, deactivate, course-threshold, audit prev-hash,
        # advance-request lookup (no linked request → None)
        session = fake_session(
            get=draft,
            execute=[_result(scalar=2), _result(), _result(), _result(), _result()],
        )
        cv = await cr.publish_draft(
            session,
            draft_id=draft.id,
            tenant_id=TENANT,
            publisher_user_id=uuid.uuid4(),
            now=NOW,
        )
        assert cv.version_number == 3  # max(2) + 1
        assert cv.is_active is True
        assert cv.course_id == draft.course_id
        assert draft.status == "published"
        assert draft.published_course_version_id == cv.id

    async def test_publish_materialises_questions_and_options(self) -> None:
        draft = make_draft(
            status="approved",
            approved_by_user_id=uuid.uuid4(),
            approved_at=NOW,
            content_hash="sha256:" + "a" * 64,
        )
        session = fake_session(
            get=draft,
            execute=[_result(scalar=0), _result(), _result(), _result(), _result()],
        )
        cv = await cr.publish_draft(
            session,
            draft_id=draft.id,
            tenant_id=TENANT,
            publisher_user_id=uuid.uuid4(),
            now=NOW,
        )
        added = [c.args[0] for c in session.add.call_args_list]
        questions = [a for a in added if isinstance(a, Question)]
        options = [a for a in added if isinstance(a, AnswerOption)]
        assert len(questions) == 1
        assert questions[0].course_version_id == cv.id
        assert questions[0].question_text == "Q1?"
        assert len(options) == 3
        assert [o.is_correct for o in options] == [True, False, False]
        assert all(o.question_id == questions[0].id for o in options)

    async def test_publish_rejects_malformed_quiz_before_db_write(self) -> None:
        draft = make_draft(
            status="approved",
            approved_by_user_id=uuid.uuid4(),
            approved_at=NOW,
            content_hash="sha256:" + "a" * 64,
            body={"quiz": {"questions": []}},
        )
        session = fake_session(get=draft)
        with pytest.raises(ValidationError):
            await cr.publish_draft(
                session,
                draft_id=draft.id,
                tenant_id=TENANT,
                publisher_user_id=uuid.uuid4(),
                now=NOW,
            )
        session.add.assert_not_called()
        session.execute.assert_not_called()

    async def test_publish_from_non_approved_raises_before_db_write(self) -> None:
        draft = make_draft(status="in_review")
        session = fake_session(get=draft)
        with pytest.raises(InvalidStateTransitionError):
            await cr.publish_draft(
                session,
                draft_id=draft.id,
                tenant_id=TENANT,
                publisher_user_id=uuid.uuid4(),
                now=NOW,
            )
        session.add.assert_not_called()


# --- video fidelity attestation ------------------------------------------
class TestVideoAttestationService:
    async def test_publish_refuses_an_unattested_video(self) -> None:
        """The service must not be able to route around the domain invariant."""
        draft = _approved_draft_with_video()
        session = fake_session(get=draft)
        with pytest.raises(InvalidStateTransitionError):
            await cr.publish_draft(
                session,
                draft_id=draft.id,
                tenant_id=TENANT,
                publisher_user_id=uuid.uuid4(),
                now=NOW,
            )
        session.add.assert_not_called()

    async def test_attesting_then_publishing_succeeds(self) -> None:
        draft = _approved_draft_with_video()
        attester = uuid.uuid4()
        attest_session = fake_session(get=draft)
        await cr.attest_draft_video(
            attest_session,
            draft_id=draft.id,
            tenant_id=TENANT,
            actor_user_id=attester,
            video_asset_hash="sha256:bytes",
            attestation_text="Footage matches the approved script.",
            now=NOW,
        )
        assert draft.video_attested_by_user_id == attester
        assert draft.video_attested_at == NOW
        assert draft.video_asset_hash == "sha256:bytes"
        assert draft.video_attestation_text == "Footage matches the approved script."

        # execute: max-version, deactivate, course-threshold, audit prev-hash,
        # advance-request lookup (no linked request → None) — same shape as
        # TestPublish's video-free publish tests.
        publish_session = fake_session(
            get=draft,
            execute=[_result(scalar=0), _result(), _result(), _result(), _result()],
        )
        await cr.publish_draft(
            publish_session,
            draft_id=draft.id,
            tenant_id=TENANT,
            publisher_user_id=uuid.uuid4(),
            now=NOW,
        )
        assert draft.status == ContentDraftStatus.PUBLISHED.value

    async def test_attestation_writes_an_audit_entry(self) -> None:
        draft = _approved_draft_with_video()
        session = fake_session(get=draft)
        await cr.attest_draft_video(
            session,
            draft_id=draft.id,
            tenant_id=TENANT,
            actor_user_id=uuid.uuid4(),
            video_asset_hash="sha256:bytes",
            attestation_text="Footage matches the approved script.",
            now=NOW,
        )
        added = [c.args[0] for c in session.add.call_args_list]
        events = [a.event_type for a in added if isinstance(a, AuditLog)]
        assert f"content_draft.{ContentEvent.ATTEST_VIDEO.value}" in events

    async def test_attest_separation_of_duties(self) -> None:
        generator = uuid.uuid4()
        draft = _approved_draft_with_video(generated_by_user_id=generator)
        session = fake_session(get=draft)
        with pytest.raises(SeparationOfDutiesError):
            await cr.attest_draft_video(
                session,
                draft_id=draft.id,
                tenant_id=TENANT,
                actor_user_id=generator,
                video_asset_hash="sha256:bytes",
                attestation_text="x",
                now=NOW,
            )

    async def test_attest_wrong_tenant_not_found(self) -> None:
        draft = _approved_draft_with_video()
        session = fake_session(get=draft)
        with pytest.raises(NotFoundError):
            await cr.attest_draft_video(
                session,
                draft_id=draft.id,
                tenant_id=uuid.uuid4(),
                actor_user_id=uuid.uuid4(),
                video_asset_hash="sha256:bytes",
                attestation_text="x",
                now=NOW,
            )

    async def test_attest_requires_approved_status(self) -> None:
        # Not-yet-approved, so no approval fields — those would fail the
        # snapshot's own consistency check before attest_video ever runs.
        draft = make_draft(
            status="in_review",
            body={
                "modules": [{"heading": "x"}],
                "video": {"asset_ref": "video/course/draft.mp4", "min_watch_pct": 0},
            },
        )
        session = fake_session(get=draft)
        with pytest.raises(InvalidStateTransitionError):
            await cr.attest_draft_video(
                session,
                draft_id=draft.id,
                tenant_id=TENANT,
                actor_user_id=uuid.uuid4(),
                video_asset_hash="sha256:bytes",
                attestation_text="x",
                now=NOW,
            )


# --- list ----------------------------------------------------------------
class TestList:
    async def test_list_returns_items_and_total(self) -> None:
        draft = make_draft()
        session = fake_session(execute=[_result(scalar=1), _result(rows=[draft])])
        items, total = await cr.list_drafts(session, tenant_id=TENANT, page=1, page_size=50)
        assert total == 1
        assert list(items) == [draft]

    async def test_quarantined_filter_returns_empty(self) -> None:
        session = fake_session()
        items, total = await cr.list_drafts(session, tenant_id=TENANT, quarantined=True)
        assert (list(items), total) == ([], 0)
        session.execute.assert_not_called()


def test_parse_status_rejects_unknown() -> None:
    with pytest.raises(InvalidStateTransitionError):
        cr.parse_status("bogus")
    assert cr.parse_status("approved") is ContentDraftStatus.APPROVED
