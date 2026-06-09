"""Tests for the audit hash-chain helper."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pramana.services.audit import compute_audit_hash

NOW = datetime(2026, 6, 5, 13, 0, tzinfo=UTC)


def _hash(**overrides):
    base = {
        "prev_audit_hash": None,
        "tenant_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "actor_user_id": None,
        "entity_type": "content_draft",
        "entity_id": "abc",
        "event_type": "content_draft.receive",
        "payload": {"package_version": 1},
        "occurred_at": NOW,
    }
    base.update(overrides)
    return compute_audit_hash(**base)


def test_hash_is_deterministic() -> None:
    assert _hash() == _hash()


def test_hash_is_64_hex_chars() -> None:
    digest = _hash()
    assert len(digest) == 64
    int(digest, 16)  # parses as hex


def test_prev_hash_changes_the_digest() -> None:
    assert _hash(prev_audit_hash=None) != _hash(prev_audit_hash="a" * 64)


def test_payload_change_changes_the_digest() -> None:
    assert _hash(payload={"a": 1}) != _hash(payload={"a": 2})


def test_payload_key_order_does_not_matter() -> None:
    assert _hash(payload={"a": 1, "b": 2}) == _hash(payload={"b": 2, "a": 1})
