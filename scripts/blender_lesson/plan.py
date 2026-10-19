"""Plan the render: one job per scene, plus the transcript timing.

Pure functions only. The planner decides how long each scene lasts, how many
frames that is, and where each job writes its frames. It does no I/O, so the
whole plan can be checked by a dry run before any tool is invoked.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.blender_lesson.layout import layout_visual
from scripts.blender_lesson.primitives import primitive_to_dict
from scripts.blender_lesson.spec import DialogueVisual, Lesson, Scene

#: Speaking-rate estimate used only when a scene's audio has not been measured.
WORDS_PER_SECOND = 2.5
MIN_SCENE_SECONDS = 2.0
RESOLUTION = (1280, 720)


@dataclass(frozen=True)
class SceneJob:
    scene_id: int
    narration: str
    duration_s: float
    frames: int
    fps: int
    frames_dir: Path
    primitives: tuple[dict[str, Any], ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "fps": self.fps,
            "frames": self.frames,
            "frames_dir": str(self.frames_dir),
            "resolution": list(RESOLUTION),
            "primitives": list(self.primitives),
        }


def estimate_duration(narration: str) -> float:
    """Seconds a line takes to speak, when no audio has been measured."""
    words = len(narration.split())
    return max(MIN_SCENE_SECONDS, words / WORDS_PER_SECOND)


def plan_jobs(
    lesson: Lesson,
    work_dir: Path,
    fps: int,
    durations: dict[int, float] | None = None,
) -> list[SceneJob]:
    """Build one job per scene.

    ``durations`` maps scene id to measured seconds, from the narration audio.
    Scenes missing from it fall back to :func:`estimate_duration`.
    """
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    measured = durations or {}
    seats = {speaker.id: (index, speaker.name) for index, speaker in enumerate(lesson.cast)}
    jobs: list[SceneJob] = []
    for scene in lesson.scenes:
        duration = measured.get(scene.id, estimate_duration(scene.narration))
        frames = max(1, math.ceil(duration * fps))
        if isinstance(scene.visual, DialogueVisual):
            side, name = seats[scene.visual.speaker]
            layout = layout_visual(
                scene.visual, narration=scene.narration, speaker_name=name, side=side
            )
        else:
            layout = layout_visual(scene.visual)
        primitives = tuple(primitive_to_dict(p) for p in layout)
        jobs.append(_job(scene, work_dir, fps, duration, frames, primitives))
    return jobs


def _job(
    scene: Scene,
    work_dir: Path,
    fps: int,
    duration: float,
    frames: int,
    primitives: tuple[dict[str, Any], ...],
) -> SceneJob:
    return SceneJob(
        scene_id=scene.id,
        narration=scene.narration,
        duration_s=duration,
        frames=frames,
        fps=fps,
        frames_dir=work_dir / f"scene-{scene.id:02d}" / "frames",
        primitives=primitives,
    )


def timeline(jobs: list[SceneJob]) -> list[tuple[float, float, str]]:
    """Return ``(start, end, text)`` per scene, with cumulative times in seconds."""
    spans: list[tuple[float, float, str]] = []
    cursor = 0.0
    for job in jobs:
        spans.append((cursor, cursor + job.duration_s, job.narration))
        cursor += job.duration_s
    return spans
