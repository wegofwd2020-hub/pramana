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
