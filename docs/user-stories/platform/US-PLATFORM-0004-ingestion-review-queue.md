---
id: US-PLATFORM-0004
title: Ingestion review & approval queue
framework: platform
domain: [compliance, governance]
industries: [cross-industry]
persona: content-author
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/03_ai_drafted_human_approved_content.md
  - pramana/domain/content_approval.py
  - pramana/services/consumer_library.py
  - US-FCPA-0005
  - ADR-011
---

# US-PLATFORM-0004 — Ingestion review & approval queue

## Story

> **As a** content author / compliance reviewer (who did **not** generate the draft),
> **I want** a queue where I can preview a received package, then approve, request
> changes, or reject it,
> **so that** no AI-drafted content reaches a learner until a qualified human has
> verified it — "the AI wrote it" is not a defence.

## Context

This is the **Approve** gate made operable — the UI over the existing
`content_approval` state machine (`RECEIVED → IN_REVIEW → APPROVED → PUBLISHED /
REJECTED`). A pushed Consumable Package becomes an *untrusted* `RECEIVED` draft
(`consumer_library`); this surface lets a reviewer examine it against the source
clauses and provenance, and move it through the gate. It is framework-agnostic;
US-FCPA-0005 is the FCPA instance of the same policy.

## Acceptance criteria

1. **Given** received drafts, **when** the reviewer opens the queue, **then** they see
   each draft labelled "AI-DRAFTED — NOT APPROVED" with framework, title, version,
   and state, plus a separate **quarantine** list for packages that failed
   signature/`content_hash` verification (never publishable).
2. **Given** a draft, **when** the reviewer opens it (`RECEIVED → IN_REVIEW`), **then**
   they can preview modules + quiz + animated visuals + the compiled artifact, with
   **each claim's source citation** shown and the **provenance** (engine, model,
   prompt version, generated_at) and the **sig/hash verification badge**.
3. **Given** a draft in review, **when** the reviewer approves, **then** the system
   **enforces separation of duties** (approver ≠ the requester/generator), captures
   an **attestation** + freezes the content hash, and the draft becomes `APPROVED`.
4. **Given** an approved draft, **when** the reviewer publishes, **then** it
   materializes into an immutable `CourseVersion` and becomes assignable.
5. **Given** a draft in review, **when** the reviewer requests changes (with notes) or
   rejects, **then** it transitions accordingly (`→ RECEIVED/DRAFT` or `→ REJECTED`).
6. **Given** any action, **when** it occurs, **then** it is written to the audit log
   (actor, draft, transition, attestation/notes, timestamp).

## Out of scope / notes

- **Regenerate with updated parameters** is its own story (US-PLATFORM-0005), since it
  loops back into the Create phase.
- In-app **editing** of a draft (vs. request-changes + regenerate) is an open product
  question (`docs/03` §10) — not assumed here.

## Traceability

- State machine: `pramana/domain/content_approval.py`; policy: `docs/03_…` §2–§3.
- Ingestion that creates the draft: `pramana/services/consumer_library.py` (ADR-011).
- FCPA instance of the gate: [US-FCPA-0005](../fcpa/US-FCPA-0005-human-approved-fcpa-content.md).
