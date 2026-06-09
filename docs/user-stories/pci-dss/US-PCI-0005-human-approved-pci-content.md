---
id: US-PCI-0005
title: Human-approved PCI content before assignment
framework: pci-dss
domain: [compliance, governance]
industries: [retail, financial-services, cross-industry]
persona: content-author
priority: must
status: draft
also_satisfies: [fcpa, sox, hipaa, gdpr, iso27001]
traces_to:
  - docs/03_ai_drafted_human_approved_content.md
  - ADR-011
  - US-PLATFORM-0004
---

# US-PCI-0005 — Human-approved PCI content before assignment

## Story

> **As a** content author / PCI SME,
> **I want** AI-drafted PCI DSS content to arrive as an *untrusted draft* that I must review
> and approve before assignment,
> **so that** inaccurate awareness or secure-development content does not reach CDE personnel
> as official training — which a QSA would treat as a control gap.

## Context

The standard **generate → human-approve → version-pin → assign** path with separation of
duties applies unchanged. This is the PCI instance of the platform approval gate
(US-PLATFORM-0004) and the `docs/03` policy. The gate is now proven framework-agnostic across
all six frameworks — hence the comprehensive `also_satisfies`.

## Acceptance criteria

1. **Given** a Mentible PCI package pushed to `consumer_library`, **when** its signature +
   content hash verify, **then** it lands as a `RECEIVED` draft — not assignable — with
   provenance and requirement citations.
2. **Given** a PCI draft in review, **when** an approver who is **not** the generator approves
   it (attestation + frozen hash), **then** it can publish to an immutable course version.
3. **Given** each module, **when** the reviewer reads it, **then** every claim cites its PCI
   requirement.
4. **Given** a draft that fails verification, **when** it arrives, **then** it is quarantined
   and never silently published.

## Reuses (platform)

- The review/approval gate: [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md);
  regenerate: [US-PLATFORM-0005](../platform/US-PLATFORM-0005-regenerate-with-updated-parameters.md).
- Same policy as every other framework's `*-0005/0006/0007` approval story.

## Traceability

- Approval policy + state machine: `docs/03_…`, `pramana/domain/content_approval.py`.
- Boundary: **ADR-011** + `pramana/services/consumer_library.py`.
