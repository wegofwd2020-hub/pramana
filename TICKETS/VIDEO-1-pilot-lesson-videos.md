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

**Render numbers — not yet filled in.** The actual SOX-pilot render
(duration, resolution, wall-clock time, peak memory, cost) has not completed
as of this writing; a run was in progress on `mambakkam` when this section
was written. `<FILL IN FROM THE ACTUAL RUN: duration_s, resolution, render
wall-clock time, peak RSS, provider/cost>`. Do not treat the illustrative
`docs/local-diffusion-cpu-poc.md` / §2 numbers on this ticket as the pilot's
own measurement — those describe the local-preview validation path, not the
pilot's actual render.

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
