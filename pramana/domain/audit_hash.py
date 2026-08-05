"""Canonical audit-hash function — pure domain.

The one place the audit chain's canonical form is defined. It takes no session,
touches no I/O, and returns a string, so verification tooling can recompute
hashes from exported rows without the database, the application, or even Python
(architecture §2.2). The writer (:func:`pramana.services.audit.append_audit`)
and the verifier (:mod:`pramana.domain.audit_verification`) both build on this.

The canonicalisation is deliberate and pinned — ``sort_keys=True`` with tight
separators — so the same logical event always hashes identically regardless of
dict ordering. Changing it would break every existing chain; don't.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from hashlib import sha256
from typing import Any


def compute_audit_hash(
    *,
    prev_audit_hash: str | None,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    entity_type: str,
    entity_id: str,
    event_type: str,
    payload: dict[str, Any],
    occurred_at: datetime,
) -> str:
    """Return the SHA-256 hex of an audit row's canonical form.

    Chains off ``prev_audit_hash`` (``None`` for the very first row) so the log
    forms a tamper-evident sequence.
    """
    canonical = json.dumps(
        {
            "prev": prev_audit_hash,
            "tenant_id": str(tenant_id),
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "event_type": event_type,
            "payload": payload,
            "occurred_at": occurred_at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
