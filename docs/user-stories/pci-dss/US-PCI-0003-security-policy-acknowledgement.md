---
id: US-PCI-0003
title: Security-policy acknowledgement
framework: pci-dss
domain: [compliance]
industries: [retail, financial-services, cross-industry]
persona: employee
priority: should
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_pci_dss.md#acknowledgement
  - US-PLATFORM-0002
---

# US-PCI-0003 — Security-policy acknowledgement

## Story

> **As an** employee with CDE access,
> **I want** to acknowledge that I have read and understood the security policy as part of my
> training,
> **so that** the company has the Requirement 12.8 acknowledgement evidence a QSA expects.

## Context

Req 12.8 requires personnel to acknowledge the security policy. The product's existing
attestation mechanism satisfies this — the value is capturing the acknowledgement as
first-class, version-pinned audit evidence tied to the 12.6 training. No new mechanism; this
is the PCI framing of the attestation step the player already supports.

## Acceptance criteria

1. **Given** the security-policy module, **when** the employee completes it, **then** they
   must record an explicit **acknowledgement** to finish.
2. **Given** a recorded acknowledgement, **when** it is saved, **then** the audit log
   captures the employee, the exact policy/content version, and the timestamp.
3. **Given** the annual cadence, **when** a year elapses, **then** re-acknowledgement is
   required (reuses the platform cadence trigger).
4. **Given** an employee who has not acknowledged, **when** the officer reviews coverage,
   **then** the gap is visible in the PCI dashboard.

## Reuses (platform)

- Player + attestation capture: [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).
- Cadence: [US-PCI-0004](US-PCI-0004-cde-cadence-retraining.md).

## Out of scope / notes

- Acknowledgement is reused across frameworks (mirrors SOX-0002 / FCPA-0008 attestations);
  PCI maps it to Req 12.8.

## Traceability

- Req 12.8 acknowledgement: `framework_pci_dss.md#acknowledgement`.
