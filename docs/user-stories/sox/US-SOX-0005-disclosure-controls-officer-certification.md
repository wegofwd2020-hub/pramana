---
id: US-SOX-0005
title: Disclosure controls & officer certification (§302/§906)
framework: sox
domain: [compliance, governance, regulatory]
industries: [cross-industry]
persona: compliance-officer
priority: should
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_sox.md#section-302
  - US-PLATFORM-0003
---

# US-SOX-0005 — Disclosure controls & officer certification (§302/§906)

## Story

> **As a** compliance officer,
> **I want** to commission and assign disclosure-controls training to executives and
> SEC filers who certify the financials (§302/§906),
> **so that** certifying officers understand what they attest to, and the company
> evidences that they were trained before signing.

## Context

Under §302 (and the criminal §906), the CEO/CFO personally certify the accuracy of
filings and the effectiveness of disclosure controls. Training the certifying
officers and SEC-filer population on what those certifications mean is a high-value,
narrowly-targeted control. Delivery and approval are the platform surfaces; this
story supplies the §302 content and the executive/SEC-filer audience.

## Acceptance criteria

1. **Given** the disclosure-controls course, **when** the officer commissions it,
   **then** the Package Request references `framework_sox.md#section-302` and targets
   the executive / SEC-filer population.
2. **Given** the targeted population, **when** assigned, **then** completion is tracked
   and certificated, version-pinned.
3. **Given** the sensitivity, **when** the course is assigned, **then** it is
   reportable as a distinct certifying-officer population in the SOX dashboard.

## Reuses (platform)

- Commission from a §: [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md).
- Approve before assignment: [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md).
- Library + player: [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md) /
  [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).

## Out of scope / notes

- The certification **signing workflow** (officers actually signing filings) is out of
  scope — this is the *training* that precedes it.
- A dedicated `executive` persona may be warranted later; for now the trainee is an
  `employee` targeted by scope, commissioned by the `compliance-officer`.

## Traceability

- §302 certification: `docs/frameworks/framework_sox.md#section-302`.
