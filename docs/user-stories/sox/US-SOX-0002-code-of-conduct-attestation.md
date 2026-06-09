---
id: US-SOX-0002
title: Annual Code of Conduct & ethics attestation
framework: sox
domain: [compliance, governance]
industries: [cross-industry]
persona: employee
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_sox.md#section-404
  - US-PLATFORM-0002
---

# US-SOX-0002 — Annual Code of Conduct & ethics attestation

## Story

> **As an** employee,
> **I want** to complete the annual Code of Conduct / ethics training and attest that
> I have read and will follow it,
> **so that** the company has signed evidence of a working ethics control for SOX.

## Context

A current, acknowledged Code of Conduct is a foundational SOX control (and a COSO
"control environment" element). The value here is the **annual attestation** captured
as audit evidence. Delivery is the standard platform player; this story adds the SOX
ethics content and the explicit attestation step.

## Acceptance criteria

1. **Given** the annual Code of Conduct course, **when** the employee completes it,
   **then** they must record an explicit **attestation** to finish.
2. **Given** a recorded attestation, **when** it is saved, **then** the audit log
   captures the employee, the exact content version, and the timestamp.
3. **Given** the annual cadence, **when** a year elapses, **then** the employee is
   re-assigned (reuses the platform cadence trigger).
4. **Given** an employee who has not attested, **when** the officer reviews coverage,
   **then** the gap is visible in the SOX dashboard.

## Reuses (platform)

- Player + attestation capture: [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Content approved via [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md).

## Out of scope / notes

- Cadence/re-assignment mechanics are a shared platform concern (SOX planned cadence
  story); this story consumes them.

## Traceability

- Ethics as a §404 control: `docs/frameworks/framework_sox.md#section-404`.
