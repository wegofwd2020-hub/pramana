---
id: US-HIPAA-0007
title: Human-approved HIPAA content before assignment
framework: hipaa
domain: [compliance, governance]
industries: [healthcare]
persona: content-author
priority: must
status: draft
also_satisfies: [fcpa, sox, gdpr]
traces_to:
  - docs/03_ai_drafted_human_approved_content.md
  - ADR-011
  - US-PLATFORM-0004
---

# US-HIPAA-0007 — Human-approved HIPAA content before assignment

## Story

> **As a** content author / HIPAA SME,
> **I want** AI-drafted HIPAA content to arrive as an *untrusted draft* that I must
> review and approve before assignment,
> **so that** no inaccurate PHI-handling or breach-reporting guidance reaches the
> workforce as official training — which would itself be a HIPAA exposure.

## Context

HIPAA content is high-stakes: wrong minimum-necessary or breach-timeline guidance in
official training is a problem in an OCR investigation. The path is the standard
**generate → human-approve → version-pin → assign** with separation of duties. This is
the HIPAA instance of the platform approval gate (US-PLATFORM-0004) and the policy in
`docs/03`; HIPAA adds nothing to the mechanism — it runs HIPAA content through it.

## Acceptance criteria

1. **Given** a Mentible HIPAA package pushed to `consumer_library`, **when** its
   signature + content hash verify, **then** it lands as a `RECEIVED` draft — not
   assignable — with provenance and rule citations.
2. **Given** a HIPAA draft in review, **when** an approver who is **not** the generator
   approves it (attestation + frozen hash), **then** it can publish to an immutable
   course version.
3. **Given** each module, **when** the reviewer reads it, **then** every claim cites its
   HIPAA rule so accuracy is verified against the regulation.
4. **Given** a draft that fails verification, **when** it arrives, **then** it is
   quarantined and never silently published.

## Reuses (platform)

- The review/approval gate: [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md);
  regenerate: [US-PLATFORM-0005](../platform/US-PLATFORM-0005-regenerate-with-updated-parameters.md).
- Same policy as [US-FCPA-0005](../fcpa/US-FCPA-0005-human-approved-fcpa-content.md) /
  [US-SOX-0007](../sox/US-SOX-0007-human-approved-sox-content.md); `also_satisfies` reflects
  the gate being framework-agnostic.

## Traceability

- Approval policy + state machine: `docs/03_…`, `pramana/domain/content_approval.py`.
- Boundary: **ADR-011** + `pramana/services/consumer_library.py`.
