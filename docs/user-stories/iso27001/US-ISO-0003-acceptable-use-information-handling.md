---
id: US-ISO-0003
title: Acceptable use & information-handling awareness
framework: iso27001
domain: [compliance]
industries: [cross-industry]
persona: employee
priority: should
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_iso27001.md#awareness-training-control
  - US-PLATFORM-0002
---

# US-ISO-0003 — Acceptable use & information-handling awareness

## Story

> **As an** employee,
> **I want** awareness training on acceptable use and information handling (data
> classification, clean desk/clear screen, removable media, mobile/remote security),
> **so that** I handle information per ISMS policy and the organization evidences coverage
> of these Annex A topics.

## Context

Annex A.6.3 awareness spans a concrete set of day-to-day behaviours. This story carves the
"acceptable use & handling" slice out of the broad awareness program (US-ISO-0001) so it can
be assigned and evidenced against the specific Annex A controls (e.g. data classification,
clean desk, removable media). Standard platform delivery.

## Acceptance criteria

1. **Given** the acceptable-use course, **when** the employee takes it, **then** it covers
   data classification/handling, clean desk/clear screen, removable media, and mobile/remote
   security, assessed by quiz.
2. **Given** completion at threshold, **when** scoring finalizes, **then** it counts toward
   the ISO record with a version-pinned certificate.
3. **Given** Annex A mapping, **when** evidence is exported, **then** this course maps to the
   relevant Annex A controls (feeds US-ISO-0006).

## Reuses (platform)

- Player + quiz: [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Content commissioned/approved: [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) /
  [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md).

## Out of scope / notes

- The technical enforcement of these controls (MDM, DLP) is out of scope — awareness only.

## Traceability

- A.6.3 awareness topics: `framework_iso27001.md#awareness-training-control`, §3.1.
