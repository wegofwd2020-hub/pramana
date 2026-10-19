# Proposal: Blender lesson renderer

## Why

The SOX video pilot failed its fidelity gate. Generative footage hallucinated
on-screen text and depicted nothing specific, and a reviewer refused to attest
it. A renderer whose output is fully determined by the approved script avoids
both failure modes: it draws only what the spec names, and it cannot invent text.

## What changes

- A `scripts/blender_lesson/` package that renders a lesson spec (YAML) into an
  MP4 with narration, a subtitle track, a plain-text transcript and a provenance
  record.
- Visuals are restricted to four kinds (flow, checklist, roster, text), built
  from boxes, arrows and text in a font.
- Narration is synthesised offline with Piper. Each scene's length comes from its
  measured audio.
- A spec with `status: draft` is refused unless the operator passes
  `--allow-draft`. This keeps gate 1 (script approval) in front of every render.

## Out of scope

- Approval and attestation workflow. The renderer produces the artifact and its
  provenance; the existing gates decide whether it ships.
- Photoreal or animated characters. The visual vocabulary is deliberately small.
- Wiring into the `wegofwd-video` provider. That is a follow-up once the output
  has been reviewed.
