# VIDEO-1 — Generated lesson videos for six pilot user stories

**Labels:** feature, content, video
**Refs:** ADR-026 (wegofwd-video integration), US-PLATFORM-0002 (course player),
US-PLATFORM-0004 (ingestion review queue), `docs/02_resolved_decisions.md`
**Status:** SOX pilot's code side done (2026-09-09) — see "SOX pilot status"
below. The remaining frameworks (FCPA, GDPR, HIPAA, ISO 27001, PCI DSS — five
by this ticket's own "Scope" table, not the four the task brief's wording
assumed; see the note in "SOX pilot status") are still draft for discussion;
nothing about their content or population targeting is decided.

## SOX pilot status (2026-09-09)

The two-gate loop this ticket's discussion turned on is built and proven
end-to-end against a real Postgres:
`tests/integration/test_sox_video_pilot_e2e.py`. A generated-video draft now
must clear **both** gates before it can publish — the pre-existing accuracy
gate on the script (`approve_draft`) and the new fidelity attestation on the
rendered footage (`attest_draft_video`) — and `publish_draft` refuses an
approved-but-unattested video with `InvalidStateTransitionError`. Resolved
decision #274 (`docs/02_resolved_decisions.md` item 5) has been updated to
record this rather than silently rewritten — see that file for the
superseded wording kept alongside the new decision.

No new production code was required to close this loop; Tasks 1–6 already
built the seam, the state machine, and the DB constraints. Open item 6 from
"Open questions for the discussion" below (does this supersede resolved
decision #274, and who records that) is answered: yes, and this ticket +
`docs/02_resolved_decisions.md` are where it's recorded.

**ACCEPTANCE GAP — the transcript is persisted but never reaches the
learner.** `course_version.transcript` (added by `0012`, pinned to the
certificate at publish, proven end-to-end in
`tests/integration/test_publish_transcript.py`) is currently **write-only**.
A repo-wide grep finds writers and tests and no readers: `services/player.py`
(`get_player_manifest` / `PlayerManifest`) and `services/consumer/play.py`
(`start_view` / `PlaySessionManifest`) both build their manifests from
`CourseVersion` without ever reading `.transcript`, and no response schema in
`pramana/api/schemas.py` (`PlayerManifestOut` et al.) carries a `transcript`
field. Since the pilot's briefs render silent footage (`native_audio=False`
on the local-preview path — see "Audio is not covered" below), **a learner
who opens the pilot lesson today gets silent video and zero words.** This is
exactly the unreachable-control failure mode this ticket's own spec warns
against, not a nice-to-have. Wiring it is real scope, deliberately not done
here: it needs `PlayerManifest`/`PlaySessionManifest` to gain a `transcript`
field, `get_player_manifest`/`start_view` to read `version.transcript`, and
`pramana/api/schemas.py`'s player-manifest response model(s) to carry it
through to the client. Do not ship the pilot to a real learner before this is
closed.

**Render environment (the `render` extra) — pin, and why.** The spec's
argument for rendering locally at all is reproducibility ("deterministic by
seed; same seed and same torch build reproduce the frames"), which is what
makes local a *compliance* choice, not a cost one — so the environment that
produced a given render has to be pinned, not folklore. `pyproject.toml` now
declares a `render` extra: `wegofwd-video[local]`, `transformers==5.16.1`,
and `torch==2.14.0`. The `transformers` pin exists because
`transformers==5.17.0` SIGILLs mid-encode on the CPU this was verified on;
`wegofwd-video[local]`'s own extra declares `transformers>=4.56` with no
upper bound, so without this pin the next `pip install` can silently resolve
5.17 and reintroduce the crash. **CPU torch must still be installed from the
CPU wheel index, not PyPI's default** — a `pyproject.toml` extra cannot
express an `--index-url`, so this cannot be enforced by the extra alone:

```
pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
pip install -e '.[render]'
```

**Render numbers — measured 2026-09-09.** Full detail, including the nine
attempts it took and what each one taught, is in `docs/sox-video-pilot-run.md`.

| | |
|---|---|
| geometry | 576×320, 49 frames, 8 steps, guidance 1.0 |
| composition | 5 scenes × 2.0 s → 10.0 s segment, 148 675 bytes |
| seconds per step | **74.9 mean** (73.9–75.4 across five scenes, 2% spread) |
| wall clock | **98.0 min** — 5 scenes at ~19.5 min each |
| peak memory | **~24 GB** of 31 GB; the bf16 T5 encoder alone is a ~19 GB floor |
| provider / cost | `local-diffusion` on CPU — no vendor, no account, £0 |
| asset hash | `sha256:c0ddc5e5044c310432fad8329a12ec4231fc18b96c27012824e9e5dd4931f13e` |

Two things the numbers say that the plan did not:

- **The cost model was optimistic.** The plan extrapolated 0.059 s per latent
  token per step from the smaller row-1 geometry and predicted ~63 s/step and
  "about an hour". Actual is 0.069 — 17% higher — and 98 minutes. Scaling is
  *roughly* linear in latent tokens, not exactly; re-derive the constant at the
  geometry you intend to use rather than trusting an extrapolation.
- **Memory is a floor, not a function of geometry.** Reducing scenes or
  resolution does not help; the encoder is what does not fit. The render needs
  the machine substantially to itself.

## GATE 2 REFUSED, 2026-09-10 — by a human, not by a heuristic

The product owner watched the segment and declined to attest it:

> a) there is no AUDIO to follow; b) the VIDEO and the images do not seem to
> represent anything specifically and feel highly cartoonish, not the good kind;
> c) The little text on the screen are not in english and hence not readable to
> make any sense. In summary, nothing in this VIDEO made me feel I was learning
> anything.

**No attestation exists, so `publish_draft` refuses the draft. No SOX lesson
ships.** Full analysis in `docs/sox-video-pilot-run.md`.

Point **(b)** deserves emphasis because the original analysis under-weighted it:
the imagery does not depict *anything specific*. That fails gate 2's actual
question independently of the garbled text — a reviewer cannot attest that
footage matches a script when the footage depicts nothing in particular.

Point **(a)** is not a render failure. Narration was deliberately out of scope,
and the compensating control was the transcript reaching the learner as text —
which is the acceptance gap recorded below, built but not wired. The reviewer
hitting it confirms that gap from the seat that matters, and makes wiring the
transcript the higher-value next change: it fixes (a) regardless of what the
imagery ever looks like.

## THE FOOTAGE FAILED GATE 2 — the pilot's most useful result

**Every one of the five scenes carries hallucinated on-screen text** — garbled
pseudo-words, floating captions, a whiteboard of gibberish — despite the brief's
`global_negative` naming exactly that (`"text overlays, logos, watermarks,
distorted faces"`).

A reviewer running the fidelity gate would refuse to attest this segment, and
`publish_draft` would refuse the draft. **The control fired on its first real
input.** Gate 2 was argued for on the hypothesis that generated video
hallucinates on-screen text despite the negative prompt; that turned out to be
the *dominant* failure mode, in 5 of 5 scenes. Under a "script gate only, the
render is mechanical output" design this would have reached learners with nobody
having watched it.

**Consequence: no SOX lesson ships from this run, and this ticket stays open.**
The failure is a prompt/model problem, not a pipeline one — the next experiment
is a stronger negative prompt, more steps (8 is the distilled model's low end),
or a different checkpoint, one variable at a time with the seeds held fixed.

**What's left for the other frameworks.** FCPA, GDPR, HIPAA, ISO 27001, and
PCI DSS (see "Scope" below) inherit the same two-gate model unchanged — no
new plumbing, no new state-machine work. Each needs only its own content: a
reviewed-and-cited script for its framework, a rendered asset, and a human to
run the same `approve_draft` → generate/render → `attest_draft_video` →
`publish_draft` sequence this pilot proved. (The task brief that drove this
ticket update said "four" remaining frameworks; this ticket's own "Scope"
table names five non-SOX stories — FCPA/GDPR/HIPAA/ISO/PCI — so five is what's
recorded here rather than silently matching a count this document's own table
doesn't support.)

## Scope

Six stories were named as the limited set:

| story | framework | what it actually asks for |
|---|---|---|
| US-FCPA-0001 | FCPA | anti-bribery training, **risk-based population the officer selects** |
| US-GDPR-0001 | GDPR | data-protection awareness, **staff who process personal data** |
| US-HIPAA-0001 | HIPAA | Privacy Rule / PHI handling, **all workforce** (§164.530(b)) |
| US-ISO-0001 | ISO 27001 | infosec awareness, **all in-scope personnel** (A.6.3 / Cl. 7.3) |
| US-PCI-0001 | PCI DSS | CDE security awareness, **CDE-access personnel only** (Req 12.6) |
| US-SOX-0007 | SOX | **not a training story** — the human-approval gate (see below) |

## The shape of the set, which matters more than the count

**Five of the six are the same story.** FCPA/GDPR/HIPAA/ISO/PCI-0001 carry
near-identical acceptance criteria: assign to a population with a due date and an
audit entry; pass → certificate pinned to the exact content version; dashboard
coverage of complete/overdue/blocked. All five already ride US-PLATFORM-0001/0002
and 0003/0004. **They differ only in two things: who is targeted, and what the
content says.** Video is the second of those — so this is one piece of work
instantiated five times, not five pieces of work.

**The sixth is the control, not a lesson.** US-SOX-0007 says AI-drafted content
arrives as an **untrusted draft** that a human who is *not* the generator must
review and approve, with §-citations, a frozen hash, and quarantine on failed
verification. A generated video is precisely the untrusted-draft case that story
exists for. Reading it as "a sixth video to make" would miss the point: **it is
the gate the other five must pass through.** That is what makes this a coherent
set rather than an arbitrary six.

**Three of the five overlap by declaration.** ISO-0001 `also_satisfies`
[hipaa, gdpr]; GDPR-0001 and PCI-0001 both `also_satisfies` [iso27001]. The
security-awareness topics genuinely repeat across them — acceptable use,
phishing, incident reporting. Whether that means five videos or a shared core
plus framework-specific segments is an open question below, not a settled one.

## What already exists

- **The seam is built.** `domain/video_generation.build_video_brief` →
  `services/video_generation.attach_course_video` → `materialize_video`, with
  `body.video.asset_ref`, `min_watch_pct` on `CourseVersion`, and
  `play_session` recording consumer views.
- **The renderer works, on two paths.** `wegofwd-video` exposes `narrative-video`
  (Veo) and, as of 2026-09-09, `local-preview` (LTX-Video on CPU, verified —
  see `docs/local-diffusion-cpu-poc.md`). Both consume the same `VideoBrief`.
- **The approval machinery is built** — `domain/content_approval.py`, the
  review queue, separation of duties, version pinning.

So this ticket is mostly **content and policy**, not new plumbing.

## What is not settled, and blocks a plan

### 1. A resolved decision currently says the opposite

`docs/02_resolved_decisions.md:274` reads: *"Video content is **pre-recorded** and
uploaded by content authors. No live-session training in scope."* Generating video
contradicts that as written. Nobody has recorded that it was superseded. **Whatever
is decided here has to update that line**, or the two documents disagree in a repo
whose whole point is auditable evidence.

### 2. Local CPU rendering cannot produce these lessons

From the measured constant (19.7 s/step at 336 latent tokens ⇒ **~0.059 s per
latent token per step**), cost scales with `w/32 × h/32 × (frames−1)/8`:

| geometry | latent tokens | s/step | 8 steps |
|---|---|---|---|
| 448×256, 25 f (1 s) — *measured* | 336 | 19.7 | ~2.6 min |
| 576×320, 49 f (2 s) | 1 080 | ~63 | ~8 min |
| **864×480, 97 f (4 s)** | **4 860** | **~285** | **~38 min** |

A single 4-second 480p scene is ~38 minutes of stepping on mambakkam, before
load, T5 encode and VAE decode. A one-minute lesson is roughly 15 such scenes —
**~10 hours per lesson, ~50 hours for five** — and peak RSS was already 23.9 GB
of 32 GB at the *smallest* geometry, so 480p is a live out-of-memory risk, not
merely slow.

**Conclusion: local is for validating briefs, not for producing the pilot.**
Production rendering needs a rented GPU (~1 min/brief, $0.40–0.80/h spot) or
Veo — and Veo is still blocked on quota and the Vertex-vs-Developer-API decision
(`docs/provider-survey-2026-09.md`).

### 3. Nothing defines what a lesson *is*

There is no agreed length, scene count, or structure for a compliance lesson.
`tests/data/sox_lesson_brief.json` is two shots of two seconds — a smoke test,
not a lesson. Cost, effort and review burden all depend on this answer and
nothing else can be estimated until it exists.

### 4. Audio is not covered

The briefs carry `dialogue` and `audio_direction`, but neither provider produces
narration on the local path (`native_audio=False`), and Veo's audio is
Vertex-only. Awareness training without narration is a weak product. A TTS step
would have to pair with the render.

### 5. Approval of a *video* is not the same as approval of text

US-SOX-0007 requires every claim to cite its section so accuracy is verifiable.
A reviewer can check that in a script. In a rendered video the claims live in
narration and on-screen action, and the frozen hash covers the asset, not the
assertions. **How a reviewer approves a video against §-citations is genuinely
undefined**, and it is the part most likely to matter to an auditor.

## Open questions for the discussion

1. **Five videos, or a shared awareness core plus framework segments?** The
   `also_satisfies` overlaps argue for the second; the evidence trail (a
   certificate pinned to *one* content version per framework) argues for the first.
2. **What is a lesson?** Length, scene count, structure. Everything else costs
   out from this.
3. **Where does the pilot render** — rented GPU, Veo (unblock quota first), or
   local at a reduced geometry accepting the quality hit?
4. **Does US-SOX-0007's gate apply to the video asset, the script, or both** —
   and what does the reviewer actually attest to?
5. **Is narration in scope for the pilot**, or are these silent visuals over
   existing text?
6. **Does this supersede resolved decision #274**, and who records that?
7. **Is the pilot one framework end-to-end first** (SOX or HIPAA, say) rather
   than five in parallel? Cheaper to learn from, and the five are near-identical
   anyway.

## Deliberately not in this ticket

Population targeting (`User.cde_access`, risk tiering, workforce designation) —
each story flags it as a separate concern and the officer is assumed to select
the population. Dashboards, evidence binders, refresher cadence, and role
tailoring all have their own stories.

---

## BLOCKED — 2026-09-10: classifier-free guidance is broken upstream

**Status: the pilot cannot clear gate 2 until `wegofwd-video` issue #6 is fixed.**
This is not a tuning problem and no further parameter sweep will help.

### What happened

The rendered SOX segment (`docs/sox-video-pilot-run.md`) was refused at gate 2.
The reviewer's objections were: no audio; imagery that "does not represent
anything specifically"; and on-screen text that is not English.

The first is by design — `local-preview` is `native_audio=False` and the design
accepted silent footage, with `course_version.transcript` carrying the words
(wired to both player manifests in PR #43).

The other two traced to `guidance = 1.0`, which means classifier-free guidance is
**off**: nothing steers the sample toward the prompt, and — critically — the
negative prompt has no force, because a negative only acts through CFG. So
`_DEFAULT_NEGATIVE`'s `"no on-screen text artifacts"` never suppressed anything.

**What the text actually is.** Extracted frames show it is not background
texture but **burned-in subtitles** — three centred lines exactly where captions
sit. The prompt `f"a compliance presenter explains: {line}"` summons stock
corporate-training footage, which overwhelmingly ships with captions burned in;
the model reproduces the look and, unable to spell, emits letterform-shaped
marks. It appears in every successfully rendered frame, so the prompt is
actively summoning it. That makes this a **prompt problem as well as a CFG one**,
and the prompt half is fixable today.

Note this makes the spec's stated justification for gate 2 right for the wrong
reason. `docs/superpowers/specs/2026-09-09-sox-video-pilot-design.md` says the
gate catches "hallucinated on-screen text **despite** the negative prompt". The
negative prompt was never in effect.

### Why raising guidance does not fix it

Measured on rented GPUs (RTX 4090 and RTX 3090), one variable at a time, same
seed, same scene, via `scripts/bisect_render.py`:

| run | config | frame |
|---|---|---|
| control | distilled, 8 steps, g=1.0 | two people at a table ✓ |
| steps | distilled, **30 steps**, g=1.0 | **best of the set** ✓ |
| dtype / res | bfloat16 / 864x480 | ≈ control ✓ |
| guidance | distilled, **g=3.0** | blown out to a white card ✗ |
| repo | repo transformer, 8 steps, g=1.0 | washed-out smear ✗ |
| repo_g3 | repo transformer, 8 steps, g=3.0 | blank white ✗ |

**Guidance above 1.0 destroys the render on the distilled checkpoint** — the
control is a good image at the identical configuration with only guidance
changed, so the attribution is clean. Precision, resolution and step count were
each ruled out individually.

The repo (non-distilled) checkpoint failed at both guidance values, but every
repo run used **8 steps** — the distilled model's operating point, not its own
(~30-50). Those runs are misconfigured and establish nothing either way.

> **An earlier version of this section claimed both checkpoints fail at
> guidance > 1.0.** That came from comparing output file sizes: `repo.mp4` was
> 74,845 B against the control's 43,481 B and was recorded as "renders fine".
> The frame is a smear with no subject. Byte size tracks entropy, not
> correctness — a noisy smear compresses worse than a clean image. Corrected
> once the frames were extracted and viewed.

Filed upstream as **wegofwd-video#6**.

### Consequence for this pilot

The negative prompt is not merely ineffective at the current setting — it
**cannot be made effective**. Until #6 is fixed, generated footage will carry
text-shaped artifacts that no prompt or parameter change can remove, and a
fidelity attester is right to refuse it.

That the gate caught this on its first real input is the pilot's main positive
result: the control works, and it stopped unusable footage reaching a learner.

### Options when #6 is fixed

0. **Available now, no fix needed:** `steps=30` on the distilled model at
   guidance 1.0 produced the best image of the entire set, at no cost but render
   time. And rewriting the prompt away from "presenter explains" should reduce
   the caption artifacts independently of CFG.
1. Validate the repo checkpoint properly — 30 steps at g=1.0 and at g=3.0. Two
   runs, ~$0.50, and they decide whether wegofwd-video#6 is a real CFG defect or
   just "never apply CFG to a distilled checkpoint".
2. If quality is still short, the next lever is a larger model (13B, a different
   repo) — not more prompt engineering.
3. If generated video cannot clear gate 2 even with CFG, that is a legitimate
   finding: the increment becomes transcript-plus-stills, and this pilot has
   earned its cost by establishing it.

### Artifacts

- `~/Downloads/sox-variants/` — 3 clips + `results.json` (first ladder)
- `~/Downloads/sox-bisect/` — 7 clips + `bisect.json` (the 2x2)
- `scripts/render_variants.py` (PR #44, merged), `scripts/bisect_render.py`
  (branch `fix/bisect-render`)
