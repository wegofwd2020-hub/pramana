"""Audit-log read side — verification, search, and export.

Read-only over the append-only :class:`~pramana.db.models.audit.AuditLog`.
Verification runs the pure :mod:`pramana.domain.audit_verification` over the
whole (global) chain; search and export are tenant-scoped auditor views. Export
carries the ``prev_audit_hash``/``audit_hash`` columns so the file is
independently re-verifiable off the database (architecture §2.2).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.audit import AuditLog
from pramana.domain.audit_verification import AuditRow, ChainVerification, verify_chain


def to_audit_row(r: AuditLog) -> AuditRow:
    return AuditRow(
        audit_id=r.audit_id,
        tenant_id=r.tenant_id,
        actor_user_id=r.actor_user_id,
        entity_type=r.entity_type,
        entity_id=r.entity_id,
        event_type=r.event_type,
        payload=r.payload,
        occurred_at=r.occurred_at,
        prev_audit_hash=r.prev_audit_hash,
        audit_hash=r.audit_hash,
    )


async def verify_stored_chain(session: AsyncSession) -> ChainVerification:
    """Verify the entire stored audit chain (global, ascending ``audit_id``).

    Not tenant-filtered on purpose: the chain links across tenants by
    ``audit_id``, so verifying a subset would report spurious broken links. In
    v1 (single-tenant) the global chain is the tenant's chain.
    """
    rows = (
        (await session.execute(select(AuditLog).order_by(AuditLog.audit_id.asc()))).scalars().all()
    )
    return verify_chain([to_audit_row(r) for r in rows])


def _filters(
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    entity_type: str | None,
    entity_id: str | None,
    event_type: str | None,
    occurred_after: datetime | None,
    occurred_before: datetime | None,
) -> list[Any]:
    filters: list[Any] = [AuditLog.tenant_id == tenant_id]
    if actor_user_id is not None:
        filters.append(AuditLog.actor_user_id == actor_user_id)
    if entity_type is not None:
        filters.append(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        filters.append(AuditLog.entity_id == entity_id)
    if event_type is not None:
        filters.append(AuditLog.event_type == event_type)
    if occurred_after is not None:
        filters.append(AuditLog.occurred_at >= occurred_after)
    if occurred_before is not None:
        filters.append(AuditLog.occurred_at <= occurred_before)
    return filters


async def search_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    event_type: str | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[Sequence[AuditLog], int]:
    """Return a page of the tenant's audit entries matching the filters + total."""
    filters = _filters(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
    )
    total = (
        await session.execute(select(func.count()).select_from(AuditLog).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(AuditLog)
                .where(*filters)
                .order_by(AuditLog.audit_id.asc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        .scalars()
        .all()
    )
    return rows, total


async def export_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    event_type: str | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
) -> Sequence[AuditLog]:
    """Return every matching audit row (ascending ``audit_id``, no pagination).

    Includes the hash columns so the export is independently re-verifiable.
    """
    filters = _filters(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
    )
    return (
        (await session.execute(select(AuditLog).where(*filters).order_by(AuditLog.audit_id.asc())))
        .scalars()
        .all()
    )
