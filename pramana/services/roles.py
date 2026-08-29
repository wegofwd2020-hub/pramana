"""Role administration — granting and revoking, with every change audited.

Role grants were the last access-control event the audit chain did not cover.
They happened directly in the database, out of band, so the record of *who could
do what, and since when* had a hole in it exactly where an auditor looks first
(``TICKETS/PR-3``). This module closes it: every grant and revoke appends to the
chain alongside the actions those roles authorise.

Two policy rules live here rather than in the pure domain, because each needs to
query:

* **No self-modification** — the actor may not change their own roles. An
  administrator quietly escalating themselves is the failure the separation-of
  -duties rule in content approval exists to prevent; the same reasoning applies
  to the roles that gate it.
* **The last compliance admin cannot be revoked** — otherwise the deployment
  re-enters the bootstrap deadlock this module was written to escape, and needs
  ``scripts/grant_role.py`` and database access to recover.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.identity import Role, RoleName, User, UserRole
from pramana.exceptions import AuthorizationError, ConflictError, NotFoundError
from pramana.services.audit import append_audit

#: Description seeded for each fixed role. Mirrors ``SEEDED_ROLES`` in migration
#: ``0007``; ``tests/db/test_role_seed.py`` asserts the two agree. Both exist
#: because deployments seed through Alembic and the integration suite builds its
#: schema from the ORM metadata instead.
ROLE_DESCRIPTIONS: dict[str, str] = {
    RoleName.TRAINEE: "Completes assigned training and reads their own records.",
    RoleName.MANAGER: "Assigns and cancels training; reads records across users.",
    RoleName.CONTENT_AUTHOR: (
        "Commissions content, submits drafts for review, and regenerates them."
    ),
    RoleName.COMPLIANCE_ADMIN: (
        "Approves, rejects, and publishes content; administers role grants."
    ),
    RoleName.AUDITOR: ("Reads and verifies the audit chain and exports evidence; read-only."),
}

GRANTED_EVENT = "user.role_granted"
REVOKED_EVENT = "user.role_revoked"


async def ensure_roles(session: AsyncSession) -> None:
    """Insert any missing fixed role. Idempotent.

    Migration ``0007`` does this for real deployments; this serves the paths that
    never run Alembic — the integration suite, and the bootstrap script when it
    is pointed at a database somebody built by hand.
    """
    existing = set((await session.execute(select(Role.name))).scalars().all())
    for name, description in ROLE_DESCRIPTIONS.items():
        if name not in existing:
            session.add(Role(id=uuid.uuid4(), name=name, description=description))
    await session.flush()


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
async def list_user_roles(session: AsyncSession, *, user_id: uuid.UUID) -> Sequence[str]:
    """The role names a user currently holds, sorted."""
    rows = (
        (
            await session.execute(
                select(Role.name)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    return sorted(rows)


async def _load_role(session: AsyncSession, name: str) -> Role:
    """Resolve a role by name.

    The name is checked against the fixed set *before* querying, because
    ``role.name`` is a Postgres enum: comparing it to an unrecognised string
    raises a driver-level error (a 500) rather than returning no rows. The known
    set lives in code, so this is both cheaper and the only way to answer with a
    clean 404.
    """
    if name not in ROLE_DESCRIPTIONS:
        raise NotFoundError(
            "unknown role",
            context={"role": name, "known": sorted(ROLE_DESCRIPTIONS)},
        )
    role = (await session.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
    if role is None:
        raise NotFoundError(
            "role is not seeded in this database",
            context={"role": name},
        )
    return role


async def _load_user(session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise NotFoundError("user not found", context={"user_id": str(user_id)})
    return user


def _refuse_self_modification(actor_user_id: uuid.UUID, user_id: uuid.UUID) -> None:
    if actor_user_id == user_id:
        raise AuthorizationError(
            "an administrator may not change their own roles",
            context={"user_id": str(user_id)},
        )


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------
async def grant_role(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    role_name: str,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    now: datetime,
) -> Sequence[str]:
    """Grant ``role_name`` to a user and audit it. Returns their roles.

    Idempotent: re-granting a role the user already holds changes nothing and
    appends no second audit entry, so a retried request does not litter the
    chain with events that did not happen.

    Raises:
        AuthorizationError: The actor is the target.
        NotFoundError: No such user in this tenant, or no such role.
    """
    _refuse_self_modification(actor_user_id, user_id)
    await _load_user(session, user_id, tenant_id)
    role = await _load_role(session, role_name)

    already = (
        await session.execute(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
        )
    ).scalar_one_or_none()
    if already is not None:
        return await list_user_roles(session, user_id=user_id)

    session.add(
        UserRole(
            id=uuid.uuid4(),
            user_id=user_id,
            role_id=role.id,
            granted_by_user_id=actor_user_id,
        )
    )
    await session.flush()
    await append_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type="user",
        entity_id=str(user_id),
        event_type=GRANTED_EVENT,
        payload={"role": role_name},
        occurred_at=now,
    )
    return await list_user_roles(session, user_id=user_id)


async def revoke_role(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    role_name: str,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    now: datetime,
) -> Sequence[str]:
    """Revoke ``role_name`` from a user and audit it. Returns their roles.

    Idempotent in the same way as :func:`grant_role`: revoking a role the user
    does not hold is a no-op and writes no audit entry.

    Raises:
        AuthorizationError: The actor is the target.
        NotFoundError: No such user in this tenant, or no such role.
        ConflictError: This is the last compliance admin in the tenant.
    """
    _refuse_self_modification(actor_user_id, user_id)
    await _load_user(session, user_id, tenant_id)
    role = await _load_role(session, role_name)

    assignment = (
        await session.execute(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
        )
    ).scalar_one_or_none()
    if assignment is None:
        return await list_user_roles(session, user_id=user_id)

    if role_name == RoleName.COMPLIANCE_ADMIN:
        await _refuse_last_compliance_admin(session, tenant_id=tenant_id, role_id=role.id)

    await session.delete(assignment)
    await session.flush()
    await append_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type="user",
        entity_id=str(user_id),
        event_type=REVOKED_EVENT,
        payload={"role": role_name},
        occurred_at=now,
    )
    return await list_user_roles(session, user_id=user_id)


async def bootstrap_grant_role(
    session: AsyncSession, *, email: str, role_name: str, now: datetime
) -> Sequence[str]:
    """Grant a role with no authenticated actor — the deployment's first admin.

    A fresh deployment has no compliance admin, and the route that would create
    one requires being one. Something has to break that circle from outside the
    request path, so ``scripts/grant_role.py`` calls this with database access
    and no principal.

    It is deliberately *not* a special case of :func:`grant_role`: the
    self-modification rule must hold unconditionally for anything reachable over
    HTTP, and an operator acting out of band is a different kind of event. The
    audit entry records that difference — a null ``actor_user_id`` and a
    ``bootstrap`` flag — so a reviewer can tell the two apart at a glance.

    Raises:
        NotFoundError: No user with that email, or the role is not seeded.
    """
    user = (
        await session.execute(select(User).where(func.lower(User.email) == email.lower()))
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("no user with that email", context={"email": email})
    role = await _load_role(session, role_name)

    already = (
        await session.execute(
            select(UserRole).where(UserRole.user_id == user.user_id, UserRole.role_id == role.id)
        )
    ).scalar_one_or_none()
    if already is not None:
        return await list_user_roles(session, user_id=user.user_id)

    session.add(
        UserRole(
            id=uuid.uuid4(),
            user_id=user.user_id,
            role_id=role.id,
            granted_by_user_id=None,
        )
    )
    await session.flush()
    await append_audit(
        session,
        tenant_id=user.tenant_id,
        actor_user_id=None,
        entity_type="user",
        entity_id=str(user.user_id),
        event_type=GRANTED_EVENT,
        payload={"role": role_name, "bootstrap": True},
        occurred_at=now,
    )
    return await list_user_roles(session, user_id=user.user_id)


async def _refuse_last_compliance_admin(
    session: AsyncSession, *, tenant_id: uuid.UUID, role_id: uuid.UUID
) -> None:
    """Refuse a revoke that would leave the tenant with no compliance admin."""
    remaining = (
        await session.execute(
            select(func.count())
            .select_from(UserRole)
            .join(User, User.user_id == UserRole.user_id)
            .where(UserRole.role_id == role_id, User.tenant_id == tenant_id)
        )
    ).scalar_one()
    if remaining <= 1:
        raise ConflictError(
            "cannot revoke the last compliance admin; grant the role to another "
            "user first, or the tenant will have no one who can administer roles",
            context={"role": RoleName.COMPLIANCE_ADMIN},
        )
