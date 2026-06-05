---
id: US-GDPR-0001
title: Data protection awareness training
framework: gdpr
domain: [compliance, regulatory]
industries: [cross-industry]
persona: compliance-officer
priority: must
status: draft
also_satisfies: [iso27001]
traces_to:
  - docs/frameworks/framework_gdpr.md#data-protection-awareness
  - docs/02_resolved_decisions.md
  - US-PLATFORM-0001
  - US-PLATFORM-0002
---

# US-GDPR-0001 — Data protection awareness training

## Story

> **As a** Data Protection Officer (compliance officer),
> **I want** to assign data-protection awareness training to staff involved in
> processing personal data and track completion,
> **so that** we evidence the Article 32/39 "appropriate organisational measure" of
> staff awareness as part of our accountability trail.

## Context

GDPR has no explicit training mandate, but Article 39(1)(b) makes staff awareness the
DPO's duty and Article 32 treats it as a required organisational measure; regulators
expect documented, periodic training as accountability evidence. The content covers the
data-protection principles (Article 5), lawful bases (Article 6), and privacy-by-design
basics. It overlaps ISO 27001 awareness, so it carries `also_satisfies`. Delivery is the
platform library + player.

## Acceptance criteria

1. **Given** a published awareness course, **when** the DPO assigns it to processing
   staff, **then** each gets an assignment with a due date and an audit-log entry.
2. **Given** an assigned user, **when** they complete and pass, **then** a certificate is
   issued pinned to the exact content version.
3. **Given** completion data, **when** the DPO opens the GDPR dashboard, **then** they see
   coverage (complete / overdue / blocked) across processing staff.
4. **Given** the ISO overlap, **when** a user completes this course, **then** it is
   attributable to both GDPR and ISO 27001 (`also_satisfies`).

## Reuses (platform)

- Library + player: [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md),
  [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Commission + approve: [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) /
  [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md).

## Out of scope / notes

- Role-specific variants (marketing/consent, HR/employee-data, engineering/PbD) are
  planned follow-ups; this is the baseline awareness course.

## Traceability

- Awareness as an organisational measure: `framework_gdpr.md#data-protection-awareness`.
