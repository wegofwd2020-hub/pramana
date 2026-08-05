"""Audit-chain verification — pure domain.

Recomputes the audit hash chain over a sequence of rows and reports the first
break. No database, no I/O — it operates on plain :class:`AuditRow` value
objects, so an auditor can run it over *exported* rows without the app or the DB
(architecture §2.2). This is the payoff of the whole tamper-evident design:
detection needs only a recomputation pass, no external notary.

Two independent failure modes are caught:

- **hash_mismatch** — a row's stored ``audit_hash`` no longer equals the hash
  recomputed from its own fields. Someone edited the row's content.
- **broken_link** — a row's ``prev_audit_hash`` no longer equals the actual
  previous row's ``audit_hash``. A row was deleted, inserted, or reordered.

Rows must be supplied in ascending ``audit_id`` order and must be the *whole*
chain: the chain is global (``prev_audit_hash`` links across tenants by
``audit_id``), so a tenant-filtered subset is not a contiguous chain and cannot
be verified in isolation (a v2 concern — per-tenant chains / inclusion proofs).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pramana.domain.audit_hash import compute_audit_hash


@dataclass(frozen=True, slots=True)
class AuditRow:
    """The chain-relevant fields of one ``audit_log`` row."""

    audit_id: int
    tenant_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    entity_type: str
    entity_id: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    prev_audit_hash: str | None
    audit_hash: str


@dataclass(frozen=True, slots=True)
class ChainBreak:
    """The first detected break in the chain."""

    audit_id: int
    reason: str  # "hash_mismatch" | "broken_link"
    expected: str | None
    found: str | None


@dataclass(frozen=True, slots=True)
class ChainVerification:
    """Result of verifying a chain: intact, or the first break."""

    ok: bool
    total: int
    first_break: ChainBreak | None = None


def _recompute(row: AuditRow) -> str:
    return compute_audit_hash(
        prev_audit_hash=row.prev_audit_hash,
        tenant_id=row.tenant_id,
        actor_user_id=row.actor_user_id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        event_type=row.event_type,
        payload=row.payload,
        occurred_at=row.occurred_at,
    )


def verify_chain(rows: Sequence[AuditRow]) -> ChainVerification:
    """Verify the whole chain, returning at the first break (or intact).

    Args:
        rows: The full chain in ascending ``audit_id`` order.

    Returns:
        :class:`ChainVerification` — ``ok`` with no break, else the first break.
    """
    prev_hash: str | None = None
    for row in rows:
        # Link continuity: the stored back-pointer must match the real predecessor.
        if row.prev_audit_hash != prev_hash:
            return ChainVerification(
                ok=False,
                total=len(rows),
                first_break=ChainBreak(
                    audit_id=row.audit_id,
                    reason="broken_link",
                    expected=prev_hash,
                    found=row.prev_audit_hash,
                ),
            )
        # Content integrity: recomputing the row's hash must reproduce the stored one.
        recomputed = _recompute(row)
        if recomputed != row.audit_hash:
            return ChainVerification(
                ok=False,
                total=len(rows),
                first_break=ChainBreak(
                    audit_id=row.audit_id,
                    reason="hash_mismatch",
                    expected=recomputed,
                    found=row.audit_hash,
                ),
            )
        prev_hash = row.audit_hash
    return ChainVerification(ok=True, total=len(rows), first_break=None)
