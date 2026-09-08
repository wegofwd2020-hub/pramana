"""Whole-archive continuity (TICKETS/PR-2).

``segments_are_contiguous`` compares one neighbouring pair. It existed from the
day the archive was built and was called from nothing but its own tests, so the
failure the manifests were *designed* to expose — a dropped segment — was never
actually looked for. These cover the walk over a whole archive.

Pure: manifests in, verdict out. No session, no object store.
"""

from __future__ import annotations

from pramana.domain.audit_archive import (
    SegmentManifest,
    verify_segment_continuity,
)


def _manifest(first: int, last: int, prev: str | None, head: str) -> SegmentManifest:
    return SegmentManifest(
        first_audit_id=first,
        last_audit_id=last,
        row_count=last - first + 1,
        prev_audit_hash=prev,
        head_audit_hash=head,
    )


def _run(*links: tuple[int, int]) -> list[SegmentManifest]:
    """Build a correctly chained archive from (first, last) id ranges."""
    out: list[SegmentManifest] = []
    prev: str | None = None
    for first, last in links:
        head = f"hash-{last}"
        out.append(_manifest(first, last, prev, head))
        prev = head
    return out


class TestAnIntactArchive:
    def test_a_single_segment_is_intact(self) -> None:
        result = verify_segment_continuity(_run((1, 10)))
        assert result.intact
        assert result.segment_count == 1
        assert result.covered_through == 10

    def test_a_chained_run_is_intact(self) -> None:
        result = verify_segment_continuity(_run((1, 10), (11, 20), (21, 30)))
        assert result.intact
        assert result.gaps == ()
        assert result.covered_through == 30

    def test_order_of_input_does_not_matter(self) -> None:
        """Segments are sorted by id; a caller may pass them in any order."""
        segments = _run((1, 10), (11, 20), (21, 30))
        shuffled = [segments[2], segments[0], segments[1]]
        assert verify_segment_continuity(shuffled).intact

    def test_an_empty_archive_is_not_a_break(self) -> None:
        """Nothing archived is a different problem from a hole, and must not
        report as one — otherwise every fresh deployment looks tampered with."""
        result = verify_segment_continuity([])
        assert result.intact
        assert result.segment_count == 0
        assert result.covered_through is None


class TestADroppedSegmentIsDetected:
    def test_a_missing_middle_segment_is_reported(self) -> None:
        """The case the whole manifest scheme exists for."""
        segments = _run((1, 10), (11, 20), (21, 30))
        without_middle = [segments[0], segments[2]]

        result = verify_segment_continuity(without_middle)

        assert not result.intact
        assert len(result.gaps) == 1
        gap = result.gaps[0]
        assert gap.after_audit_id == 10
        assert gap.before_audit_id == 21
        assert "10 row(s) unaccounted for" in gap.reason

    def test_every_gap_is_reported_not_just_the_first(self) -> None:
        segments = _run((1, 10), (11, 20), (21, 30), (31, 40), (41, 50))
        holed = [segments[0], segments[2], segments[4]]

        result = verify_segment_continuity(holed)

        assert len(result.gaps) == 2
        assert [g.after_audit_id for g in result.gaps] == [10, 30]

    def test_covered_through_still_reports_the_high_water_mark(self) -> None:
        """A holed archive still covers *through* its last id — the gap is the
        finding, and hiding the range would make the report harder to act on."""
        segments = _run((1, 10), (11, 20), (21, 30))
        result = verify_segment_continuity([segments[0], segments[2]])
        assert result.covered_through == 30


class TestAForgedSegmentIsDetected:
    def test_consecutive_ids_with_a_broken_hash_link_are_rejected(self) -> None:
        """Ids alone are forgeable; the hash link is the real check.

        A segment fabricated with exactly the right id range would satisfy the
        arithmetic. Only a segment that genuinely follows can carry the previous
        one's head hash.
        """
        first = _manifest(1, 10, None, "hash-10")
        forged = _manifest(11, 20, "hash-SOMETHING-ELSE", "hash-20")

        result = verify_segment_continuity([first, forged])

        assert not result.intact
        assert "hash link is broken" in result.gaps[0].reason

    def test_an_overlapping_segment_is_reported(self) -> None:
        """Re-archiving a range under a different key would double-count rows."""
        first = _manifest(1, 20, None, "hash-20")
        overlapping = _manifest(11, 30, "hash-20", "hash-30")

        result = verify_segment_continuity([first, overlapping])

        assert not result.intact
        assert result.gaps[0].before_audit_id == 11
