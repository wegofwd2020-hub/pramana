# Blender lesson renderer: handoff (2026-10-19)

Resume here. Branch: `feat/blender-lesson-renderer`. No PR opened yet.

## Where things stand

Working on vaganam (Ubuntu 24.04, Blender 4.0.2, ffmpeg, Piper).

- Pipeline works end to end: spec, narration, Blender frames, ffmpeg, MP4. A video plays.
- Dialogue scenes work: speech bubbles, a cast with two voices, and text and audio look right.
- Pictures (portraits and office background) are coded and the plan contains them (19 picture entries for US-SOX-0003). In the last render, scene 5 showed no portrait and no background. Cause not yet known.
- Colour: switched to the Standard view transform (`a992399`) to stop the washed-out look. Not yet confirmed in a render.

## Open issue: pictures not visible in the render

Next step, on vaganam, from the repo root:

```bash
git pull && git log --oneline -1          # expect a992399
grep -c '"type": "picture"' out/us-sox-0003/work/scene-05/job.json   # expect 2
~/venvs/lesson/bin/python -m scripts.blender_lesson.cli \
  scripts/blender_lesson/examples/us-sox-0003.yaml \
  --out-dir out/us-sox-0003 --blender blender \
  --python /home/sivam/venvs/piper/bin/python \
  --piper-model /home/sivam/voices/en_US-lessac-medium.onnx \
  --voices-dir /home/sivam/voices --allow-draft 2>&1 | tee render.log
grep -i "image\|picture\|error\|warn" render.log | head -30
```

- Job file shows 0 pictures: the render used an old job or spec. Re-pull and remove `out/us-sox-0003` before rendering.
- Job file shows 2 pictures but the frame has none: Blender loads but does not draw them. Look at `render.log`. Likely places: the emissive texture setup in `render_bpy._picture`, or camera clipping for the z = -0.05 layer.

Pictures were visible in an earlier frame (before `a992399`), so the picture code works at least partly.

## Files and where they live

- `scripts/blender_lesson/cli.py`: entry point, exit codes, asset checks, provenance.
- `scripts/blender_lesson/spec.py`: lesson spec, cast, background, bubble length limit (160).
- `scripts/blender_lesson/layout.py`: bubble and portrait layout on a 16×9 canvas.
- `scripts/blender_lesson/primitives.py`: box, arrow, headline, picture (no third-party imports; Blender loads this).
- `scripts/blender_lesson/render_bpy.py`: runs inside Blender. Standard view transform, emissive pictures, light bubble fill.
- `scripts/blender_lesson/narrate.py`, `setup_piper.py`: Piper.
- `scripts/blender_lesson/make_placeholder_assets.py`: generates the placeholder portraits and office (Pillow needed only for this).
- `scripts/blender_lesson/examples/us-sox-0003.yaml`: DRAFT two-speaker script (manager and intern), 11 scenes.
- `scripts/blender_lesson/examples/assets/us-sox-0003/`: placeholder PNGs (manager, intern, office).
- `tests/test_blender_lesson.py`: 103 tests. `tests/test_setup_piper.py`: setup tests. All pass.
- `docs/blender-lesson-renderer.md`: runbook.

## Environment on vaganam

- Lesson venv: `~/venvs/lesson` (pydantic, pyyaml). Run the CLI with this interpreter, not system `python3`.
- Piper venv: `~/venvs/piper` (piper-tts).
- Voices: `~/voices/` holds `en_US-lessac-medium` (narrator), `en_US-ryan-high` (manager) and `en_US-joe-medium` (intern), each as `.onnx` and `.onnx.json`.
- A stray folder `~/voice` (singular) holds a copy of joe-medium from a typo. Safe to delete.

## Commits on the branch (this session)

- `2d023b6` keep pydantic out of the Blender import path (render_bpy failed inside Blender).
- `7edb97f` concat list paths relative to the list file.
- `228a2d1` clear stale frames before each scene renders.
- `8194488` dialogue scenes with cast voices and speech bubbles.
- `d255f2c` portraits, office background, picture primitive.
- `c251ce9` resolve asset paths to absolute.
- `a992399` Standard view transform.

## Pending decisions and tasks

1. Fix the picture render (see above), then confirm the colour fix in a fresh frame.
2. Check that the manager and intern voices sound right. Swap them in the YAML if not.
3. Real artwork: the placeholders are simple drawings. Replace the PNGs in `examples/assets/us-sox-0003/` with real images, keeping the names. The test `test_the_draft_assets_match_the_generator` will then fail by design; loosen it to "files exist and are valid images" if real art is used.
4. SME and legal review of the US-SOX-0003 script (gate 1). Confirm the §806 wording against `docs/frameworks/framework_sox.md` before approval. Remove `--allow-draft` only after approval.
5. Quiz (not built). Rule: 5 questions per lesson, pass at 4 of 5, otherwise retake. Open: whether a retake means re-watching the video too.
6. Storyboard v2 for US-SOX-0001 (hook, objectives, worked example, recap, quiz), drafted but not built. Waiting on the user's call.
7. Open the PR for `feat/blender-lesson-renderer`: https://github.com/wegofwd2020-hub/pramana/pull/new/feat/blender-lesson-renderer
8. Gate 2: a human reviews each rendered MP4 against its approved script before publication.

## Resume prompt

"Continue the Blender lesson renderer. Read docs/blender-lesson-handoff-2026-10-19.md on branch feat/blender-lesson-renderer. Start with the open picture-render issue."
