---
id: US-ISO-0001
title: Information security awareness training
framework: iso27001
domain: [compliance, governance]
industries: [cross-industry]
persona: compliance-officer
priority: must
status: draft
also_satisfies: [hipaa, gdpr]
traces_to:
  - docs/frameworks/framework_iso27001.md#awareness-training-control
  - docs/frameworks/framework_iso27001.md#awareness
  - US-PLATFORM-0001
  - US-PLATFORM-0002
---

# US-ISO-0001 — Information security awareness training

## Story

> **As an** ISMS manager (compliance officer),
> **I want** to assign information-security awareness training to all in-scope personnel
> and track completion,
> **so that** we satisfy Clause 7.3 / Annex A.6.3 and can pass the certification body's
> sampling of awareness-training evidence.

## Context

Annex A.6.3 requires an awareness, education and training program for **all** personnel,
and Clause 7.3 requires they understand the ISMS policy and their role. Auditors sample
people and ask for completion evidence; a gap is a nonconformity that can suspend
certification. Topics span policy, acceptable use, password hygiene, phishing, incident
reporting, data classification, clean desk. It overlaps HIPAA security awareness and GDPR
awareness, so it carries `also_satisfies`. Delivery is the platform library + player.

## Acceptance criteria

1. **Given** a published awareness course of `training_type = awareness`, **when** the ISMS
   manager assigns it to in-scope personnel, **then** each gets an assignment with a due
   date and an audit-log entry.
2. **Given** an assigned user, **when** they complete and pass, **then** a certificate is
   issued pinned to the exact content version.
3. **Given** completion data, **when** the manager opens the ISO dashboard, **then** they
   see awareness coverage across in-scope personnel.
4. **Given** the security-awareness overlap, **when** a user completes this course, **then**
   it is attributable to ISO 27001, HIPAA, and GDPR (`also_satisfies`).

## Reuses (platform)

- Library + player: [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md),
  [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Commission + approve: [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) /
  [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md).

## Out of scope / notes

- Role-specific **competence** (developers, sysadmins) is US-ISO-0002, distinct from broad
  awareness.

## Traceability

- A.6.3 / Clause 7.3: `framework_iso27001.md#awareness-training-control`, `#awareness`.
- Security-awareness twins: [US-HIPAA-0002](../hipaa/US-HIPAA-0002-security-awareness-program.md),
  [US-GDPR-0001](../gdpr/US-GDPR-0001-data-protection-awareness-training.md).
