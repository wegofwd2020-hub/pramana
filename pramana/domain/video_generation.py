"""In-process video generation from a clause (ADR-013 / ADR-026, first slice).

Pure domain: the compliance video **brief** built from a clause's prose, the
projection of a generated asset onto the draft ``body``, and the publish-time
**materialisation** of that asset onto a course version. No database and no
network — the video call is driven by the service layer through an injected
``wegofwd_video.VideoProvider`` (exactly as the quiz path injects a
``wegofwd_llm.Provider``), so the real logic stays exhaustively unit-testable with
a fake provider.

A drafted video lands on ``ContentDraft.body["video"]`` next to ``body["quiz"]``;
it is **never assignable** until a different human approves the draft, and is
copied onto the immutable :class:`~pramana.db.models.course.CourseVersion` at
publish by :func:`materialize_video` (mirrors :func:`pramana.domain.publication.
materialize_quiz`).

The ``video`` body contract::

    {
        "asset_ref": "video/<course>/<draft>.mp4",  # S3 key (caller-stored)
        "min_watch_pct": 0,  # watch-gate before the quiz
        "transcript": "...",  # approved narration, verbatim — the only text a
        # learner gets, since the footage is silent
        "provenance": {...},  # wegofwd_video.provenance()
        "duration_s": 12,
        "resolution": "1080p",
        "has_audio": true,
        "c2pa_signed": true,
    }
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from wegofwd_video import Ingredient, Shot, VideoBrief, VideoResult

from pramana.exceptions import ValidationError

# Version of THIS generator's brief + body contract. Bump on a material change so
# a draft's provenance records which generator produced its video (drift detection).
VIDEO_PROMPT_VERSION = "pramana-video-2026-09"

# gen_engine for the video stage (the asset is produced via wegofwd-video, but the
# in-house orchestration that built the brief is Pramana's — mirrors quiz GEN_ENGINE).
GEN_ENGINE = "pramana"

# Compliance house style. Photographic, not illustrated: the previous default
# said "flat illustration", and the first pilot review called the result
# "highly cartoonish" — that was the style doing exactly what it was asked,
# which is why it is a house-style decision rather than a defect to fix
# elsewhere. Rendered footage under this style cleared review.
_DEFAULT_STYLE = (
    "restrained corporate documentary photography, muted neutral palette, "
    "natural window light, shallow depth of field"
)
_DEFAULT_NEGATIVE = "no on-screen text artifacts, no logos, no real faces, no flashing"
_DEFAULT_AUDIO = "clear neutral narrator, professional pace, light ambient office tone"
_DEFAULT_SHOT_DURATION_S = 6.0

#: Visual prompt used when the author supplies no ``scene_prompts``.
#:
#: It deliberately says nothing about a presenter, an explainer, or training
#: video, and it does not include the narration text. The previous default was
#: ``f"a compliance presenter explains: {line}"``, which describes *stock
#: corporate training footage* — a genre that ships with burned-in captions. The
#: model reproduced the look and, unable to spell, drew letterform-shaped marks
#: in a caption bar. A reviewer refused the resulting footage for exactly that
#: ("the little text on the screen are not in english"), and removing the genre
#: cue removed the captions.
#:
#: This fallback is deliberately generic, and generic is the point: it is safe
#: rather than good. Every scene rendered from it looks alike, because a
#: narration line is a *claim* and not a picture. Good footage needs
#: ``scene_prompts`` written by whoever wrote the script.
_FALLBACK_SHOT_PROMPT = (
    "a quiet workplace interior, papers and a desk, no one addressing the camera"
)


def build_video_brief(
    *,
    clause_title: str,
    narration_lines: Sequence[str],
    scene_prompts: Sequence[str] | None = None,
    style: str = _DEFAULT_STYLE,
    negative: str = _DEFAULT_NEGATIVE,
    audio_direction: str = _DEFAULT_AUDIO,
    shot_duration_s: float = _DEFAULT_SHOT_DURATION_S,
    ingredients: Sequence[Ingredient] = (),
) -> VideoBrief:
    """Build a :class:`wegofwd_video.VideoBrief` from a clause's narration lines.

    One shot per narration line, in order. The line is always the spoken
    ``dialogue`` (it drives native audio, and it records which claim a scene
    belongs to even on silent paths). What the shot *looks* like comes from
    ``scene_prompts`` when supplied, and from a deliberately generic fallback
    when not.

    **Supply ``scene_prompts``.** A narration line is a claim, not a picture:
    "a missing owner is itself a finding" describes nothing a camera could see.
    Prompts written alongside the script produce footage that cleared human
    review; the fallback produces footage that is merely safe.

    A scene prompt should describe its *subject*, not restate its line. The
    footage is B-roll and asserts no statute — the claims live in the transcript,
    which the accuracy gate approves and the learner reads.

    Args:
        scene_prompts: Visual descriptions, one per entry in ``narration_lines``
            and in the same order. Blank narration lines are dropped along with
            their prompt, so correspondence survives filtering.

    Raises:
        ValidationError: ``narration_lines`` is empty (nothing to narrate), or
            ``scene_prompts`` is supplied at a different length (which would
            silently pair a scene with the wrong claim).
    """
    if scene_prompts is not None and len(scene_prompts) != len(narration_lines):
        raise ValidationError(
            "scene_prompts must have one entry per narration line, in the same order; "
            f"got {len(scene_prompts)} prompts for {len(narration_lines)} lines",
            context={"clause_title": clause_title},
        )
    # Pair BEFORE filtering, so dropping a blank line drops its prompt with it.
    # Filtering the two sequences separately would silently shift every prompt
    # after the blank onto the wrong claim — a defect with no visible symptom.
    prompts: Sequence[str | None] = (
        scene_prompts if scene_prompts is not None else [None] * len(narration_lines)
    )
    # strict=True: lengths are validated above, so a mismatch here would be an
    # internal bug — and pairing silently is exactly how a scene ends up
    # illustrating the wrong claim.
    paired = list(zip(narration_lines, prompts, strict=True))
    kept = [(line.strip(), prompt) for line, prompt in paired if line and line.strip()]
    if not kept:
        raise ValidationError(
            "cannot build a video brief with no narration",
            context={"clause_title": clause_title},
        )
    shots = tuple(
        Shot(
            scene_index=i + 1,
            prompt=prompt if prompt else _FALLBACK_SHOT_PROMPT,
            # The framing triple is left off an authored scene prompt: it was
            # empty in the configuration that cleared review, and "medium /
            # static / even office light" fights a description that already
            # states its own framing.
            shot_type="" if prompt else "medium",
            camera_move="" if prompt else "static",
            lighting="" if prompt else "even office light",
            dialogue=line,
            duration_s=shot_duration_s,
        )
        for i, (line, prompt) in enumerate(kept)
    )
    return VideoBrief(
        global_style=style,
        global_negative=negative,
        audio_direction=audio_direction,
        ingredients=tuple(ingredients),
        shots=shots,
    )


#: One scene per narration line at this length keeps a five-line segment inside
#: the local-preview role's ``max_duration_s = 10`` and each render near the
#: measured 1 080 latent tokens. The module default of 6.0 s targets the Veo
#: path, where the ceiling is higher.
_LOCAL_SHOT_DURATION_S = 2.0


def build_scene_briefs(
    *,
    clause_title: str,
    narration_lines: Sequence[str],
    scene_prompts: Sequence[str] | None = None,
    shot_duration_s: float = _LOCAL_SHOT_DURATION_S,
    style: str = _DEFAULT_STYLE,
    negative: str = _DEFAULT_NEGATIVE,
    audio_direction: str = _DEFAULT_AUDIO,
) -> list[VideoBrief]:
    """Split a lesson into one single-shot brief per narration line.

    The local provider joins a multi-shot brief's shots into a single prompt and
    sums their durations for one render, so a five-shot brief produces one clip
    rather than five scenes. Issuing one brief per line and concatenating the
    results is what actually yields scene cuts — and it keeps each render's
    latent-token count, and therefore its peak memory, near the measured figure
    instead of multiplying it by the scene count.

    Returns:
        One brief per line, in order. Empty input yields an empty list.
    """
    # build_video_brief raises ValidationError on empty narration, so a blank
    # line would abort the whole composition rather than being skipped. Filter
    # first — the same normalisation build_video_brief applies internally.
    if scene_prompts is not None and len(scene_prompts) != len(narration_lines):
        raise ValidationError(
            "scene_prompts must have one entry per narration line, in the same order; "
            f"got {len(scene_prompts)} prompts for {len(narration_lines)} lines",
            context={"clause_title": clause_title},
        )
    # Paired before filtering for the same reason as build_video_brief: a blank
    # line must take its prompt with it, or every later scene illustrates the
    # wrong claim.
    prompts: Sequence[str | None] = (
        scene_prompts if scene_prompts is not None else [None] * len(narration_lines)
    )
    # strict=True: lengths are validated above, so a mismatch here would be an
    # internal bug — and pairing silently is exactly how a scene ends up
    # illustrating the wrong claim.
    paired = list(zip(narration_lines, prompts, strict=True))
    kept = [(line.strip(), prompt) for line, prompt in paired if line and line.strip()]
    return [
        build_video_brief(
            clause_title=clause_title,
            narration_lines=[line],
            scene_prompts=[prompt] if prompt is not None else None,
            style=style,
            negative=negative,
            audio_direction=audio_direction,
            shot_duration_s=shot_duration_s,
        )
        for line, prompt in kept
    ]


def video_to_body_patch(
    result: VideoResult,
    *,
    asset_ref: str,
    provenance: Mapping[str, Any],
    min_watch_pct: int = 0,
) -> dict[str, Any]:
    """Project a generated asset onto the ``{"video": {...}}`` body fragment.

    ``asset_ref`` is the storage key the service obtained after persisting the
    asset (the package itself never stores — ADR-026 D2). ``provenance`` is the
    shared cross-product stamp from :func:`wegofwd_video.provenance`.
    """
    if not asset_ref:
        raise ValidationError("video asset_ref must be a non-empty storage key")
    if not 0 <= min_watch_pct <= 100:
        raise ValidationError(
            "min_watch_pct must be between 0 and 100",
            context={"value": min_watch_pct},
        )
    return {
        "video": {
            "asset_ref": asset_ref,
            "min_watch_pct": min_watch_pct,
            "duration_s": result.duration_s,
            "resolution": result.resolution,
            "has_audio": result.has_audio,
            "c2pa_signed": result.c2pa_signed,
            "provenance": dict(provenance),
        }
    }


@dataclass(frozen=True, slots=True)
class MaterializedVideo:
    """The video projected from a draft body, ready to stamp onto a course version."""

    asset_ref: str
    min_watch_pct: int
    transcript: str | None = None


def materialize_video(body: Mapping[str, Any]) -> MaterializedVideo | None:
    """Project a draft ``body`` onto the course version's video fields.

    Returns ``None`` when the draft carries **no** video (a quiz-only course is
    valid — ``CourseVersion.video_asset_id`` is nullable). When a ``video`` block
    is present it must be well-formed, mirroring :func:`materialize_quiz`'s
    strictness: a malformed block on an ``APPROVED`` draft raises rather than
    publishing a broken version.

    Raises:
        ValidationError: ``body.video`` is present but malformed (missing/blank
            ``asset_ref`` or an out-of-range ``min_watch_pct``).
    """
    video = body.get("video") if isinstance(body, Mapping) else None
    if video is None:
        return None
    if not isinstance(video, Mapping):
        raise ValidationError("draft body.video must be an object", context={"field": "body.video"})

    asset_ref = video.get("asset_ref")
    if not isinstance(asset_ref, str) or not asset_ref.strip():
        raise ValidationError(
            "body.video.asset_ref must be a non-empty string",
            context={"field": "body.video.asset_ref"},
        )

    raw_pct = video.get("min_watch_pct", 0)
    # bool is an int subclass — reject it so True/False can't pose as 1/0.
    if not isinstance(raw_pct, int) or isinstance(raw_pct, bool) or not 0 <= raw_pct <= 100:
        raise ValidationError(
            "body.video.min_watch_pct must be an integer in [0, 100]",
            context={"field": "body.video.min_watch_pct", "value": raw_pct},
        )
    raw_transcript = video.get("transcript")
    if raw_transcript is not None and not isinstance(raw_transcript, str):
        raise ValidationError(
            "draft body.video.transcript must be a string",
            context={"field": "body.video.transcript"},
        )
    # Blank is the same as absent: a whitespace-only transcript would render as
    # an empty panel that looks like a bug rather than an intentional silence.
    transcript = raw_transcript.strip() if raw_transcript else None
    return MaterializedVideo(
        asset_ref=asset_ref, min_watch_pct=raw_pct, transcript=transcript or None
    )
