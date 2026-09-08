#!/usr/bin/env python3
"""Check that the audit evidence is intact (TICKETS/PR-2).

Answers one question — *has the evidence been altered or lost?* — from a shell,
against the database directly. Three independent checks:

  1. **Row chain.** Every ``audit_log`` row's hash recomputed and its
     ``prev_audit_hash`` link followed. Detects an edited or removed row.
  2. **Archive continuity.** The recorded segments walked end to end. Detects a
     dropped *segment* — the failure the manifests were designed to expose, and
     which nothing looked for before this script:
     ``segments_are_contiguous`` had only ever been called from its own tests.
  3. **Archive lag.** How many rows have not reached WORM storage. An archive
     that quietly stopped is not an archive, and nothing else reports it.

Why a script and not only ``GET /audit/verify``: the API answers as the
application, over the application's own connection, behind the application's
auth. When the question is *"has this been tampered with?"* the answer should not
depend on the component under suspicion still being healthy and honest. This
needs only ``DATABASE_URL``.

Usage::

    DATABASE_URL=... python scripts/verify_audit.py
    DATABASE_URL=... python scripts/verify_audit.py --quiet   # exit code only

Exit codes:
  0 — chain intact and archive contiguous
  1 — a break was found, or the check could not run
  2 — intact, but rows are pending archival (``--strict-archive`` only)
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pramana.config import get_settings
from pramana.exceptions import PramanaError
from pramana.services.audit_archive import (
    high_water_mark,
    unarchived_count,
    verify_archive,
)
from pramana.services.audit_query import verify_stored_chain

OK = "  ok"
BAD = "  BREAK"


async def _run(*, quiet: bool, strict_archive: bool) -> int:
    def say(msg: str = "") -> None:
        if not quiet:
            print(msg)

    engine = create_async_engine(get_settings().database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    broken = False
    pending = 0
    try:
        async with sessions() as session:
            # 1. the row chain
            chain = await verify_stored_chain(session)
            if chain.ok:
                say(f"{OK}  row chain: {chain.total} row(s), unbroken")
            else:
                broken = True
                # ChainVerification reports the FIRST break only — everything
                # after it is unverifiable anyway, since each link depends on
                # the one before.
                brk = chain.first_break
                say(f"{BAD}  row chain: broken after {chain.total} row(s) checked")
                if brk is not None:
                    say(f"          audit_id {brk.audit_id}: {brk.reason}")
                    say(f"          expected {brk.expected!r}, found {brk.found!r}")

            # 2. the archive, segment to segment
            archive = await verify_archive(session)
            if archive.segment_count == 0:
                say("  --    archive: nothing archived yet")
            elif archive.intact:
                say(
                    f"{OK}  archive: {archive.segment_count} segment(s), contiguous "
                    f"through audit_id {archive.covered_through}"
                )
            else:
                broken = True
                say(f"{BAD}  archive: {len(archive.gaps)} gap(s)")
                for gap in archive.gaps:
                    say(f"          after {gap.after_audit_id}: {gap.reason}")

            # 3. how far behind archival is
            pending = await unarchived_count(session)
            mark = await high_water_mark(session)
            if pending:
                say(f"  --    {pending} row(s) pending archival (archived through {mark})")
            else:
                say(f"{OK}  archival current (through audit_id {mark})")
    except PramanaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()

    if broken:
        say()
        say("  EVIDENCE IS NOT INTACT — do not treat this log as authoritative.")
        return 1
    if strict_archive and pending:
        return 2
    say()
    say("  evidence intact")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="report through the exit code only")
    parser.add_argument(
        "--strict-archive",
        action="store_true",
        help="exit 2 when rows are pending archival, for scheduled monitoring",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(quiet=args.quiet, strict_archive=args.strict_archive))


if __name__ == "__main__":
    raise SystemExit(main())
