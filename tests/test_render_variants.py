"""The variant render harness, exercised without weights or a GPU.

The renders themselves need ~26 GB of weights and a rented GPU, so CI cannot
run them. What CI can check is that the ladder is actually a ladder: that each
rung differs from the next in exactly the dimension it claims to isolate, that
hand-written prompts reach the model unmangled, and that the correspondence
between prompts and narration lines cannot silently drift.

That last one matters most. If the hand-written prompts and the narration lines
fall out of step, every variant still renders happily and the comparison is
quietly meaningless — the failure has no symptom at render time.
"""

from __future__ import annotations

import pytest

from scripts import render_variants as harness


def _by_name(name: str) -> harness.Variant:
    return next(v for v in harness.VARIANTS if v.name == name)


class TestTheLadder:
    """Each rung must isolate one variable, or the experiment proves nothing."""

    def test_baseline_reproduces_the_refused_configuration(self) -> None:
        """The control. These are the numbers recorded in sox-pilot.json."""
        baseline = _by_name("baseline")
        assert baseline.resolution == "320p"
        assert baseline.steps == 8
        assert baseline.guidance == 1.0
        assert baseline.is_distilled
        assert baseline.scene_prompts is None

    def test_quality_changes_render_settings_but_not_the_prompt(self) -> None:
        """baseline -> quality must be attributable to settings alone."""
        baseline, quality = _by_name("baseline"), _by_name("quality")
        assert quality.scene_prompts is None, "quality must keep the templated prompt"
        assert quality.guidance > baseline.guidance
        assert quality.steps > baseline.steps
        assert not quality.is_distilled

    def test_prompted_changes_the_prompt_but_not_the_render_settings(self) -> None:
        """quality -> prompted must be attributable to the prompt alone.

        If a stray settings change crept into `prompted`, the second comparison
        would silently measure two things at once.
        """
        quality, prompted = _by_name("quality"), _by_name("prompted")
        assert prompted.scene_prompts is not None
        assert prompted.resolution == quality.resolution
        assert prompted.steps == quality.steps
        assert prompted.guidance == quality.guidance
        assert prompted.transformer_file == quality.transformer_file

    def test_cfg_is_off_only_in_the_baseline(self) -> None:
        """guidance 1.0 IS "no classifier-free guidance" — the thing under test."""
        off = [v.name for v in harness.VARIANTS if v.guidance == 1.0]
        assert off == ["baseline"]

    def test_guidance_is_only_raised_off_the_distilled_checkpoint(self) -> None:
        """Distilled checkpoints are trained for guidance 1.0.

        Raising guidance on one usually degrades the output, so "turn CFG on"
        and "leave the distilled transformer" have to happen together.
        """
        for variant in harness.VARIANTS:
            if variant.guidance > 1.0:
                assert not variant.is_distilled, (
                    f"{variant.name} raises guidance on a distilled checkpoint"
                )


class TestBriefComposition:
    def test_every_variant_yields_one_brief_per_narration_line(self) -> None:
        for variant in harness.VARIANTS:
            briefs = harness.build_briefs(variant, shot_duration_s=2.0)
            assert len(briefs) == len(harness.SCRIPT_LINES), variant.name

    def test_each_brief_holds_exactly_one_shot(self) -> None:
        """The provider joins a multi-shot brief into ONE clip and sums the
        durations, so anything but one shot per brief silently collapses the
        scene cuts this harness exists to produce."""
        for variant in harness.VARIANTS:
            for brief in harness.build_briefs(variant, shot_duration_s=2.0):
                assert len(brief.shots) == 1, variant.name

    def test_hand_written_prompts_reach_the_shot_verbatim(self) -> None:
        """Not routed through build_video_brief, whose template would prefix
        "a compliance presenter explains:" onto a visual description."""
        prompted = _by_name("prompted")
        briefs = harness.build_briefs(prompted, shot_duration_s=2.0)
        rendered = [b.shots[0].prompt for b in briefs]
        assert rendered == list(harness.SCENE_PROMPTS)
        assert not any(p.startswith("a compliance presenter explains") for p in rendered)

    def test_the_templated_variants_still_use_the_template(self) -> None:
        """Otherwise `quality` would not be a like-for-like control."""
        briefs = harness.build_briefs(_by_name("quality"), shot_duration_s=2.0)
        for brief in briefs:
            assert brief.shots[0].prompt.startswith("a compliance presenter explains")

    def test_hand_written_scenes_keep_their_narration_line_as_dialogue(self) -> None:
        """The provider drops dialogue (there is no audio track), but it is what
        records which narration line each scene belongs to."""
        briefs = harness.build_briefs(_by_name("prompted"), shot_duration_s=2.0)
        assert [b.shots[0].dialogue for b in briefs] == list(harness.SCRIPT_LINES)

    def test_a_prompt_count_mismatch_is_refused(self) -> None:
        """The silent-drift guard: without this the renders all succeed and the
        comparison is meaningless with no symptom."""
        broken = harness.Variant(
            name="broken",
            why="test",
            resolution="480p",
            steps=30,
            guidance=3.0,
            transformer_file=None,
            style="s",
            negative="n",
            scene_prompts=("only one prompt",),
        )
        with pytest.raises(ValueError, match="1:1"):
            harness.build_briefs(broken, shot_duration_s=2.0)


class TestPrompts:
    def test_the_shipped_prompts_correspond_to_the_narration_lines(self) -> None:
        assert len(harness.SCENE_PROMPTS) == len(harness.SCRIPT_LINES)

    def test_no_prompt_will_be_silently_truncated_by_t5(self) -> None:
        """T5 truncates at PROMPT_MAX_TOKENS and says nothing; an over-long
        prompt renders normally, having dropped its tail."""
        budget_words = int(harness.PROMPT_MAX_TOKENS / 1.3)
        for variant in harness.VARIANTS:
            briefs = harness.build_briefs(variant, shot_duration_s=2.0)
            for i, words in enumerate(harness.check_prompt_length(briefs, variant)):
                assert words <= budget_words, f"{variant.name} scene {i}: ~{words} words"

    def test_the_improved_negative_names_depictions_not_instructions(self) -> None:
        """A diffusion negative is a description of what to steer away from, not
        a command. "no on-screen text artifacts" contains "text" and reads as a
        request for it; the improved negative lists the depictions instead."""
        assert "no " not in harness.QUALITY_NEGATIVE
        for term in ("text", "letters", "captions", "watermark"):
            assert term in harness.QUALITY_NEGATIVE

    def test_the_baseline_negative_is_preserved_as_written(self) -> None:
        """The control has to carry the ineffective negative, unchanged."""
        assert harness.BASELINE_NEGATIVE.startswith("no on-screen text artifacts")


class TestEnvironmentCapture:
    def test_environment_records_what_determinism_depends_on(self) -> None:
        """Determinism here is per (seed, torch build, device). If any of this
        footage is ever attested, this block is the provenance saying on what."""
        env = harness.environment()
        assert "torch" in env
        assert "python" in env
        assert "platform" in env
