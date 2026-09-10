# SOX generated-video pilot — design

_2026-09-09. Status: agreed, ready for an implementation plan._

## Why this exists

Six user stories were named as the limited set for generated lesson video
(`TICKETS/VIDEO-1-pilot-lesson-videos.md`). Reading them showed the set is not
six comparable items: **US-FCPA-0001, US-GDPR-0001, US-HIPAA-0001, US-ISO-0001
and US-PCI-0001 are one story wearing five frameworks** — near-identical
acceptance criteria, differing only in who is targeted and what the content
says — while **US-SOX-0007 is not a training story at all.** It is the
human-approval gate: AI-drafted content arrives as an *untrusted draft* that a
reviewer who is not the generator must approve, with §-citations, a frozen hash,
and quarantine on failed verification.

A generated video is exactly that untrusted-draft case. So the sixth story is not
a sixth video; it is the control the other five must pass through.

Because the five are near-identical, doing all five in parallel would pay five
times to learn the same lessons. **This pilot takes one framework end-to-end.**

## Decisions

| decision | choice |
|---|---|
| Framework | **SOX** |
| Scope of the render | one segment, 5 scenes × ~2 s ≈ **10 s**, one brief per scene |
| Geometry | 576×320 ("320p"), 8 steps, guidance 1.0, **fixed seed** |
| Render path | `wegofwd-video` `local-preview` (LTX-Video, CPU) |
| Narration | **none** — silent visuals; the approved script is shown as text |
| Approval model | **two gates**: script accuracy, then video fidelity |
| Attestation storage | four new columns on `content_draft` |

SOX because the loop is already complete in the story set — US-SOX-0001 (ICFR
awareness assignment) → US-SOX-0007 (the gate) → US-SOX-0006 (auditor §404
evidence binder) — it is the product's declared initial scope
(`docs/02_resolved_decisions.md`), the gate story chosen is already SOX,
`tests/data/sox_lesson_brief.json` is the brief both prior renders used, and a
wrong §404 or §302 claim is the harshest accuracy case available, which is what
the approval model most needs to be tested against.

### Why local rendering is a compliance choice, not only a cost one

US-SOX-0007 requires an approved version to be reproducible. The
`local-diffusion` provider is `deterministic=True` — same seed and same torch
build reproduce the frames. The Veo **Gemini Developer API path rejects `seed`
outright** (`docs/provider-survey-2026-09.md`, and the first-run findings), so
reproducible regeneration of an approved SOX version is not achievable on it at
all. Local is currently the only one of the two render paths that satisfies the
requirement.

The cost is quality and time, both accepted: measured at 0.059 s per latent token
per step, a 2-second 576×320 scene (49 frames, 1 080 latent tokens) is ~63 s/step,
so 8 steps is ~8.5 min of stepping and roughly 11–12 min per scene once model
load, T5 encode and VAE decode are counted. **Five scenes is about an hour** — not
an overnight run — at zero cost, with peak RSS near the measured 23.9 GB rather
than the out-of-memory risk 480p carries on a 32 GB box.

## The two gates

The claims that need §-citation live in the **narration script**, which is text.
The visuals are B-roll and assert no statute. Accuracy review and footage review
are therefore different questions, and splitting them is what makes the problem
tractable.

**Gate 1 — accuracy.** The reviewer checks every claim against its § citation.
This is the existing US-PLATFORM-0004 gate, unchanged: `ContentDraft` already
carries `approved_by_user_id`, `approved_at`, `content_hash` and
`attestation_text`, with a database CHECK enforcing that the approver is not the
generator. **No new machinery.**

**Gate 2 — fidelity.** The reviewer watches the render and attests: *this footage
faithfully depicts the approved script and depicts nothing misleading.* This
catches what generation specifically gets wrong — hallucinated on-screen text
despite the negative prompt, the wrong document type, a person performing the
wrong action. It cannot reuse gate 1's columns: those hold one approver and one
hash, so writing the video sign-off there would destroy the evidence that the
script was approved separately.

Neither reviewer is asked to do the other's job.

## Pipeline

```
SOX ICFR script            →  ContentDraft (DRAFT)
                                  │
one single-shot brief PER narration line          (see below)
                                  │
wegofwd-video local-preview  →  one .mp4 per brief (576×320, 8 steps, fixed seed)
ffmpeg concat                →  the segment
                                  │
attach_course_video        →  body.video.asset_ref + min_watch_pct   [DRAFT only]
                                  │
submit_for_review                                  DRAFT → IN_REVIEW
                                  │
          GATE 1 (existing): accuracy; approver ≠ generator
                             freezes content_hash over the body      → APPROVED
                                  │
          GATE 2 (new): fidelity; attester ≠ generator
                             records video_asset_hash over the bytes
                                  │
publish                    →  immutable CourseVersion
                                  │  ← REFUSES a draft carrying an unattested video
assign (US-SOX-0001) → watch to min_watch_pct → quiz → pass
                                  │
certificate pinned to the exact CourseVersion
                                  │
US-SOX-0006 §404 binder: the completion plus both attestations
```

**Why the render happens before review, not after approval.**
`attach_course_video` refuses any draft not in `DRAFT` status, so the video is
attached before the draft is ever submitted. That is the better order anyway: the
reviewer can watch the footage at review time, and the two hashes then cover two
different things — `content_hash` freezes the body (script plus asset reference),
`video_asset_hash` freezes the rendered bytes. An earlier draft of this spec had
the render after approval, which would have mutated the body after `content_hash`
froze it and broken the freeze.

Scene count is a property of the script: `build_video_brief` emits **one shot per
narration line**, so a 5-scene segment means a 5-line approved script. Scene count
is not chosen separately and cannot drift from what was approved.

### Two integration facts that shape this, found while designing

**The local provider flattens a multi-shot brief into a single clip.** It joins
the shots into one prompt and *sums* their durations for one render
(`local_diffusion.py`, the `brief.shots` loop and the duration helper). A 5-shot
brief therefore yields one clip, not five scenes. The pilot must issue **one
single-shot brief per narration line** and concatenate the results with ffmpeg —
which is also what the runbook already advises for anything longer than one clip.

**`build_video_brief`'s default `shot_duration_s` is 6.0 s.** Five narration
lines at the default is a 30-second brief, and the `local-preview` role declares
`max_duration_s = 10` — so the default composition would be **refused by the
capability check** before rendering. The pilot passes an explicit
`shot_duration_s ≈ 2.0`. This mismatch between Pramana's default and the local
provider's ceiling is real and pre-existing; the implementation should decide
whether to change the default, or to document that the default targets the Veo
path only.

## The load-bearing invariant

**`APPROVED → PUBLISHED` must refuse a draft that carries a video asset with no
fidelity attestation.**

This is the whole control. Without it, gate 2 is advisory — and an advisory
control is precisely the failure mode PR-1 and PR-2 each uncovered: a migration
that skipped silently when `APP_DB_ROLE` was unset, and a segment-continuity
check that nothing ever called. Both were correct code that no path invoked. This
invariant gets an explicit test that fails if the check is removed.

## Schema — migration `0012` (current head: `0011_audit_log_no_truncate`)

Four nullable columns on `content_draft`:

| column | type |
|---|---|
| `video_asset_hash` | `text` |
| `video_attested_by_user_id` | `uuid`, FK → `user` |
| `video_attested_at` | `timestamptz` |
| `video_attestation_text` | `text` |

Three CHECK constraints. Names are **bare and short** — the metadata naming
convention prefixes `ck_content_draft_`, and pre-prefixing produces the
double-prefix bug already hit on the consumer tables:

```python
CheckConstraint(
    "(video_attested_by_user_id IS NULL) = (video_attested_at IS NULL)",
    name="video_attestation_pair",
),
# Mirrors the script gate exactly, including the null-generator escape:
# generated_by_user_id is nullable, and without that clause a draft with no
# recorded generator could never be attested.
CheckConstraint(
    "video_attested_by_user_id IS NULL "
    "OR generated_by_user_id IS NULL "
    "OR video_attested_by_user_id <> generated_by_user_id",
    name="video_separation_of_duties",
),
CheckConstraint(
    "video_attested_at IS NULL OR video_asset_hash IS NOT NULL",
    name="video_attestation_needs_asset",
),
```

The third has no counterpart in the script gate and is deliberate: an attestation
that names no artifact attests to nothing.

## Testing

| test | what it pins | kind |
|---|---|---|
| publish refuses an attached-but-unattested video | the load-bearing invariant | unit |
| a user cannot attest a draft they generated | separation of duties at gate 2 | unit + DB CHECK |
| an attestation without an asset hash is rejected | the third CHECK | DB |
| script approval evidence survives video attestation | that gate 2 does not overwrite gate 1 | unit |
| `build_video_brief` yields one shot per narration line | scene count cannot drift from the approved script | unit |
| full loop on real Postgres: assign → watch → quiz → certificate → binder | end-to-end | integration |

The render itself is a **scripted manual step, not a CI test.** CI installs
`.[dev]` only — no torch, no weights — which is also why `wegofwd-video`'s own
CI green does not prove its diffusers path. The render is run and its output
recorded by hand, the same way `scripts/first_local_run.py` was.

## What this supersedes

`docs/02_resolved_decisions.md:274` reads *"Video content is **pre-recorded** and
uploaded by content authors. No live-session training in scope."* Generating
video contradicts that as written, and nothing currently records it as
superseded. **The implementation must update that line**, or two documents
disagree in a repository whose entire purpose is auditable evidence.

## Out of scope

- **The other four frameworks.** They are near-identical to SOX; they follow once
  this loop is proven, and inherit the same two-gate model.
- **Narration.** Neither render path gives usable audio — `local-preview` is
  `native_audio=False`, and Veo's audio is Vertex-only — so narration needs a
  separate TTS step. That would add a second generated artifact needing its own
  fidelity attestation, widening the very question this pilot exists to answer.
  It is the expected next increment.
- **Population targeting.** Each of the five stories flags this as a separate
  concern and assumes the officer selects the population.
- **A generic attestation table.** Four columns are YAGNI-correct for one
  generated artifact. When narration lands and a second artifact needs its own
  sign-off, the right move is a `content_attestation` table keyed by artifact
  kind — noted here so that migration is a decision rather than a surprise.
- **Dashboards, refresher cadence, role tailoring, evidence-binder changes.**
  All have their own stories; the binder is consumed, not modified.
