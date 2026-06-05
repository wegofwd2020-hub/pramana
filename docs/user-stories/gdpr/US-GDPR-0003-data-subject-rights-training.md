---
id: US-GDPR-0003
title: Data subject rights handling training
framework: gdpr
domain: [compliance, regulatory]
industries: [cross-industry]
persona: employee
priority: should
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_gdpr.md#data-subject-rights
  - US-PLATFORM-0001
---

# US-GDPR-0003 — Data subject rights handling training

## Story

> **As an** employee in a customer-facing, HR, or support role,
> **I want** training on recognising and routing data-subject requests (access,
> rectification, erasure, portability, objection),
> **so that** requests are handled within the one-month deadline and not missed or
> mishandled.

## Context

Articles 15-22 give individuals rights the organisation must service, typically within
one month. The staff who *receive* such requests (support, HR, sales) need to recognise a
DSR and route it correctly. This is **targeted** training (not all staff), mirroring the
role-based targeting used in FCPA/SOX/HIPAA. Delivery via the platform; GDPR supplies the
content and the audience.

## Acceptance criteria

1. **Given** a DSR-handling population (by role), **when** the DPO assigns this course,
   **then** only that population is targeted.
2. **Given** the course, **when** the employee takes it, **then** it covers each right,
   how to recognise a request, the routing/escalation path, and the one-month deadline.
3. **Given** completion, **when** scoring finalizes, **then** it is recorded with a
   version-pinned certificate.

## Reuses (platform)

- Library + player + targeting: [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md),
  [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).

## Out of scope / notes

- The `DataSubjectRequest` tracking workflow (intake, 30-day SLA) is a separate system
  capability; this story is awareness/routing training.
- Actually *fulfilling* an erasure request is US-GDPR-0004.

## Traceability

- Articles 15-22 rights: `framework_gdpr.md#data-subject-rights`.
- Targeting pattern: [US-HIPAA-0004](../hipaa/US-HIPAA-0004-role-based-training-paths.md).
