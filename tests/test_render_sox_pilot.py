"""The pilot render harness, exercised without weights.

The render itself needs ~10 GB of model weights and about an hour of CPU, so
CI cannot run it. What CI can check is that the harness composes the right
briefs, refuses a segment the provider would reject, and reports honestly.
"""

from __future__ import annotations

import pytest

from scripts import render_sox_pilot as harness

SCRIPT_LINES = [
    "Every control has an owner.",
    "Evidence is recorded when the control runs.",
    "The record is what the auditor will see.",
]


def test_plan_builds_one_brief_per_line() -> None:
    plan = harness.build_plan(narration_lines=SCRIPT_LINES, clause_title="ICFR")
    assert len(plan.briefs) == len(SCRIPT_LINES)


def test_plan_refuses_a_segment_the_provider_would_reject() -> None:
    """max_duration_s = 10; catch it here rather than an hour into a render."""
    with pytest.raises(ValueError, match="max_duration_s"):
        harness.build_plan(narration_lines=SCRIPT_LINES, clause_title="ICFR", shot_duration_s=6.0)


def test_sha256_of_a_known_byte_string() -> None:
    assert harness.sha256_bytes(b"abc").startswith("sha256:ba7816bf")
