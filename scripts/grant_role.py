#!/usr/bin/env python3
"""Grant a role out of band — the deployment's first compliance admin.

A fresh deployment has no compliance admin, and ``POST /users/{id}/roles``
requires being one. Something has to break that circle from outside the request
path, so this does: an operator with database access runs it once, and every
grant afterwards goes through the audited API.

It is not a general administration tool. Use it to bootstrap, and to recover if
a tenant somehow loses its last admin.

Usage::

    DATABASE_URL=... python scripts/grant_role.py --email you@example.com
    DATABASE_URL=... python scripts/grant_role.py --email x@y.com --role auditor

Or ``make grant-role email=you@example.com``.

The grant is written to the audit chain like any other, with a null actor and a
``bootstrap`` flag, so the record shows an operator acted rather than a user.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pramana.config import get_settings
from pramana.db.models.identity import RoleName
from pramana.domain.assignment_state import utcnow
from pramana.exceptions import PramanaError
from pramana.services.roles import bootstrap_grant_role, ensure_roles


async def _run(email: str, role: str) -> int:
    engine = create_async_engine(get_settings().database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            # Seed first: a database built without Alembic has no roles at all,
            # and this script is exactly the path used when things are unusual.
            await ensure_roles(session)
            roles = await bootstrap_grant_role(session, email=email, role_name=role, now=utcnow())
            await session.commit()
    except PramanaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()

    print(f"{email} now holds: {', '.join(roles)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="the user to grant the role to")
    parser.add_argument(
        "--role",
        default=RoleName.COMPLIANCE_ADMIN,
        choices=RoleName.values(),
        help="role to grant (default: compliance_admin)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.email, args.role))


if __name__ == "__main__":
    raise SystemExit(main())
