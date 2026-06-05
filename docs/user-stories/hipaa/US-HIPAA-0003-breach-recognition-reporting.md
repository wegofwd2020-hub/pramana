---
id: US-HIPAA-0003
title: Breach recognition & reporting training
framework: hipaa
domain: [compliance, regulatory]
industries: [healthcare, cross-industry]
persona: employee
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_hipaa.md#breach-notification-rule
  - US-PLATFORM-0002
---

# US-HIPAA-0003 — Breach recognition & reporting training

## Story

> **As an** employee,
> **I want** training on what constitutes a PHI breach and how/when to report it,
> **so that** I escalate incidents quickly and the company can meet the 60-day breach
> notification obligation — and evidence the workforce was trained to recognise breaches.

## Context

The Breach Notification Rule (§164.400-414) depends on the workforce **recognising and
reporting** incidents fast; missed or late reporting drives penalties. The training
covers what a breach is, the internal reporting channel, and (for relevant staff) the
notification recipients and 60-day timeline. Standard platform delivery; HIPAA-specific
content + the reporting-channel awareness.

## Acceptance criteria

1. **Given** the breach course, **when** the employee takes it, **then** it covers
   breach definition, examples, and the internal reporting channel, assessed by quiz.
2. **Given** relevant staff, **when** the course renders, **then** it explains the
   notification recipients (OCR, individuals, sometimes media) and the 60-day timeline.
3. **Given** completion at threshold, **when** scoring finalizes, **then** it counts
   toward the HIPAA record with a version-pinned certificate.

## Reuses (platform)

- Player + quiz: [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Content commissioned/approved: [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) /
  [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md).

## Out of scope / notes

- The incident-intake / breach-management system itself is out of scope — this is
  awareness training, not the workflow.

## Traceability

- Breach Notification Rule: `docs/frameworks/framework_hipaa.md#breach-notification-rule`.
