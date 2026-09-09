"""The pilot render harness, exercised without weights.

The render itself needs ~10 GB of model weights and about an hour of CPU, so
CI cannot run it. What CI can check is that the harness composes the right
briefs, enforces both its limits (the provider's own per-render cap, and this
harness's own total-duration budget for the segment), and reports honestly.
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


def test_plan_refuses_a_segment_over_the_total_duration_budget() -> None:
    """The harness's own budget, not the provider's per-render cap.

    No single render here exceeds the provider's cap (each is 6.0s, not over
    10s) — the provider would accept all three. What fires is the harness's
    OWN total-duration budget for the concatenated segment (3 x 6.0s =
    18.0s), which deliberately reuses the provider's ceiling as its value
    but is a cost guard, not a provider rejection.
    """
    with pytest.raises(ValueError, match="budget"):
        harness.build_plan(narration_lines=SCRIPT_LINES, clause_title="ICFR", shot_duration_s=6.0)


def test_plan_refuses_a_single_render_over_the_provider_cap() -> None:
    """The provider's own rule: one render longer than the ceiling.

    A single line's total duration equals its one render's duration, so this
    input also happens to exceed the segment budget — both checks would fire
    on it. The match is narrowed to wording unique to the per-render message
    ("refuse this render"), not just "max_duration_s" (which the budget
    message also names, to contrast itself with the provider's own rule), so
    this test cannot pass via the wrong guard.
    """
    with pytest.raises(ValueError, match="refuse this render"):
        harness.build_plan(
            narration_lines=["one long scene"], clause_title="ICFR", shot_duration_s=12.0
        )


def test_sha256_of_a_known_byte_string() -> None:
    assert harness.sha256_bytes(b"abc").startswith("sha256:ba7816bf")
