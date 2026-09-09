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

import itertools
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


@dataclass(frozen=True, slots=True)
class ArchiveGap:
    """A break between two consecutive archived segments."""

    #: ``last_audit_id`` of the segment before the break.
    after_audit_id: int
    #: ``first_audit_id`` of the segment after it.
    before_audit_id: int
    reason: str


@dataclass(frozen=True, slots=True)
class ArchiveVerification:
    """Whether the archive, as recorded, is one unbroken run of segments."""

    segment_count: int
    gaps: tuple[ArchiveGap, ...]
    #: Highest ``last_audit_id`` covered, or ``None`` when nothing is archived.
    covered_through: int | None

    @property
    def intact(self) -> bool:
        return not self.gaps


def verify_segment_continuity(manifests: Sequence[SegmentManifest]) -> ArchiveVerification:
    """Check a whole archive end to end, not just one neighbouring pair.

    :func:`segments_are_contiguous` has existed since the archive was built and
    was called from nothing but its own tests, so a **dropped segment — the
    exact failure the manifests were designed to expose — was never actually
    looked for.** This walks the recorded segments in order and reports every
    break.

    Ordering is by ``first_audit_id`` rather than by insertion: the caller may
    hand these over in any order, and a gap is a property of the id/hash run,
    not of when rows happened to be written.

    An empty archive is reported as intact with ``covered_through=None``. That is
    not an endorsement — nothing archived is a *different* problem, and the
    caller should look at how many rows are still pending — but it is genuinely
    not a *break*, and conflating the two would make "the archive has a hole"
    fire on every fresh deployment.
    """
    ordered = sorted(manifests, key=lambda m: m.first_audit_id)
    gaps: list[ArchiveGap] = []
    for earlier, later in itertools.pairwise(ordered):
        if segments_are_contiguous(earlier, later):
            continue
        if later.first_audit_id != earlier.last_audit_id + 1:
            reason = (
                f"ids jump from {earlier.last_audit_id} to {later.first_audit_id} "
                f"— {later.first_audit_id - earlier.last_audit_id - 1} row(s) unaccounted for"
            )
        else:
            # Ids line up but the hash link does not: the stronger signal, since
            # only a segment that genuinely follows can carry the right hash.
            reason = (
                "ids are consecutive but the hash link is broken — the later "
                "segment does not follow the earlier one"
            )
        gaps.append(
            ArchiveGap(
                after_audit_id=earlier.last_audit_id,
                before_audit_id=later.first_audit_id,
                reason=reason,
            )
        )

    return ArchiveVerification(
        segment_count=len(ordered),
        gaps=tuple(gaps),
        covered_through=ordered[-1].last_audit_id if ordered else None,
    )
