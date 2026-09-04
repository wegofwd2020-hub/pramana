"""Admin router: create a consumer account and grant/revoke package access."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.api.dependencies import get_db_session, get_principal, require_roles
from pramana.api.schemas import ConsumerGrantIn, ConsumerGrantOut, EntitlementOut
from pramana.db.models.identity import RoleName
from pramana.domain.assignment_state import utcnow
from pramana.services.auth import Principal
from pramana.services.consumer import entitlements as ent

router = APIRouter(prefix="/admin/consumers", tags=["consumer-admin"])

Session = Annotated[AsyncSession, Depends(get_db_session)]
Caller = Annotated[Principal, Depends(get_principal)]
_ADMIN = require_roles(RoleName.COMPLIANCE_ADMIN)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ConsumerGrantOut,
    dependencies=[Depends(_ADMIN)],
)
async def create_and_grant(
    body: ConsumerGrantIn, session: Session, caller: Caller
) -> ConsumerGrantOut:
    now = utcnow()
    tenant_id = await ent.get_consumer_tenant_id(session)
    user = await ent.create_consumer_user(
        session,
        tenant_id=tenant_id,
        email=body.email,
        first_name=body.first_name,
        last_name=body.last_name,
        now=now,
    )
    entitlement = await ent.grant_package(
        session,
        tenant_id=tenant_id,
        user_id=user.user_id,
        package_id=body.package_id,
        granted_by_user_id=caller.user_id,
        now=now,
    )
    return ConsumerGrantOut(
        user_id=user.user_id, entitlement=EntitlementOut.model_validate(entitlement)
    )


@router.post(
    "/entitlements/{entitlement_id}/revoke",
    response_model=EntitlementOut,
    dependencies=[Depends(_ADMIN)],
)
async def revoke(entitlement_id: uuid.UUID, session: Session, caller: Caller) -> EntitlementOut:
    tenant_id = await ent.get_consumer_tenant_id(session)
    e = await ent.revoke_entitlement(
        session,
        tenant_id=tenant_id,
        entitlement_id=entitlement_id,
        revoked_by_user_id=caller.user_id,
        now=utcnow(),
    )
    return EntitlementOut.model_validate(e)
