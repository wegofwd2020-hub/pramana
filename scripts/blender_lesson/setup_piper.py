"""Set up the Piper narration stack for the Blender lesson renderer.

Does four things, in order, and stops at the first failure:

1. Checks the external tools the renderer needs (``blender``, ``ffmpeg``,
   ``ffprobe``) and reports any that are missing.
2. Creates a virtualenv and installs the ``piper-tts`` package into it.
3. Downloads a Piper voice: the ``.onnx`` model and its ``.onnx.json`` config,
   placed side by side.
4. Synthesises a short check phrase and confirms the WAV has a real duration.

Usage::

    python -m scripts.blender_lesson.setup_piper                  # full setup
    python -m scripts.blender_lesson.setup_piper --check-only     # tools only
    python -m scripts.blender_lesson.setup_piper --voice en_US-amy-medium

Exit codes: 0 ok · 2 missing tools or bad arguments · 3 setup or download failed ·
4 synthesis check failed.

Voices come from the Piper voices collection on Hugging Face. Downloads go through
the standard library, so they honour ``HTTPS_PROXY`` and the system CA bundle.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
DEFAULT_VOICE = "en_US-lessac-medium"
DEFAULT_VENV = Path.home() / "venvs" / "piper"
DEFAULT_VOICES_DIR = Path.home() / "voices"
CHECK_PHRASE = "Piper is installed."
REQUIRED_TOOLS = ("blender", "ffmpeg", "ffprobe")
DOWNLOAD_TIMEOUT_S = 120
CHUNK_BYTES = 1 << 16

# lang_REGION-name-quality, e.g. en_US-lessac-medium or en_GB-alba-medium.
_VOICE_RE = re.compile(
    r"^(?P<lang>[a-z]{2})_(?P<region>[A-Z]{2})-(?P<name>[a-z0-9_]+)-(?P<quality>x_low|low|medium|high)$"
)

EXIT_OK = 0
EXIT_MISSING_TOOLS = 2
EXIT_SETUP = 3
EXIT_SYNTHESIS = 4


class SetupError(RuntimeError):
    """A setup step failed. The message says which step and why."""


@dataclass(frozen=True)
class VoiceFiles:
    """The two files that make up one Piper voice."""

    name: str
    model_url: str
    config_url: str

    @property
    def model_filename(self) -> str:
        return f"{self.name}.onnx"

    @property
    def config_filename(self) -> str:
        return f"{self.name}.onnx.json"


def voice_files(name: str) -> VoiceFiles:
    """Map a voice name to its download URLs.

    Raises:
        SetupError: the name is not of the form ``lang_REGION-name-quality``.
    """
    match = _VOICE_RE.match(name)
    if match is None:
        raise SetupError(
            f"voice name {name!r} is not of the form lang_REGION-name-quality, "
            "for example en_US-lessac-medium"
        )
    lang, region = match["lang"], f"{match['lang']}_{match['region']}"
    path = f"{lang}/{region}/{match['name']}/{match['quality']}/{name}"
    base = f"{VOICE_BASE_URL}/{path}"
    return VoiceFiles(name=name, model_url=f"{base}.onnx", config_url=f"{base}.onnx.json")


def missing_tools(tools: tuple[str, ...] = REQUIRED_TOOLS) -> list[str]:
    """Names of the required tools that are not on PATH."""
    return [tool for tool in tools if shutil.which(tool) is None]


def download(url: str, dest: Path) -> Path:
    """Fetch ``url`` into ``dest``. Skips the fetch if ``dest`` already has content.

    The file is written to a ``.part`` name and renamed on success, so an
    interrupted download never leaves a half-written voice that looks complete.

    Raises:
        SetupError: the network request failed or the file could not be written.
    """
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    try:
        with (
            urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_S) as response,  # noqa: S310 - fixed https URL
            partial.open("wb") as handle,
        ):
            while chunk := response.read(CHUNK_BYTES):
                handle.write(chunk)
    except urllib.error.HTTPError as exc:
        partial.unlink(missing_ok=True)
        raise SetupError(f"download failed for {url}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise SetupError(f"download failed for {url}: {exc}") from exc
    partial.replace(dest)
    return dest


def install_voice(voice: VoiceFiles, voices_dir: Path) -> Path:
    """Download both files of a voice. Returns the path of the ``.onnx`` model."""
    model = download(voice.model_url, voices_dir / voice.model_filename)
    download(voice.config_url, voices_dir / voice.config_filename)
    return model


def create_venv(venv_dir: Path) -> Path:
    """Create the virtualenv if needed. Returns the path of its Python.

    Raises:
        SetupError: the venv could not be created.
    """
    python = venv_dir / "bin" / "python"
    if python.is_file():
        return python
    _run([sys.executable, "-m", "venv", str(venv_dir)], "create virtualenv")
    if not python.is_file():
        raise SetupError(f"virtualenv created but {python} is missing")
    return python


def install_piper(venv_python: Path) -> None:
    """Install ``piper-tts`` into the venv.

    Raises:
        SetupError: pip failed.
    """
    _run([str(venv_python), "-m", "pip", "install", "--upgrade", "piper-tts"], "install piper-tts")


def verify_synthesis(
    venv_python: Path, model: Path, out_wav: Path, *, ffprobe: str = "ffprobe"
) -> float:
    """Synthesise the check phrase and return the WAV's duration in seconds.

    Raises:
        SetupError: Piper failed, wrote no file, or the file has no duration.
    """
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(venv_python), "-m", "piper", "-m", str(model), "-f", str(out_wav)]
    try:
        proc = subprocess.run(  # noqa: S603 - argv built here; the phrase goes on stdin
            cmd,
            input=CHECK_PHRASE,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SetupError(f"{venv_python} does not exist") from exc
    if proc.returncode != 0 or not out_wav.is_file():
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        raise SetupError(f"piper synthesis failed: {' | '.join(tail) or 'no output'}")
    return _duration(out_wav, ffprobe)


def _duration(path: Path, ffprobe: str) -> float:
    proc = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nk=1:nw=1",
            str(path),
        ],
        "probe WAV duration",
    )
    try:
        seconds = float(proc.strip())
    except ValueError as exc:
        raise SetupError(f"ffprobe gave no duration for {path.name}") from exc
    if seconds <= 0:
        raise SetupError(f"{path.name} has non-positive duration {seconds}")
    return seconds


def _run(cmd: list[str], step: str) -> str:
    """Run one external command, returning stdout. Raises SetupError on any failure."""
    try:
        proc = subprocess.run(  # noqa: S603 - argv built here, never from user input
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SetupError(f"could not {step}: {cmd[0]} not found") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        raise SetupError(f"could not {step} (exit {proc.returncode}): {' | '.join(tail)}")
    return proc.stdout


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set up Piper for the Blender lesson renderer.")
    parser.add_argument("--venv", type=Path, default=DEFAULT_VENV, help="virtualenv for piper-tts")
    parser.add_argument("--voices-dir", type=Path, default=DEFAULT_VOICES_DIR)
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Piper voice name")
    parser.add_argument("--check-only", action="store_true", help="check external tools and stop")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the setup. Returns a process exit code."""
    args = _parse_args(argv)

    missing = missing_tools()
    for tool in REQUIRED_TOOLS:
        status = "missing" if tool in missing else "ok"
        print(f"{tool:<8} {status}")
    if missing:
        print(f"error: install {', '.join(missing)} before rendering", file=sys.stderr)
        return EXIT_MISSING_TOOLS
    if args.check_only:
        return EXIT_OK

    try:
        voice = voice_files(args.voice)
        venv_python = create_venv(args.venv)
        install_piper(venv_python)
        model = install_voice(voice, args.voices_dir)
    except SetupError as exc:
        print(f"error: setup: {exc}", file=sys.stderr)
        return EXIT_SETUP

    try:
        seconds = verify_synthesis(venv_python, model, args.voices_dir / "setup-check.wav")
    except SetupError as exc:
        print(f"error: check: {exc}", file=sys.stderr)
        return EXIT_SYNTHESIS

    print(f"piper ready: python={venv_python} model={model} check={seconds:.2f}s")
    print(f"use: --python {venv_python} --piper-model {model}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
