---
id: US-PCI-0002
title: Secure development training for developers
framework: pci-dss
domain: [compliance, regulatory]
industries: [technology, retail, financial-services]
persona: compliance-officer
priority: must
status: draft
also_satisfies: [iso27001]
traces_to:
  - docs/frameworks/framework_pci_dss.md#secure-development-training
  - US-ISO-0002
  - US-PLATFORM-0001
---

# US-PCI-0002 — Secure development training for developers

## Story

> **As a** security/compliance officer,
> **I want** to assign secure-development training to software-development personnel at
> least annually,
> **so that** we satisfy Requirement 6.2.2 and evidence that developers were trained on
> secure design and common vulnerabilities (OWASP Top 10).

## Context

Req 6.2.2 requires developers to be trained annually in secure software development relevant
to their role and languages — secure design, OWASP Top 10, and the secure-development tools
used. This is the **same course** as ISO 27001's developer competence (Clause 7.2), so a
single tagged course satisfies both via `also_satisfies`. Targeting is by developer role.

## Acceptance criteria

1. **Given** a secure-development course tagged for Req 6.2.2 with `applicable_roles =
   developer`, **when** the officer assigns it, **then** only development personnel are
   targeted.
2. **Given** an assigned developer, **when** they pass and attest, **then** completion is
   recorded as evidence, version-pinned, with annual cadence.
3. **Given** the ISO overlap, **when** a developer completes this course, **then** it is
   attributable to both PCI DSS and ISO 27001 competence (`also_satisfies`).

## Reuses (platform / cross-framework)

- Library + player + role targeting: [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md),
  [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Same course as [US-ISO-0002](../iso27001/US-ISO-0002-role-based-competence-training.md)
  (developer competence).

## Out of scope / notes

- The specific OWASP/ASVS curriculum is a content item; this story is the assignment +
  evidence requirement.

## Traceability

- Req 6.2.2: `framework_pci_dss.md#secure-development-training`.
