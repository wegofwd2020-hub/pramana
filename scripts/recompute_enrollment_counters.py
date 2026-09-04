"""Reconcile enrollment counters against the play_session / consumer_attempt event tables.

Usage:
    python -m scripts.recompute_enrollment_counters [--dry-run] [--tenant consumer]
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.consumer import Enrollment
from pramana.db.session import session_scope
from pramana.services.consumer.enrollment import recompute_counters


async def recompute_all(session: AsyncSession, *, dry_run: bool) -> list[dict[str, Any]]:
    drift: list[dict[str, Any]] = []
    ids = list((await session.execute(select(Enrollment.id))).scalars())
    for enrollment_id in ids:
        before = await session.get(Enrollment, enrollment_id)
        prev = (before.view_count, before.completion_count, before.best_score_pct)
        after = await recompute_counters(session, enrollment_id=enrollment_id)
        now = (after.view_count, after.completion_count, after.best_score_pct)
        if prev != now:
            drift.append({"enrollment_id": enrollment_id, "before": prev, "after": now})
    if dry_run:
        await session.rollback()
    return drift


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tenant", default="consumer")
    args = parser.parse_args()
    async with session_scope() as session:
        drift = await recompute_all(session, dry_run=args.dry_run)
    print(
        f"{len(drift)} enrollment(s) drifted" + (" (dry-run, not written)" if args.dry_run else "")
    )
    for d in drift:
        print(f"  {d['enrollment_id']}: {d['before']} -> {d['after']}")


if __name__ == "__main__":
    asyncio.run(_main())
