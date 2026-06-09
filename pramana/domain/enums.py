"""Domain-level enumerations.

These are pure value objects — no database or framework imports — so they
can be re-used by the persistence layer, the API layer, and the test suite
without coupling.
"""

from __future__ import annotations

from enum import StrEnum, auto


class AssignmentStatus(StrEnum):
    """Lifecycle state of a course assignment.

    See Section 7 of ``docs/02_resolved_decisions.md`` for the full state
    machine. Terminal states are :attr:`PASSED`, :attr:`BLOCKED`,
    :attr:`CANCELLED`, and :attr:`EXPIRED` — no transitions out of them are
    permitted.
    """

    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    @property
    def is_terminal(self) -> bool:
        """True if no transitions out of this state are permitted."""
        return self in _TERMINAL_STATES

    @property
    def is_active(self) -> bool:
        """True if the assignment counts as 'currently being worked on'."""
        return self == AssignmentStatus.IN_PROGRESS

    @property
    def started_cooldown(self) -> bool:
        """True if reaching this state begins the course re-assignment cooldown.

        Per FR8 / Section 4 of the resolved decisions doc, both ``PASSED`` and
        ``BLOCKED`` start the cooldown. ``CANCELLED`` and ``EXPIRED`` do not —
        the user remains eligible for immediate re-assignment in those cases.
        """
        return self in {AssignmentStatus.PASSED, AssignmentStatus.BLOCKED}


_TERMINAL_STATES: frozenset[AssignmentStatus] = frozenset(
    {
        AssignmentStatus.PASSED,
        AssignmentStatus.BLOCKED,
        AssignmentStatus.CANCELLED,
        AssignmentStatus.EXPIRED,
    }
)


class AttemptOutcome(StrEnum):
    """Outcome of a single quiz attempt."""

    IN_PROGRESS = "in_progress"
    # "pass" is an outcome value, not a credential — silence S105 (ruff) + B105 (bandit).
    PASS = "pass"  # noqa: S105  # nosec B105
    FAIL = "fail"


class TerminalReason(StrEnum):
    """Why an assignment reached a terminal state.

    Captured on the assignment record at the moment of terminal transition;
    used by audit reporting and exception reports.
    """

    PASSED = "passed"
    MAX_ATTEMPTS_FAILED = "max_attempts_failed"
    CANCELLED_BY_ADMIN = "cancelled_by_admin"
    EXPIRED_DUE_DATE = "expired_due_date"


class TransitionEvent(StrEnum):
    """Events that drive state transitions on the assignment.

    Exposed as discriminated values so audit-log entries can name the
    triggering event without re-deriving it from the before/after states.
    """

    START_ATTEMPT = auto()
    SUBMIT_ATTEMPT = auto()
    CANCEL = auto()
    EXPIRE = auto()


class ContentDraftStatus(StrEnum):
    """Lifecycle state of an AI-drafted training-content draft.

    See ``docs/03_ai_drafted_human_approved_content.md`` §3. Generation is a
    drafting aid only — no draft is assignable until a human ``APPROVED`` it
    and it is ``PUBLISHED`` into an immutable :class:`CourseVersion`. Terminal
    states are :attr:`PUBLISHED` and :attr:`REJECTED`.

    :attr:`RECEIVED` is the entry state for content that arrived as a *Mentible
    Consumable Package* (Mentible ADR-011 §7): an externally generated package
    that passed signature + ``content_hash`` verification but is **untrusted**
    until a human reviews it. It joins the same review path as a locally
    authored :attr:`DRAFT`. Both are valid pre-review entry states.
    """

    RECEIVED = "received"
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"

    @property
    def is_terminal(self) -> bool:
        """True if no transitions out of this state are permitted."""
        return self in _CONTENT_TERMINAL_STATES

    @property
    def is_approved(self) -> bool:
        """True once a human has approved the content (APPROVED or PUBLISHED)."""
        return self in {ContentDraftStatus.APPROVED, ContentDraftStatus.PUBLISHED}

    @property
    def is_pre_review(self) -> bool:
        """True for the entry states a draft can be submitted for review from.

        Both a locally authored :attr:`DRAFT` and an ingested :attr:`RECEIVED`
        package are submittable; everything else has already entered (or left)
        the review workflow.
        """
        return self in {ContentDraftStatus.DRAFT, ContentDraftStatus.RECEIVED}


_CONTENT_TERMINAL_STATES: frozenset[ContentDraftStatus] = frozenset(
    {ContentDraftStatus.PUBLISHED, ContentDraftStatus.REJECTED}
)


class QuestionType(StrEnum):
    """Allowed kinds of quiz question.

    Pure value object shared by the persistence layer (the ``question_type``
    column) and the publish-time materialization that destructures a draft's
    quiz into :class:`~pramana.db.models.course.Question` rows.
    """

    SINGLE_SELECT = "single_select"
    TRUE_FALSE = "true_false"

    @classmethod
    def values(cls) -> list[str]:
        """The string values, for building the SQL enum."""
        return [t.value for t in cls]


class ContentRequestStatus(StrEnum):
    """Lifecycle state of a commissioned content (Package) Request.

    The **Create** side of the pipeline (US-PLATFORM-0003): an author commissions
    content, Pramana pushes a Package Request to Mentible, and the request tracks
    the work until the manufactured package lands in the review queue and is
    published. ``FAILED`` is terminal (push rejected / generation abandoned).

    Mirrors the ingested draft's progress: once a package arrives the request is
    ``RECEIVED`` and its ``draft_id`` points at the resulting
    :class:`~pramana.db.models.content.ContentDraft`.
    """

    REQUESTED = "requested"
    GENERATING = "generating"
    RECEIVED = "received"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """True if no transitions out of this state are permitted."""
        return self in {ContentRequestStatus.PUBLISHED, ContentRequestStatus.FAILED}


class ContentEvent(StrEnum):
    """Events that drive the content-approval state machine.

    Named on each audit-log entry so the trail records *why* a draft moved,
    without re-deriving it from before/after states.
    """

    # In-process generation (ADR-013): Pramana drafted this content itself via
    # the wegofwd-llm seam (distinct from RECEIVE, an ingested Mentible package).
    GENERATE = auto()
    RECEIVE = auto()
    SUBMIT_FOR_REVIEW = auto()
    REQUEST_CHANGES = auto()
    APPROVE = auto()
    REJECT = auto()
    PUBLISH = auto()


class ContentRequestEvent(StrEnum):
    """Events on the content-request lifecycle, named on each audit entry."""

    COMMISSION = auto()
    PUSH = auto()
    REGENERATE = auto()
    RECEIVE = auto()
    ADVANCE = auto()
    FAIL = auto()
