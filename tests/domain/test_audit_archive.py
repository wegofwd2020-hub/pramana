"""Building an archive segment is pure, and so is checking one.

The archive exists to be trusted after the database it came from is gone, so the
segment format is the deliverable: rows with their hashes, plus a manifest that
lets a reader confirm both that the segment is internally intact *and* that it
follows the segment before it. Nothing here touches S3 or a session.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from pramana.domain.audit_archive import (
    SegmentManifest,
    build_segment,
    segment_key,
    segments_are_contiguous,
)
from pramana.domain.audit_hash import compute_audit_hash
from pramana.domain.audit_verification import AuditRow, verify_chain

TENANT = uuid.uuid4()


def chain(n: int, *, start_id: int = 1) -> list[AuditRow]:
    """``n`` rows forming a valid chain, as the database would hold them."""
    rows: list[AuditRow] = []
    prev: str | None = None
    for i in range(n):
        occurred = datetime(2026, 1, 1, tzinfo=UTC)
        payload = {"seq": i}
        digest = compute_audit_hash(
            prev_audit_hash=prev,
            tenant_id=TENANT,
            actor_user_id=None,
            entity_type="user",
            entity_id="u",
            event_type="test.event",
            payload=payload,
            occurred_at=occurred,
        )
        rows.append(
            AuditRow(
                audit_id=start_id + i,
                tenant_id=TENANT,
                actor_user_id=None,
                entity_type="user",
                entity_id="u",
                event_type="test.event",
                payload=payload,
                occurred_at=occurred,
                prev_audit_hash=prev,
                audit_hash=digest,
            )
        )
        prev = digest
    return rows


class TestSegmentBuilding:
    def test_segment_carries_every_row_as_ndjson(self) -> None:
        rows = chain(3)
        segment = build_segment(rows)
        lines = segment.body.decode("utf-8").strip().split("\n")
        assert len(lines) == 3
        assert [json.loads(line)["audit_id"] for line in lines] == [1, 2, 3]

    def test_rows_keep_their_hashes(self) -> None:
        """Without the hashes the archive is a document to be taken on trust."""
        rows = chain(2)
        first = json.loads(build_segment(rows).body.decode("utf-8").split("\n")[0])
        assert first["audit_hash"] == rows[0].audit_hash
        assert first["prev_audit_hash"] == rows[0].prev_audit_hash

    def test_manifest_describes_the_range(self) -> None:
        rows = chain(5, start_id=10)
        manifest = build_segment(rows).manifest
        assert manifest.first_audit_id == 10
        assert manifest.last_audit_id == 14
        assert manifest.row_count == 5

    def test_manifest_pins_both_chain_boundaries(self) -> None:
        """The head hash lets the next segment prove it follows this one."""
        rows = chain(3)
        manifest = build_segment(rows).manifest
        assert manifest.head_audit_hash == rows[-1].audit_hash
        assert manifest.prev_audit_hash == rows[0].prev_audit_hash

    def test_empty_input_is_rejected(self) -> None:
        """An empty segment would archive nothing while advancing the marker."""
        with pytest.raises(ValueError):
            build_segment([])

    def test_archived_body_still_verifies(self) -> None:
        """The whole point: a reader can re-verify the archive without the database."""
        rows = chain(4)
        body = build_segment(rows).body.decode("utf-8")
        restored = [
            AuditRow(
                audit_id=d["audit_id"],
                tenant_id=uuid.UUID(d["tenant_id"]),
                actor_user_id=None,
                entity_type=d["entity_type"],
                entity_id=d["entity_id"],
                event_type=d["event_type"],
                payload=d["payload"],
                occurred_at=datetime.fromisoformat(d["occurred_at"]),
                prev_audit_hash=d["prev_audit_hash"],
                audit_hash=d["audit_hash"],
            )
            for d in (json.loads(line) for line in body.strip().split("\n"))
        ]
        assert verify_chain(restored).ok


class TestSegmentChaining:
    def test_consecutive_segments_are_contiguous(self) -> None:
        rows = chain(6)
        first = build_segment(rows[:3]).manifest
        second = build_segment(rows[3:]).manifest
        assert segments_are_contiguous(first, second)

    def test_a_gap_between_segments_is_detected(self) -> None:
        """A missing segment must be as visible as a missing row."""
        rows = chain(9)
        first = build_segment(rows[:3]).manifest
        skipped_one = build_segment(rows[6:]).manifest
        assert not segments_are_contiguous(first, skipped_one)

    def test_reordered_segments_are_not_contiguous(self) -> None:
        rows = chain(6)
        first = build_segment(rows[:3]).manifest
        second = build_segment(rows[3:]).manifest
        assert not segments_are_contiguous(second, first)


class TestSegmentKey:
    def test_key_sorts_lexicographically_by_id(self) -> None:
        """Zero-padded so a bucket listing is in chain order, not string order."""
        keys = [segment_key(first=2, last=3), segment_key(first=10, last=11)]
        assert keys == sorted(keys)

    def test_key_is_deterministic(self) -> None:
        """Re-archiving the same range overwrites rather than duplicating."""
        assert segment_key(first=1, last=9) == segment_key(first=1, last=9)

    def test_manifest_serialises_to_json(self) -> None:
        manifest = build_segment(chain(2)).manifest
        assert isinstance(manifest, SegmentManifest)
        assert json.loads(manifest.to_json())["row_count"] == 2
