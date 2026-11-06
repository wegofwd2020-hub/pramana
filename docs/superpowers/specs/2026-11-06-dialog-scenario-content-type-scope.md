# Dialog scenario content type — scope

_2026-11-06. Status: scoping, not agreed. Open questions below need answers before a plan._

## Why this exists

John Thomas (demo, 2026-04-26) asked for scenario-based compliance questions:
a dialog stimulus followed by a true/false legal question. His example is a US
vendor, an overseas client, and subsidiary contract routing.

Pramana cannot express this today. A quiz question is `{prompt, options,
answer_index}` (`pramana/domain/content_generation.py`, `GeneratedQuestion`).
Question types are single-select and true/false only (`pramana/domain/publication.py`).
The `scenario-based` value in `pramana/domain/package_request.py` is a label. Nothing
downstream changes shape based on it.

## Proposed shape

A new content type, `dialog_scenario`, stored on the draft body next to `quiz` and
`video`:

```
{
  "scenario_id": "...",
  "compliance_domain": "...",          # see open question 3
  "dialog": [{"speaker": "...", "line": "..."}],
  "stem": "...",                       # the legal question the learner answers
  "options": [{"id": "a", "text": "..."}, ...],   # true/false = two options
  "correct": "a",
  "rationale": "...",
  "citations": [...]                   # framework + clause refs, as on quizzes
}
```

Every scenario must cite at least one definitions-library clause. The existing rule
applies: no definition, no request.

## Components

1. **Domain model and validation.** Reject a dialog with no turns, a blank speaker or
   line, fewer than two options, or a `correct` id that is not in `options`.
2. **Generation.** A dialog prompt builder alongside the quiz builder, driven through
   the same provider path. Retry on schema failure, as quizzes do.
3. **Persistence.** Stored in the JSONB `ContentDraft.body`. No migration is expected,
   to be confirmed in the plan.
4. **Approval and publication.** Human approval gates it, as for quizzes. Publication
   copies it onto the immutable `CourseVersion`, following the `materialize_quiz`
   pattern, so completions stay pinned to the version answered.
5. **Player and grading.** The server grades against the stored key. The learner sees
   the dialog, then the stem and options. Rationale is shown per the course's review
   settings, without revealing the key in a way that allows gaming a retake
   (US-FCPA-0002 AC2).
6. **Renderer.** Shows the dialog as a transcript, then the question. Location depends
   on open question 5.
7. **Tests.** Unit tests for validation and grading. Integration test for generate →
   approve → publish → play.

## Out of scope

- Multi-select and free-text answers. Deferred to v2 (`docs/02_resolved_decisions.md`).
- Video of the dialog. Not part of v1.
- Subsidiary contract-routing logic. John's example is scenario content, not a
  workflow engine. Confirm this reading (open question 1).
- Multi-tenancy. Single-tenant per the current spec.

## Open questions

1. Is the dialog question a standalone learning object, or a quiz item inside an
   assignment? Does subsidiary routing need to be modelled, or only described?
2. One true/false question per dialog, or a set of questions per dialog?
3. Keep framework and clause targeting only, or adopt John's role-band and
   compliance-domain vocabulary? Pramana currently targets by framework, not seniority.
4. Who authors the dialog? AI draft plus human approval, as today? Or author-written,
   as Venkit asked (teacher-authored content)?
5. Which repo owns the renderer? No web app appears in the Pramana tree.
6. Who signs off the legal answer key? The FCPA README states outputs are not legal
   advice and need counsel confirmation.

## Traceability

- Question types and v1 scope: `docs/02_resolved_decisions.md`
- Scenario stories: `docs/user-stories/fcpa/US-FCPA-0002-gifts-travel-hospitality-scenarios.md`,
  `docs/user-stories/fcpa/US-FCPA-0005-human-approved-fcpa-content.md`
- Approval workflow: `docs/03_ai_drafted_human_approved_content.md`
- Generation: ADR-013 (referenced in `pramana/domain/content_generation.py`)
- Source feedback: StudyBuddy demo feedback, John Thomas, 2026-04-26
