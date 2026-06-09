---
id: US-SOX-0007
title: Human-approved SOX content before assignment
framework: sox
domain: [compliance, governance]
industries: [cross-industry]
persona: content-author
priority: must
status: draft
also_satisfies: [fcpa, hipaa, gdpr]
traces_to:
  - docs/03_ai_drafted_human_approved_content.md
  - ADR-011
  - US-PLATFORM-0004
---

# US-SOX-0007 — Human-approved SOX content before assignment

## Story

> **As a** content author / SOX SME,
> **I want** AI-drafted SOX content to arrive as an *untrusted draft* that I must
> review and approve before assignment,
> **so that** no inaccurate controls or §-citation reaches certifying officers or
> finance staff as official training — a SOX control failure in the training itself.

## Context

SOX content is high-stakes: a wrong statement about §404 controls or §302
certification in *official* training is an audit problem. So the path is the standard
**generate → human-approve → version-pin → assign** with separation of duties. This is
the SOX instance of the platform approval gate (US-PLATFORM-0004) and the policy in
`docs/03`; SOX adds nothing new to the mechanism — it just runs SOX content through it.

## Acceptance criteria

1. **Given** a Mentible SOX package pushed to `consumer_library`, **when** its
   signature + content hash verify, **then** it lands as a `RECEIVED` draft — not
   assignable — with provenance and §-citations.
2. **Given** a SOX draft in review, **when** an approver who is **not** the generator
   approves it (attestation + frozen hash), **then** it can publish to an immutable
   course version.
3. **Given** each module, **when** the reviewer reads it, **then** every claim cites
   its SOX section so accuracy is verified against the statute.
4. **Given** a draft that fails verification, **when** it arrives, **then** it is
   quarantined and never silently published.

## Reuses (platform)

- The review/approval gate: [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md);
  regenerate: [US-PLATFORM-0005](../platform/US-PLATFORM-0005-regenerate-with-updated-parameters.md).
- Same policy as [US-FCPA-0005](../fcpa/US-FCPA-0005-human-approved-fcpa-content.md);
  `also_satisfies` reflects that the gate is framework-agnostic.

## Traceability

- Approval policy + state machine: `docs/03_…`, `pramana/domain/content_approval.py`.
- Boundary: **ADR-011** + `pramana/services/consumer_library.py`.
