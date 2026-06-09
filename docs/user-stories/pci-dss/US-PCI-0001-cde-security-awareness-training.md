---
id: US-PCI-0001
title: CDE security awareness training
framework: pci-dss
domain: [compliance, regulatory]
industries: [retail, financial-services, cross-industry]
persona: compliance-officer
priority: must
status: draft
also_satisfies: [iso27001]
traces_to:
  - docs/frameworks/framework_pci_dss.md#security-awareness-program
  - US-PLATFORM-0001
  - US-PLATFORM-0002
---

# US-PCI-0001 — CDE security awareness training

## Story

> **As a** security/compliance officer,
> **I want** to assign security awareness training to all personnel with access to the
> cardholder-data environment (CDE) and track completion,
> **so that** we satisfy Requirement 12.6 and can show a QSA the formal-training evidence
> for in-scope personnel.

## Context

Req 12.6 requires a security awareness program for **CDE-access personnel** covering
acceptable use, CDE threats/vulnerabilities, phishing/social engineering, and incident
reporting. Targeting is CDE-scoped (`User.cde_access`), not everyone — distinguishing PCI
from the broader awareness frameworks. It overlaps ISO security awareness, so it carries
`also_satisfies`. Delivery is the platform library + player.

## Acceptance criteria

1. **Given** a published 12.6 awareness course, **when** the officer assigns it to the
   CDE-access population, **then** each gets an assignment with a due date and an audit-log
   entry.
2. **Given** an assigned user, **when** they complete and pass, **then** a certificate is
   issued pinned to the exact content version.
3. **Given** completion data, **when** the officer opens the PCI dashboard, **then** they see
   coverage across CDE-access personnel.
4. **Given** the ISO overlap, **when** a user completes this course, **then** it is
   attributable to both PCI DSS and ISO 27001 (`also_satisfies`).

## Reuses (platform)

- Library + player: [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md),
  [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Commission + approve: [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) /
  [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md).

## Out of scope / notes

- This product is one **method** of a multi-method program — reporting must reflect that
  (US-PCI-0007).
- CDE-access designation is a planned data story; this assumes the officer can target it.

## Traceability

- Req 12.6: `framework_pci_dss.md#security-awareness-program`.
- Security-awareness family: [US-ISO-0001](../iso27001/US-ISO-0001-security-awareness-training.md),
  [US-HIPAA-0002](../hipaa/US-HIPAA-0002-security-awareness-program.md).
