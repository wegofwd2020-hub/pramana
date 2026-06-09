---
id: US-SOX-0003
title: Fraud awareness, reporting & whistleblower (§806)
framework: sox
domain: [compliance, governance]
industries: [cross-industry]
persona: employee
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_sox.md#section-806
  - US-PLATFORM-0002
---

# US-SOX-0003 — Fraud awareness, reporting & whistleblower (§806)

## Story

> **As an** employee,
> **I want** training on how to recognise and report financial fraud and on my
> whistleblower protections,
> **so that** I know the reporting channels and that the company evidences a working
> fraud-reporting / §806 control.

## Context

§806 protects employees who report fraud; an effective program trains staff on the
red flags and the (anonymous) reporting channels, and keeps evidence that the
training occurred. This is a standard annual SOX topic delivered through the platform
player; the SOX-specific part is the content and the reporting-channel awareness.

## Acceptance criteria

1. **Given** the fraud/whistleblower course, **when** the employee takes it, **then**
   it covers fraud red flags and the available reporting channels (including
   anonymous), assessed by quiz.
2. **Given** completion at threshold, **when** scoring finalizes, **then** it counts
   toward the SOX training record with a certificate pinned to the version.
3. **Given** the §806 non-retaliation message, **when** the course renders, **then**
   the protection is presented clearly (and acknowledged).

## Reuses (platform)

- Player + quiz: [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Content commissioned/approved: [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) /
  [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md).

## Out of scope / notes

- The reporting **hotline/intake system** itself is out of scope — this is awareness
  training, not the channel.

## Traceability

- §806 whistleblower protection: `docs/frameworks/framework_sox.md#section-806`.
