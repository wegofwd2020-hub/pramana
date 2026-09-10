"""Tests for :mod:`pramana.domain.content_approval`.

A pure-function state machine, so we drive it with hand-crafted flows (the §3
worked path) plus :mod:`hypothesis` properties for the invariants — chiefly that
terminal states are dead ends and separation of duties is never bypassable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pramana.domain import content_approval as ca
from pramana.domain.content_approval import (
    ContentDraftSnapshot,
    approve,
    initial_draft_snapshot,
    publish,
    reject,
    request_changes,
    submit_for_review,
)
from pramana.domain.enums import ContentDraftStatus
from pramana.exceptions import (
    InvalidStateTransitionError,
    SeparationOfDutiesError,
)

NOW = datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC)
NAIVE = datetime(2026, 6, 5, 12, 0, 0)
GENERATOR = uuid.uuid4()
APPROVER = uuid.uuid4()
HASH = "sha256:" + "ab" * 8
VERSION_ID = uuid.uuid4()

# Constants for video attestation tests
GENERATOR_ID = uuid.uuid4()
APPROVER_ID = uuid.uuid4()
ATTESTER_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Happy path (§3 worked flow)
# ---------------------------------------------------------------------------
def test_full_lifecycle_draft_to_published() -> None:
    s = initial_draft_snapshot(generated_by_user_id=GENERATOR)
    assert s.status is ContentDraftStatus.DRAFT

    s = submit_for_review(s)
    assert s.status is ContentDraftStatus.IN_REVIEW

    s = approve(s, approver_user_id=APPROVER, content_hash=HASH, now=NOW)
    assert s.status is ContentDraftStatus.APPROVED
    assert s.approved_by_user_id == APPROVER
    assert s.approved_at == NOW
    assert s.content_hash == HASH

    s = publish(s, course_version_id=VERSION_ID)
    assert s.status is ContentDraftStatus.PUBLISHED
    assert s.published_course_version_id == VERSION_ID
    assert s.status.is_terminal


def test_request_changes_returns_to_draft() -> None:
    s = submit_for_review(initial_draft_snapshot(generated_by_user_id=GENERATOR))
    s = request_changes(s)
    assert s.status is ContentDraftStatus.DRAFT


def test_reject_is_terminal() -> None:
    s = submit_for_review(initial_draft_snapshot())
    s = reject(s)
    assert s.status is ContentDraftStatus.REJECTED
    assert s.status.is_terminal


# ---------------------------------------------------------------------------
# Separation of duties (SOX)
# ---------------------------------------------------------------------------
def test_approver_may_not_be_generator() -> None:
    s = submit_for_review(initial_draft_snapshot(generated_by_user_id=GENERATOR))
    with pytest.raises(SeparationOfDutiesError):
        approve(s, approver_user_id=GENERATOR, content_hash=HASH, now=NOW)


def test_separation_not_enforced_when_generator_unknown() -> None:
    # A system-seeded draft (no attributable generator) can be approved by anyone.
    s = submit_for_review(initial_draft_snapshot(generated_by_user_id=None))
    s = approve(s, approver_user_id=APPROVER, content_hash=HASH, now=NOW)
    assert s.status is ContentDraftStatus.APPROVED


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------
def test_cannot_submit_empty_draft() -> None:
    s = initial_draft_snapshot(has_content=False)
    with pytest.raises(InvalidStateTransitionError):
        submit_for_review(s)


def test_approve_requires_in_review_and_tz_aware_now_and_hash() -> None:
    draft = initial_draft_snapshot(generated_by_user_id=GENERATOR)
    with pytest.raises(InvalidStateTransitionError):
        approve(draft, approver_user_id=APPROVER, content_hash=HASH, now=NOW)  # DRAFT

    in_review = submit_for_review(draft)
    with pytest.raises(InvalidStateTransitionError):
        approve(in_review, approver_user_id=APPROVER, content_hash=HASH, now=NAIVE)
    with pytest.raises(InvalidStateTransitionError):
        approve(in_review, approver_user_id=APPROVER, content_hash="", now=NOW)


def test_publish_requires_approved() -> None:
    s = submit_for_review(initial_draft_snapshot())
    with pytest.raises(InvalidStateTransitionError):
        publish(s, course_version_id=VERSION_ID)


# ---------------------------------------------------------------------------
# Snapshot invariants
# ---------------------------------------------------------------------------
def test_approved_snapshot_requires_approval_fields() -> None:
    with pytest.raises(ValueError):
        ContentDraftSnapshot(status=ContentDraftStatus.APPROVED, has_content=True)


def test_published_snapshot_requires_version_id() -> None:
    with pytest.raises(ValueError):
        ContentDraftSnapshot(
            status=ContentDraftStatus.PUBLISHED,
            has_content=True,
            approved_by_user_id=APPROVER,
            approved_at=NOW,
            content_hash=HASH,
        )


def test_in_review_requires_content() -> None:
    with pytest.raises(ValueError):
        ContentDraftSnapshot(status=ContentDraftStatus.IN_REVIEW, has_content=False)


# ---------------------------------------------------------------------------
# Property: terminal states are dead ends
# ---------------------------------------------------------------------------
def _terminal_snapshot(status: ContentDraftStatus) -> ContentDraftSnapshot:
    if status is ContentDraftStatus.PUBLISHED:
        return ContentDraftSnapshot(
            status=status,
            has_content=True,
            approved_by_user_id=APPROVER,
            approved_at=NOW,
            content_hash=HASH,
            published_course_version_id=VERSION_ID,
        )
    return ContentDraftSnapshot(status=ContentDraftStatus.REJECTED, has_content=True)


@given(status=st.sampled_from([ContentDraftStatus.PUBLISHED, ContentDraftStatus.REJECTED]))
def test_no_transition_out_of_terminal(status: ContentDraftStatus) -> None:
    s = _terminal_snapshot(status)
    assert s.status.is_terminal
    with pytest.raises(InvalidStateTransitionError):
        submit_for_review(s)
    with pytest.raises(InvalidStateTransitionError):
        request_changes(s)
    with pytest.raises(InvalidStateTransitionError):
        approve(s, approver_user_id=APPROVER, content_hash=HASH, now=NOW)
    with pytest.raises(InvalidStateTransitionError):
        reject(s)
    with pytest.raises(InvalidStateTransitionError):
        publish(s, course_version_id=VERSION_ID)


class TestVideoFidelityAttestation:
    """The second gate: the rendered bytes, not the script's claims."""

    def _approved(self, **overrides) -> ca.ContentDraftSnapshot:
        base = {
            "status": ContentDraftStatus.APPROVED,
            "has_content": True,
            "has_video": True,
            "generated_by_user_id": GENERATOR_ID,
            "approved_by_user_id": APPROVER_ID,
            "approved_at": NOW,
            "content_hash": "sha256:script",
        }
        base.update(overrides)
        return ca.ContentDraftSnapshot(**base)

    def test_publish_refuses_a_draft_whose_video_is_not_attested(self) -> None:
        """The load-bearing invariant. Without it, gate 2 is advisory."""
        with pytest.raises(InvalidStateTransitionError) as ei:
            ca.publish(self._approved(), course_version_id=uuid.uuid4())
        assert "attest" in str(ei.value).lower()

    def test_publish_allows_a_draft_with_no_video_at_all(self) -> None:
        """A quiz-only course is valid and must not be blocked by this gate."""
        version_id = uuid.uuid4()
        new = ca.publish(self._approved(has_video=False), course_version_id=version_id)
        assert new.status is ContentDraftStatus.PUBLISHED

    def test_publish_allows_an_attested_video(self) -> None:
        attested = ca.attest_video(
            self._approved(),
            attester_user_id=ATTESTER_ID,
            video_asset_hash="sha256:bytes",
            now=NOW,
        )
        new = ca.publish(attested, course_version_id=uuid.uuid4())
        assert new.status is ContentDraftStatus.PUBLISHED

    def test_the_attester_may_not_be_the_generator(self) -> None:
        with pytest.raises(SeparationOfDutiesError):
            ca.attest_video(
                self._approved(),
                attester_user_id=GENERATOR_ID,
                video_asset_hash="sha256:bytes",
                now=NOW,
            )

    def test_a_draft_with_no_generator_can_still_be_attested(self) -> None:
        """generated_by_user_id is nullable; system-seeded drafts must not deadlock."""
        snapshot = self._approved(generated_by_user_id=None)
        attested = ca.attest_video(
            snapshot, attester_user_id=ATTESTER_ID, video_asset_hash="sha256:b", now=NOW
        )
        assert attested.video_attested_by_user_id == ATTESTER_ID

    def test_cannot_attest_a_draft_that_carries_no_video(self) -> None:
        with pytest.raises(InvalidStateTransitionError):
            ca.attest_video(
                self._approved(has_video=False),
                attester_user_id=ATTESTER_ID,
                video_asset_hash="sha256:bytes",
                now=NOW,
            )

    def test_cannot_attest_before_the_script_is_approved(self) -> None:
        """Fidelity is 'matches the approved script' — there must be one."""
        in_review = ca.ContentDraftSnapshot(
            status=ContentDraftStatus.IN_REVIEW,
            has_content=True,
            has_video=True,
            generated_by_user_id=GENERATOR_ID,
        )
        with pytest.raises(InvalidStateTransitionError):
            ca.attest_video(
                in_review, attester_user_id=ATTESTER_ID, video_asset_hash="sha256:b", now=NOW
            )

    def test_attestation_requires_a_non_empty_asset_hash(self) -> None:
        with pytest.raises(InvalidStateTransitionError):
            ca.attest_video(
                self._approved(), attester_user_id=ATTESTER_ID, video_asset_hash="", now=NOW
            )

    def test_attestation_requires_an_aware_timestamp(self) -> None:
        with pytest.raises(InvalidStateTransitionError):
            ca.attest_video(
                self._approved(),
                attester_user_id=ATTESTER_ID,
                video_asset_hash="sha256:b",
                now=datetime(2026, 9, 9, 12, 0, 0),
            )

    def test_attestation_fields_must_be_set_together(self) -> None:
        with pytest.raises(ValueError):
            ca.ContentDraftSnapshot(
                status=ContentDraftStatus.APPROVED,
                has_content=True,
                has_video=True,
                approved_by_user_id=APPROVER_ID,
                approved_at=NOW,
                content_hash="sha256:script",
                video_attested_by_user_id=ATTESTER_ID,
                video_attested_at=None,
            )

    def test_script_approval_survives_video_attestation(self) -> None:
        """Gate 2 must not overwrite gate 1's evidence."""
        attested = ca.attest_video(
            self._approved(),
            attester_user_id=ATTESTER_ID,
            video_asset_hash="sha256:bytes",
            now=NOW,
        )
        assert attested.approved_by_user_id == APPROVER_ID
        assert attested.content_hash == "sha256:script"

    def test_a_published_snapshot_cannot_carry_an_unattested_video(self) -> None:
        """The invariant must hold even when nobody replayed the transition."""
        with pytest.raises(ValueError, match="fidelity attestation"):
            ca.ContentDraftSnapshot(
                status=ContentDraftStatus.PUBLISHED,
                has_content=True,
                has_video=True,
                approved_by_user_id=APPROVER_ID,
                approved_at=NOW,
                content_hash="sha256:script",
                published_course_version_id=uuid.uuid4(),
            )

    def test_approved_may_carry_an_unattested_video(self) -> None:
        """The gap between the two gates is a legal state, not a violation."""
        snapshot = ca.ContentDraftSnapshot(
            status=ContentDraftStatus.APPROVED,
            has_content=True,
            has_video=True,
            approved_by_user_id=APPROVER_ID,
            approved_at=NOW,
            content_hash="sha256:script",
        )
        assert snapshot.video_attested_at is None


class TestVideoProducerSeparationOfDuties:
    """Gate 2 must bar whoever produced the footage, not only the script's author.

    `attach_course_video` takes a `generated_by_user_id` and writes it to the
    audit payload; `draft.generated_by_user_id` means the *script* author and is
    never updated by it. So before this rule, Carol could render the footage and
    then attest her own bytes, because the check compared her against Alice.
    """

    PRODUCER_ID = uuid.uuid4()

    def _approved(self, **overrides) -> ca.ContentDraftSnapshot:
        base = {
            "status": ContentDraftStatus.APPROVED,
            "has_content": True,
            "has_video": True,
            "generated_by_user_id": GENERATOR_ID,
            "video_generated_by_user_id": self.PRODUCER_ID,
            "approved_by_user_id": APPROVER_ID,
            "approved_at": NOW,
            "content_hash": "sha256:script",
        }
        base.update(overrides)
        return ca.ContentDraftSnapshot(**base)

    def test_the_footage_producer_may_not_attest_their_own_bytes(self) -> None:
        """The finding: Carol renders, Carol must not sign off."""
        with pytest.raises(SeparationOfDutiesError, match="produced the footage"):
            ca.attest_video(
                self._approved(),
                attester_user_id=self.PRODUCER_ID,
                video_asset_hash="sha256:bytes",
                now=NOW,
            )

    def test_the_script_author_is_still_barred(self) -> None:
        """The pre-existing rule must not be loosened by adding the new one."""
        with pytest.raises(SeparationOfDutiesError):
            ca.attest_video(
                self._approved(),
                attester_user_id=GENERATOR_ID,
                video_asset_hash="sha256:bytes",
                now=NOW,
            )

    def test_a_third_party_may_attest(self) -> None:
        """Neither author nor producer — the intended reviewer."""
        attested = ca.attest_video(
            self._approved(),
            attester_user_id=ATTESTER_ID,
            video_asset_hash="sha256:bytes",
            now=NOW,
        )
        assert attested.video_attested_by_user_id == ATTESTER_ID

    def test_a_draft_with_no_recorded_producer_is_unaffected(self) -> None:
        """Legacy drafts predate the column; the rule must not retro-block them."""
        attested = ca.attest_video(
            self._approved(video_generated_by_user_id=None),
            attester_user_id=ATTESTER_ID,
            video_asset_hash="sha256:bytes",
            now=NOW,
        )
        assert attested.video_attested_by_user_id == ATTESTER_ID
