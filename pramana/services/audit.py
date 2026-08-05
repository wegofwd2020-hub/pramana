"""Audit-log append helper.

The :class:`~pramana.db.models.audit.AuditLog` table is an append-only hash
chain (each row hashes its canonical form plus the previous row's hash, so
tampering is detectable). This module provides the minimal writer the ingestion
path needs; richer audit reporting is a later phase.

:func:`compute_audit_hash` is pure and exhaustively testable;
:func:`append_audit` is the thin async shell that reads the chain head and
inserts the next row.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.audit import AuditLog
from pramana.domain.audit_hash import compute_audit_hash

__all__ = ["append_audit", "compute_audit_hash"]


async def append_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: str,
    event_type: str,
    payload: dict[str, Any],
    occurred_at: datetime,
    actor_user_id: uuid.UUID | None = None,
) -> AuditLog:
    """Append one entry to the audit hash chain and return it (not committed)."""
    prev_hash = (
        await session.execute(
            select(AuditLog.audit_hash).order_by(AuditLog.audit_id.desc()).limit(1)
        )
    ).scalar_one_or_none()

    audit_hash = compute_audit_hash(
        prev_audit_hash=prev_hash,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload=payload,
        occurred_at=occurred_at,
    )
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload=payload,
        occurred_at=occurred_at,
        prev_audit_hash=prev_hash,
        audit_hash=audit_hash,
    )
    session.add(entry)
    return entry
