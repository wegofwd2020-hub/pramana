# Design: Blender lesson renderer

## Stages

1. **Validate** — `spec.load_lesson` parses YAML and validates with pydantic.
   Errors are `SpecError` with a path-qualified message.
2. **Narrate** — `narrate.synthesize` runs Piper per scene; `narrate.probe_duration`
   reads each WAV's length with ffprobe.
3. **Plan** — `plan.plan_jobs` turns each scene into a job: frames = ceil(duration × fps).
   Pure; no I/O.
4. **Render** — `render_bpy.py`, run by `blender -b --python`, builds one scene per job and
   renders PNG frames with EEVEE.
5. **Assemble** — `assemble` builds ffmpeg argv lists: one clip per scene, then a
   stream-copy concat.
6. **Record** — `lesson.srt`, `transcript.txt` and `provenance.json` (spec SHA-256, render
   script SHA-256, Blender version, Piper model name, video SHA-256).

## Decisions

- **Pure planning, impure execution.** Layout, planning and command construction are
  pure functions, so they are tested without Blender or ffmpeg. The only code that
  touches the outside world is `run_tool`, `synthesize` and `probe_duration`.
- **`bpy` is imported only in `main`.** The scene builder takes `bpy` as a parameter,
  so tests pass a `MagicMock` and assert on the calls it receives.
- **Deterministic output.** No randomness, a fixed camera, a fixed resolution, and
  frame numbering from 1 on both sides. The same approved spec renders the same frames,
  and the provenance hash pins them.
- **Errors map to exit codes.** 2 spec/usage, 3 narration, 4 render, 5 assembly. A
  partially written output is never reported as success.
- **Narration on stdin.** The text reaches Piper on stdin, never on the command line,
  so punctuation and length cannot break argument parsing.

## Known limits

- Eevee needs a display or GPU context. Headless servers may need Cycles or a virtual
  display; a laptop with a GPU is the supported path.
- Long labels are not auto-wrapped. The spec caps label length at 40 characters.
