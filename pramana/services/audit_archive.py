"""Mirror the audit log to WORM object storage.

The hash chain proves the log has not been altered *where it sits*. It says
nothing about a log that has been dropped, restored from an old backup, or lost
with the database. Archival to write-once storage is the answer to that, and it
is the last of the three defences in ``docs/00_architecture.md`` §2.3 to be
built.

The transactional shell around the pure segment format in
:mod:`pramana.domain.audit_archive`. The upload is injected — the same seam
pattern as the video uploader — so this is testable without boto3 or a network.

**Ordering matters here.** The object is written *before* the segment row is
recorded. Getting that backwards would let a crash between the two leave the
high-water mark pointing past rows that never reached the store, and the gap
would be permanent: the next run resumes after the mark and never looks back.
The chosen order can only produce the opposite failure — an object written twice
— and the key is deterministic, so the retry overwrites rather than duplicating.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.audit import AuditArchiveSegment, AuditLog
from pramana.domain.audit_archive import SegmentManifest, build_segment
from pramana.services.audit_query import to_audit_row

#: ``(body, key, retain_until) -> stored key``. Injected so the service is
#: testable without object storage; ``retain_until`` is what the store applies
#: as its Object Lock retention.
ArchiveUploader = Callable[[bytes, str, datetime], str]

#: Rows per segment. Large enough that objects are not tiny, small enough that a
#: run is bounded and a retry is cheap.
DEFAULT_BATCH_SIZE = 5_000


async def archive_pending(
    session: AsyncSession,
    *,
    upload: ArchiveUploader,
    now: datetime,
    batch_size: int = DEFAULT_BATCH_SIZE,
    retention_years: int = 7,
) -> SegmentManifest | None:
    """Archive the next batch of unarchived rows. Returns its manifest, or ``None``.

    ``None`` means the archive is already current — the caller can stop, or a
    scheduler can treat it as a no-op tick.

    Raises:
        Exception: Whatever ``upload`` raises. Nothing is recorded in that case,
            so the next run retries the same range.
    """
    mark = await high_water_mark(session)
    rows = (
        (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.audit_id > mark)
                .order_by(AuditLog.audit_id.asc())
                .limit(batch_size)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None

    segment = build_segment([to_audit_row(row) for row in rows])
    retain_until = now + timedelta(days=365 * retention_years)

    # Store first, record second — see the module docstring.
    upload(segment.body, segment.key, retain_until)

    session.add(
        AuditArchiveSegment(
            id=uuid.uuid4(),
            first_audit_id=segment.manifest.first_audit_id,
            last_audit_id=segment.manifest.last_audit_id,
            row_count=segment.manifest.row_count,
            prev_audit_hash=segment.manifest.prev_audit_hash,
            head_audit_hash=segment.manifest.head_audit_hash,
            object_key=segment.key,
            retain_until=retain_until,
        )
    )
    await session.flush()
    return segment.manifest


async def high_water_mark(session: AsyncSession) -> int:
    """The highest ``audit_id`` known to be archived (``0`` if none)."""
    mark = (
        await session.execute(select(func.max(AuditArchiveSegment.last_audit_id)))
    ).scalar_one_or_none()
    return int(mark or 0)


async def unarchived_count(session: AsyncSession) -> int:
    """How many rows are not yet archived — the operational "am I current?"."""
    mark = await high_water_mark(session)
    return int(
        (
            await session.execute(
                select(func.count()).select_from(AuditLog).where(AuditLog.audit_id > mark)
            )
        ).scalar_one()
    )
