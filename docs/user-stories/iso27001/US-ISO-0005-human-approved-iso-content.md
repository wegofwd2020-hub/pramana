---
id: US-ISO-0005
title: Human-approved ISO content before assignment
framework: iso27001
domain: [compliance, governance]
industries: [cross-industry]
persona: content-author
priority: must
status: draft
also_satisfies: [fcpa, sox, hipaa, gdpr]
traces_to:
  - docs/03_ai_drafted_human_approved_content.md
  - ADR-011
  - US-PLATFORM-0004
---

# US-ISO-0005 — Human-approved ISO content before assignment

## Story

> **As a** content author / ISMS SME,
> **I want** AI-drafted ISO 27001 content to arrive as an *untrusted draft* that I must
> review and approve before assignment,
> **so that** inaccurate awareness or competence content does not reach personnel as
> official training — which a certification auditor would treat as a control weakness.

## Context

The standard **generate → human-approve → version-pin → assign** path with separation of
duties applies unchanged. This is the ISO instance of the platform approval gate
(US-PLATFORM-0004); ISO adds nothing to the mechanism. By now the gate is proven
framework-agnostic across FCPA/SOX/HIPAA/GDPR — hence the broad `also_satisfies`.

## Acceptance criteria

1. **Given** a Mentible ISO package pushed to `consumer_library`, **when** its signature +
   content hash verify, **then** it lands as a `RECEIVED` draft — not assignable — with
   provenance and clause/control citations.
2. **Given** an ISO draft in review, **when** an approver who is **not** the generator
   approves it (attestation + frozen hash), **then** it can publish to an immutable course
   version.
3. **Given** each module, **when** the reviewer reads it, **then** every claim cites its ISO
   clause/Annex A control.
4. **Given** a draft that fails verification, **when** it arrives, **then** it is quarantined
   and never silently published.

## Reuses (platform)

- The review/approval gate: [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md);
  regenerate: [US-PLATFORM-0005](../platform/US-PLATFORM-0005-regenerate-with-updated-parameters.md).
- Same policy as the other frameworks' `*-0005/0006/0007` approval stories.

## Traceability

- Approval policy + state machine: `docs/03_…`, `pramana/domain/content_approval.py`.
- Boundary: **ADR-011** + `pramana/services/consumer_library.py`.
