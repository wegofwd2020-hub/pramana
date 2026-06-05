---
id: US-FCPA-0009
title: M&A successor-liability onboarding training trigger
framework: fcpa
domain: [compliance, governance]
industries: [cross-industry]
persona: compliance-officer
priority: should
status: draft
also_satisfies: []
traces_to:
  - docs/02_resolved_decisions.md
  - US-FCPA-0001
  - US-FCPA-0003
---

# US-FCPA-0009 — M&A successor-liability onboarding training trigger

## Story

> **As a** compliance officer,
> **I want** acquired-company employees (and their in-scope third parties) to be
> automatically enrolled in FCPA training as part of post-close onboarding,
> **so that** we promptly remediate inherited FCPA exposure — acquirers take on the
> target's successor liability.

## Context

FCPA **successor liability** means an acquirer can inherit the target's pre-close
violations; regulators expect prompt post-acquisition due diligence and integration,
including training the newly-acquired population. This story is an **assignment
trigger**: when a cohort is onboarded as part of an acquisition, FCPA training is
issued automatically with a tight due date, rather than relying on someone to
remember to assign it.

## Acceptance criteria

1. **Given** an acquired cohort is imported/marked as an M&A onboarding group,
   **when** the group is created, **then** the configured FCPA onboarding curriculum
   is auto-assigned to every member with an accelerated due date.
2. **Given** the cohort includes third-party intermediaries, **when** the trigger
   fires, **then** those parties are enrolled via the third-party path
   (US-FCPA-0003).
3. **Given** an auto-assigned M&A cohort, **when** the officer views the FCPA
   dashboard, **then** the cohort's completion is reportable as a distinct
   remediation population.
4. **Given** the trigger configuration, **when** it runs, **then** the auto-
   assignment event (who/what/when, and that it was M&A-triggered) is in the audit log.

## Out of scope / notes

- Pre-close **due-diligence questionnaires / risk assessment** are out of scope —
  this is post-close *training* integration only.
- Generic assignment triggers (on-hire, on-role-change) are a broader capability;
  this story is the FCPA M&A case specifically.

## Traceability

- Assignment triggers / cohorts: `docs/02_resolved_decisions.md`.
- Reuses core + third-party flows: [US-FCPA-0001](US-FCPA-0001-anti-bribery-training-assignment.md),
  [US-FCPA-0003](US-FCPA-0003-third-party-intermediary-training.md).
