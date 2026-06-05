---
id: US-SOX-0001
title: §404 internal-controls (ICFR) awareness training
framework: sox
domain: [compliance, regulatory]
industries: [cross-industry]
persona: compliance-officer
priority: must
status: draft
also_satisfies: [fcpa]
traces_to:
  - docs/frameworks/framework_sox.md#section-404
  - docs/02_resolved_decisions.md
  - US-PLATFORM-0001
  - US-PLATFORM-0002
---

# US-SOX-0001 — §404 internal-controls (ICFR) awareness training

## Story

> **As a** compliance officer,
> **I want** to assign internal-controls-over-financial-reporting (ICFR) training to
> the SOX-in-scope population and track completion to a passing score,
> **so that** when external auditors assess §404, I can show the right people were
> trained, with reliable, tamper-evident evidence.

## Context

This is SOX's core training control. §404 requires management to assess ICFR;
training finance, IT, and internal-audit personnel on controls, fraud, and code of
conduct is one of those controls, and the auditor wants **evidence**. It overlaps the
FCPA accounting pillar, so the same module can satisfy both. The *delivery* is the
platform library + player; this story is the SOX-specific scoping, content, and
evidence requirement.

## Acceptance criteria

1. **Given** a published ICFR course, **when** the officer assigns it to the
   SOX-in-scope population (by role/department), **then** each user gets an
   assignment with a due date and an audit-log entry (who/what/when).
2. **Given** an assigned user, **when** they complete the course and pass the quiz,
   **then** a certificate is issued pinned to the exact content version.
3. **Given** completion data, **when** the officer opens the SOX dashboard, **then**
   they see completion %, overdue, and blocked for the in-scope population.
4. **Given** the accounting-pillar overlap, **when** a user completes this course,
   **then** the completion is attributable to **both** SOX and FCPA
   (`also_satisfies`) without double-assigning.

## Reuses (platform)

- Learner library + player: [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md),
  [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Content commissioned + approved via [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) /
  [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md).

## Out of scope / notes

- SOX-in-scope **population designation** (`User.in_scope_for_sox`) is a separate
  planned story; this assumes the officer can select that population.

## Traceability

- §404 ICFR: `docs/frameworks/framework_sox.md#section-404`.
- Cross-framework overlap: [US-FCPA-0004](../fcpa/US-FCPA-0004-books-records-internal-controls.md).
