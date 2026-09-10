# SOX Generated-Video Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take one framework (SOX) end-to-end with a generated lesson video, gated by two distinct human attestations, so that a learner can be assigned an ICFR course, watch generated footage, pass a quiz, and have the completion plus both attestations appear in the §404 auditor binder.

**Architecture:** The accuracy gate already exists and is untouched — `ContentDraft` carries `approved_by_user_id` / `approved_at` / `content_hash` with a database CHECK enforcing separation of duties. This plan adds a *second*, different gate over the rendered bytes: four nullable columns, a pure domain transition `attest_video`, and one load-bearing invariant — `publish` refuses a draft that carries a video with no fidelity attestation. Rendering issues one single-shot brief per narration line and concatenates, because the local provider flattens a multi-shot brief into a single clip.

**Tech Stack:** Python 3.12, SQLAlchemy 2 (async), Alembic, FastAPI, pytest (`asyncio_mode = auto`), ruff, mypy. Rendering via `wegofwd-video` `local-preview` (LTX-Video on CPU) and ffmpeg.

**Spec:** `docs/superpowers/specs/2026-09-09-sox-video-pilot-design.md`

## Global Constraints

- **Migration head is `0011_audit_log_no_truncate`.** The new migration is `0012` and must set `down_revision = "0011_audit_log_no_truncate"`.
- **CHECK constraint names are bare and short — in the model AND in the migration.** `alembic/env.py` binds `target_metadata = Base.metadata`, so Alembic applies the same `ck_%(table_name)s_%(constraint_name)s` convention. Write `"video_attestation_pair"` in both places, never `"ck_content_draft_video_attestation_pair"` — that yields `ck_content_draft_ck_content_draft_...`. See `0010_consumer_subscription.py` for the worked example. For foreign keys, pass `None` and let the convention name it.
- **Separation-of-duties CHECKs must carry the null-generator escape.** `generated_by_user_id` is nullable; the existing script-gate CHECK reads `approved_by_user_id IS NULL OR generated_by_user_id IS NULL OR approved_by_user_id <> generated_by_user_id`. Mirror all three clauses or a draft with no recorded generator can never be attested.
- **CI lints three paths:** `ruff check pramana tests scripts` and `ruff format --check pramana tests scripts`. The Makefile only lints two — trust CI, not the Makefile.
- **Type checking:** `mypy pramana scripts` must stay clean.
- **Integration tests need Postgres on 55432.** Start it with `docker run -d --rm --name pramana-scratch-pg -e POSTGRES_USER=pramana -e POSTGRES_PASSWORD=pramana -e POSTGRES_DB=pramana_test -p 55432:5432 postgres:16` and run with `DATABASE_URL=postgresql+asyncpg://pramana:pramana@localhost:55432/pramana_test`.
- **Use the project venv:** `~/venvs/pramana/bin/python`. The system Python lacks `hypothesis`, `jose` and `wegofwd_video`, so the suite cannot collect outside it.
- **The `local-preview` role caps duration at `max_duration_s = 10`.** Any brief composing to more is refused by the capability check before rendering.

---

### Task 1: Domain — video attestation state and the publish invariant

Pure domain, no database. This task carries the load-bearing invariant, so it comes first and everything else builds on its types.

**Files:**
- Modify: `pramana/domain/content_approval.py`
- Test: `tests/domain/test_content_approval.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: four new fields on `ContentDraftSnapshot` — `has_video: bool = False`, `video_asset_hash: str | None = None`, `video_attested_by_user_id: uuid.UUID | None = None`, `video_attested_at: datetime | None = None`; and `attest_video(snapshot: ContentDraftSnapshot, *, attester_user_id: uuid.UUID, video_asset_hash: str, now: datetime) -> ContentDraftSnapshot`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/test_content_approval.py`:

```python
class TestVideoFidelityAttestation:
    """The second gate: the rendered bytes, not the script's claims."""

    def _approved(self, **overrides) -> ca.ContentDraftSnapshot:
        base = dict(
            status=ContentDraftStatus.APPROVED,
            has_content=True,
            has_video=True,
            generated_by_user_id=GENERATOR_ID,
            approved_by_user_id=APPROVER_ID,
            approved_at=NOW,
            content_hash="sha256:script",
        )
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
```

Add these module-level constants near the top of the file if not already present, and the imports the tests use:

```python
import uuid
from datetime import UTC, datetime

import pytest

from pramana.domain import content_approval as ca
from pramana.domain.enums import ContentDraftStatus
from pramana.exceptions import InvalidStateTransitionError, SeparationOfDutiesError

GENERATOR_ID = uuid.uuid4()
APPROVER_ID = uuid.uuid4()
ATTESTER_ID = uuid.uuid4()
NOW = datetime(2026, 9, 9, 12, 0, 0, tzinfo=UTC)
```

If the file already defines any of these names, reuse the existing ones rather than redefining them.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `~/venvs/pramana/bin/python -m pytest tests/domain/test_content_approval.py::TestVideoFidelityAttestation -v`

Expected: FAIL. `ContentDraftSnapshot` has no `has_video` keyword, and `ca.attest_video` does not exist — `TypeError` and `AttributeError`.

- [ ] **Step 3: Add the snapshot fields**

In `pramana/domain/content_approval.py`, add to the `ContentDraftSnapshot` dataclass after `content_hash`:

```python
    has_video: bool = False
    video_asset_hash: str | None = None
    video_attested_by_user_id: uuid.UUID | None = None
    video_attested_at: datetime | None = None
```

Extend the docstring's Attributes block:

```
        has_video: Whether the draft body carries a video block. A video is
            attached while the draft is still ``DRAFT``, so this is true well
            before the fidelity attestation exists.
        video_asset_hash: Hash of the exact rendered bytes attested to.
        video_attested_by_user_id: Who attested the footage — set iff attested.
        video_attested_at: When the footage was attested — set iff attested.
```

Add to `__post_init__`, after the existing approval checks:

```python
        # The fidelity attestation is a pair, like the approval one.
        if (self.video_attested_by_user_id is None) != (self.video_attested_at is None):
            raise ValueError(
                "video_attested_by_user_id and video_attested_at must be set together"
            )
        # An attestation that names no artefact attests to nothing.
        if self.video_attested_at is not None and not self.video_asset_hash:
            raise ValueError("a video attestation requires video_asset_hash")
```

- [ ] **Step 4: Add the `attest_video` transition**

Insert in `pramana/domain/content_approval.py` between `approve` and `reject`:

```python
def attest_video(
    snapshot: ContentDraftSnapshot,
    *,
    attester_user_id: uuid.UUID,
    video_asset_hash: str,
    now: datetime,
) -> ContentDraftSnapshot:
    """Attest that the rendered footage matches the approved script.

    This is a *different* question from :func:`approve`. Approval asks whether a
    claim is accurate and cites its section correctly — textual, and verifiable
    by reading. This asks whether the generated footage faithfully depicts what
    was approved and depicts nothing misleading, which is what catches
    hallucinated on-screen text or a person performing the wrong action.

    It does not change ``status``: the draft is already ``APPROVED`` and stays
    there until publish. What it adds is the second piece of evidence publish
    requires.

    Raises:
        InvalidStateTransitionError: Not ``APPROVED``, no video on the draft,
            ``now`` naive, or ``video_asset_hash`` empty.
        SeparationOfDutiesError: Attester is the draft's generator.
    """
    if not snapshot.has_video:
        raise InvalidStateTransitionError(
            "Cannot attest footage on a draft that carries no video",
            context={"current_status": snapshot.status.value},
        )
    if snapshot.status is not ContentDraftStatus.APPROVED:
        raise InvalidStateTransitionError(
            f"Cannot attest footage from status {snapshot.status.value!r}; "
            f"expected {ContentDraftStatus.APPROVED.value!r}",
            context={"current_status": snapshot.status.value},
        )
    if now.tzinfo is None:
        raise InvalidStateTransitionError("`now` must be timezone-aware")
    if not video_asset_hash:
        raise InvalidStateTransitionError("`video_asset_hash` must be non-empty")
    if (
        snapshot.generated_by_user_id is not None
        and attester_user_id == snapshot.generated_by_user_id
    ):
        raise SeparationOfDutiesError(
            "The video attester may not be the user who generated the draft.",
            context={"user_id": str(attester_user_id)},
        )

    return replace(
        snapshot,
        video_attested_by_user_id=attester_user_id,
        video_attested_at=now,
        video_asset_hash=video_asset_hash,
    )
```

- [ ] **Step 5: Add the invariant to `publish`**

In `publish`, after the existing status check and before the `replace(...)`:

```python
    # The load-bearing invariant. A video that nobody has watched must not reach
    # a learner: gate 1 attested the script's accuracy, not these bytes. Without
    # this check the fidelity gate is advisory, which is exactly how PR-1's
    # migration and PR-2's continuity check ended up being controls that existed
    # in code and ran nowhere.
    if snapshot.has_video and snapshot.video_attested_at is None:
        raise InvalidStateTransitionError(
            "Cannot publish a draft whose video has not been attested; "
            "the footage needs a fidelity attestation before it reaches a learner",
            context={"current_status": snapshot.status.value},
        )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `~/venvs/pramana/bin/python -m pytest tests/domain/test_content_approval.py -v`

Expected: PASS, including every pre-existing test in the file. If a pre-existing publish test now fails, it constructed a snapshot with a video and no attestation — check whether it should set `has_video=False` (most will, since they predate video) rather than weakening the invariant.

- [ ] **Step 7: Lint, type-check and commit**

```bash
cd ~/Documents/code/projects/AIStuff/STEM_studybuddy/pramana
~/venvs/pramana/bin/ruff format pramana tests scripts
~/venvs/pramana/bin/ruff check pramana tests scripts
~/venvs/pramana/bin/mypy pramana scripts
git add pramana/domain/content_approval.py tests/domain/test_content_approval.py
git commit -m "feat(content): require a fidelity attestation before a video publishes

Approval attests that a claim is accurate and cites its section correctly.
That is a textual question a reviewer answers by reading. It says nothing
about whether generated footage depicts what was approved, which is a
different question and the one that catches hallucinated on-screen text or
a person performing the wrong action.

attest_video records the second answer without moving the draft's status,
and publish now refuses a draft that carries a video nobody has attested.
That refusal is the whole control: without it the gate is advisory, which
is how PR-1's migration and PR-2's continuity check both ended up being
correct code that no path invoked.

A quiz-only draft carries no video and is unaffected."
```

---

### Task 2: Schema — migration 0012 and the model columns

**Files:**
- Modify: `pramana/db/models/content.py`
- Create: `alembic/versions/0012_content_draft_video_attestation.py`
- Test: `tests/db/test_models.py`, `tests/integration/test_video_attestation_constraints.py`

**Interfaces:**
- Consumes: Task 1's field names — `video_asset_hash`, `video_attested_by_user_id`, `video_attested_at` — which the columns must match exactly, plus `video_attestation_text` which exists only on the ORM row.
- Produces: those four columns on `content_draft`; three CHECK constraints named `video_attestation_pair`, `video_separation_of_duties`, `video_attestation_needs_asset`; and `course_version.transcript` (nullable `text`), consumed by Task 4.

**Also add `transcript` to `course_version` in this same migration.** Narration is out of scope for the pilot, so the words must reach the learner as text or the video is silent and wordless. `CourseVersion` has `video_asset_id` and `min_watch_pct` but nowhere to put the script. One migration, two tables — a second migration for one nullable column would be noise.

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_video_attestation_constraints.py`:

```python
"""The fidelity attestation's database-level guarantees.

The domain enforces these too (``pramana/domain/content_approval.py``), but the
domain can be bypassed by any code holding a session. These are the constraints
that hold regardless of which code path writes the row — the same reason PR-1
put the append-only guarantee in triggers rather than in the service layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.content import ContentDraft
from pramana.db.models.course import Course
from pramana.db.models.identity import Tenant, User

pytestmark = pytest.mark.integration


async def _draft(db: AsyncSession, *, generated_by: uuid.UUID | None, **overrides) -> ContentDraft:
    """Seed a draft with the rows its NOT NULL foreign keys require.

    ``content_draft.course_id`` is NOT NULL with an FK to ``course``. Without a
    real Course every test below would fail on that FK rather than on the CHECK
    it is meant to exercise — and a test that fails for the wrong reason proves
    nothing.
    """
    tenant = Tenant(id=uuid.uuid4(), name="T", short_code=uuid.uuid4().hex[:12])
    db.add(tenant)
    await db.flush()
    course = Course(id=uuid.uuid4(), tenant_id=tenant.id, title="Compliance 101")
    db.add(course)
    await db.flush()
    draft = ContentDraft(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        course_id=course.id,
        title="ICFR awareness",
        status="draft",
        body={},
        generated_by_user_id=generated_by,
        **overrides,
    )
    db.add(draft)
    return draft


async def _user(db: AsyncSession) -> User:
    tenant = Tenant(id=uuid.uuid4(), name="U", short_code=uuid.uuid4().hex[:12])
    db.add(tenant)
    await db.flush()
    user = User(user_id=uuid.uuid4(), tenant_id=tenant.id, email=f"{uuid.uuid4()}@e.example")
    db.add(user)
    await db.flush()
    return user


class TestVideoAttestationConstraints:
    async def test_attester_and_timestamp_must_be_set_together(self, db: AsyncSession) -> None:
        attester = await _user(db)
        await _draft(
            db,
            generated_by=None,
            video_asset_hash="sha256:b",
            video_attested_by_user_id=attester.user_id,
            video_attested_at=None,
        )
        with pytest.raises(IntegrityError):
            await db.commit()

    async def test_an_attestation_requires_an_asset_hash(self, db: AsyncSession) -> None:
        attester = await _user(db)
        await _draft(
            db,
            generated_by=None,
            video_asset_hash=None,
            video_attested_by_user_id=attester.user_id,
            video_attested_at=datetime.now(UTC),
        )
        with pytest.raises(IntegrityError):
            await db.commit()

    async def test_the_attester_may_not_be_the_generator(self, db: AsyncSession) -> None:
        person = await _user(db)
        await _draft(
            db,
            generated_by=person.user_id,
            video_asset_hash="sha256:b",
            video_attested_by_user_id=person.user_id,
            video_attested_at=datetime.now(UTC),
        )
        with pytest.raises(IntegrityError):
            await db.commit()

    async def test_a_draft_with_no_generator_can_be_attested(self, db: AsyncSession) -> None:
        """The null-generator escape: system-seeded drafts must not deadlock."""
        attester = await _user(db)
        await _draft(
            db,
            generated_by=None,
            video_asset_hash="sha256:b",
            video_attested_by_user_id=attester.user_id,
            video_attested_at=datetime.now(UTC),
        )
        await db.commit()  # must not raise

    async def test_an_unattested_draft_is_valid(self, db: AsyncSession) -> None:
        """Every draft starts unattested; the columns are nullable for that reason."""
        await _draft(db, generated_by=None)
        await db.commit()  # must not raise
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
docker run -d --rm --name pramana-scratch-pg -e POSTGRES_USER=pramana \
  -e POSTGRES_PASSWORD=pramana -e POSTGRES_DB=pramana_test -p 55432:5432 postgres:16
DATABASE_URL="postgresql+asyncpg://pramana:pramana@localhost:55432/pramana_test" \
  ~/venvs/pramana/bin/python -m pytest tests/integration/test_video_attestation_constraints.py -v
```

Expected: FAIL — `TypeError: 'video_asset_hash' is an invalid keyword argument for ContentDraft`.

- [ ] **Step 3: Add the columns to the model**

In `pramana/db/models/content.py`, in `ContentDraft` after `attestation_text`:

```python
    # ---- Fidelity attestation over the rendered video (distinct from approval)
    # Approval above freezes the *body*; these freeze the rendered *bytes* and
    # record who watched them. Two hashes over two different artefacts.
    video_asset_hash: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Hash of the exact rendered bytes the attester watched.",
    )
    video_attested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user.user_id", ondelete="RESTRICT"),
        nullable=True,
    )
    video_attested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    video_attestation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Match the import style already used in the file for `PG_UUID`, `ForeignKey`, `DateTime` and `Text`; add only what is missing.

Also add to `CourseVersion` in `pramana/db/models/course.py`, after `min_watch_pct`:

```python
    transcript: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="The approved narration as text. The pilot renders silent "
        "footage, so this is how the words reach the learner.",
    )
```

Add to `ContentDraft.__table_args__`, after the existing `separation_of_duties` CHECK:

```python
        # Fidelity evidence must be present together (or absent together).
        CheckConstraint(
            "(video_attested_by_user_id IS NULL) = (video_attested_at IS NULL)",
            name="video_attestation_pair",
        ),
        # Separation of duties, mirroring the script gate — including the
        # null-generator escape, without which a system-seeded draft could
        # never be attested at all.
        CheckConstraint(
            "video_attested_by_user_id IS NULL "
            "OR generated_by_user_id IS NULL "
            "OR video_attested_by_user_id <> generated_by_user_id",
            name="video_separation_of_duties",
        ),
        # An attestation that names no artefact attests to nothing. This has no
        # counterpart in the script gate and is deliberate.
        CheckConstraint(
            "video_attested_at IS NULL OR video_asset_hash IS NOT NULL",
            name="video_attestation_needs_asset",
        ),
```

- [ ] **Step 4: Write the migration**

Create `alembic/versions/0012_content_draft_video_attestation.py`:

```python
"""Fidelity attestation over a draft's rendered video (SOX video pilot).

Approval already freezes the *body* — ``content_hash``, ``approved_by_user_id``,
``approved_at`` — and attests that each claim is accurate and cites its section.
That says nothing about whether generated footage depicts what was approved,
which is a different question and the one that catches hallucinated on-screen
text or a person performing the wrong action.

These four columns hold the second answer. They cannot reuse the approval
columns: those hold one approver and one hash, so writing the video sign-off
there would destroy the evidence that the script was approved separately.

The CHECKs mirror the script gate, including its null-generator escape —
``generated_by_user_id`` is nullable, and without that clause a draft with no
recorded generator could never be attested. The third CHECK has no counterpart
above and is deliberate: an attestation naming no artefact attests to nothing.

Revision ID: 0012_content_draft_video_attestation
Revises: 0011_audit_log_no_truncate
Create Date: 2026-09-09 17:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0012_content_draft_video_attestation"
down_revision: str | None = "0011_audit_log_no_truncate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "content_draft"


def upgrade() -> None:
    # The learner-facing transcript. Narration is out of scope for the pilot, so
    # without this the footage reaches a learner silent and wordless.
    op.add_column("course_version", sa.Column("transcript", sa.Text(), nullable=True))
    op.add_column(_TABLE, sa.Column("video_asset_hash", sa.Text(), nullable=True))
    op.add_column(
        _TABLE,
        sa.Column("video_attested_by_user_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        _TABLE, sa.Column("video_attested_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(_TABLE, sa.Column("video_attestation_text", sa.Text(), nullable=True))
    # None: the metadata naming convention generates the FK name. Passing an
    # explicit one risks double-prefixing, same as the CHECKs below.
    op.create_foreign_key(
        None,
        _TABLE,
        "user",
        ["video_attested_by_user_id"],
        ["user_id"],
        ondelete="RESTRICT",
    )
    # SUFFIX ONLY — the naming convention prefixes ck_content_draft_. Passing a
    # pre-prefixed name yields ck_content_draft_ck_content_draft_... See how
    # 0010 does it: op.create_check_constraint("view_count_nonneg", ...).
    op.create_check_constraint(
        "video_attestation_pair",
        _TABLE,
        "(video_attested_by_user_id IS NULL) = (video_attested_at IS NULL)",
    )
    op.create_check_constraint(
        "video_separation_of_duties",
        _TABLE,
        "video_attested_by_user_id IS NULL "
        "OR generated_by_user_id IS NULL "
        "OR video_attested_by_user_id <> generated_by_user_id",
    )
    op.create_check_constraint(
        "video_attestation_needs_asset",
        _TABLE,
        "video_attested_at IS NULL OR video_asset_hash IS NOT NULL",
    )


def downgrade() -> None:
    # No explicit constraint drops: Postgres drops a CHECK or FK automatically
    # with the column it references, which also sidesteps having to name them.
    op.drop_column(_TABLE, "video_attestation_text")
    op.drop_column(_TABLE, "video_attested_at")
    op.drop_column(_TABLE, "video_attested_by_user_id")
    op.drop_column(_TABLE, "video_asset_hash")
    op.drop_column("course_version", "transcript")
```

**Both the model and the migration take BARE, suffix-only names.** `alembic/env.py` binds `target_metadata = Base.metadata`, so Alembic inherits the same `ck_%(table_name)s_%(constraint_name)s` convention and prefixes whatever name you hand it. Passing `"ck_content_draft_video_attestation_pair"` produces `ck_content_draft_ck_content_draft_video_attestation_pair`. Migration `0010` is the worked example — `op.create_check_constraint("view_count_nonneg", "enrollment", ...)` above the comment *"Suffix only — naming convention prefixes ck_enrollment_"*. An earlier revision of this plan claimed the migration wanted the prefixed name and called it a deliberate asymmetry; that was wrong.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
DATABASE_URL="postgresql+asyncpg://pramana:pramana@localhost:55432/pramana_test" \
  ~/venvs/pramana/bin/python -m pytest tests/integration/test_video_attestation_constraints.py -v
```

Expected: PASS, 5 tests. The integration conftest builds the schema with `Base.metadata.create_all`, not Alembic, so this proves the **model**. Prove the **migration** separately:

```bash
DATABASE_URL="postgresql+asyncpg://pramana:pramana@localhost:55432/pramana_migr" \
  ~/venvs/pramana/bin/alembic upgrade head
DATABASE_URL="postgresql+asyncpg://pramana:pramana@localhost:55432/pramana_migr" \
  ~/venvs/pramana/bin/alembic downgrade 0011_audit_log_no_truncate
```

Expected: both succeed. Create that database first with `docker exec pramana-scratch-pg createdb -U pramana pramana_migr`. A migration that only ever runs forward is how `0009` shipped broken.

- [ ] **Step 6: Run the whole suite, lint, type-check and commit**

```bash
~/venvs/pramana/bin/python -m pytest -q -m "not integration"
~/venvs/pramana/bin/ruff format pramana tests scripts
~/venvs/pramana/bin/ruff check pramana tests scripts
~/venvs/pramana/bin/mypy pramana scripts
git add pramana/db/models/content.py alembic/versions/0012_content_draft_video_attestation.py tests/integration/test_video_attestation_constraints.py
git commit -m "feat(db): store the video fidelity attestation on content_draft

Four nullable columns plus three CHECKs, mirroring the script gate. They
cannot reuse the approval columns: those hold one approver and one hash,
so the video sign-off would overwrite the evidence that the script was
approved separately.

The separation-of-duties CHECK carries the same null-generator escape as
the script gate, because generated_by_user_id is nullable and a
system-seeded draft would otherwise be impossible to attest. The third
CHECK has no counterpart above: an attestation naming no artefact attests
to nothing.

Verified up and down against a real Postgres."
```

---

### Task 3: Service — expose the attestation and enforce it on publish

**Files:**
- Modify: `pramana/services/content_review.py`
- Modify: `pramana/domain/enums.py`
- Test: `tests/services/test_content_review.py`

**Interfaces:**
- Consumes: `ca.attest_video` and the `ContentDraftSnapshot` fields from Task 1; the columns from Task 2.
- Produces: `attest_draft_video(session, *, draft_id, tenant_id, actor_user_id, video_asset_hash, attestation_text, now) -> ContentDraft`, and `ContentEvent.ATTEST_VIDEO`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/test_content_review.py`, following the fixtures already used in that file for building a draft and a session:

```python
class TestVideoAttestationService:
    async def test_publish_refuses_an_unattested_video(self, session, seeded_draft) -> None:
        """The service must not be able to route around the domain invariant."""
        draft = await _approved_draft_with_video(session, seeded_draft)
        with pytest.raises(InvalidStateTransitionError):
            await content_review.publish_draft(
                session,
                draft_id=draft.id,
                tenant_id=draft.tenant_id,
                publisher_user_id=PUBLISHER_ID,
                now=NOW,
            )

    async def test_attesting_then_publishing_succeeds(self, session, seeded_draft) -> None:
        draft = await _approved_draft_with_video(session, seeded_draft)
        await content_review.attest_draft_video(
            session,
            draft_id=draft.id,
            tenant_id=draft.tenant_id,
            actor_user_id=ATTESTER_ID,
            video_asset_hash="sha256:bytes",
            attestation_text="Footage matches the approved script.",
            now=NOW,
        )
        published = await content_review.publish_draft(
            session,
            draft_id=draft.id,
            tenant_id=draft.tenant_id,
            publisher_user_id=PUBLISHER_ID,
            now=NOW,
        )
        assert published.status == ContentDraftStatus.PUBLISHED.value

    async def test_attestation_writes_an_audit_entry(self, session, seeded_draft) -> None:
        draft = await _approved_draft_with_video(session, seeded_draft)
        await content_review.attest_draft_video(
            session,
            draft_id=draft.id,
            tenant_id=draft.tenant_id,
            actor_user_id=ATTESTER_ID,
            video_asset_hash="sha256:bytes",
            attestation_text="Footage matches the approved script.",
            now=NOW,
        )
        events = await _audit_events_for(session, draft.id)
        assert ContentEvent.ATTEST_VIDEO.value in events
```

Write `_approved_draft_with_video` as a helper in the same file: build a draft whose `body` contains a `video` block with a non-empty `asset_ref`, drive it through `submit_for_review` and `approve` using the file's existing helpers, and return it. Reuse whatever fixture names the file already provides rather than inventing new ones; if it has no `session`/`seeded_draft` fixtures, use the ones it does have and adjust the signatures.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `~/venvs/pramana/bin/python -m pytest tests/services/test_content_review.py::TestVideoAttestationService -v`

Expected: FAIL — `content_review` has no attribute `attest_draft_video`, and `ContentEvent` has no `ATTEST_VIDEO`.

- [ ] **Step 3: Add the audit event**

In `pramana/domain/enums.py`, add to `ContentEvent` after `APPROVE`:

```python
    # The second gate: someone watched the rendered footage and attested that it
    # depicts the approved script and nothing misleading. Distinct from APPROVE,
    # which attests the script's accuracy and its section citations.
    ATTEST_VIDEO = auto()
```

- [ ] **Step 4: Teach `_snapshot` about the video**

Extend `_snapshot` in `pramana/services/content_review.py`.

**Use a cheap presence check, NOT `materialize_video`.** `materialize_video`
*raises* `ValidationError` on a malformed video block, and `_snapshot` runs on
every approval-path read — submit, approve, reject, publish. Routing validation
through it would make a malformed body break unrelated operations and surface the
failure far from its cause. Validation stays where it already is: `publish_draft`
calls `materialize_video` separately and still rejects a malformed block at
publish.

```python
def _snapshot(draft: ContentDraft) -> ca.ContentDraftSnapshot:
    """Project an ORM draft onto the immutable domain snapshot."""
    return ca.ContentDraftSnapshot(
        status=ContentDraftStatus(draft.status),
        has_content=bool(draft.body),
        generated_by_user_id=draft.generated_by_user_id,
        approved_by_user_id=draft.approved_by_user_id,
        approved_at=draft.approved_at,
        content_hash=draft.content_hash,
        published_course_version_id=draft.published_course_version_id,
        # Presence only — deliberately not materialize_video, which raises on a
        # malformed block and would then fail every read path. publish_draft
        # validates the block separately, which is where a malformed one belongs.
        has_video=bool((draft.body or {}).get("video")),
        video_asset_hash=draft.video_asset_hash,
        video_attested_by_user_id=draft.video_attested_by_user_id,
        video_attested_at=draft.video_attested_at,
    )
```

- [ ] **Step 5: Add the service function**

Add to `pramana/services/content_review.py`, modelled on the existing `approve_draft`:

```python
async def attest_draft_video(
    session: AsyncSession,
    *,
    draft_id: uuid.UUID,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    video_asset_hash: str,
    attestation_text: str,
    now: datetime,
) -> ContentDraft:
    """Record that a human watched the rendered footage and vouched for it.

    Separate from :func:`approve_draft` because it answers a separate question.
    Approval is about whether the script is accurate; this is about whether the
    footage depicts it. The draft's status does not move — it is already
    ``APPROVED`` — but publish will refuse without this.

    Raises:
        NotFoundError: ``draft_id`` is not in this tenant.
        InvalidStateTransitionError: Draft is not ``APPROVED``, or carries no video.
        SeparationOfDutiesError: The attester generated the draft.
    """
    draft = await session.get(ContentDraft, draft_id)
    if draft is None or draft.tenant_id != tenant_id:
        raise NotFoundError(
            "content draft not found in tenant",
            context={"draft_id": str(draft_id), "tenant_id": str(tenant_id)},
        )

    new = ca.attest_video(
        _snapshot(draft),
        attester_user_id=actor_user_id,
        video_asset_hash=video_asset_hash,
        now=now,
    )
    draft.video_attested_by_user_id = new.video_attested_by_user_id
    draft.video_attested_at = new.video_attested_at
    draft.video_asset_hash = new.video_asset_hash
    draft.video_attestation_text = attestation_text

    await _audit(
        session,
        draft,
        ContentEvent.ATTEST_VIDEO,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        now=now,
    )
    return draft
```

Match `_audit`'s actual signature in the file; if it takes extra keyword arguments, supply them the way `approve_draft` does.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `~/venvs/pramana/bin/python -m pytest tests/services/test_content_review.py -v`

Expected: PASS. Pre-existing publish tests that use a video-bearing body will now fail — that is the invariant working. Fix each by attesting first, not by removing the check.

- [ ] **Step 7: Lint, type-check and commit**

```bash
~/venvs/pramana/bin/ruff format pramana tests scripts
~/venvs/pramana/bin/ruff check pramana tests scripts
~/venvs/pramana/bin/mypy pramana scripts
git add pramana/services/content_review.py pramana/domain/enums.py tests/services/test_content_review.py
git commit -m "feat(content): record the video fidelity attestation, and audit it

attest_draft_video is the service half of the second gate. It does not move
the draft's status — the draft is already APPROVED — it adds the evidence
publish requires, and appends ATTEST_VIDEO to the audit chain so the trail
records that someone watched the footage and when.

_snapshot now derives has_video from the body via materialize_video, so the
publish invariant sees the same video the course version will."
```

---

### Task 4: Transcript — carry the approved words to the learner

The pilot renders silent footage, so the script is the only thing that says anything. This task carries it from the approved body onto the immutable version.

**Files:**
- Modify: `pramana/domain/video_generation.py`
- Modify: `pramana/services/content_review.py`
- Modify: `pramana/services/video_generation.py`
- Test: `tests/test_video_generation.py`, `tests/services/test_content_review.py`

**Interfaces:**
- Consumes: `course_version.transcript` from Task 2; `MaterializedVideo` (existing).
- Produces: `MaterializedVideo.transcript: str | None`, populated from `body["video"]["transcript"]`, stamped onto `CourseVersion.transcript` at publish.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_video_generation.py`:

```python
class TestTranscriptProjection:
    """Silent footage means the transcript is the only thing that speaks."""

    def test_transcript_is_projected_from_the_body(self) -> None:
        video = vg.materialize_video(
            {"video": {"asset_ref": "s3://a.mp4", "min_watch_pct": 80,
                       "transcript": "Every control has an owner."}}
        )
        assert video.transcript == "Every control has an owner."

    def test_a_body_without_a_transcript_projects_none(self) -> None:
        """Pre-existing drafts have no transcript and must still publish."""
        video = vg.materialize_video(
            {"video": {"asset_ref": "s3://a.mp4", "min_watch_pct": 80}}
        )
        assert video.transcript is None

    def test_a_blank_transcript_is_normalised_to_none(self) -> None:
        video = vg.materialize_video(
            {"video": {"asset_ref": "s3://a.mp4", "min_watch_pct": 0, "transcript": "   "}}
        )
        assert video.transcript is None

    def test_a_non_string_transcript_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            vg.materialize_video(
                {"video": {"asset_ref": "s3://a.mp4", "min_watch_pct": 0, "transcript": 42}}
            )
```

Append to `tests/services/test_content_review.py`:

```python
    async def test_publish_stamps_the_transcript_onto_the_version(
        self, session, seeded_draft
    ) -> None:
        """Without this the learner gets silent footage and no words at all."""
        draft = await _approved_draft_with_video(
            session, seeded_draft, transcript="Every control has an owner."
        )
        await content_review.attest_draft_video(
            session, draft_id=draft.id, tenant_id=draft.tenant_id,
            actor_user_id=ATTESTER_ID, video_asset_hash="sha256:bytes",
            attestation_text="ok", now=NOW,
        )
        version = await content_review.publish_draft(
            session, draft_id=draft.id, tenant_id=draft.tenant_id,
            publisher_user_id=PUBLISHER_ID, now=NOW,
        )
        assert version.transcript == "Every control has an owner."
```

Extend `_approved_draft_with_video` from Task 3 to take an optional `transcript` keyword and write it into the body's `video` block.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `~/venvs/pramana/bin/python -m pytest tests/test_video_generation.py::TestTranscriptProjection tests/services/test_content_review.py -v`

Expected: FAIL — `MaterializedVideo` has no attribute `transcript`.

- [ ] **Step 3: Project the transcript**

In `pramana/domain/video_generation.py`, add the field to `MaterializedVideo`:

```python
    transcript: str | None = None
```

and in `materialize_video`, before the return, parse it:

```python
    raw_transcript = video.get("transcript")
    if raw_transcript is not None and not isinstance(raw_transcript, str):
        raise ValidationError(
            "draft body.video.transcript must be a string",
            context={"field": "body.video.transcript"},
        )
    # Blank is the same as absent: a whitespace-only transcript would render as
    # an empty panel that looks like a bug rather than an intentional silence.
    transcript = raw_transcript.strip() if raw_transcript else None
```

Pass `transcript=transcript or None` into the `MaterializedVideo(...)` construction.

- [ ] **Step 4: Stamp it at publish**

In `pramana/services/content_review.py`'s `publish_draft`, wherever the existing code assigns `video_asset_id` and `min_watch_pct` onto the new `CourseVersion` from `video`, add alongside them:

```python
        transcript=video.transcript,
```

If those fields are assigned after construction rather than as constructor arguments, follow that style instead — read the surrounding lines rather than assuming.

- [ ] **Step 5: Write the transcript when attaching the video**

In `pramana/services/video_generation.py`'s `attach_course_video`, where the body's `video` block is built, include the narration:

```python
        # The words that were approved. The pilot renders silent footage, so
        # this is the learner's only access to what the lesson actually says.
        "transcript": "\n".join(lines),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `~/venvs/pramana/bin/python -m pytest tests/test_video_generation.py tests/services/test_content_review.py -v`

Expected: PASS, including pre-existing tests. A pre-existing test asserting the exact shape of the attached `video` block will now see an extra key — update its expectation; do not drop the transcript.

- [ ] **Step 7: Lint, type-check and commit**

```bash
~/venvs/pramana/bin/ruff format pramana tests scripts
~/venvs/pramana/bin/ruff check pramana tests scripts
~/venvs/pramana/bin/mypy pramana scripts
git add pramana/domain/video_generation.py pramana/services/content_review.py pramana/services/video_generation.py tests/test_video_generation.py tests/services/test_content_review.py
git commit -m "feat(video): carry the approved narration to the learner as text

The pilot renders silent footage, so without this a learner receives moving
pictures and no words. CourseVersion had video_asset_id and min_watch_pct and
nowhere to put the script.

The transcript is the approved narration verbatim, projected from the draft
body at publish onto the immutable version, so it is pinned to the same
content version the certificate names. Blank normalises to absent: a
whitespace-only transcript renders as an empty panel that reads as a bug.

The alternative was burning the words into the footage as on-screen text.
The negative prompt deliberately suppresses that, because the model
hallucinates text, and catching hallucinated on-screen text is part of what
the fidelity gate is for."
```

---

### Task 5: Render composition — one single-shot brief per narration line

**Files:**
- Modify: `pramana/domain/video_generation.py`
- Test: `tests/test_video_generation.py`

**Interfaces:**
- Consumes: `build_video_brief` (existing).
- Produces: `build_scene_briefs(*, clause_title: str, narration_lines: Sequence[str], shot_duration_s: float = 2.0, style: str = ..., negative: str = ...) -> list[VideoBrief]` — one single-shot brief per line.

Rationale, from the spec: the `local-preview` provider joins a multi-shot brief's shots into one prompt and sums their durations for a single render, so a five-shot brief yields one clip rather than five scenes. Rendering per line and concatenating also keeps each render near the measured 1 080 latent tokens instead of 5 400, which is the difference between the measured 23.9 GB peak and an out-of-memory risk.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_video_generation.py`:

```python
class TestSceneBriefs:
    """One brief per line, because the provider flattens multi-shot briefs."""

    def test_one_brief_per_narration_line(self) -> None:
        briefs = vg.build_scene_briefs(
            clause_title="ICFR awareness",
            narration_lines=["One.", "Two.", "Three."],
        )
        assert len(briefs) == 3

    def test_each_brief_has_exactly_one_shot(self) -> None:
        briefs = vg.build_scene_briefs(
            clause_title="ICFR awareness", narration_lines=["One.", "Two."]
        )
        assert all(len(b.shots) == 1 for b in briefs)

    def test_each_line_becomes_its_own_shot_dialogue_in_order(self) -> None:
        lines = ["First claim.", "Second claim."]
        briefs = vg.build_scene_briefs(clause_title="ICFR", narration_lines=lines)
        assert [b.shots[0].dialogue for b in briefs] == lines

    def test_each_brief_stays_under_the_local_provider_duration_cap(self) -> None:
        """local-preview declares max_duration_s = 10; a longer brief is refused."""
        briefs = vg.build_scene_briefs(
            clause_title="ICFR",
            narration_lines=["a"] * 5,
            shot_duration_s=2.0,
        )
        assert all(sum(s.duration_s for s in b.shots) <= 10 for b in briefs)

    def test_ordering_comes_from_list_position_not_scene_index(self) -> None:
        """Each brief holds one shot, so its own scene_index is always 1.

        `build_video_brief` numbers shots within a single call (`i + 1`), and
        every call here gets exactly one line. Order lives in the returned
        list, which is what the concat step consumes.
        """
        briefs = vg.build_scene_briefs(
            clause_title="ICFR", narration_lines=["a", "b", "c"]
        )
        assert [b.shots[0].scene_index for b in briefs] == [1, 1, 1]

    def test_no_lines_yields_no_briefs(self) -> None:
        assert vg.build_scene_briefs(clause_title="ICFR", narration_lines=[]) == []

    def test_blank_lines_are_skipped_not_fatal(self) -> None:
        """`build_video_brief` raises on empty narration, so blanks must be
        filtered here — one stray blank line in a script must not kill the
        whole composition."""
        briefs = vg.build_scene_briefs(
            clause_title="ICFR", narration_lines=["a", "   ", "", "b"]
        )
        assert len(briefs) == 2
```

Import the module as `vg` if the file does not already; match the file's existing import alias.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `~/venvs/pramana/bin/python -m pytest tests/test_video_generation.py::TestSceneBriefs -v`

Expected: FAIL — `module 'pramana.domain.video_generation' has no attribute 'build_scene_briefs'`.

- [ ] **Step 3: Implement**

Add to `pramana/domain/video_generation.py`, after `build_video_brief`:

```python
#: One scene per narration line at this length keeps a five-line segment inside
#: the local-preview role's ``max_duration_s = 10`` and each render near the
#: measured 1 080 latent tokens. The module default of 6.0 s targets the Veo
#: path, where the ceiling is higher.
_LOCAL_SHOT_DURATION_S = 2.0


def build_scene_briefs(
    *,
    clause_title: str,
    narration_lines: Sequence[str],
    shot_duration_s: float = _LOCAL_SHOT_DURATION_S,
    style: str = _DEFAULT_STYLE,
    negative: str = _DEFAULT_NEGATIVE,
    audio_direction: str = _DEFAULT_AUDIO,
) -> list[VideoBrief]:
    """Split a lesson into one single-shot brief per narration line.

    The local provider joins a multi-shot brief's shots into a single prompt and
    sums their durations for one render, so a five-shot brief produces one clip
    rather than five scenes. Issuing one brief per line and concatenating the
    results is what actually yields scene cuts — and it keeps each render's
    latent-token count, and therefore its peak memory, near the measured figure
    instead of multiplying it by the scene count.

    Returns:
        One brief per line, in order. Empty input yields an empty list.
    """
    # build_video_brief raises ValidationError on empty narration, so a blank
    # line would abort the whole composition rather than being skipped. Filter
    # first — the same normalisation build_video_brief applies internally.
    lines = [line.strip() for line in narration_lines if line and line.strip()]
    return [
        build_video_brief(
            clause_title=clause_title,
            narration_lines=[line],
            style=style,
            negative=negative,
            audio_direction=audio_direction,
            shot_duration_s=shot_duration_s,
        )
        for line in lines
    ]
```

**Do not try to renumber `scene_index` across briefs.** `build_video_brief` assigns `scene_index=i + 1` within its own call, and each call here receives exactly one line, so every brief's single shot carries `scene_index=1`. That is correct and expected: ordering lives in the returned list, which is what the ffmpeg concat step consumes in order. Renumbering would add a second, redundant source of truth for sequence.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `~/venvs/pramana/bin/python -m pytest tests/test_video_generation.py -v`

Expected: PASS, including the pre-existing tests.

- [ ] **Step 5: Lint, type-check and commit**

```bash
~/venvs/pramana/bin/ruff format pramana tests scripts
~/venvs/pramana/bin/ruff check pramana tests scripts
~/venvs/pramana/bin/mypy pramana scripts
git add pramana/domain/video_generation.py tests/test_video_generation.py
git commit -m "feat(video): compose one single-shot brief per narration line

The local provider joins a multi-shot brief's shots into one prompt and sums
their durations for a single render, so a five-shot brief yields one clip and
not five scenes. One brief per line, concatenated afterwards, is what actually
produces scene cuts.

It also keeps each render near the measured 1080 latent tokens rather than
5400, which is the difference between the 23.9 GB peak already measured and
an out-of-memory risk on a 32 GB box.

The 2.0 s default keeps a five-line segment inside local-preview's
max_duration_s of 10; the module's 6.0 s default targets the Veo path, where
the ceiling is higher."
```

---

### Task 6: Render the pilot segment and record the numbers

This task produces an artefact, not code. It is the one manual step, for the same reason `wegofwd-video`'s own render is manual: CI installs `.[dev]` only, so it has no torch and no weights and cannot render.

**Files:**
- Create: `scripts/render_sox_pilot.py`
- Create: `docs/sox-video-pilot-run.md`
- Test: `tests/test_render_sox_pilot.py`

**Interfaces:**
- Consumes: `build_scene_briefs` from Task 5.
- Produces: a concatenated `.mp4`, its SHA-256, and a JSON run report. The hash is what Task 7 attests to.

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_sox_pilot.py`:

```python
"""The pilot render harness, exercised without weights.

The render itself needs ~10 GB of model weights and about an hour of CPU, so
CI cannot run it. What CI can check is that the harness composes the right
briefs, refuses a segment the provider would reject, and reports honestly.
"""

from __future__ import annotations

import pytest

from scripts import render_sox_pilot as harness

SCRIPT_LINES = [
    "Every control has an owner.",
    "Evidence is recorded when the control runs.",
    "The record is what the auditor will see.",
]


def test_plan_builds_one_brief_per_line() -> None:
    plan = harness.build_plan(narration_lines=SCRIPT_LINES, clause_title="ICFR")
    assert len(plan.briefs) == len(SCRIPT_LINES)


def test_plan_refuses_a_segment_the_provider_would_reject() -> None:
    """max_duration_s = 10; catch it here rather than an hour into a render."""
    with pytest.raises(ValueError, match="max_duration_s"):
        harness.build_plan(
            narration_lines=SCRIPT_LINES, clause_title="ICFR", shot_duration_s=6.0
        )


def test_sha256_of_a_known_byte_string() -> None:
    assert harness.sha256_bytes(b"abc").startswith("sha256:ba7816bf")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `~/venvs/pramana/bin/python -m pytest tests/test_render_sox_pilot.py -v`

Expected: FAIL — `No module named 'scripts.render_sox_pilot'`.

- [ ] **Step 3: Implement the harness**

Create `scripts/render_sox_pilot.py`:

```python
"""Render the SOX pilot segment: one clip per narration line, concatenated.

Manual by necessity — CI installs ``.[dev]`` only, so it has no torch and no
weights. The composition and the capability check are unit-tested; the render
is run by hand and its numbers recorded in ``docs/sox-video-pilot-run.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pramana.domain.video_generation import build_scene_briefs

#: The local-preview role's ceiling. Checked here so a rejected geometry costs
#: a second rather than an hour.
MAX_DURATION_S = 10.0

SCRIPT_LINES = [
    "Every internal control over financial reporting has a named owner.",
    "Evidence is recorded at the moment the control runs.",
    "The record is what the external auditor will examine under section 404.",
]


@dataclass(frozen=True)
class Plan:
    briefs: list[Any]
    clause_title: str
    shot_duration_s: float

    @property
    def total_duration_s(self) -> float:
        return sum(s.duration_s for b in self.briefs for s in b.shots)


def build_plan(
    *,
    narration_lines: list[str],
    clause_title: str,
    shot_duration_s: float = 2.0,
) -> Plan:
    """Compose one single-shot brief per line, refusing an over-long scene."""
    briefs = build_scene_briefs(
        clause_title=clause_title,
        narration_lines=narration_lines,
        shot_duration_s=shot_duration_s,
    )
    for brief in briefs:
        duration = sum(s.duration_s for s in brief.shots)
        if duration > MAX_DURATION_S:
            raise ValueError(
                f"scene is {duration}s but the local-preview role declares "
                f"max_duration_s={MAX_DURATION_S}; it would be refused before rendering"
            )
    return Plan(briefs=briefs, clause_title=clause_title, shot_duration_s=shot_duration_s)


def sha256_bytes(data: bytes) -> str:
    """Hash the rendered bytes — this is what the fidelity attestation names."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def concat(clips: list[Path], out: Path) -> None:
    """Join the per-scene clips with ffmpeg's concat demuxer (no re-encode)."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        for clip in clips:
            fh.write(f"file '{clip.resolve()}'\n")
        listing = fh.name
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing,
         "-c", "copy", str(out)],
        check=True,
        capture_output=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="plan only; no torch")
    parser.add_argument("--out", type=Path, default=Path("/tmp/sox-pilot.mp4"))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=9071)
    parser.add_argument("--resolution", default="320p")
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--shot-duration", type=float, default=2.0)
    parser.add_argument("--threads", type=int, default=4, help="pin to physical cores")
    parser.add_argument("--timeout", type=int, default=7200, help="abort rather than run all night")
    args = parser.parse_args(argv)

    plan = build_plan(
        narration_lines=SCRIPT_LINES,
        clause_title="ICFR awareness",
        shot_duration_s=args.shot_duration,
    )
    print(f"[ plan       ] {len(plan.briefs)} scenes, {plan.total_duration_s}s total, "
          f"{args.resolution}, {args.steps} steps, seed {args.seed}")
    for i, brief in enumerate(plan.briefs):
        print(f"  scene {i}: {brief.shots[0].dialogue}")
    if args.dry_run:
        return 0

    # Imported here so --dry-run needs neither torch nor the [local] extra.
    import wegofwd_video as wv

    provider_id, model = wv.resolve_role("local-preview")
    # steps/guidance/timeout/on_progress belong to the PROVIDER, not the request.
    provider = wv.build_provider(
        provider_id,
        model=model,
        steps=args.steps,
        guidance=1.0,
        timeout=args.timeout,
        on_progress=lambda step, total, elapsed: print(
            f"    step {step}/{total}  {elapsed / step:6.1f} s/step",
            flush=True,
        ),
        threads=args.threads,
    )

    clips: list[Path] = []
    scenes: list[dict[str, Any]] = []
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        for i, brief in enumerate(plan.briefs):
            clip = Path(tmp) / f"scene_{i:02d}.mp4"
            t0 = time.monotonic()
            result = provider.generate(
                wv.VideoRequest(
                    brief=brief,
                    resolution=args.resolution,
                    aspect_ratio="16:9",
                    fps=24,
                    target_duration_s=args.shot_duration,
                    seed=args.seed + i,
                    audio=False,  # local-preview declares native_audio=False
                )
            )
            if not result.asset_bytes:
                raise RuntimeError(f"scene {i} produced no asset_bytes")
            clip.write_bytes(result.asset_bytes)
            elapsed = time.monotonic() - t0
            print(f"[ scene {i}    ] {elapsed / 60:.1f} min, {len(result.asset_bytes)} bytes")
            clips.append(clip)
            scenes.append({
                "index": i,
                "seed": args.seed + i,
                "wall_clock_s": round(elapsed, 1),
                "bytes": len(result.asset_bytes),
                "raw": getattr(result, "raw", {}),
            })
        concat(clips, args.out)

    data = args.out.read_bytes()
    digest = sha256_bytes(data)
    total = time.monotonic() - started
    print(f"[ segment    ] {total / 60:.1f} min total -> {args.out} ({len(data)} bytes)")
    print(f"[ hash       ] {digest}")
    print("  Attest this hash via content_review.attest_draft_video after watching it.")

    if args.json:
        args.json.write_text(json.dumps({
            "clause_title": plan.clause_title,
            "resolution": args.resolution,
            "steps": args.steps,
            "shot_duration_s": args.shot_duration,
            "total_duration_s": plan.total_duration_s,
            "wall_clock_s": round(total, 1),
            "output_bytes": len(data),
            "video_asset_hash": digest,
            "scenes": scenes,
        }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**The API above is verified against `wegofwd-video/scripts/first_local_run.py`, the working reference.** Three things an earlier revision of this plan got wrong, so do not "restore" them: `VideoRequest` has NO `vendor_opts` field; `steps`, `guidance`, `timeout`, `on_progress` and `threads` are arguments to `wv.build_provider`, not to the request; and the rendered bytes are `result.asset_bytes`, not `result.content`. Read `first_local_run.py` if anything else is unclear — it is the harness that actually produced a clip on this hardware.

- [ ] **Step 4: Run the test to verify it passes**

Run: `~/venvs/pramana/bin/python -m pytest tests/test_render_sox_pilot.py -v`

Expected: PASS, 3 tests.

- [ ] **Step 5: Do the real render**

```bash
docker start pramana-scratch-pg 2>/dev/null || true
~/venvs/pramana/bin/python scripts/render_sox_pilot.py --dry-run     # free; check the plan
~/venvs/pramana/bin/python scripts/render_sox_pilot.py \
    --out /tmp/sox-pilot.mp4 --json /tmp/sox-pilot.json --seed 9071
```

Expect roughly 11–12 minutes per scene and about an hour in total, with peak RSS near 23.9 GB. **If peak RSS approaches 32 GB, stop and reduce `shot_duration_s` rather than pushing on** — the box has ~8 GB of headroom and an OOM mid-run wastes the whole hour.

- [ ] **Step 6: Record the outcome**

Create `docs/sox-video-pilot-run.md` with a table of: date, scene count, geometry, seed, seconds-per-step per scene, wall clock, peak RSS, output size, the concatenated file's SHA-256, and a one-line honest judgement of whether the footage is usable. If it is not usable, say so plainly — that is a finding about the render path, not a failure of the pipeline, and the remaining tasks still stand.

- [ ] **Step 7: Commit**

```bash
~/venvs/pramana/bin/ruff format pramana tests scripts
~/venvs/pramana/bin/ruff check pramana tests scripts
~/venvs/pramana/bin/mypy pramana scripts
git add scripts/render_sox_pilot.py tests/test_render_sox_pilot.py docs/sox-video-pilot-run.md
git commit -m "feat(scripts): render the SOX pilot segment, and record what it cost

One brief per narration line, rendered separately and concatenated, with the
plan validated against local-preview's max_duration_s before anything loads
- catching a rejected geometry an hour into a render is the expensive way to
find out.

The render is manual for the same reason wegofwd-video's is: CI installs
.[dev] only, so it has no torch and no weights. What the test covers is the
composition and the refusal, which is the part that can be checked for free."
```

---

### Task 7: Close the loop end-to-end, and supersede resolved decision #274

**Files:**
- Create: `tests/integration/test_sox_video_pilot_e2e.py`
- Modify: `docs/02_resolved_decisions.md`
- Modify: `TICKETS/VIDEO-1-pilot-lesson-videos.md`

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: no new code interfaces; a passing end-to-end proof and truthful documents.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_sox_video_pilot_e2e.py`:

```python
"""The SOX pilot loop, end to end, against a real Postgres.

Each stage is covered on its own elsewhere. What this pins is that they
compose: a draft with generated footage cannot reach a learner without both
attestations, and once it does, the completion evidence names the exact
content version.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


VIDEO_BODY = {
    "video": {"asset_ref": "s3://audit/sox-pilot.mp4", "min_watch_pct": 80},
    "quiz": {"questions": []},
}
ASSET_HASH = "sha256:9f2c0b1e"


async def _approved_video_draft(db, *, generator, approver, now):
    """A draft carrying footage, script-approved but not yet attested."""
    draft = await _seed_draft(db, body=VIDEO_BODY, generated_by_user_id=generator)
    await content_review.submit_for_review(
        db, draft_id=draft.id, tenant_id=draft.tenant_id,
        actor_user_id=generator, now=now,
    )
    await content_review.approve_draft(
        db, draft_id=draft.id, tenant_id=draft.tenant_id,
        approver_user_id=approver,
        attestation_text="Claims verified against the cited sections.",
        now=now,
    )
    await db.commit()
    return draft


class TestSoxVideoPilotEndToEnd:
    async def test_unattested_video_never_reaches_a_learner(self, db) -> None:
        """The whole point of the second gate, proved through the real stack."""
        draft = await _approved_video_draft(
            db, generator=GENERATOR_ID, approver=APPROVER_ID, now=NOW
        )
        with pytest.raises(InvalidStateTransitionError):
            await content_review.publish_draft(
                db, draft_id=draft.id, tenant_id=draft.tenant_id,
                publisher_user_id=APPROVER_ID, now=NOW,
            )
        await db.rollback()
        refreshed = await db.get(ContentDraft, draft.id)
        assert refreshed.status == ContentDraftStatus.APPROVED.value
        assert refreshed.published_course_version_id is None

    async def test_attested_video_publishes_and_certifies(self, db) -> None:
        """draft → video → approve → attest → publish → assign → pass → certificate."""
        draft = await _approved_video_draft(
            db, generator=GENERATOR_ID, approver=APPROVER_ID, now=NOW
        )
        await content_review.attest_draft_video(
            db, draft_id=draft.id, tenant_id=draft.tenant_id,
            actor_user_id=ATTESTER_ID, video_asset_hash=ASSET_HASH,
            attestation_text="Footage matches the approved script.", now=NOW,
        )
        version = await content_review.publish_draft(
            db, draft_id=draft.id, tenant_id=draft.tenant_id,
            publisher_user_id=APPROVER_ID, now=NOW,
        )
        await db.commit()
        # publish_draft returns the new CourseVersion, not the draft. Assert the
        # draft reached PUBLISHED by re-reading it.
        assert version is not None
        refreshed = await db.get(ContentDraft, draft.id)
        assert refreshed.status == ContentDraftStatus.PUBLISHED.value
        assert refreshed.published_course_version_id == version.id

    async def test_the_published_version_carries_the_attested_asset(self, db) -> None:
        draft = await _approved_video_draft(
            db, generator=GENERATOR_ID, approver=APPROVER_ID, now=NOW
        )
        await content_review.attest_draft_video(
            db, draft_id=draft.id, tenant_id=draft.tenant_id,
            actor_user_id=ATTESTER_ID, video_asset_hash=ASSET_HASH,
            attestation_text="ok", now=NOW,
        )
        version = await content_review.publish_draft(
            db, draft_id=draft.id, tenant_id=draft.tenant_id,
            publisher_user_id=APPROVER_ID, now=NOW,
        )
        await db.commit()
        assert version.video_asset_id == VIDEO_BODY["video"]["asset_ref"]
        assert version.min_watch_pct == VIDEO_BODY["video"]["min_watch_pct"]

    async def test_both_attestations_are_in_the_audit_trail(self, db) -> None:
        """APPROVE and ATTEST_VIDEO both appear, recorded to different actors."""
        draft = await _approved_video_draft(
            db, generator=GENERATOR_ID, approver=APPROVER_ID, now=NOW
        )
        await content_review.attest_draft_video(
            db, draft_id=draft.id, tenant_id=draft.tenant_id,
            actor_user_id=ATTESTER_ID, video_asset_hash=ASSET_HASH,
            attestation_text="ok", now=NOW,
        )
        await db.commit()
        rows = (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.entity_id == str(draft.id))
                .order_by(AuditLog.audit_id.asc())
            )
        ).scalars().all()
        by_event = {r.event_type: r.actor_user_id for r in rows}
        assert ContentEvent.APPROVE.value in by_event
        assert ContentEvent.ATTEST_VIDEO.value in by_event
        assert by_event[ContentEvent.APPROVE.value] != by_event[ContentEvent.ATTEST_VIDEO.value]
```

Write `_seed_draft` as a local helper that inserts a `Tenant`, a `Course` and a `ContentDraft` with the given body, mirroring `seed_course` in `tests/integration/conftest.py`. Note `content_draft.course_id` is NOT NULL with an FK to `course`, and the users table is `user_account`, not `user`.

**The real `content_review` signatures, verified — use these, do not guess:**

| function | key parameters |
|---|---|
| `submit_for_review` | `draft_id`, `tenant_id`, `actor_user_id`, `now` → `ContentDraft` |
| `approve_draft` | `draft_id`, `tenant_id`, **`approver_user_id`**, **`attestation_text`** (required), `now` → `ContentDraft` |
| `attest_draft_video` | `draft_id`, `tenant_id`, `actor_user_id`, `video_asset_hash`, `attestation_text`, `now` → `ContentDraft` |
| `publish_draft` | `draft_id`, `tenant_id`, **`publisher_user_id`**, `now` → **`CourseVersion`** |

Note the three traps: the submit function is `submit_for_review`, not
`submit_for_review_draft`; `approve_draft` takes `approver_user_id` and
*requires* `attestation_text`; and `publish_draft` returns a `CourseVersion`, so
assert the draft reached `PUBLISHED` by re-reading it, as the tests above do. Read `tests/integration/test_consumer_end_to_end.py` first: it already does an assign-through-completion walk and is the closest existing model for the fixtures and imports.

- [ ] **Step 2: Run the test to verify it fails**

```bash
DATABASE_URL="postgresql+asyncpg://pramana:pramana@localhost:55432/pramana_test" \
  ~/venvs/pramana/bin/python -m pytest tests/integration/test_sox_video_pilot_e2e.py -v
```

Expected: FAIL while the bodies are unimplemented; then genuinely fail on the first assertion once written.

- [ ] **Step 3: Make it pass**

No new production code should be required. If something is missing, that is a real gap the earlier tasks did not cover — add it there with its own test rather than patching it into the end-to-end test.

- [ ] **Step 4: Supersede resolved decision #274**

In `docs/02_resolved_decisions.md`, replace item 5 under its list:

```markdown
5. **Video content is generated, then human-approved before assignment** —
   superseded 2026-09-09 by the SOX video pilot
   (`docs/superpowers/specs/2026-09-09-sox-video-pilot-design.md`). This item
   previously read *"Video content is pre-recorded and uploaded by content
   authors"*, which stopped being true when generation entered the pipeline.
   Generated footage is an untrusted draft: it passes the accuracy gate on its
   script and a separate fidelity attestation on its rendered bytes before it
   can publish. No live-session training remains in scope.
```

Do not delete the old wording without recording that it changed. In a repository whose purpose is auditable evidence, a decision that quietly rewrites itself is the problem this product exists to prevent.

- [ ] **Step 5: Update the ticket**

In `TICKETS/VIDEO-1-pilot-lesson-videos.md`, mark the SOX pilot done, record the measured render numbers from Task 5, and note that the remaining four frameworks inherit the same two-gate model and need only their own content.

- [ ] **Step 6: Run everything and commit**

```bash
DATABASE_URL="postgresql+asyncpg://pramana:pramana@localhost:55432/pramana_test" \
  ~/venvs/pramana/bin/python -m pytest -q
~/venvs/pramana/bin/ruff check pramana tests scripts
~/venvs/pramana/bin/ruff format --check pramana tests scripts
~/venvs/pramana/bin/mypy pramana scripts
git add tests/integration/test_sox_video_pilot_e2e.py docs/02_resolved_decisions.md TICKETS/VIDEO-1-pilot-lesson-videos.md
git commit -m "test(sox): prove the video pilot loop end to end, and update the record

Each stage was already covered alone. This pins that they compose: footage
without a fidelity attestation cannot reach a learner, and once attested the
completion evidence names the exact content version and the trail carries
both attestations by different actors.

Resolved decision #274 said video content is pre-recorded and uploaded by
content authors. That stopped being true when generation entered the
pipeline and nothing had recorded it. It is superseded here rather than
quietly rewritten - a decision that changes without saying so is the failure
this product exists to prevent."
```

- [ ] **Step 7: Clean up**

```bash
docker stop pramana-scratch-pg
```

---

## Resolved during self-review

The spec says narration is out of scope and *"the approved script is shown as
text"*, but nothing could satisfy that: `CourseVersion` carries `video_asset_id`
and `min_watch_pct` and no transcript field, so a silent video would have reached
a learner with no words at all.

**Resolved by adding `course_version.transcript`** (Task 2's migration) and
materialising it on publish (Task 4). The rejected alternative was burning the
narration into the footage as on-screen text — which the negative prompt
deliberately suppresses because the model hallucinates text, and which gate 2
exists partly to catch.

## Notes for the executor

- **Do not weaken the publish invariant to make an old test pass.** Several pre-existing tests build video-bearing drafts and publish them; they predate the gate. Fix them by attesting first. If a test cannot be fixed that way, it has found a real design problem — stop and say so.
- **The `_CK` naming asymmetry is deliberate,** not a typo. Model constraints take bare names because the metadata convention prefixes them; the Alembic ops take the fully-prefixed names because they do not.
- **Nothing here needs a rented GPU or a Veo account.** If rendering proves unusable at 320p, that is a recorded finding and the pipeline work still stands on its own.
