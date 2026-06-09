---
id: US-PCI-0004
title: On-hire & annual cadence + material-change retraining
framework: pci-dss
domain: [compliance, regulatory]
industries: [retail, financial-services, cross-industry]
persona: compliance-officer
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_pci_dss.md#security-awareness-program
  - US-HIPAA-0005
  - US-ISO-0004
---

# US-PCI-0004 — On-hire & annual cadence + material-change retraining

## Story

> **As a** security/compliance officer,
> **I want** CDE security awareness training auto-assigned on hire, re-issued at least
> annually, and re-triggered when the threat environment or policy changes materially,
> **so that** Requirement 12.6's on-hire / annual / on-change cadence is met without manual
> tracking.

## Context

Req 12.6 explicitly mandates training on hire, at least annually, and when the threat
environment or policy changes materially. The platform owns the trigger/cadence engine
(shared with HIPAA and ISO); this story supplies the PCI cadence rules scoped to CDE-access
personnel.

## Acceptance criteria

1. **Given** an `on_hire` trigger, **when** a CDE-access person is created, **then** their
   required 12.6 training is auto-assigned with a due date.
2. **Given** a configured annual cadence, **when** a user's certification reaches 12 months,
   **then** a refresher is issued before expiry and the user/manager is notified.
3. **Given** a material threat/policy change (published as a material content version), **when**
   it publishes, **then** the CDE-access population is re-assigned (existing completions stay
   pinned).
4. **Given** any auto-assignment, **when** it fires, **then** the trigger type is recorded in
   the audit log.

## Reuses (platform / cross-framework)

- Trigger/cadence engine shared with [US-HIPAA-0005](../hipaa/US-HIPAA-0005-onhire-policy-change-triggers.md)
  and [US-ISO-0004](../iso27001/US-ISO-0004-surveillance-cadence-retraining.md).

## Out of scope / notes

- HRIS / threat-intel feeds that emit "hire" / "material change" events are upstream.

## Traceability

- Req 12.6 cadence: `framework_pci_dss.md#security-awareness-program`, §3.1.
