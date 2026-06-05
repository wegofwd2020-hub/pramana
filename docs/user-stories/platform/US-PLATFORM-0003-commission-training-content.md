---
id: US-PLATFORM-0003
title: Commission training content from a regulation
framework: platform
domain: [compliance, regulatory]
industries: [cross-industry]
persona: content-author
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/user-stories/_templates/package-request.md
  - docs/frameworks/regulatory_frameworks_index.md
  - ADR-011
---

# US-PLATFORM-0003 — Commission training content from a regulation

## Story

> **As a** content author / compliance SME,
> **I want** to pick a regulation and the specific clauses to cover, set the content
> parameters, and send the request to Mentible,
> **so that** I can commission new training content without hand-writing it, with the
> request captured as an auditable artifact.

## Context

This is the **Create** phase made operable — the authoring side of the Package
Request contract (`_templates/package-request.md`). "Pick a law" means selecting a
**framework + clause anchors** from the definitions library (`docs/frameworks/*`);
the form collects the generation parameters (US-PLATFORM-0003 §AC2); on submit Pramana
builds a Package Request and pushes it to Mentible (ADR-011). Mentible then
manufactures and returns a Consumable Package, which lands in the review queue
(US-PLATFORM-0004).

## Acceptance criteria

1. **Given** the definitions library, **when** the author starts a new request,
   **then** they can select a framework and one or more **clause anchors** (e.g.
   `framework_fcpa.md#anti-bribery`) which populate `source_definitions`.
2. **Given** a request in progress, **when** the author sets parameters, **then** they
   can customize: **audience** (personas, risk tier, industries), **coverage**
   (learning objectives), **assessment** (pass threshold, min questions, style),
   **constraints** (length, reading level, citations-required, language), and
   **deliverables/visuals** (epub3/pdf/mp4, animated SVG).
3. **Given** sensible defaults, **when** the form opens, **then** values pre-fill from
   the framework/course defaults (e.g. pass threshold 80) and are editable.
4. **Given** a clause reference, **when** it does **not** resolve to a real anchor in
   the definitions library, **then** the request cannot be submitted (no definition,
   no request).
5. **Given** a completed request, **when** the author submits, **then** Pramana
   records the Package Request (with `requested_by` for audit) and pushes it to
   Mentible, and the author can see its status (requested → received → in review).

## Out of scope / notes

- Mentible's generation itself is external (ADR-011) — this story ends at "request
  sent" and resumes at the review queue.
- A machine-readable feed of framework/clause anchors is a dependency (so the picker
  has data) — flag for the definitions-library work.

## Traceability

- Package Request schema + mapping: [`../_templates/package-request.md`](../_templates/package-request.md).
- Definitions library (the law picker source): `docs/frameworks/regulatory_frameworks_index.md`.
- Boundary contract & reverse direction: **ADR-011** §4 "The Package Request".
- Worked example: [`../fcpa/briefs/PR-FCPA-anti-bribery.jsonc`](../fcpa/briefs/PR-FCPA-anti-bribery.jsonc).
