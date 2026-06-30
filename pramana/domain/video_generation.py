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
        "asset_ref": "video/<course>/<draft>.mp4",   # S3 key (caller-stored)
        "min_watch_pct": 0,                            # watch-gate before the quiz
        "provenance": { ... },                         # wegofwd_video.provenance()
        "duration_s": 12, "resolution": "1080p", "has_audio": true,
        "c2pa_signed": true
    }
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from wegofwd_video import Ingredient, Shot, VideoBrief, VideoResult

from pramana.exceptions import ValidationError

# Version of THIS generator's brief + body contract. Bump on a material change so
# a draft's provenance records which generator produced its video (drift detection).
VIDEO_PROMPT_VERSION = "pramana-video-2026-06"

# gen_engine for the video stage (the asset is produced via wegofwd-video, but the
# in-house orchestration that built the brief is Pramana's — mirrors quiz GEN_ENGINE).
GEN_ENGINE = "pramana"

# Compliance house style — neutral, text/logo-free, professional narration. These
# are deliberately conservative; an author can override per call.
_DEFAULT_STYLE = "clean corporate explainer, flat illustration, neutral palette"
_DEFAULT_NEGATIVE = "no on-screen text artifacts, no logos, no real faces, no flashing"
_DEFAULT_AUDIO = "clear neutral narrator, professional pace, light ambient office tone"
_DEFAULT_SHOT_DURATION_S = 6.0


def build_video_brief(
    *,
    clause_title: str,
    narration_lines: Sequence[str],
    style: str = _DEFAULT_STYLE,
    negative: str = _DEFAULT_NEGATIVE,
    audio_direction: str = _DEFAULT_AUDIO,
    shot_duration_s: float = _DEFAULT_SHOT_DURATION_S,
    ingredients: Sequence[Ingredient] = (),
) -> VideoBrief:
    """Build a :class:`wegofwd_video.VideoBrief` from a clause's narration lines.

    One shot per narration line, in order — the line is the spoken ``dialogue``
    (drives native audio) and seeds a neutral visual ``prompt``. The brief carries
    only what the model needs; it invents no content beyond the lines supplied.

    Raises:
        ValidationError: ``narration_lines`` is empty (nothing to narrate).
    """
    lines = [line.strip() for line in narration_lines if line and line.strip()]
    if not lines:
        raise ValidationError(
            "cannot build a video brief with no narration",
            context={"clause_title": clause_title},
        )
    shots = tuple(
        Shot(
            scene_index=i + 1,
            prompt=f"a compliance presenter explains: {line}",
            shot_type="medium",
            camera_move="static",
            lighting="even office light",
            dialogue=line,
            duration_s=shot_duration_s,
        )
        for i, line in enumerate(lines)
    )
    return VideoBrief(
        global_style=style,
        global_negative=negative,
        audio_direction=audio_direction,
        ingredients=tuple(ingredients),
        shots=shots,
    )


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
    return MaterializedVideo(asset_ref=asset_ref, min_watch_pct=raw_pct)
