---
id: US-FCPA-0005
title: Human-approved FCPA content before assignment
framework: fcpa
domain: [compliance, governance]
industries: [cross-industry]
persona: content-author
priority: must
status: draft
also_satisfies: [sox, hipaa, gdpr]
traces_to:
  - docs/03_ai_drafted_human_approved_content.md
  - ADR-011
---

# US-FCPA-0005 — Human-approved FCPA content before assignment

## Story

> **As a** content author / compliance SME,
> **I want** AI-drafted FCPA training to land as an *untrusted draft* that I must
> review and approve before it can be assigned,
> **so that** no hallucinated or inaccurate FCPA claim ever reaches employees as
> official training — "the AI wrote it" is not a defence.

## Context

FCPA content is high-stakes: a wrong statement about facilitation payments or a
mischaracterized G&H threshold in *official* training is itself an exposure. The
product's content path is therefore **generate → human-approve → version-pin →
assign**, with separation of duties (the approver is not the generator). This story
is the FCPA-specific application of ADR-011 / `docs/03`: a Mentible-generated FCPA
package arrives in the `consumer_library` as `RECEIVED`, and only a qualified human
can move it toward `PUBLISHED`.

## Acceptance criteria

1. **Given** a Mentible FCPA Consumable Package pushed to `consumer_library`,
   **when** its signature and content hash verify, **then** it is recorded as a
   `RECEIVED` draft — **not** assignable — carrying its provenance and source-clause
   citations.
2. **Given** a `RECEIVED`/`DRAFT` FCPA draft, **when** an author submits it for
   review and an approver who is **not** the generator approves it, **then** the
   content is frozen (hashed), the approver + attestation are captured, and it can
   be published into an immutable course version.
3. **Given** a draft that fails signature/hash verification, **when** it arrives,
   **then** it is quarantined and never silently published.
4. **Given** each FCPA module, **when** the reviewer reads it, **then** every claim
   shows its source citation (e.g. the FCPA provision it rests on) so accuracy is
   verified against the regulation, not vibes.

## Out of scope / notes

- The generation engine itself (Mentible) is external; this story is Pramana's
  ingestion + approval side, already implemented for the general case in ADR-011.
- `also_satisfies` lists other frameworks because the approval gate is framework-
  agnostic; FCPA is simply the first content set run through it here.

## Traceability

- `docs/03_ai_drafted_human_approved_content.md` (§2–§3 approval machine, §5 handoff).
- **ADR-011** consumer_library ingestion (PR #1): `pramana/services/consumer_library.py`,
  `pramana/domain/consumable_package.py`.
