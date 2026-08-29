"""Role administration against a real Postgres.

The point of this feature is the audit trail, so these assert on the chain
itself, not only on the returned role list: a grant that does not append a
verifiable entry has not closed the gap it was written to close.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.audit import AuditLog
from pramana.db.models.identity import RoleName, Tenant, User
from pramana.domain.assignment_state import utcnow
from pramana.exceptions import AuthorizationError, ConflictError, NotFoundError
from pramana.services import roles as svc
from pramana.services.audit_query import verify_stored_chain

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class Fixture:
    tenant_id: uuid.UUID
    admin_id: uuid.UUID
    target_id: uuid.UUID


async def seed(db: AsyncSession) -> Fixture:
    """A tenant with the roles seeded, one compliance admin, and one other user."""
    tenant = Tenant(id=uuid.uuid4(), name=f"T {uuid.uuid4()}", short_code=uuid.uuid4().hex[:12])
    admin = User(user_id=uuid.uuid4(), tenant_id=tenant.id, email=f"{uuid.uuid4()}@x.com")
    target = User(user_id=uuid.uuid4(), tenant_id=tenant.id, email=f"{uuid.uuid4()}@x.com")
    db.add_all([tenant, admin, target])
    await db.flush()
    await svc.ensure_roles(db)
    # A second admin exists so the last-admin guard does not block unrelated tests.
    bootstrap = User(user_id=uuid.uuid4(), tenant_id=tenant.id, email=f"{uuid.uuid4()}@x.com")
    db.add(bootstrap)
    await db.flush()
    for holder in (admin, bootstrap):
        await svc.grant_role(
            db,
            user_id=holder.user_id,
            role_name=RoleName.COMPLIANCE_ADMIN,
            tenant_id=tenant.id,
            actor_user_id=target.user_id,  # not self — target is not an admin
            now=utcnow(),
        )
    await db.commit()
    return Fixture(tenant_id=tenant.id, admin_id=admin.user_id, target_id=target.user_id)


async def _events(db: AsyncSession, user_id: uuid.UUID) -> list[tuple[str, str]]:
    rows = (
        (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.entity_type == "user", AuditLog.entity_id == str(user_id))
                .order_by(AuditLog.audit_id.asc())
            )
        )
        .scalars()
        .all()
    )
    return [(r.event_type, r.payload.get("role", "")) for r in rows]


class TestGrant:
    async def test_grant_adds_the_role_and_audits_it(self, db: AsyncSession) -> None:
        f = await seed(db)

        result = await svc.grant_role(
            db,
            user_id=f.target_id,
            role_name=RoleName.MANAGER,
            tenant_id=f.tenant_id,
            actor_user_id=f.admin_id,
            now=utcnow(),
        )
        await db.commit()

        assert RoleName.MANAGER in result
        assert await svc.list_user_roles(db, user_id=f.target_id) == [RoleName.MANAGER]
        assert (svc.GRANTED_EVENT, RoleName.MANAGER) in await _events(db, f.target_id)

    async def test_grant_records_who_granted_it(self, db: AsyncSession) -> None:
        """`granted_by_user_id` is the point of the column — attribution."""
        f = await seed(db)
        await svc.grant_role(
            db,
            user_id=f.target_id,
            role_name=RoleName.AUDITOR,
            tenant_id=f.tenant_id,
            actor_user_id=f.admin_id,
            now=utcnow(),
        )
        await db.commit()

        rows = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.entity_id == str(f.target_id),
                        AuditLog.event_type == svc.GRANTED_EVENT,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert any(r.actor_user_id == f.admin_id for r in rows)

    async def test_regranting_is_idempotent_and_writes_no_second_entry(
        self, db: AsyncSession
    ) -> None:
        """A retried request must not litter the chain with events that did not happen."""
        f = await seed(db)
        for _ in range(2):
            await svc.grant_role(
                db,
                user_id=f.target_id,
                role_name=RoleName.MANAGER,
                tenant_id=f.tenant_id,
                actor_user_id=f.admin_id,
                now=utcnow(),
            )
        await db.commit()

        granted = [e for e in await _events(db, f.target_id) if e[0] == svc.GRANTED_EVENT]
        assert granted.count((svc.GRANTED_EVENT, RoleName.MANAGER)) == 1

    async def test_unknown_role_is_rejected(self, db: AsyncSession) -> None:
        f = await seed(db)
        with pytest.raises(NotFoundError):
            await svc.grant_role(
                db,
                user_id=f.target_id,
                role_name="wizard",
                tenant_id=f.tenant_id,
                actor_user_id=f.admin_id,
                now=utcnow(),
            )

    async def test_user_from_another_tenant_is_not_found(self, db: AsyncSession) -> None:
        f = await seed(db)
        with pytest.raises(NotFoundError):
            await svc.grant_role(
                db,
                user_id=uuid.uuid4(),
                role_name=RoleName.MANAGER,
                tenant_id=f.tenant_id,
                actor_user_id=f.admin_id,
                now=utcnow(),
            )


class TestSelfModification:
    async def test_admin_cannot_grant_themselves_a_role(self, db: AsyncSession) -> None:
        """Self-escalation is the failure separation of duties exists to stop."""
        f = await seed(db)
        with pytest.raises(AuthorizationError):
            await svc.grant_role(
                db,
                user_id=f.admin_id,
                role_name=RoleName.AUDITOR,
                tenant_id=f.tenant_id,
                actor_user_id=f.admin_id,
                now=utcnow(),
            )

    async def test_admin_cannot_revoke_their_own_role(self, db: AsyncSession) -> None:
        f = await seed(db)
        with pytest.raises(AuthorizationError):
            await svc.revoke_role(
                db,
                user_id=f.admin_id,
                role_name=RoleName.COMPLIANCE_ADMIN,
                tenant_id=f.tenant_id,
                actor_user_id=f.admin_id,
                now=utcnow(),
            )


class TestRevoke:
    async def test_revoke_removes_the_role_and_audits_it(self, db: AsyncSession) -> None:
        f = await seed(db)
        await svc.grant_role(
            db,
            user_id=f.target_id,
            role_name=RoleName.MANAGER,
            tenant_id=f.tenant_id,
            actor_user_id=f.admin_id,
            now=utcnow(),
        )
        await svc.revoke_role(
            db,
            user_id=f.target_id,
            role_name=RoleName.MANAGER,
            tenant_id=f.tenant_id,
            actor_user_id=f.admin_id,
            now=utcnow(),
        )
        await db.commit()

        assert await svc.list_user_roles(db, user_id=f.target_id) == []
        assert (svc.REVOKED_EVENT, RoleName.MANAGER) in await _events(db, f.target_id)

    async def test_revoking_a_role_not_held_is_a_no_op(self, db: AsyncSession) -> None:
        f = await seed(db)
        await svc.revoke_role(
            db,
            user_id=f.target_id,
            role_name=RoleName.MANAGER,
            tenant_id=f.tenant_id,
            actor_user_id=f.admin_id,
            now=utcnow(),
        )
        await db.commit()
        assert not [e for e in await _events(db, f.target_id) if e[0] == svc.REVOKED_EVENT]

    async def test_last_compliance_admin_cannot_be_revoked(self, db: AsyncSession) -> None:
        """Otherwise the tenant re-enters the bootstrap deadlock."""
        f = await seed(db)
        # Drop to a single admin, then try to remove that one too.
        admins = [
            u
            for u in (await db.execute(select(User).where(User.tenant_id == f.tenant_id)))
            .scalars()
            .all()
            if RoleName.COMPLIANCE_ADMIN in await svc.list_user_roles(db, user_id=u.user_id)
        ]
        assert len(admins) == 2
        await svc.revoke_role(
            db,
            user_id=admins[0].user_id,
            role_name=RoleName.COMPLIANCE_ADMIN,
            tenant_id=f.tenant_id,
            actor_user_id=f.target_id,
            now=utcnow(),
        )
        await db.commit()

        with pytest.raises(ConflictError):
            await svc.revoke_role(
                db,
                user_id=admins[1].user_id,
                role_name=RoleName.COMPLIANCE_ADMIN,
                tenant_id=f.tenant_id,
                actor_user_id=f.target_id,
                now=utcnow(),
            )


class TestBootstrap:
    """The out-of-band first grant, run by an operator with database access."""

    async def test_bootstrap_grants_without_an_actor_and_is_audited(self, db: AsyncSession) -> None:
        tenant = Tenant(id=uuid.uuid4(), name=f"T {uuid.uuid4()}", short_code=uuid.uuid4().hex[:12])
        first = User(user_id=uuid.uuid4(), tenant_id=tenant.id, email="first@example.com")
        db.add_all([tenant, first])
        await db.flush()
        await svc.ensure_roles(db)
        await db.commit()

        roles = await svc.bootstrap_grant_role(
            db, email="first@example.com", role_name=RoleName.COMPLIANCE_ADMIN, now=utcnow()
        )
        await db.commit()

        assert roles == [RoleName.COMPLIANCE_ADMIN]
        rows = (
            (await db.execute(select(AuditLog).where(AuditLog.entity_id == str(first.user_id))))
            .scalars()
            .all()
        )
        entry = next(r for r in rows if r.event_type == svc.GRANTED_EVENT)
        # No authenticated actor, and the payload says why.
        assert entry.actor_user_id is None
        assert entry.payload["bootstrap"] is True

    async def test_bootstrap_rejects_an_unknown_email(self, db: AsyncSession) -> None:
        await svc.ensure_roles(db)
        await db.commit()
        with pytest.raises(NotFoundError):
            await svc.bootstrap_grant_role(
                db,
                email=f"nobody-{uuid.uuid4()}@example.com",
                role_name=RoleName.COMPLIANCE_ADMIN,
                now=utcnow(),
            )


class TestAuditChain:
    async def test_role_changes_leave_the_chain_verifiable(self, db: AsyncSession) -> None:
        """The whole point: role events join the chain, they do not break it."""
        f = await seed(db)
        await svc.grant_role(
            db,
            user_id=f.target_id,
            role_name=RoleName.MANAGER,
            tenant_id=f.tenant_id,
            actor_user_id=f.admin_id,
            now=utcnow(),
        )
        await svc.revoke_role(
            db,
            user_id=f.target_id,
            role_name=RoleName.MANAGER,
            tenant_id=f.tenant_id,
            actor_user_id=f.admin_id,
            now=utcnow(),
        )
        await db.commit()

        verification = await verify_stored_chain(db)
        assert verification.ok, verification.first_break
