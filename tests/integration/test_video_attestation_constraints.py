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
    # Unique name: tenant.name is unique, so a test needing two users
    # would otherwise fail on uq_tenant_name rather than on the CHECK
    # it is actually exercising.
    tenant = Tenant(
        id=uuid.uuid4(), name=f"U-{uuid.uuid4().hex[:8]}", short_code=uuid.uuid4().hex[:12]
    )
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

    async def test_the_footage_producer_may_not_attest_it(self, db: AsyncSession) -> None:
        """The database backstop for gate 2's real question.

        The domain enforces this too, but the domain can be bypassed by any code
        holding a session — the same reason the other constraints in this file
        exist.
        """
        producer = await _user(db)
        await _draft(
            db,
            generated_by=None,
            video_generated_by_user_id=producer.user_id,
            video_asset_hash="sha256:b",
            video_attested_by_user_id=producer.user_id,
            video_attested_at=datetime.now(UTC),
        )
        with pytest.raises(IntegrityError):
            await db.commit()

    async def test_a_third_party_may_attest_the_footage(self, db: AsyncSession) -> None:
        producer = await _user(db)
        attester = await _user(db)
        await _draft(
            db,
            generated_by=None,
            video_generated_by_user_id=producer.user_id,
            video_asset_hash="sha256:b",
            video_attested_by_user_id=attester.user_id,
            video_attested_at=datetime.now(UTC),
        )
        await db.commit()  # must not raise

    async def test_a_draft_with_no_recorded_producer_can_be_attested(
        self, db: AsyncSession
    ) -> None:
        """Drafts predating the column must not be retro-blocked."""
        attester = await _user(db)
        await _draft(
            db,
            generated_by=None,
            video_generated_by_user_id=None,
            video_asset_hash="sha256:b",
            video_attested_by_user_id=attester.user_id,
            video_attested_at=datetime.now(UTC),
        )
        await db.commit()  # must not raise

    async def test_an_unattested_draft_is_valid(self, db: AsyncSession) -> None:
        """Every draft starts unattested; the columns are nullable for that reason."""
        await _draft(db, generated_by=None)
        await db.commit()  # must not raise
