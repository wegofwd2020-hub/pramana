"""Archiving real audit rows to a fake object store.

The uploader is injected, so these exercise selection, batching, resume, and the
bookkeeping that makes "is everything archived?" answerable from the database —
without boto3 or a network.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.audit import AuditArchiveSegment
from pramana.db.models.identity import Tenant
from pramana.services import audit_archive as svc
from pramana.services.audit import append_audit

pytestmark = pytest.mark.integration


class FakeStore:
    """Records what would have been written, plus the retention it carried."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.retentions: dict[str, datetime] = {}

    def __call__(self, data: bytes, key: str, retain_until: datetime) -> str:
        self.objects[key] = data
        self.retentions[key] = retain_until
        return key


async def seed_events(db: AsyncSession, n: int) -> uuid.UUID:
    """Append ``n`` audit entries and commit."""
    tenant = Tenant(id=uuid.uuid4(), name=f"T {uuid.uuid4()}", short_code=uuid.uuid4().hex[:12])
    db.add(tenant)
    await db.flush()
    for i in range(n):
        await append_audit(
            db,
            tenant_id=tenant.id,
            entity_type="test",
            entity_id=str(i),
            event_type="test.event",
            payload={"seq": i},
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    await db.commit()
    return tenant.id


async def _segments(db: AsyncSession) -> list[AuditArchiveSegment]:
    return list(
        (await db.execute(select(AuditArchiveSegment).order_by(AuditArchiveSegment.first_audit_id)))
        .scalars()
        .all()
    )


class TestArchiving:
    async def test_archives_pending_rows_and_records_the_segment(self, db: AsyncSession) -> None:
        await seed_events(db, 3)
        store = FakeStore()

        result = await svc.archive_pending(db, upload=store, now=_now())
        await db.commit()

        assert result is not None
        assert result.row_count == 3
        assert len(store.objects) == 1
        recorded = await _segments(db)
        assert [s.row_count for s in recorded] == [3]
        assert recorded[0].object_key in store.objects

    async def test_archived_object_is_independently_verifiable(self, db: AsyncSession) -> None:
        """Someone holding only the object can re-check it."""
        await seed_events(db, 4)
        store = FakeStore()
        await svc.archive_pending(db, upload=store, now=_now())
        await db.commit()

        body = next(iter(store.objects.values())).decode("utf-8")
        rows = [json.loads(line) for line in body.strip().split("\n")]
        assert len(rows) == 4
        assert all(r["audit_hash"] for r in rows)

    async def test_nothing_to_archive_returns_none(self, db: AsyncSession) -> None:
        await seed_events(db, 2)
        store = FakeStore()
        await svc.archive_pending(db, upload=store, now=_now())
        await db.commit()

        assert await svc.archive_pending(db, upload=store, now=_now()) is None
        assert len(store.objects) == 1

    async def test_resumes_from_the_high_water_mark(self, db: AsyncSession) -> None:
        """A second run archives only what arrived since the first."""
        tenant_id = await seed_events(db, 2)
        store = FakeStore()
        await svc.archive_pending(db, upload=store, now=_now())
        await db.commit()

        await append_audit(
            db,
            tenant_id=tenant_id,
            entity_type="test",
            entity_id="later",
            event_type="test.event",
            payload={},
            occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        await db.commit()

        second = await svc.archive_pending(db, upload=store, now=_now())
        await db.commit()

        assert second is not None
        assert second.row_count == 1
        assert len(store.objects) == 2

    async def test_consecutive_segments_chain(self, db: AsyncSession) -> None:
        """A dropped segment must be detectable, not just a dropped row."""
        tenant_id = await seed_events(db, 2)
        store = FakeStore()
        first = await svc.archive_pending(db, upload=store, now=_now())
        await db.commit()
        await append_audit(
            db,
            tenant_id=tenant_id,
            entity_type="test",
            entity_id="x",
            event_type="test.event",
            payload={},
            occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        await db.commit()
        second = await svc.archive_pending(db, upload=store, now=_now())
        await db.commit()

        assert first is not None and second is not None
        from pramana.domain.audit_archive import segments_are_contiguous

        assert segments_are_contiguous(first, second)

    async def test_batch_size_caps_one_run(self, db: AsyncSession) -> None:
        await seed_events(db, 5)
        store = FakeStore()

        first = await svc.archive_pending(db, upload=store, batch_size=2, now=_now())
        await db.commit()
        assert first is not None and first.row_count == 2

        second = await svc.archive_pending(db, upload=store, batch_size=2, now=_now())
        await db.commit()
        assert second is not None and second.row_count == 2

    async def test_retention_is_applied_to_the_object(self, db: AsyncSession) -> None:
        """Object Lock is the whole point; a missing date is a missing control."""
        await seed_events(db, 1)
        store = FakeStore()
        now = _now()
        await svc.archive_pending(db, upload=store, retention_years=7, now=now)
        await db.commit()

        retain_until = next(iter(store.retentions.values()))
        assert retain_until > now + timedelta(days=365 * 6)

    async def test_a_failed_upload_archives_nothing(self, db: AsyncSession) -> None:
        """The marker must not advance past rows that never reached the store."""
        await seed_events(db, 2)

        def explode(data: bytes, key: str, retain_until: datetime) -> str:
            raise RuntimeError("s3 is down")

        with pytest.raises(RuntimeError):
            await svc.archive_pending(db, upload=explode, now=_now())
        await db.rollback()

        assert await _segments(db) == []


def _now() -> datetime:
    return datetime(2026, 8, 29, tzinfo=UTC)
