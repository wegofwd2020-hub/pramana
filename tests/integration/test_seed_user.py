"""The out-of-band user seed — bootstrap before the first login.

Auth never creates users, so a fresh deployment needs a row created from
outside the request path. These check it creates the tenant + user and is
idempotent, because the operator may re-run it while getting a deploy right.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.identity import Tenant, User
from scripts.seed_user import seed_user

pytestmark = pytest.mark.integration


class TestSeedUser:
    async def test_creates_the_tenant_and_the_user(self, db: AsyncSession) -> None:
        email = f"{uuid.uuid4()}@example.com"
        code = f"t{uuid.uuid4().hex[:8]}"

        user, created = await seed_user(db, email=email, tenant_name="Acme", tenant_short_code=code)
        await db.commit()

        assert created is True
        assert user.email == email
        tenant = (await db.execute(select(Tenant).where(Tenant.short_code == code))).scalar_one()
        assert user.tenant_id == tenant.id

    async def test_defaults_make_the_user_loginable(self, db: AsyncSession) -> None:
        """First-login provisioning needs active + unbound; assert those defaults."""
        email = f"{uuid.uuid4()}@example.com"
        user, _ = await seed_user(
            db, email=email, tenant_name="Acme", tenant_short_code=f"t{uuid.uuid4().hex[:8]}"
        )
        await db.commit()
        assert user.status == "active"
        assert user.sso_subject is None

    async def test_is_idempotent(self, db: AsyncSession) -> None:
        email = f"{uuid.uuid4()}@example.com"
        code = f"t{uuid.uuid4().hex[:8]}"

        await seed_user(db, email=email, tenant_name="Acme", tenant_short_code=code)
        await db.commit()
        _user, created = await seed_user(
            db, email=email, tenant_name="Acme", tenant_short_code=code
        )
        await db.commit()

        assert created is False
        count = (
            await db.execute(
                select(func.count()).select_from(User).where(func.lower(User.email) == email)
            )
        ).scalar_one()
        assert count == 1
