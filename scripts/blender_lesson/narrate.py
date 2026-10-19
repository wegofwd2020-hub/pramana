"""Narration: synthesise each scene's line with Piper and measure its length.

Piper is an offline text-to-speech engine. The scene's length comes from the
audio it produces, so the picture and the voice stay in step. The command is
built as data and the subprocess call is isolated, so the tests can check the
exact invocation without a voice model installed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.blender_lesson.assemble import AssemblyError, run_tool


class NarrationError(RuntimeError):
    """Piper is missing, the model is absent, or synthesis failed."""


def build_piper_cmd(piper_bin: str, model: Path, out_wav: Path) -> list[str]:
    """The Piper argv. The text is supplied on stdin, never on the command line."""
    return [piper_bin, "--model", str(model), "--output_file", str(out_wav)]


def synthesize(text: str, out_wav: Path, *, piper_bin: str, model: Path) -> None:
    """Speak one line to a WAV file.

    Raises:
        NarrationError: the model file is missing, Piper is not installed, or it
            exited non-zero.
    """
    if not model.is_file():
        raise NarrationError(f"Piper voice model not found: {model}")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_piper_cmd(piper_bin, model, out_wav)
    try:
        proc = subprocess.run(  # noqa: S603 - argv is built here; text goes on stdin
            cmd,
            input=text,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise NarrationError(f"{piper_bin} is not installed or not on PATH") from exc
    if proc.returncode != 0 or not out_wav.is_file():
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        raise NarrationError(f"piper failed for {out_wav.name}: {' | '.join(tail)}")


def probe_duration(path: Path, *, ffprobe: str = "ffprobe") -> float:
    """Length of a media file in seconds, from ffprobe.

    Raises:
        NarrationError: ffprobe failed or reported no usable duration.
    """
    try:
        out = run_tool(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ]
        )
    except AssemblyError as exc:
        raise NarrationError(str(exc)) from exc
    try:
        seconds = float(out.strip())
    except ValueError as exc:
        raise NarrationError(f"ffprobe reported no duration for {path.name}") from exc
    if seconds <= 0:
        raise NarrationError(f"{path.name} has non-positive duration {seconds}")
    return seconds
