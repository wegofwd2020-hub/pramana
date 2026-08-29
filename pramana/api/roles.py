"""``/users/{user_id}/roles`` — role administration.

Thin HTTP shell over :mod:`pramana.services.roles`, which holds the policy
(no self-modification, no revoking the last compliance admin) and appends the
audit entries. Granting authority is itself a privileged act, so the mutating
routes are compliance-admin only; auditors may read, because who holds which
role, and since when, is access-control evidence.

Closes the outstanding half of ``TICKETS/PR-3``: role changes are now audited.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.api.dependencies import get_db_session, get_principal, require_roles
from pramana.api.schemas import RoleGrantRequest, UserRolesOut
from pramana.db.models.identity import RoleName
from pramana.domain.assignment_state import utcnow
from pramana.services import roles as svc
from pramana.services.auth import Principal

router = APIRouter(prefix="/users", tags=["roles"])

Session = Annotated[AsyncSession, Depends(get_db_session)]
Caller = Annotated[Principal, Depends(get_principal)]

# Only a compliance admin hands out authority. Auditors read it as evidence.
_ADMIN = require_roles(RoleName.COMPLIANCE_ADMIN)
_ADMIN_OR_AUDITOR = require_roles(RoleName.COMPLIANCE_ADMIN, RoleName.AUDITOR)


@router.get(
    "/{user_id}/roles",
    response_model=UserRolesOut,
    summary="List a user's roles",
    dependencies=[Depends(_ADMIN_OR_AUDITOR)],
)
async def list_roles(user_id: uuid.UUID, session: Session) -> UserRolesOut:
    return UserRolesOut(
        user_id=user_id, roles=list(await svc.list_user_roles(session, user_id=user_id))
    )


@router.post(
    "/{user_id}/roles",
    status_code=status.HTTP_201_CREATED,
    response_model=UserRolesOut,
    summary="Grant a role (audited)",
    dependencies=[Depends(_ADMIN)],
)
async def grant_role(
    user_id: uuid.UUID, body: RoleGrantRequest, session: Session, caller: Caller
) -> UserRolesOut:
    roles = await svc.grant_role(
        session,
        user_id=user_id,
        role_name=body.role,
        tenant_id=caller.tenant_id,
        actor_user_id=caller.user_id,
        now=utcnow(),
    )
    return UserRolesOut(user_id=user_id, roles=list(roles))


@router.delete(
    "/{user_id}/roles/{role_name}",
    response_model=UserRolesOut,
    summary="Revoke a role (audited)",
    dependencies=[Depends(_ADMIN)],
)
async def revoke_role(
    user_id: uuid.UUID, role_name: str, session: Session, caller: Caller
) -> UserRolesOut:
    roles = await svc.revoke_role(
        session,
        user_id=user_id,
        role_name=role_name,
        tenant_id=caller.tenant_id,
        actor_user_id=caller.user_id,
        now=utcnow(),
    )
    return UserRolesOut(user_id=user_id, roles=list(roles))
