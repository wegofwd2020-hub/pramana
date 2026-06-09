---
id: US-HIPAA-0002
title: Security awareness & training program
framework: hipaa
domain: [compliance, regulatory]
industries: [healthcare, cross-industry]
persona: employee
priority: must
status: draft
also_satisfies: [iso27001]
traces_to:
  - docs/frameworks/framework_hipaa.md#security-rule
  - US-PLATFORM-0002
  - US-HIPAA-0005
---

# US-HIPAA-0002 — Security awareness & training program

## Story

> **As an** employee who handles ePHI,
> **I want** ongoing security awareness training (phishing/malware, passwords, log-in
> monitoring, security reminders),
> **so that** I protect ePHI and the company evidences a §164.308(a)(5) security
> awareness **program** — not a one-time event.

## Context

The Security Rule requires a security awareness training *program*, with named topics:
security reminders, protection from malicious software, log-in monitoring, and password
management. "Program" implies **periodic** delivery (reminders over time), so this story
leans on the platform cadence (US-HIPAA-0005). It overlaps ISO 27001 security awareness,
so it carries `also_satisfies`.

## Acceptance criteria

1. **Given** the security awareness course, **when** assigned to ePHI-handling staff,
   **then** it covers the required Security Rule topics and is assessed by quiz.
2. **Given** the "program" requirement, **when** configured, **then** periodic
   reminders/refreshers are issued on a cadence (reuses US-HIPAA-0005).
3. **Given** completion, **when** scoring finalizes, **then** it counts toward the HIPAA
   security training record with a version-pinned certificate.
4. **Given** the ISO overlap, **when** a user completes this course, **then** it is
   attributable to both HIPAA and ISO 27001 (`also_satisfies`).

## Reuses (platform)

- Player + quiz: [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Periodic cadence: [US-HIPAA-0005](US-HIPAA-0005-onhire-policy-change-triggers.md).

## Out of scope / notes

- Simulated-phishing campaigns are a separate security capability, not this training.

## Traceability

- Security Rule training program: `docs/frameworks/framework_hipaa.md#security-rule`.
