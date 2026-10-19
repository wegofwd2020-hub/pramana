"""Render a lesson spec to MP4, with subtitles and a provenance record.

Usage::

    # Plan only: validates the spec and prints the jobs. Needs no tools.
    python -m scripts.blender_lesson.cli spec.yaml --out-dir out/ --dry-run

    # Full render. Needs blender, ffmpeg and a Piper voice model.
    python -m scripts.blender_lesson.cli spec.yaml --out-dir out/ \\
        --piper-model ~/voices/en_US-lessac-medium.onnx --blender blender

Stages: validate → narrate → render frames in Blender → encode per scene →
concatenate → write transcript, subtitles and provenance.

Exit codes: 0 ok · 2 spec or usage error · 3 narration · 4 render · 5 assembly.
A ``draft`` lesson is refused unless ``--allow-draft`` is given, so an
unapproved script cannot be rendered by accident.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scripts.blender_lesson.assemble import (
    AssemblyError,
    build_concat_cmd,
    build_concat_list,
    build_scene_clip_cmd,
    build_srt,
    build_transcript,
    run_tool,
)
from scripts.blender_lesson.narrate import NarrationError, probe_duration, synthesize
from scripts.blender_lesson.plan import SceneJob, plan_jobs, timeline
from scripts.blender_lesson.spec import DialogueVisual, Lesson, SpecError, load_lesson

EXIT_OK = 0
EXIT_SPEC = 2
EXIT_NARRATION = 3
EXIT_RENDER = 4
EXIT_ASSEMBLY = 5

RENDER_SCRIPT = Path(__file__).resolve().parent / "render_bpy.py"


class RenderStageError(RuntimeError):
    """Blender ran but did not produce the frames the job asked for."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a lesson spec to MP4.")
    parser.add_argument("spec", type=Path, help="lesson spec (YAML)")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--blender", default="blender", help="blender executable")
    parser.add_argument("--python", default="python3", help="python that has piper-tts installed")
    parser.add_argument("--piper-model", type=Path, help="narrator's Piper .onnx voice model")
    parser.add_argument(
        "--voices-dir",
        type=Path,
        help="folder with the cast voices, <voice>.onnx each (default: beside --piper-model)",
    )
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--dry-run", action="store_true", help="plan only; run no tools")
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="render a script whose status is still 'draft' (not yet approved)",
    )
    return parser.parse_args(argv)


def _plan_summary(lesson: Lesson, jobs: list[SceneJob]) -> dict[str, Any]:
    return {
        "lesson": lesson.id,
        "clause": lesson.clause,
        "status": lesson.status,
        "scenes": [asdict(job) | {"frames_dir": str(job.frames_dir)} for job in jobs],
        "timeline": [
            {"start_s": round(s, 3), "end_s": round(e, 3), "text": t} for s, e, t in timeline(jobs)
        ],
    }


def _voices_dir(args: argparse.Namespace) -> Path | None:
    voices: Path | None = args.voices_dir
    if voices is not None:
        return voices
    narrator: Path | None = args.piper_model
    return narrator.parent if narrator is not None else None


def _voice_model(scene_visual: object, lesson: Lesson, args: argparse.Namespace) -> Path:
    """The voice for one scene: the speaker's cast voice, or the narrator's."""
    if isinstance(scene_visual, DialogueVisual):
        voices = {speaker.id: speaker.voice for speaker in lesson.cast}
        folder = _voices_dir(args)
        if folder is None:
            raise NarrationError("a dialogue lesson needs --voices-dir or --piper-model")
        return folder / f"{voices[scene_visual.speaker]}.onnx"
    narrator: Path | None = args.piper_model
    if narrator is None:
        raise NarrationError("--piper-model is required for narrator scenes")
    return narrator


def _narrate(lesson: Lesson, out_dir: Path, args: argparse.Namespace) -> dict[int, float]:
    durations: dict[int, float] = {}
    for scene in lesson.scenes:
        wav = out_dir / "narration" / f"scene-{scene.id:02d}.wav"
        model = _voice_model(scene.visual, lesson, args)
        synthesize(scene.narration, wav, python_bin=args.python, model=model)
        durations[scene.id] = probe_duration(wav, ffprobe=args.ffprobe)
    return durations


def _render_frames(job: SceneJob, job_file: Path, args: argparse.Namespace) -> None:
    job_file.parent.mkdir(parents=True, exist_ok=True)
    # Frames left by an earlier run would be counted with this run's frames, so
    # clear them first. Narration length can change between runs, and a stale
    # tail would make the frame count wrong.
    job.frames_dir.mkdir(parents=True, exist_ok=True)
    for stale in job.frames_dir.glob("frame_*.png"):
        stale.unlink()
    job_file.write_text(json.dumps(job.to_json(), indent=2), encoding="utf-8")
    run_tool(
        [
            args.blender,
            "-b",
            "--python",
            str(RENDER_SCRIPT),
            "--",
            str(job_file),
        ]
    )
    produced = len(list(job.frames_dir.glob("frame_*.png")))
    if produced != job.frames:
        raise RenderStageError(
            f"scene {job.scene_id}: expected {job.frames} frames, Blender wrote {produced}"
        )


def _blender_version(args: argparse.Namespace) -> str:
    first = run_tool([args.blender, "--version"]).strip().splitlines()
    return first[0] if first else "unknown"


def _assemble(
    jobs: list[SceneJob],
    narration_dir: Path,
    out_dir: Path,
    args: argparse.Namespace,
) -> Path:
    clips: list[Path] = []
    for job in jobs:
        audio = narration_dir / f"scene-{job.scene_id:02d}.wav"
        clip = out_dir / "clips" / f"scene-{job.scene_id:02d}.mp4"
        clip.parent.mkdir(parents=True, exist_ok=True)
        run_tool(
            build_scene_clip_cmd(frames_dir=job.frames_dir, fps=job.fps, audio=audio, out_clip=clip)
        )
        clips.append(clip)
    list_file = out_dir / "clips" / "concat.txt"
    list_file.write_text(build_concat_list(clips, list_file.parent), encoding="utf-8")
    video = out_dir / "lesson.mp4"
    run_tool(build_concat_cmd(list_file=list_file, out_video=video))
    return video


def _write_outputs(
    lesson: Lesson,
    spec_sha: str,
    jobs: list[SceneJob],
    video: Path,
    out_dir: Path,
    args: argparse.Namespace,
) -> None:
    spans = timeline(jobs)
    (out_dir / "lesson.srt").write_text(build_srt(spans), encoding="utf-8")
    (out_dir / "transcript.txt").write_text(build_transcript(spans), encoding="utf-8")
    provenance = {
        "lesson": lesson.id,
        "clause": lesson.clause,
        "status": lesson.status,
        "spec_sha256": spec_sha,
        "render_script_sha256": _sha256(RENDER_SCRIPT),
        "blender": _blender_version(args),
        "piper_model": args.piper_model.name if args.piper_model else None,
        "cast_voices": {speaker.id: speaker.voice for speaker in lesson.cast},
        "fps": args.fps,
        "resolution": [1280, 720],
        "scene_durations_s": {str(j.scene_id): round(j.duration_s, 3) for j in jobs},
        "video_sha256": _sha256(video),
    }
    (out_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        lesson, spec_sha = load_lesson(args.spec)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_SPEC

    if lesson.status != "approved" and not args.allow_draft and not args.dry_run:
        print(
            f"error: {lesson.id} is status '{lesson.status}'. Approve the script, or "
            "pass --allow-draft to render it anyway.",
            file=sys.stderr,
        )
        return EXIT_SPEC

    out_dir: Path = args.out_dir
    work = out_dir / "work"

    if args.dry_run:
        jobs = plan_jobs(lesson, work, args.fps)
        print(json.dumps(_plan_summary(lesson, jobs), indent=2))
        return EXIT_OK

    try:
        durations = _narrate(lesson, out_dir, args)
    except NarrationError as exc:
        print(f"error: narration: {exc}", file=sys.stderr)
        return EXIT_NARRATION

    jobs = plan_jobs(lesson, work, args.fps, durations)
    try:
        for job in jobs:
            _render_frames(job, work / f"scene-{job.scene_id:02d}" / "job.json", args)
    except (AssemblyError, RenderStageError) as exc:
        print(f"error: render: {exc}", file=sys.stderr)
        return EXIT_RENDER

    try:
        video = _assemble(jobs, out_dir / "narration", out_dir, args)
        _write_outputs(lesson, spec_sha, jobs, video, out_dir, args)
    except AssemblyError as exc:
        print(f"error: assembly: {exc}", file=sys.stderr)
        return EXIT_ASSEMBLY

    print(f"wrote {video}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
