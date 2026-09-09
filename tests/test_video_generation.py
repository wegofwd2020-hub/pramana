"""Unit tests for in-process video generation (ADR-026), no DB, no live API.

The video provider is a fake :class:`wegofwd_video.VideoProvider` returning a
canned asset, so the make-step (brief build → capability check → projection onto
the draft body) and the publish-time materialisation are exercised
deterministically. The async DB shell (:func:`attach_course_video`) is left for
the integration-test phase, consistent with the repo's other services.
"""

from __future__ import annotations

import pytest
from wegofwd_video import VideoCapabilities, VideoProvider, VideoRequest, VideoResult
from wegofwd_video.errors import VideoCapabilityError

from pramana.domain import video_generation as vg
from pramana.domain.video_generation import (
    GEN_ENGINE,
    VIDEO_PROMPT_VERSION,
    MaterializedVideo,
    build_video_brief,
    materialize_video,
    video_to_body_patch,
)
from pramana.exceptions import ValidationError
from pramana.services.video_generation import generate_video_result

_LINES = ["A second approver is required.", "The submitter cannot self-approve."]


class FakeVideoProvider(VideoProvider):
    """A scripted provider returning one canned asset. provider_id='veo' so the
    capability check resolves the real veo limits from the registry."""

    provider_id = "veo"
    capabilities = VideoCapabilities(
        max_duration_s=60, resolutions=("720p", "1080p", "4k"), native_audio=True
    )

    def __init__(self, result: VideoResult | None = None) -> None:
        self._result = result or VideoResult(
            provider_id="veo",
            model="veo-3.1",
            asset_bytes=b"\x00\x01mp4",
            duration_s=12.0,
            resolution="1080p",
            has_audio=True,
            c2pa_signed=True,
            watermark="SynthID",
        )
        self.seen: VideoRequest | None = None

    @property
    def model(self) -> str:
        return "veo-3.1"

    def generate(self, req: VideoRequest) -> VideoResult:
        self.seen = req
        return self._result


# ── build_video_brief ─────────────────────────────────────────────────────────
def test_build_video_brief_one_shot_per_line():
    brief = build_video_brief(clause_title="SOX 404", narration_lines=_LINES)
    assert len(brief.shots) == 2
    assert brief.shots[0].scene_index == 1
    assert brief.shots[0].dialogue == _LINES[0]
    assert brief.shots[1].dialogue == _LINES[1]
    assert brief.global_style  # compliance house style present
    assert brief.global_negative


def test_build_video_brief_skips_blank_lines():
    brief = build_video_brief(clause_title="x", narration_lines=["  ", "real line", ""])
    assert len(brief.shots) == 1
    assert brief.shots[0].dialogue == "real line"


def test_build_video_brief_rejects_empty_narration():
    with pytest.raises(ValidationError):
        build_video_brief(clause_title="x", narration_lines=["", "   "])


# ── generate_video_result (make step) ─────────────────────────────────────────
def test_generate_video_result_calls_provider():
    provider = FakeVideoProvider()
    brief = build_video_brief(clause_title="SOX 404", narration_lines=_LINES)
    result = generate_video_result(provider, brief, resolution="1080p")
    assert result.resolution == "1080p"
    # request was shaped with the summed duration
    assert provider.seen is not None
    assert provider.seen.target_duration_s == sum(s.duration_s for s in brief.shots)


def test_generate_video_result_capability_check_rejects_over_spec():
    provider = FakeVideoProvider()
    brief = build_video_brief(clause_title="SOX 404", narration_lines=_LINES)
    with pytest.raises(VideoCapabilityError):
        generate_video_result(provider, brief, resolution="8k")  # veo max is 4k


# ── video_to_body_patch ───────────────────────────────────────────────────────
def test_video_to_body_patch_shape():
    result = FakeVideoProvider()._result
    patch = video_to_body_patch(
        result,
        asset_ref="video/c/d.mp4",
        provenance={"engine": "wegofwd-video", "provider": "veo", "model": "veo-3.1"},
        min_watch_pct=90,
    )
    v = patch["video"]
    assert v["asset_ref"] == "video/c/d.mp4"
    assert v["min_watch_pct"] == 90
    assert v["has_audio"] is True
    assert v["c2pa_signed"] is True
    assert v["provenance"]["provider"] == "veo"


def test_video_to_body_patch_rejects_blank_ref_and_bad_pct():
    result = FakeVideoProvider()._result
    with pytest.raises(ValidationError):
        video_to_body_patch(result, asset_ref="", provenance={})
    with pytest.raises(ValidationError):
        video_to_body_patch(result, asset_ref="k", provenance={}, min_watch_pct=101)


# ── materialize_video (publish step) ──────────────────────────────────────────
def test_materialize_video_absent_returns_none():
    assert materialize_video({"quiz": {}}) is None


def test_materialize_video_present_ok():
    body = {"video": {"asset_ref": "video/c/d.mp4", "min_watch_pct": 80}}
    mv = materialize_video(body)
    assert mv == MaterializedVideo(asset_ref="video/c/d.mp4", min_watch_pct=80)


def test_materialize_video_defaults_min_watch_to_zero():
    mv = materialize_video({"video": {"asset_ref": "k"}})
    assert mv is not None and mv.min_watch_pct == 0


@pytest.mark.parametrize(
    "video",
    [
        {"asset_ref": ""},
        {"asset_ref": "   "},
        {"asset_ref": "k", "min_watch_pct": 101},
        {"asset_ref": "k", "min_watch_pct": True},  # bool must not pose as 1
        "not-an-object",
    ],
)
def test_materialize_video_malformed_raises(video):
    with pytest.raises(ValidationError):
        materialize_video({"video": video})


def test_generator_constants_stable():
    assert GEN_ENGINE == "pramana"
    assert VIDEO_PROMPT_VERSION.startswith("pramana-video")


# ── transcript projection ──────────────────────────────────────────────────────
class TestTranscriptProjection:
    """Silent footage means the transcript is the only thing that speaks."""

    def test_transcript_is_projected_from_the_body(self) -> None:
        video = materialize_video(
            {
                "video": {
                    "asset_ref": "s3://a.mp4",
                    "min_watch_pct": 80,
                    "transcript": "Every control has an owner.",
                }
            }
        )
        assert video is not None
        assert video.transcript == "Every control has an owner."

    def test_a_body_without_a_transcript_projects_none(self) -> None:
        """Pre-existing drafts have no transcript and must still publish."""
        video = materialize_video({"video": {"asset_ref": "s3://a.mp4", "min_watch_pct": 80}})
        assert video is not None
        assert video.transcript is None

    def test_a_blank_transcript_is_normalised_to_none(self) -> None:
        video = materialize_video(
            {"video": {"asset_ref": "s3://a.mp4", "min_watch_pct": 0, "transcript": "   "}}
        )
        assert video is not None
        assert video.transcript is None

    def test_a_non_string_transcript_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            materialize_video(
                {"video": {"asset_ref": "s3://a.mp4", "min_watch_pct": 0, "transcript": 42}}
            )


class TestSceneBriefs:
    """One brief per line, because the provider flattens multi-shot briefs."""

    def test_one_brief_per_narration_line(self) -> None:
        briefs = vg.build_scene_briefs(
            clause_title="ICFR awareness",
            narration_lines=["One.", "Two.", "Three."],
        )
        assert len(briefs) == 3

    def test_each_brief_has_exactly_one_shot(self) -> None:
        briefs = vg.build_scene_briefs(
            clause_title="ICFR awareness", narration_lines=["One.", "Two."]
        )
        assert all(len(b.shots) == 1 for b in briefs)

    def test_each_line_becomes_its_own_shot_dialogue_in_order(self) -> None:
        lines = ["First claim.", "Second claim."]
        briefs = vg.build_scene_briefs(clause_title="ICFR", narration_lines=lines)
        assert [b.shots[0].dialogue for b in briefs] == lines

    def test_each_brief_stays_under_the_local_provider_duration_cap(self) -> None:
        """local-preview declares max_duration_s = 10; a longer brief is refused."""
        briefs = vg.build_scene_briefs(
            clause_title="ICFR",
            narration_lines=["a"] * 5,
            shot_duration_s=2.0,
        )
        assert all(sum(s.duration_s for s in b.shots) <= 10 for b in briefs)

    def test_ordering_comes_from_list_position_not_scene_index(self) -> None:
        """Each brief holds one shot, so its own scene_index is always 1.

        `build_video_brief` numbers shots within a single call (`i + 1`), and
        every call here gets exactly one line. Order lives in the returned
        list, which is what the concat step consumes.
        """
        briefs = vg.build_scene_briefs(clause_title="ICFR", narration_lines=["a", "b", "c"])
        assert [b.shots[0].scene_index for b in briefs] == [1, 1, 1]

    def test_no_lines_yields_no_briefs(self) -> None:
        assert vg.build_scene_briefs(clause_title="ICFR", narration_lines=[]) == []

    def test_blank_lines_are_skipped_not_fatal(self) -> None:
        """`build_video_brief` raises on empty narration, so blanks must be
        filtered here — one stray blank line in a script must not kill the
        whole composition."""
        briefs = vg.build_scene_briefs(clause_title="ICFR", narration_lines=["a", "   ", "", "b"])
        assert len(briefs) == 2
