"""The audit binder: what a regulator is handed, and what it admits it lacks.

Two things are asserted here that a rendering test normally would not bother
with. First, the framing — the binder has to say which citation it answers, or
the reader has to take on trust that it is responsive to their request. Second,
the out-of-scope section, because each framework's §6 asks for evidence Pramana
does not hold, and a document that quietly omits those items implies a
completeness it does not have.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from pramana.domain.binder_document import (
    FRAMINGS,
    AttemptLine,
    BinderDocument,
    BinderItem,
    build_binder_html,
)

PERIOD_START = datetime(2026, 1, 1, tzinfo=UTC)
PERIOD_END = datetime(2026, 12, 31, tzinfo=UTC)


def item(**overrides: object) -> BinderItem:
    base = {
        "course_title": "SOX Awareness",
        "course_version_id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "course_version_number": 3,
        "status": "passed",
        "assigned_at": datetime(2026, 2, 1, tzinfo=UTC),
        "terminal_at": datetime(2026, 3, 1, tzinfo=UTC),
        "attempts": (
            AttemptLine(
                attempt_number=1,
                outcome="failed",
                score_pct=40.0,
                submitted_at=datetime(2026, 2, 10, tzinfo=UTC),
            ),
            AttemptLine(
                attempt_number=2,
                outcome="passed",
                score_pct=95.0,
                submitted_at=datetime(2026, 3, 1, tzinfo=UTC),
            ),
        ),
        "certificate_code": "CODE123",
        "certificate_issued_at": datetime(2026, 3, 1, tzinfo=UTC),
        "attestation_text_version": "v1",
        "attestation_timestamp": datetime(2026, 3, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return BinderItem(**base)  # type: ignore[arg-type]


def doc(**overrides: object) -> BinderDocument:
    base = {
        "subject_name": "Ada Lovelace",
        "subject_email": "ada@example.com",
        "framing": FRAMINGS["sox"],
        "period_start": PERIOD_START,
        "period_end": PERIOD_END,
        "generated_at": datetime(2026, 12, 31, tzinfo=UTC),
        "items": (item(),),
    }
    base.update(overrides)
    return BinderDocument(**base)  # type: ignore[arg-type]


class TestFraming:
    def test_names_the_citation_it_answers(self) -> None:
        """Otherwise the reader must take responsiveness on trust."""
        assert "404" in build_binder_html(doc())

    def test_uses_the_regulator_s_own_term(self) -> None:
        html = build_binder_html(doc())
        assert FRAMINGS["sox"].artifact_name in html

    @pytest.mark.parametrize("code", sorted(FRAMINGS))
    def test_every_framework_has_a_usable_framing(self, code: str) -> None:
        framing = FRAMINGS[code]
        assert framing.title.strip()
        assert framing.citation.strip()
        assert framing.artifact_name.strip()
        assert framing.out_of_scope, f"{code} lists nothing as out of scope"

    def test_hipaa_binder_cites_the_privacy_rule(self) -> None:
        assert "164.530(b)" in build_binder_html(doc(framing=FRAMINGS["hipaa"]))

    def test_pci_binder_cites_requirement_12_6(self) -> None:
        assert "12.6" in build_binder_html(doc(framing=FRAMINGS["pci_dss"]))


class TestOutOfScope:
    def test_the_binder_states_what_it_does_not_cover(self) -> None:
        """An auditor discovering the gap themselves is the worse outcome."""
        html = build_binder_html(doc())
        assert "not covered" in html.lower()
        for gap in FRAMINGS["sox"].out_of_scope:
            assert gap in html

    def test_gaps_differ_by_framework(self) -> None:
        """Each regulator asks for different things Pramana does not hold."""
        assert FRAMINGS["hipaa"].out_of_scope != FRAMINGS["sox"].out_of_scope


class TestEvidenceContent:
    def test_every_attempt_is_listed_including_failures(self) -> None:
        """A binder showing only the passing attempt hides the retry history."""
        html = build_binder_html(doc())
        assert "40.0" in html
        assert "95.0" in html

    def test_the_pinned_course_version_is_shown(self) -> None:
        assert "22222222-2222-2222-2222-222222222222" in build_binder_html(doc())

    def test_the_attestation_is_included(self) -> None:
        """SOX §6.3 asks for it by name; the JSON binder omits it."""
        html = build_binder_html(doc())
        assert "v1" in html
        assert "attestation" in html.lower()

    def test_the_certificate_code_is_shown(self) -> None:
        assert "CODE123" in build_binder_html(doc())

    def test_an_assignment_without_a_certificate_still_renders(self) -> None:
        html = build_binder_html(
            doc(
                items=(
                    item(
                        status="failed",
                        certificate_code=None,
                        certificate_issued_at=None,
                        attestation_text_version=None,
                        attestation_timestamp=None,
                    ),
                )
            )
        )
        assert "failed" in html


class TestEmptyBinder:
    def test_an_empty_period_says_so_explicitly(self) -> None:
        """A blank page reads as a broken export, not as 'no records'."""
        html = build_binder_html(doc(items=()))
        assert "no training records" in html.lower()


class TestEscaping:
    def test_course_titles_are_escaped(self) -> None:
        html = build_binder_html(doc(items=(item(course_title="<img src=x>"),)))
        assert "<img src=x>" not in html
        assert "&lt;img" in html

    def test_subject_name_is_escaped(self) -> None:
        html = build_binder_html(doc(subject_name="<b>Ada</b>"))
        assert "<b>Ada</b>" not in html
