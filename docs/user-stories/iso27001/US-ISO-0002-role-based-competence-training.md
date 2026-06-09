---
id: US-ISO-0002
title: Role-based competence training & evidence
framework: iso27001
domain: [compliance, governance]
industries: [cross-industry, technology]
persona: compliance-officer
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_iso27001.md#competence
  - US-PLATFORM-0001
---

# US-ISO-0002 — Role-based competence training & evidence

## Story

> **As an** ISMS manager,
> **I want** to assign deeper, role-specific competence training (e.g. secure coding for
> developers, hardening for sysadmins, IR for the response team) and capture competence
> evidence,
> **so that** we satisfy Clause 7.2's requirement that personnel are **competent**, not
> merely aware.

## Context

Clause 7.2 goes beyond awareness: specific ISMS roles must be **competent** through
training. The framework doc adds `Course.training_type = competence` to distinguish these
from awareness courses, and reuses `Course.applicable_roles` for targeting. A passing,
attested, version-pinned completion is the competence evidence an auditor accepts.

## Acceptance criteria

1. **Given** competence courses tagged `training_type = competence` with `applicable_roles`,
   **when** the manager assigns them, **then** each role's population is targeted (devs,
   sysadmins, IR, internal auditors).
2. **Given** an assigned user, **when** they pass and attest, **then** the completion is
   recorded as competence evidence, version-pinned.
3. **Given** the awareness/competence distinction, **when** evidence is reported, **then**
   competence completions are distinguishable from awareness completions.
4. **Given** Annex A.6.4, **when** a trained user later violates policy, **then** the "was
   trained" evidence is available to support a defensible disciplinary process.

## Reuses (platform)

- Library + player + role targeting: [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md),
  [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Role-targeting pattern: [US-HIPAA-0004](../hipaa/US-HIPAA-0004-role-based-training-paths.md).

## Out of scope / notes

- The specific secure-coding curriculum (OWASP/ASVS) is a planned content item.

## Traceability

- Clause 7.2 competence: `framework_iso27001.md#competence`; disciplinary linkage
  `#disciplinary-process`.
