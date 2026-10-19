"""Narration: synthesise each scene's line with Piper and measure its length.

Piper is an offline text-to-speech engine. The current project is
``OHF-Voice/piper1-gpl`` (installed as the ``piper-tts`` package), which runs as
``python3 -m piper``. ``-m`` takes the path to the ``.onnx`` voice, ``-f`` the WAV
output, and the text arrives on stdin, one line per utterance. Scene length comes
from the measured audio, so the picture and the voice stay in step.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.blender_lesson.assemble import AssemblyError, run_tool


class NarrationError(RuntimeError):
    """Piper is missing, the voice files are absent, or synthesis failed."""


def build_piper_cmd(python_bin: str, model: Path, out_wav: Path) -> list[str]:
    """The argv for one line of narration. The text is not in it; it goes on stdin.

    Keeping the text off the command line means no line of narration can be read
    as an option, whatever it contains.
    """
    return [python_bin, "-m", "piper", "-m", str(model), "-f", str(out_wav)]


def synthesize(text: str, out_wav: Path, *, python_bin: str, model: Path) -> None:
    """Speak one line to a WAV file.

    ``model`` is the ``.onnx`` file. Its ``.onnx.json`` config must sit beside it.

    Raises:
        NarrationError: a voice file is missing, Python or Piper is not
            available, or synthesis exited non-zero.
    """
    if not model.is_file():
        raise NarrationError(f"Piper voice model not found: {model}")
    config = model.with_name(model.name + ".json")
    if not config.is_file():
        raise NarrationError(f"Piper voice config not found: {config}")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_piper_cmd(python_bin, model, out_wav)
    try:
        proc = subprocess.run(  # noqa: S603 - argv is built here; text goes on stdin
            cmd,
            input=text,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise NarrationError(f"{python_bin} is not installed or not on PATH") from exc
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
