# AI-Drafted, Human-Approved Training Content

**Document type:** Design decision / ADR (architecture + spec)
**Stage:** Proposal — awaiting decision
**Status:** Proposed
**Relates to:** `docs/02_resolved_decisions.md` (FR1–FR8, assignment state machine),
`docs/frameworks/framework_sox.md`, `docs/api/openapi.yaml`. Introduces a new
**content-authoring sub-domain** upstream of Courses/Assignments.
**Decision-maker:** Sivakumar Mambakkam / WeGoFwd

---

## 1. Context

`02_resolved_decisions.md` assumes employees are assigned **video-based training
courses with quizzes**, but is silent on **where that content comes from** — it
treats a Course's material as a given. WeGoFwd has an LLM content-generation
capability (the StudyBuddy/Mentible pipeline: scoped prompt → structured lesson
JSON with sections + quiz → rendered artifact, plus a free *animated-SVG* visual
path). The question: can that capability author Pramana's training content — a
**deck + a narrated training video + a quiz**?

**Technically: yes.** Decks and quizzes are exactly what the pipeline produces; a
narrated "video" can be **composed** (generated slides + animated SVG + text-to-
speech + render-to-MP4) without a paid AI-video model.

**But Pramana's product is *evidence of compliance*.** That makes raw LLM output a
**liability**: a hallucinated control description or wrong SOX claim in *official*
training is an audit problem, and "the AI wrote it" is not a defence. So the
content path cannot be "generate → assign." It must be **generate → human review
→ approve → version-pin → assign**, with the whole chain auditable.

This document specifies that safe model.

## 2. Decision

1. **LLM generation is a drafting aid, never the source of truth.** No AI-authored
   content is assignable until a qualified human has reviewed and **approved** it.
2. Add a **content-authoring sub-domain**: a draft is generated, moves through an
   **approval state machine**, and on approval becomes an **immutable, hashed,
   versioned** `CourseContentVersion`.
3. **Assignments pin to a specific approved content version** — the audit record
   shows *exactly which version* each user was trained on (critical for SOX §404).
4. **Separation of duties:** the approver must be a qualified SME / compliance
   owner, and **must not** be the person who triggered the generation (a SOX
   control). No self-approval.
5. **Every step is written to the existing tamper-evident audit log** (hash chain
   → DB + S3 Object Lock): draft created, each review action, approval (with
   approver identity + content hash), publication, retirement.
6. **No auto-publish, ever.** Generation can be batched/scheduled; *approval is
   always a deliberate human act.*

## 3. Content-approval state machine

A new lifecycle, parallel to the assignment state machine and equally pure/testable:

```
DRAFT ──submit──▶ IN_REVIEW ──approve──▶ APPROVED ──publish──▶ PUBLISHED ──retire──▶ RETIRED
  ▲                   │
  └──changes_requested┘
```

- **DRAFT** — AI-generated (or hand-edited); labelled "AI-DRAFTED — NOT APPROVED".
- **IN_REVIEW** — an SME/compliance owner is reviewing.
- **changes_requested** — back to DRAFT with reviewer notes (re-generate or edit).
- **APPROVED** — SME attests accuracy; content is frozen + hashed; approver,
  timestamp, and attestation captured. **Terminal-immutable**: any change forks a
  new draft, never edits an approved version.
- **PUBLISHED** — the approved version is the assignable content (effective dates).
- **RETIRED** — superseded by a newer version or withdrawn; existing completion
  records keep pointing at the version they were trained on (no rewrite of history).

Terminal/immutable states: APPROVED content body, RETIRED. Events
(`SUBMIT_FOR_REVIEW`, `REQUEST_CHANGES`, `APPROVE`, `PUBLISH`, `RETIRE`) are named
on each audit entry, mirroring `TransitionEvent` in the assignment domain.

## 4. What gets generated (the "deck + video")

One approved `CourseContentVersion` is the source; rendered artifacts are derived:

- **Content** — structured module JSON (sections, key points, scenarios) + a
  **quiz** (feeds the existing Attempt/quiz domain and pass-threshold scoring).
- **Deck** — the content rendered as slides (HTML/PDF), reusing the artifact
  renderer.
- **Narrated training video** — *composed*, not AI-generated: slides + free
  **animated-SVG** visuals + **text-to-speech** narration + a render-to-MP4 step
  (headless browser frames + ffmpeg/audio mux). No paid video model.
- **Source citations** — each generated section cites the framework clause it is
  based on (traceable to `docs/frameworks/framework_sox.md` §302/§404), so a
  reviewer can verify against the regulation, not just vibes.

## 5. Generation pipeline (reuse, don't couple)

- The LLM capability is reached through a **shared / vendored generation service**,
  not a runtime dependency on StudyBuddy's backend (those are separate products;
  StudyBuddy ADR-002 forbids cross-product imports). Same discipline here.
- Every draft carries **provenance**: model, provider, prompt-template version,
  generation timestamp. Stored on the draft and on the approved version so we can
  (a) audit how content was produced and (b) flag content made with an outdated
  model/prompt and offer re-draft (drift detection).
- Generation is **deterministic-enough + retried/validated** against the content
  schema before a human ever sees it (no malformed drafts in review).

## 6. Data-model additions (extends Phase B)

New entities, all tenant-scoped, all audited:

- **`ContentDraft`** — id, course_id, status (the §3 machine), body (JSON),
  provenance (model/provider/prompt_version/generated_at), created_by, review notes.
- **`CourseContentVersion`** — id, course_id, version_no, **content_hash**,
  approved_by, approved_at, attestation_text, effective_from/to, derived-artifact
  refs (deck, video, quiz). Immutable once APPROVED.
- **`Assignment.content_version_id`** — FK pinning the assignment to the exact
  approved version the user was trained on (extends FR-assignment).
- Audit-log entries for every draft/review/approval/publish/retire event, in the
  existing hash chain.

## 7. SOX / liability guardrails (why this is safe)

- **Mandatory human approval + attestation** before assignable — the human, not
  the model, owns accuracy. Captured in the audit trail as evidence.
- **Separation of duties** (generator ≠ approver) — a SOX-style internal control.
- **Immutability + hashing** — an approved version can't be silently altered; the
  hash + Object-Lock archive prove what was taught.
- **Version pinning per assignment** — answers "what exactly did employee X see?"
- **Re-review triggers** — a regulation change (framework doc updated) or a model/
  prompt change (provenance drift) flags affected versions for re-approval.
- **Clear labelling** — drafts are visibly "AI-DRAFTED — NOT APPROVED" everywhere
  until approved; approved content shows version + approver.

## 8. Options considered

1. **Buy/author all content manually (status quo assumption).** Safe but slow and
   costly; no leverage from the capability. _Not rejected — remains valid; this ADR
   makes AI-drafting an *option* alongside it._
2. **AI generate → auto-assign (no human gate).** _Rejected_ — unacceptable
   compliance/liability risk for SOX evidence.
3. **AI-draft → human-approve → version-pin (this decision).** Captures the speed
   of generation with the accountability SOX requires.

## 9. Phasing

1. **Approval domain + data model** — the state machine, `ContentDraft` /
   `CourseContentVersion`, audit wiring, assignment version-pin. (Highest value,
   lowest risk; safe even before any generation exists.)
2. **Generation integration** — shared service emits schema-valid drafts with
   provenance + source citations into DRAFT.
3. **Deck render** — approved version → slides (HTML/PDF).
4. **Narrated video** — slides + animated SVG + TTS → MP4 (verify free/low-cost TTS
   first).
5. **Re-review / drift triggers** — regulation- and model-change flags.

## 10. Open questions

- **Who can approve?** A dedicated `compliance_owner` role, or any manager-level
  SME? (Recommend a distinct role for the separation-of-duties control.)
- **One approver or N?** SOX-sensitive content may warrant dual approval.
- **TTS provider** — is there a genuinely free/compliant TTS for the narrated
  video, or is voiceover a paid line item? (Verify before committing Phase 4.)
- **Edit-after-generate** — do reviewers edit drafts in-app, or only
  request-changes + re-generate? (Editing is more flexible but widens the surface.)
- **Localization** — generated multi-language content multiplies the review burden;
  out of v1.

## 11. Recommendation

Accept the **AI-draft → human-approve → version-pin** model and **phase it**: build
the **approval domain + version pinning first** (it hardens the compliance story
even with zero AI), then layer generation, deck, and narrated video behind that
gate. Generation never bypasses human approval.
