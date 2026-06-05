---
id: US-GDPR-0002
title: Personal-data breach (72-hour) training
framework: gdpr
domain: [compliance, regulatory]
industries: [cross-industry]
persona: employee
priority: must
status: draft
also_satisfies: [hipaa]
traces_to:
  - docs/frameworks/framework_gdpr.md#breach-notification
  - US-HIPAA-0003
  - US-PLATFORM-0002
---

# US-GDPR-0002 — Personal-data breach (72-hour) training

## Story

> **As an** employee,
> **I want** training on recognising a personal-data breach and reporting it immediately,
> **so that** the controller can meet the **72-hour** Article 33 notification deadline —
> and we evidence that breach-response staff were trained.

## Context

Article 33 requires notifying the supervisory authority of a personal-data breach within
72 hours of awareness. That deadline depends on the **workforce reporting fast**, so
recognition + internal escalation training is essential, and breach-response staff must be
*demonstrably* trained. This is the GDPR analogue of the HIPAA breach story
(US-HIPAA-0003) — same shape, GDPR specifics (72h, supervisory authority), so it carries
`also_satisfies: [hipaa]`.

## Acceptance criteria

1. **Given** the breach course, **when** the employee takes it, **then** it covers what a
   personal-data breach is, examples, and the internal reporting channel, assessed by quiz.
2. **Given** breach-response staff, **when** the course renders, **then** it explains the
   72-hour clock, the supervisory-authority recipient, and when data subjects must be told
   (Article 34).
3. **Given** completion at threshold, **when** scoring finalizes, **then** it counts toward
   the GDPR record with a version-pinned certificate.

## Reuses (platform / cross-framework)

- Player + quiz: [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Reuses the breach pattern from [US-HIPAA-0003](../hipaa/US-HIPAA-0003-breach-recognition-reporting.md).

## Out of scope / notes

- The breach-management/notification workflow itself is out of scope — awareness only.

## Traceability

- Article 33 breach notification: `framework_gdpr.md#breach-notification`.
