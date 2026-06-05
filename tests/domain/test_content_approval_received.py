"""The RECEIVED entry state for ingested packages (Mentible ADR-011 §7)."""

from __future__ import annotations

import uuid

import pytest

from pramana.domain.content_approval import (
    ContentDraftSnapshot,
    approve,
    received_package_snapshot,
    submit_for_review,
    utcnow,
)
from pramana.domain.enums import ContentDraftStatus
from pramana.exceptions import InvalidStateTransitionError


def test_received_is_pre_review() -> None:
    assert ContentDraftStatus.RECEIVED.is_pre_review
    assert ContentDraftStatus.DRAFT.is_pre_review
    assert not ContentDraftStatus.IN_REVIEW.is_pre_review
    assert not ContentDraftStatus.RECEIVED.is_terminal


def test_received_snapshot_has_content_no_generator() -> None:
    snap = received_package_snapshot()
    assert snap.status is ContentDraftStatus.RECEIVED
    assert snap.has_content
    assert snap.generated_by_user_id is None


def test_received_can_be_submitted_for_review() -> None:
    snap = received_package_snapshot()
    after = submit_for_review(snap)
    assert after.status is ContentDraftStatus.IN_REVIEW


def test_received_then_approved_by_any_user() -> None:
    # No in-house generator, so SoD reduces to "any human may approve".
    in_review = submit_for_review(received_package_snapshot())
    approved = approve(
        in_review,
        approver_user_id=uuid.uuid4(),
        content_hash="sha256:" + "a" * 64,
        now=utcnow(),
    )
    assert approved.status is ContentDraftStatus.APPROVED


def test_cannot_submit_an_empty_received_snapshot() -> None:
    snap = ContentDraftSnapshot(status=ContentDraftStatus.RECEIVED, has_content=False)
    with pytest.raises(InvalidStateTransitionError, match="empty"):
        submit_for_review(snap)
