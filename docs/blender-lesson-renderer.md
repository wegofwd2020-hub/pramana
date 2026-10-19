# Blender lesson renderer — runbook

Renders a lesson spec (`scripts/blender_lesson/examples/*.yaml`) to an MP4 with a
subtitle track, a transcript and a provenance record. Design:
`openspec/changes/add-blender-lesson-renderer/`.

## Requirements (vaganam, Ubuntu 24.04)

| Tool | Checked | Notes |
|---|---|---|
| Blender | `blender --version` → 4.0.2 | Renders with EEVEE (`BLENDER_EEVEE`) |
| ffmpeg / ffprobe | `which ffmpeg` → `/usr/bin/ffmpeg` | Encodes clips and the concat |
| Piper | `python3 -m piper --help` | Offline TTS, from the `piper-tts` pip package |
| Piper voice | `*.onnx` plus its `*.onnx.json` | Downloaded from the Piper voices collection |

Python 3.12 with the repo's dev extras is enough for the planner, the tests and the
CLI. Blender runs its own Python (`bpy`); the renderer does not need the repo venv
inside Blender.

### Install Piper and a voice (vaganam)

Piper's old standalone binary (`rhasspy/piper`) is archived. The maintained project
is `OHF-Voice/piper1-gpl`, installed as the `piper-tts` package and run as a module.

```bash
# 1. A virtualenv for Piper, kept apart from the repo venv
python3 -m venv ~/venvs/piper
~/venvs/piper/bin/pip install --upgrade pip
~/venvs/piper/bin/pip install piper-tts

# 2. A voice: the model and its config, side by side
mkdir -p ~/voices && cd ~/voices
B=https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium
curl -fLO "$B/en_US-lessac-medium.onnx"
curl -fLO "$B/en_US-lessac-medium.onnx.json"

# 3. Check that synthesis works (writes a WAV, speaks one line from stdin)
echo "Piper is installed." | ~/venvs/piper/bin/python -m piper \
  -m ~/voices/en_US-lessac-medium.onnx -f /tmp/piper-check.wav
ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 /tmp/piper-check.wav
```

Then point the renderer at that interpreter with `--python ~/venvs/piper/bin/python`.
The default is `python3`, which works only if `piper-tts` was installed there.

Other tools: Blender 4.0.2 and ffmpeg are already present. Nothing else is needed.

## 1. Plan without rendering

Needs no tools, so run this first to check the spec and the timing:

```bash
python -m scripts.blender_lesson.cli \
  scripts/blender_lesson/examples/us-sox-0001.yaml \
  --out-dir out/us-sox-0001 --dry-run
```

## 2. Render the draft for review

The US-SOX-0001 narration is a draft until a human approves it, so the renderer
needs the explicit override:

```bash
python -m scripts.blender_lesson.cli \
  scripts/blender_lesson/examples/us-sox-0001.yaml \
  --out-dir out/us-sox-0001 \
  --blender blender \
  --python ~/venvs/piper/bin/python \
  --piper-model ~/voices/en_US-lessac-medium.onnx \
  --allow-draft
```

Outputs in `out/us-sox-0001/`:

- `lesson.mp4`, the video
- `lesson.srt`, the subtitle track
- `transcript.txt`, the text the learner reads
- `provenance.json`, the hashes that pin this exact artifact
- `work/` and `narration/`, intermediates that can be deleted once reviewed

## 3. Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 2 | Spec invalid, or a draft was refused |
| 3 | Narration failed (Piper missing, voice model or config missing, or synthesis error) |
| 4 | Render failed (Blender exited non-zero, or wrote the wrong number of frames) |
| 5 | Assembly failed (ffmpeg missing or failed) |

## Things to verify on the first run

These are the parts I could not check in the sandbox, so they are the first things
to confirm on vaganam:

1. **EEVEE in background mode.** `blender -b` may need a GPU or display context.
   If the render fails with an OpenGL error, try a Blender build with GPU support
   or run the render under a virtual display, and tell me what happened.
2. **Piper synthesis.** The renderer runs `python -m piper -m MODEL -f OUT` and
   writes each scene's line to stdin. The `piper --help` output was checked against
   the package source, but no voice could be downloaded in the sandbox, so the first
   real synthesis is still unconfirmed. Step 3 of the install section is that check.
   If it fails, the narration step reports Piper's stderr in the message.
3. **Frame count.** The renderer checks that Blender wrote exactly
   `duration × fps` frames per scene. A mismatch stops the run with exit code 4.

## After the render

Gate 2 is a human watching `lesson.mp4` and deciding whether it depicts the approved
script. The renderer does not attest anything; the provenance record gives the
reviewer the exact spec, script and tool versions to check against.
