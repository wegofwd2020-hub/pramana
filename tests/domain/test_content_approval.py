"""Tests for :mod:`pramana.domain.content_approval`.

A pure-function state machine, so we drive it with hand-crafted flows (the §3
worked path) plus :mod:`hypothesis` properties for the invariants — chiefly that
terminal states are dead ends and separation of duties is never bypassable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from hypothesis import given, strategies as st

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

NOW = datetime(2026, 6, 5, 12, 0, 0, tzinfo=timezone.utc)
NAIVE = datetime(2026, 6, 5, 12, 0, 0)
GENERATOR = uuid.uuid4()
APPROVER = uuid.uuid4()
HASH = "sha256:" + "ab" * 8
VERSION_ID = uuid.uuid4()


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
