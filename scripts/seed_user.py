#!/usr/bin/env python3
"""Seed a user row (and its tenant) out of band — bootstrap before first login.

Authentication never creates users: ``_provision_by_email`` binds an IdP subject
to a user that must already exist, be unbound, and be active. A fresh deployment
therefore has no users at all and no way to make one over HTTP. This creates the
row from outside the request path, so the first person can log in and
``scripts/grant_role.py`` can make them an admin.

Idempotent: re-running with the same email is a no-op, and the tenant is created
once and reused. ``sso_subject`` is left null — the IdP binds it on first login.

Usage::

    DATABASE_URL=... python scripts/seed_user.py --email you@example.com
    ... --email x@y.com --tenant-name "Acme Corp" --tenant-short-code acme

Or, on the box, ``scripts/launch/seed_admin.sh`` runs this then grant_role.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pramana.config import get_settings
from pramana.db.models.identity import Tenant, User


async def seed_user(
    session: AsyncSession,
    *,
    email: str,
    tenant_name: str,
    tenant_short_code: str,
) -> tuple[User, bool]:
    """Ensure a tenant and an active user with ``email`` exist.

    Returns ``(user, created)`` where ``created`` is ``False`` if the user was
    already present. The user's type and status take their model defaults
    (employee / active), which is what first-login provisioning requires.
    """
    tenant = (
        await session.execute(select(Tenant).where(Tenant.short_code == tenant_short_code))
    ).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(id=uuid.uuid4(), name=tenant_name, short_code=tenant_short_code)
        session.add(tenant)
        await session.flush()

    user = (
        await session.execute(select(User).where(func.lower(User.email) == email.lower()))
    ).scalar_one_or_none()
    if user is not None:
        return user, False

    user = User(user_id=uuid.uuid4(), tenant_id=tenant.id, email=email)
    session.add(user)
    await session.flush()
    return user, True


async def _run(email: str, tenant_name: str, tenant_short_code: str) -> int:
    engine = create_async_engine(get_settings().database_url, future=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            _user, created = await seed_user(
                session,
                email=email,
                tenant_name=tenant_name,
                tenant_short_code=tenant_short_code,
            )
            await session.commit()
    finally:
        await engine.dispose()

    print(f"{'created' if created else 'already present'}: {email} (tenant {tenant_short_code})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="the user's email (must match the IdP)")
    parser.add_argument("--tenant-name", default="WeGoFwd", help="tenant display name if created")
    parser.add_argument(
        "--tenant-short-code", default="wegofwd", help="tenant short code (unique key)"
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.email, args.tenant_name, args.tenant_short_code))


if __name__ == "__main__":
    raise SystemExit(main())
