---
id: US-HIPAA-0004
title: Role-based training paths by PHI access
framework: hipaa
domain: [compliance, regulatory]
industries: [healthcare]
persona: compliance-officer
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_hipaa.md#privacy-rule
  - docs/frameworks/framework_hipaa.md#security-rule
  - US-PLATFORM-0001
---

# US-HIPAA-0004 — Role-based training paths by PHI access

## Story

> **As a** Privacy Officer,
> **I want** to assign different HIPAA training paths by role and PHI-access level
> (clinical, billing, IT, executive),
> **so that** each group gets relevant depth — which HIPAA explicitly permits — without
> over-training low-access staff.

## Context

HIPAA explicitly allows training to be **tailored to function**. The framework doc adds
`User.phi_access_level` and `Course.applicable_roles` for this. This is HIPAA's analogue
of FCPA risk-tier targeting and SOX MNPI targeting — the platform supports assignment by
role/attribute; this story defines the HIPAA path mapping.

## Acceptance criteria

1. **Given** users carry a role + `phi_access_level`, **when** the officer defines
   training paths, **then** each path maps a population to a set of HIPAA courses.
2. **Given** defined paths, **when** the officer assigns, **then** they target by path
   (e.g. "all full-PHI clinical staff") rather than enumerating users.
3. **Given** a user whose role/PHI access changes, **when** the change is recorded,
   **then** their required path is re-evaluated (feeds US-HIPAA-0005).
4. **Given** path coverage, **when** the officer reviews the dashboard, **then**
   completion is reported per path.

## Reuses (platform)

- Library + player: [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md),
  [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).

## Out of scope / notes

- The `phi_access_level` source-of-truth is upstream identity data; this story consumes it.

## Traceability

- Role-based variation: `framework_hipaa.md` §3.4; rules `#privacy-rule`, `#security-rule`.
- Targeting pattern mirrors [US-FCPA-0007](../fcpa/US-FCPA-0007-high-risk-geography-targeting.md)
  and [US-SOX-0004](../sox/US-SOX-0004-insider-trading-reg-fd.md).
