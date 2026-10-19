"""Assemble rendered frames and narration into the lesson video.

The command builders are pure: they return argument lists, so tests can assert
on exactly what ffmpeg will be asked to do. Running them is a separate step,
done by :func:`run_tool`, which turns any failure into :class:`AssemblyError`.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path


class AssemblyError(RuntimeError):
    """An external tool failed, or was not installed."""


def format_srt_time(seconds: float) -> str:
    """Format seconds as an SRT timestamp, ``HH:MM:SS,mmm``."""
    if seconds < 0:
        raise ValueError(f"negative time {seconds}")
    millis = round(seconds * 1000)
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_srt(spans: Sequence[tuple[float, float, str]]) -> str:
    """Render the learner-facing subtitle track from the timeline."""
    blocks = []
    for index, (start, end, text) in enumerate(spans, start=1):
        blocks.append(f"{index}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}\n")
    return "\n".join(blocks)


def build_transcript(spans: Sequence[tuple[float, float, str]]) -> str:
    """The plain-text transcript, which is what the learner reads in the player."""
    return "\n".join(text for _, _, text in spans) + "\n"


def build_scene_clip_cmd(
    *,
    frames_dir: Path,
    fps: int,
    audio: Path,
    out_clip: Path,
) -> list[str]:
    """Encode one scene's PNG frames and its narration into an MP4.

    ``-shortest`` ends the clip with the audio, so the picture never runs past
    the voice.
    """
    return [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-framerate",
        str(fps),
        # Blender numbers frames from 1; ffmpeg would start at 0 and drop frame 1.
        "-start_number",
        "1",
        "-i",
        str(frames_dir / "frame_%04d.png"),
        "-i",
        str(audio),
        "-shortest",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(out_clip),
    ]


def build_concat_list(clips: Sequence[Path]) -> str:
    """The concat-demuxer list file for the scene clips, in order."""
    return "".join(f"file '{clip.as_posix()}'\n" for clip in clips)


def build_concat_cmd(*, list_file: Path, out_video: Path) -> list[str]:
    """Join the scene clips without re-encoding them."""
    return [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(out_video),
    ]


def run_tool(cmd: Sequence[str]) -> str:
    """Run an external tool and return its stdout.

    Raises:
        AssemblyError: the tool is not installed, or exited non-zero.
    """
    try:
        proc = subprocess.run(  # noqa: S603 - argv is built here, never from user input
            list(cmd),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AssemblyError(f"{cmd[0]} is not installed or not on PATH") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-5:]
        raise AssemblyError(f"{cmd[0]} exited {proc.returncode}: {' | '.join(tail)}")
    return proc.stdout
