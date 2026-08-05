"""Tests for the pure audit-chain verifier."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

from pramana.domain.audit_hash import compute_audit_hash
from pramana.domain.audit_verification import AuditRow, verify_chain

TENANT = uuid.uuid4()
NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _row(
    audit_id: int, prev_hash: str | None, *, event: str = "x.y", payload: dict | None = None
) -> AuditRow:
    payload = payload or {"n": audit_id}
    h = compute_audit_hash(
        prev_audit_hash=prev_hash,
        tenant_id=TENANT,
        actor_user_id=None,
        entity_type="assignment",
        entity_id=str(audit_id),
        event_type=event,
        payload=payload,
        occurred_at=NOW,
    )
    return AuditRow(
        audit_id=audit_id,
        tenant_id=TENANT,
        actor_user_id=None,
        entity_type="assignment",
        entity_id=str(audit_id),
        event_type=event,
        payload=payload,
        occurred_at=NOW,
        prev_audit_hash=prev_hash,
        audit_hash=h,
    )


def _chain(n: int) -> list[AuditRow]:
    rows: list[AuditRow] = []
    prev: str | None = None
    for i in range(1, n + 1):
        row = _row(i, prev)
        rows.append(row)
        prev = row.audit_hash
    return rows


def test_empty_chain_is_ok() -> None:
    result = verify_chain([])
    assert result.ok is True
    assert result.total == 0


def test_valid_chain_verifies() -> None:
    result = verify_chain(_chain(5))
    assert result.ok is True
    assert result.total == 5
    assert result.first_break is None


def test_tampered_payload_is_hash_mismatch() -> None:
    chain = _chain(5)
    # edit row 3's payload in place (its stored audit_hash now no longer matches)
    chain[2] = replace(chain[2], payload={"n": 999})
    result = verify_chain(chain)
    assert result.ok is False
    assert result.first_break is not None
    assert result.first_break.audit_id == 3
    assert result.first_break.reason == "hash_mismatch"


def test_deleted_row_is_broken_link() -> None:
    chain = _chain(5)
    del chain[2]  # remove row 3; row 4's prev now points at a missing predecessor
    result = verify_chain(chain)
    assert result.ok is False
    assert result.first_break is not None
    assert result.first_break.audit_id == 4
    assert result.first_break.reason == "broken_link"


def test_reordered_rows_is_broken_link() -> None:
    chain = _chain(5)
    chain[1], chain[2] = chain[2], chain[1]  # swap rows 2 and 3
    result = verify_chain(chain)
    assert result.ok is False
    assert result.first_break is not None
    assert result.first_break.reason == "broken_link"


def test_first_row_with_nonnull_prev_breaks() -> None:
    chain = _chain(3)
    chain[0] = replace(chain[0], prev_audit_hash="deadbeef")
    result = verify_chain(chain)
    assert result.ok is False
    assert result.first_break is not None
    assert result.first_break.audit_id == 1
    assert result.first_break.reason == "broken_link"


def test_reports_first_break_only() -> None:
    chain = _chain(6)
    chain[1] = replace(chain[1], payload={"n": -1})  # break at row 2
    chain[4] = replace(chain[4], payload={"n": -2})  # and row 5
    result = verify_chain(chain)
    assert result.first_break is not None
    assert result.first_break.audit_id == 2
