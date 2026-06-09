---
id: US-GDPR-0006
title: Human-approved GDPR content before assignment
framework: gdpr
domain: [compliance, governance]
industries: [cross-industry]
persona: content-author
priority: must
status: draft
also_satisfies: [fcpa, sox, hipaa]
traces_to:
  - docs/03_ai_drafted_human_approved_content.md
  - ADR-011
  - US-PLATFORM-0004
---

# US-GDPR-0006 — Human-approved GDPR content before assignment

## Story

> **As a** content author / GDPR SME,
> **I want** AI-drafted GDPR content to arrive as an *untrusted draft* that I must review
> and approve before assignment,
> **so that** no inaccurate lawful-basis, rights, or 72-hour-breach guidance reaches staff
> as official training.

## Context

GDPR content is high-stakes and jurisdiction-sensitive: a wrong statement about a lawful
basis or the breach deadline in official training is an accountability problem. The path is
the standard **generate → human-approve → version-pin → assign** with separation of
duties. This is the GDPR instance of the platform approval gate (US-PLATFORM-0004) and the
`docs/03` policy; GDPR adds nothing to the mechanism.

## Acceptance criteria

1. **Given** a Mentible GDPR package pushed to `consumer_library`, **when** its signature +
   content hash verify, **then** it lands as a `RECEIVED` draft — not assignable — with
   provenance and article citations.
2. **Given** a GDPR draft in review, **when** an approver who is **not** the generator
   approves it (attestation + frozen hash), **then** it can publish to an immutable course
   version.
3. **Given** each module, **when** the reviewer reads it, **then** every claim cites its
   GDPR article so accuracy is verified against the regulation.
4. **Given** a draft that fails verification, **when** it arrives, **then** it is quarantined
   and never silently published.

## Reuses (platform)

- The review/approval gate: [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md);
  regenerate: [US-PLATFORM-0005](../platform/US-PLATFORM-0005-regenerate-with-updated-parameters.md).
- Same policy as [US-FCPA-0005](../fcpa/US-FCPA-0005-human-approved-fcpa-content.md) /
  [US-SOX-0007](../sox/US-SOX-0007-human-approved-sox-content.md) /
  [US-HIPAA-0007](../hipaa/US-HIPAA-0007-human-approved-hipaa-content.md).

## Traceability

- Approval policy + state machine: `docs/03_…`, `pramana/domain/content_approval.py`.
- Boundary: **ADR-011** + `pramana/services/consumer_library.py`.
