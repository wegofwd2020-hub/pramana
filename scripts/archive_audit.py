#!/usr/bin/env python3
"""Mirror pending audit rows to WORM object storage.

Run on a schedule (cron, a scheduled container task) or by hand. There is no
Celery app in this repo, and archival does not need one: it is idempotent,
resumable, and safe to run twice, so scheduling is a deployment concern rather
than something the application has to own.

Usage::

    DATABASE_URL=... python scripts/archive_audit.py            # archive everything pending
    DATABASE_URL=... python scripts/archive_audit.py --status   # report, change nothing
    DATABASE_URL=... python scripts/archive_audit.py --dry-run  # build segments, upload nothing

Or ``make archive-audit``.

Each run loops until the archive is current, one segment per iteration, so a
long backlog drains without needing a large batch size.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pramana.config import get_settings
from pramana.domain.assignment_state import utcnow
from pramana.exceptions import PramanaError
from pramana.services.audit_archive import (
    DEFAULT_BATCH_SIZE,
    archive_pending,
    high_water_mark,
    unarchived_count,
)
from pramana.services.storage import build_s3_audit_archiver


def _discarding_uploader(data: bytes, key: str, retain_until: datetime) -> str:
    """A --dry-run uploader: exercises segment building, stores nothing."""
    print(f"  would store {key} ({len(data)} bytes, retain until {retain_until:%Y-%m-%d})")
    return key


async def _run(*, batch_size: int, status_only: bool, dry_run: bool) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            pending = await unarchived_count(session)
            mark = await high_water_mark(session)
            print(f"archived through audit_id {mark}; {pending} row(s) pending")
            if status_only or pending == 0:
                return 0

            upload = _discarding_uploader if dry_run else build_s3_audit_archiver(settings)
            segments = 0
            while True:
                manifest = await archive_pending(
                    session,
                    upload=upload,
                    now=utcnow(),
                    batch_size=batch_size,
                    retention_years=settings.default_record_retention_years,
                )
                if manifest is None:
                    break
                segments += 1
                print(
                    f"  segment {manifest.first_audit_id}-{manifest.last_audit_id} "
                    f"({manifest.row_count} rows)"
                )
                if dry_run:
                    # Nothing was stored, so nothing may be recorded either.
                    await session.rollback()
                    break
            if dry_run:
                print("dry run — nothing stored, nothing recorded")
            else:
                await session.commit()
                print(f"archived {segments} segment(s)")
    except PramanaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="rows per segment"
    )
    parser.add_argument(
        "--status", action="store_true", help="report progress and exit without archiving"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build the next segment and report it without storing or recording",
    )
    args = parser.parse_args(argv)
    return asyncio.run(
        _run(batch_size=args.batch_size, status_only=args.status, dry_run=args.dry_run)
    )


if __name__ == "__main__":
    raise SystemExit(main())
