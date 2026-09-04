"""Entitlement service — the consumer access grant + check.

This is the single seam a future payment webhook calls: manual and paid grants
differ only by ``source``/``external_ref``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.consumer import Entitlement, PackageCourse
from pramana.db.models.identity import Tenant, User, UserStatus, UserType
from pramana.exceptions import NotFoundError
from pramana.services.audit import append_audit


async def get_consumer_tenant_id(session: AsyncSession) -> uuid.UUID:
    tid = (
        await session.execute(select(Tenant.id).where(Tenant.short_code == "consumer"))
    ).scalar_one_or_none()
    if tid is None:
        raise NotFoundError("consumer tenant not seeded")
    return tid


async def create_consumer_user(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    email: str,
    first_name: str | None,
    last_name: str | None,
    now: datetime,
) -> User:
    user = User(
        tenant_id=tenant_id,
        email=email,
        first_name=first_name,
        last_name=last_name,
        user_type=UserType.EMPLOYEE,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()
    await append_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=None,
        entity_type="user",
        entity_id=str(user.user_id),
        event_type="user.consumer_created",
        payload={"email": email},
        occurred_at=now,
    )
    return user


async def grant_package(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    package_id: uuid.UUID,
    granted_by_user_id: uuid.UUID | None,
    now: datetime,
    source: str = "manual",
    external_ref: str | None = None,
    expires_at: datetime | None = None,
) -> Entitlement:
    existing = (
        await session.execute(
            select(Entitlement).where(
                Entitlement.user_id == user_id,
                Entitlement.package_id == package_id,
                Entitlement.status == "active",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    ent = Entitlement(
        tenant_id=tenant_id,
        user_id=user_id,
        package_id=package_id,
        status="active",
        source=source,
        external_ref=external_ref,
        granted_by_user_id=granted_by_user_id,
        granted_at=now,
        expires_at=expires_at,
    )
    session.add(ent)
    await session.flush()
    await append_audit(
        session,
        tenant_id=tenant_id,
        actor_user_id=granted_by_user_id,
        entity_type="entitlement",
        entity_id=str(ent.id),
        event_type="entitlement.granted",
        payload={"user_id": str(user_id), "package_id": str(package_id), "source": source},
        occurred_at=now,
    )
    return ent


async def revoke_entitlement(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entitlement_id: uuid.UUID,
    revoked_by_user_id: uuid.UUID | None,
    now: datetime,
    reason: str | None = None,
) -> Entitlement:
    """Revoke an active entitlement and append an audit event.

    Idempotency contract: if the entitlement is already in a non-active state
    (e.g. already revoked), this function returns it unchanged without writing
    another audit event.  This is deliberate — a payment webhook that fires
    twice must be a safe no-op on the second call; the audit chain already
    captured the first revoke.

    Raises ``NotFoundError`` if the entitlement does not exist or belongs to a
    different tenant (tenant-isolation contract).
    """
    ent = await session.get(Entitlement, entitlement_id)
    if ent is None or ent.tenant_id != tenant_id:
        raise NotFoundError(
            "entitlement not found", context={"entitlement_id": str(entitlement_id)}
        )
    if ent.status == "active":
        ent.status = "revoked"
        ent.revoked_at = now
        ent.revoked_reason = reason
        await append_audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=revoked_by_user_id,
            entity_type="entitlement",
            entity_id=str(ent.id),
            event_type="entitlement.revoked",
            payload={"reason": reason},
            occurred_at=now,
        )
    return ent


async def has_active_entitlement_for_course(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    course_id: uuid.UUID,
    now: datetime,
) -> bool:
    covered = (
        select(Entitlement.id)
        .join(PackageCourse, PackageCourse.package_id == Entitlement.package_id)
        .where(
            Entitlement.tenant_id == tenant_id,
            Entitlement.user_id == user_id,
            Entitlement.status == "active",
            or_(Entitlement.expires_at.is_(None), Entitlement.expires_at > now),
            PackageCourse.course_id == course_id,
        )
    )
    return bool((await session.execute(select(exists(covered)))).scalar())
