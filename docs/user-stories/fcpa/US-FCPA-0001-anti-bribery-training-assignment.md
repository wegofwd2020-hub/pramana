---
id: US-FCPA-0001
title: Risk-based anti-bribery training assignment & completion
framework: fcpa
domain: [compliance, regulatory]
industries: [cross-industry]
persona: compliance-officer
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/02_resolved_decisions.md      # FR-assignment, assignment state machine
  - docs/03_ai_drafted_human_approved_content.md
---

# US-FCPA-0001 — Risk-based anti-bribery training assignment & completion

## Story

> **As a** compliance officer,
> **I want** to assign FCPA anti-bribery training to employees based on their
> role and exposure, and track completion to a passing score,
> **so that** I can demonstrate to the DOJ/SEC that at-risk staff were trained and
> attested, with auditable evidence.

## Context

Anti-bribery is the headline FCPA obligation: no thing of value to a foreign
official to obtain or retain business. DOJ's compliance-program guidance expects
**risk-based** training — not a blanket annual click-through, but targeting the
employees whose roles touch government interactions, sales in high-risk markets,
or third parties. The product must let the program owner scope, assign, and prove
completion, reusing the existing assignment → attempt → certificate flow.

## Acceptance criteria

1. **Given** a published FCPA anti-bribery course, **when** the compliance officer
   assigns it to a set of users (by individual, role, or department),
   **then** each user gets an assignment in `ASSIGNED` with a due date, and an
   audit-log entry records who assigned what, to whom, and when.
2. **Given** an assigned user, **when** they complete the course and pass the quiz
   at or above the course pass threshold, **then** the assignment moves to `PASSED`
   and a certificate is issued bearing the exact content version they were trained on.
3. **Given** a user who fails up to the allowed attempts, **when** the last attempt
   fails, **then** the assignment is `BLOCKED` and surfaced on the compliance
   officer's exception report for intervention.
4. **Given** an in-flight program, **when** the compliance officer opens the FCPA
   dashboard, **then** they see completion %, overdue count, and blocked count for
   the assigned population.

## Out of scope / notes

- Geography/role *risk-tiering* logic is its own story (planned: high-risk geography
  targeting). This story assumes the officer selects the population.
- Refresher cadence / re-assignment triggers are a separate story.

## Traceability

- Assignment lifecycle & version pinning: `docs/02_resolved_decisions.md`.
- Certificate ties to an immutable approved content version: `docs/03_…`.
