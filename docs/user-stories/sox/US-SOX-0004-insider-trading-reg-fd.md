---
id: US-SOX-0004
title: Insider trading / Reg FD for MNPI holders
framework: sox
domain: [compliance, regulatory]
industries: [cross-industry]
persona: employee
priority: should
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_sox.md#section-404
  - US-PLATFORM-0001
---

# US-SOX-0004 — Insider trading / Reg FD for MNPI holders

## Story

> **As an** employee with access to material non-public information (MNPI),
> **I want** targeted training on insider-trading rules and Regulation FD,
> **so that** I understand trading windows, the prohibition on tipping, and selective-
> disclosure rules — and the company evidences that MNPI holders were trained.

## Context

Not everyone needs this; it is **targeted** at MNPI holders (finance, executives,
investor relations, certain IT). This is the SOX analogue of FCPA's risk-based
targeting — the platform supports assigning by role, and this story supplies the
audience definition and the insider-trading/Reg FD content.

## Acceptance criteria

1. **Given** an MNPI-holder population (by role/flag), **when** the officer assigns
   this course, **then** only that population is targeted (not all staff).
2. **Given** an assigned MNPI holder, **when** they complete the course, **then**
   completion is recorded with a version-pinned certificate.
3. **Given** the targeted nature, **when** the officer reviews coverage, **then**
   completion is reported against the MNPI population specifically.

## Reuses (platform)

- Library + player: [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md),
  [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).

## Out of scope / notes

- Maintaining the **MNPI/insider list** is an upstream data concern; this story
  consumes a role/flag to target.

## Traceability

- Disclosure/controls context: `docs/frameworks/framework_sox.md#section-404`.
- Targeting pattern mirrors [US-FCPA-0007](../fcpa/US-FCPA-0007-high-risk-geography-targeting.md).
