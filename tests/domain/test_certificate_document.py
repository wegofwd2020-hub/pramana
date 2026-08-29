"""What a certificate says.

The rendering engine is uninteresting; the *content* is the part with legal
weight. A certificate that names the course but not the version the learner was
actually tested on is a document that says someone was trained on material that
may since have changed — so these assert the pinned facts are present, without a
PDF engine anywhere near the test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pramana.domain.certificate_document import (
    CertificateDocument,
    build_certificate_html,
)

ISSUED = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
EXPIRES = datetime(2027, 5, 1, 12, 0, tzinfo=UTC)


def doc(**overrides: object) -> CertificateDocument:
    base = {
        "learner_name": "Ada Lovelace",
        "learner_email": "ada@example.com",
        "course_title": "SOX Awareness",
        "course_version_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "course_version_number": 2,
        "score_pct": 92.5,
        "issued_at": ISSUED,
        "expires_at": EXPIRES,
        "verification_code": "ABC123XYZ",
        "attestation_text_version": "v1",
    }
    base.update(overrides)
    return CertificateDocument(**base)  # type: ignore[arg-type]


class TestPinnedFacts:
    def test_names_the_course_version_not_just_the_course(self) -> None:
        """The claim is about the version tested on, which may since be retired."""
        html = build_certificate_html(doc())
        assert "11111111-1111-1111-1111-111111111111" in html
        assert "version 2" in html.lower()

    def test_carries_the_verification_code(self) -> None:
        """Without it the document cannot be checked against the system."""
        assert "ABC123XYZ" in build_certificate_html(doc())

    def test_carries_the_attestation_text_version(self) -> None:
        """*Which* attestation the learner accepted is itself evidence."""
        assert "v1" in build_certificate_html(doc())

    def test_shows_issue_and_expiry(self) -> None:
        html = build_certificate_html(doc())
        assert "2026-05-01" in html
        assert "2027-05-01" in html

    def test_shows_the_score(self) -> None:
        assert "92.5" in build_certificate_html(doc())


class TestEscaping:
    def test_a_course_title_containing_markup_is_escaped(self) -> None:
        """Course titles are author-supplied; they must not become markup."""
        html = build_certificate_html(doc(course_title="<script>alert(1)</script>"))
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_a_learner_name_containing_markup_is_escaped(self) -> None:
        html = build_certificate_html(doc(learner_name="Bobby <b>Tables</b>"))
        assert "<b>Tables</b>" not in html
        assert "&lt;b&gt;" in html


class TestExpiry:
    #: The visible banner, not the CSS class name — the stylesheet mentions
    #: "expired" either way, so asserting on the word alone proves nothing.
    BANNER = "THIS CERTIFICATE HAS EXPIRED"

    def test_an_expired_certificate_says_so(self) -> None:
        """A reader holding the paper must be able to see it has lapsed."""
        html = build_certificate_html(doc(expires_at=datetime(2026, 1, 1, tzinfo=UTC)), now=ISSUED)
        assert self.BANNER in html

    def test_a_current_certificate_is_not_marked_expired(self) -> None:
        html = build_certificate_html(doc(), now=ISSUED)
        assert self.BANNER not in html
        assert ">Valid<" in html


class TestDeterminism:
    def test_the_same_document_renders_identically(self) -> None:
        """Re-rendering replaces storage, so it has to be reproducible."""
        assert build_certificate_html(doc(), now=ISSUED) == build_certificate_html(
            doc(), now=ISSUED
        )
