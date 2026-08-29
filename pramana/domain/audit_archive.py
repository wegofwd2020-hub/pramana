"""Archive segment format — pure, no session and no S3.

WORM archival exists for the case where the database is gone, untrusted, or
being disputed. That makes the *format* the deliverable, not the upload: a
segment has to be verifiable by someone who has only the object and a
description of the scheme.

So a segment is NDJSON of rows carrying their own hashes — the same shape
:func:`~pramana.domain.audit_verification.verify_chain` consumes — plus a
manifest pinning both ends of the range. The manifest is what makes a *missing
segment* as detectable as a missing row: each one records the hash it starts
after and the hash it ends on, so consecutive segments link exactly the way
consecutive rows do. Verifying rows alone would prove each object intact while
saying nothing about whether an object had been quietly dropped.

Kept in the domain layer, and pure, for the reason the hash function is: an
auditor must be able to re-implement this and agree, without running Pramana.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from pramana.domain.audit_verification import AuditRow

#: Width of the zero-padded ids in a segment key. Ten digits covers ten billion
#: rows; the padding matters because it makes a lexicographic bucket listing
#: come back in chain order.
_ID_WIDTH = 10


@dataclass(frozen=True, slots=True)
class SegmentManifest:
    """What one archived segment contains, and where it sits in the chain."""

    first_audit_id: int
    last_audit_id: int
    row_count: int
    #: ``prev_audit_hash`` of the first row — the hash this segment follows.
    prev_audit_hash: str | None
    #: ``audit_hash`` of the last row — the chain head as of this segment.
    head_audit_hash: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class Segment:
    """A built segment: the bytes to store and the manifest describing them."""

    manifest: SegmentManifest
    body: bytes

    @property
    def key(self) -> str:
        return segment_key(first=self.manifest.first_audit_id, last=self.manifest.last_audit_id)


def segment_key(*, first: int, last: int) -> str:
    """Deterministic object key for an id range.

    Deterministic so re-archiving a range overwrites rather than duplicating,
    and zero-padded so a bucket listing sorts in chain order.
    """
    return f"audit/segment-{first:0{_ID_WIDTH}d}-{last:0{_ID_WIDTH}d}.ndjson"


def _row_to_dict(row: AuditRow) -> dict[str, object]:
    return {
        "audit_id": row.audit_id,
        "tenant_id": str(row.tenant_id),
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "event_type": row.event_type,
        "payload": row.payload,
        "occurred_at": row.occurred_at.isoformat(),
        "prev_audit_hash": row.prev_audit_hash,
        "audit_hash": row.audit_hash,
    }


def build_segment(rows: Sequence[AuditRow]) -> Segment:
    """Build one segment from rows in ascending ``audit_id`` order.

    Raises:
        ValueError: ``rows`` is empty — an empty segment would archive nothing
            while still advancing the caller's high-water mark, silently leaving
            a hole in the archive.
    """
    if not rows:
        raise ValueError("cannot build an archive segment from no rows")

    body = "\n".join(
        json.dumps(_row_to_dict(row), sort_keys=True, separators=(",", ":")) for row in rows
    )
    manifest = SegmentManifest(
        first_audit_id=rows[0].audit_id,
        last_audit_id=rows[-1].audit_id,
        row_count=len(rows),
        prev_audit_hash=rows[0].prev_audit_hash,
        head_audit_hash=rows[-1].audit_hash,
    )
    return Segment(manifest=manifest, body=(body + "\n").encode("utf-8"))


def segments_are_contiguous(earlier: SegmentManifest, later: SegmentManifest) -> bool:
    """True if ``later`` picks up exactly where ``earlier`` left off.

    Checks the hash link rather than only the id arithmetic: ids alone would be
    satisfied by a fabricated segment with the right numbers, while the hash can
    only match if ``later`` genuinely follows the rows ``earlier`` ends with.
    """
    return (
        later.first_audit_id == earlier.last_audit_id + 1
        and later.prev_audit_hash == earlier.head_audit_hash
    )
