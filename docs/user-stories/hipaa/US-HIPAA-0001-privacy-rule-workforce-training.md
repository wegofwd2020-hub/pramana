---
id: US-HIPAA-0001
title: Privacy Rule workforce training
framework: hipaa
domain: [compliance, regulatory]
industries: [healthcare, cross-industry]
persona: compliance-officer
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_hipaa.md#privacy-rule
  - docs/02_resolved_decisions.md
  - US-PLATFORM-0001
  - US-PLATFORM-0002
---

# US-HIPAA-0001 — Privacy Rule workforce training

## Story

> **As a** Privacy Officer (compliance officer),
> **I want** to assign Privacy Rule (PHI handling) training to **all** workforce
> members and track completion,
> **so that** we satisfy the §164.530(b) duty to train the workforce and can produce
> the completion evidence OCR asks for.

## Context

The Privacy Rule explicitly **requires** training every workforce member (employees,
volunteers, trainees, contractors) on PHI policies — minimum necessary, permitted
uses/disclosures, patient rights. This is HIPAA's foundational training control.
Delivery is the platform library + player; this story is the HIPAA-specific scope
(*all* workforce), content, and evidence.

## Acceptance criteria

1. **Given** a published Privacy Rule course, **when** the officer assigns it to the
   full workforce population, **then** each member gets an assignment with a due date
   and an audit-log entry.
2. **Given** an assigned member, **when** they complete the course and pass, **then** a
   certificate is issued pinned to the exact content version.
3. **Given** completion data, **when** the officer opens the HIPAA dashboard, **then**
   they see coverage across the workforce (complete / overdue / blocked).
4. **Given** OCR evidence needs, **when** an export is run, **then** Privacy Rule
   completions appear in the HIPAA evidence binder (US-HIPAA-0008).

## Reuses (platform)

- Library + player: [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md),
  [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Commission + approve: [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) /
  [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md).

## Out of scope / notes

- New-hire / policy-change **auto-triggers** are US-HIPAA-0005; this story is the
  baseline workforce assignment.
- Role tailoring is US-HIPAA-0004.

## Traceability

- Privacy Rule training duty: `docs/frameworks/framework_hipaa.md#privacy-rule`.
