"""Content-approval state machine.

Pure domain module: no database, no HTTP, no I/O. Encodes §3 of
``docs/03_ai_drafted_human_approved_content.md`` — the lifecycle that keeps
AI-drafted training content a *drafting aid* rather than the source of truth:

    DRAFT ──submit──▶ IN_REVIEW ──approve──▶ APPROVED ──publish──▶ PUBLISHED
      ▲                   │  └────reject────▶ REJECTED (terminal)
      └──request_changes──┘

No draft is assignable until a human has **approved** it and it is **published**
into an immutable :class:`CourseVersion`. Two SOX-relevant rules live here:

* **Separation of duties** — the approver must not be the user who generated the
  draft (raises :class:`SeparationOfDutiesError`).
* **Approval is evidence** — approving records the approver, the timestamp, and a
  ``content_hash`` of exactly what was approved (frozen thereafter).

Like the assignment machine, this is a function over an immutable
:class:`ContentDraftSnapshot`, so it is exhaustively testable without a database.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from pramana.domain.enums import ContentDraftStatus
from pramana.exceptions import (
    InvalidStateTransitionError,
    SeparationOfDutiesError,
)


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ContentDraftSnapshot:
    """Immutable snapshot of a content draft's approval state.

    Attributes:
        status: Current lifecycle state.
        has_content: Whether a content body has been attached. A draft cannot be
            submitted for review or approved while empty.
        generated_by_user_id: User who triggered AI generation (or hand-authored
            the draft). ``None`` for system-seeded drafts with no attributable
            generator. Used for the separation-of-duties check on approval.
        approved_by_user_id: Approver — set iff approved.
        approved_at: When the content was approved — set iff approved.
        content_hash: Hash of the exact approved content body — set iff approved.
        published_course_version_id: The immutable ``CourseVersion`` this draft
            materialised into — set iff ``PUBLISHED``.
    """

    status: ContentDraftStatus
    has_content: bool = False
    generated_by_user_id: uuid.UUID | None = None
    approved_by_user_id: uuid.UUID | None = None
    approved_at: datetime | None = None
    content_hash: str | None = None
    published_course_version_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        approved = self.status.is_approved  # APPROVED or PUBLISHED
        approval_fields_set = (
            self.approved_by_user_id is not None
            and self.approved_at is not None
            and bool(self.content_hash)
        )
        if approved and not approval_fields_set:
            raise ValueError(
                f"status {self.status.value!r} is approved but approval fields "
                "(approved_by_user_id / approved_at / content_hash) are not all set"
            )
        if not approved and (
            self.approved_by_user_id is not None
            or self.approved_at is not None
            or self.content_hash is not None
        ):
            raise ValueError(
                f"status {self.status.value!r} is not approved but approval "
                "fields are set"
            )

        is_published = self.status is ContentDraftStatus.PUBLISHED
        if is_published and self.published_course_version_id is None:
            raise ValueError("PUBLISHED draft must reference a course version")
        if not is_published and self.published_course_version_id is not None:
            raise ValueError(
                f"status {self.status.value!r} is not published but references a "
                "course version"
            )

        # Content must exist once a draft is under review or beyond.
        if not self.has_content and self.status in {
            ContentDraftStatus.IN_REVIEW,
            ContentDraftStatus.APPROVED,
            ContentDraftStatus.PUBLISHED,
        }:
            raise ValueError(
                f"status {self.status.value!r} requires content but has_content is False"
            )


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------
def submit_for_review(snapshot: ContentDraftSnapshot) -> ContentDraftSnapshot:
    """Move a draft into review. Permitted only from ``DRAFT`` and only when a
    content body has been attached.

    Raises:
        InvalidStateTransitionError: Not in ``DRAFT``, or no content attached.
    """
    if snapshot.status is not ContentDraftStatus.DRAFT:
        raise InvalidStateTransitionError(
            f"Cannot submit for review from status {snapshot.status.value!r}; "
            f"expected {ContentDraftStatus.DRAFT.value!r}",
            context={"current_status": snapshot.status.value},
        )
    if not snapshot.has_content:
        raise InvalidStateTransitionError(
            "Cannot submit an empty draft for review",
            context={"current_status": snapshot.status.value},
        )
    return replace(snapshot, status=ContentDraftStatus.IN_REVIEW)


def request_changes(snapshot: ContentDraftSnapshot) -> ContentDraftSnapshot:
    """Send a draft back to ``DRAFT`` for revision. Permitted from ``IN_REVIEW``.

    Raises:
        InvalidStateTransitionError: Not in ``IN_REVIEW``.
    """
    if snapshot.status is not ContentDraftStatus.IN_REVIEW:
        raise InvalidStateTransitionError(
            f"Cannot request changes from status {snapshot.status.value!r}; "
            f"expected {ContentDraftStatus.IN_REVIEW.value!r}",
            context={"current_status": snapshot.status.value},
        )
    return replace(snapshot, status=ContentDraftStatus.DRAFT)


def approve(
    snapshot: ContentDraftSnapshot,
    *,
    approver_user_id: uuid.UUID,
    content_hash: str,
    now: datetime,
) -> ContentDraftSnapshot:
    """Approve the content under review.

    The approver attests the content is accurate; we freeze it by recording the
    approver, the timestamp, and a hash of exactly what was approved. **The
    approver must not be the user who generated the draft** (SOX separation of
    duties).

    Raises:
        InvalidStateTransitionError: Not in ``IN_REVIEW``, ``now`` naive, or
            ``content_hash`` empty.
        SeparationOfDutiesError: Approver is the draft's generator.
    """
    if snapshot.status is not ContentDraftStatus.IN_REVIEW:
        raise InvalidStateTransitionError(
            f"Cannot approve from status {snapshot.status.value!r}; "
            f"expected {ContentDraftStatus.IN_REVIEW.value!r}",
            context={"current_status": snapshot.status.value},
        )
    if now.tzinfo is None:
        raise InvalidStateTransitionError("`now` must be timezone-aware")
    if not content_hash:
        raise InvalidStateTransitionError("`content_hash` must be non-empty")
    if (
        snapshot.generated_by_user_id is not None
        and approver_user_id == snapshot.generated_by_user_id
    ):
        raise SeparationOfDutiesError(
            "The approver may not be the user who generated the draft.",
            context={"user_id": str(approver_user_id)},
        )

    return replace(
        snapshot,
        status=ContentDraftStatus.APPROVED,
        approved_by_user_id=approver_user_id,
        approved_at=now,
        content_hash=content_hash,
    )


def reject(snapshot: ContentDraftSnapshot) -> ContentDraftSnapshot:
    """Reject content under review (terminal). Permitted from ``IN_REVIEW``.

    Raises:
        InvalidStateTransitionError: Not in ``IN_REVIEW``.
    """
    if snapshot.status is not ContentDraftStatus.IN_REVIEW:
        raise InvalidStateTransitionError(
            f"Cannot reject from status {snapshot.status.value!r}; "
            f"expected {ContentDraftStatus.IN_REVIEW.value!r}",
            context={"current_status": snapshot.status.value},
        )
    return replace(snapshot, status=ContentDraftStatus.REJECTED)


def publish(
    snapshot: ContentDraftSnapshot,
    *,
    course_version_id: uuid.UUID,
) -> ContentDraftSnapshot:
    """Materialise approved content into an immutable course version (terminal).

    Permitted only from ``APPROVED``. The caller has created the
    :class:`CourseVersion` row; we record its id on the draft.

    Raises:
        InvalidStateTransitionError: Not in ``APPROVED``.
    """
    if snapshot.status is not ContentDraftStatus.APPROVED:
        raise InvalidStateTransitionError(
            f"Cannot publish from status {snapshot.status.value!r}; "
            f"expected {ContentDraftStatus.APPROVED.value!r}",
            context={"current_status": snapshot.status.value},
        )
    return replace(
        snapshot,
        status=ContentDraftStatus.PUBLISHED,
        published_course_version_id=course_version_id,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def initial_draft_snapshot(
    *,
    generated_by_user_id: uuid.UUID | None = None,
    has_content: bool = True,
) -> ContentDraftSnapshot:
    """Construct a snapshot for a freshly created draft (``DRAFT`` status)."""
    return ContentDraftSnapshot(
        status=ContentDraftStatus.DRAFT,
        has_content=has_content,
        generated_by_user_id=generated_by_user_id,
    )


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(tz=timezone.utc)
