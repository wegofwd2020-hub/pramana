---
id: US-ISO-0004
title: Surveillance-cycle cadence & post-incident retraining
framework: iso27001
domain: [compliance, governance]
industries: [cross-industry]
persona: compliance-officer
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_iso27001.md#awareness
  - US-HIPAA-0005
  - US-FCPA-0010
---

# US-ISO-0004 — Surveillance-cycle cadence & post-incident retraining

## Story

> **As an** ISMS manager,
> **I want** awareness training to recur at least annually (aligned to the surveillance
> cycle), on-hire, and after a security incident or significant change,
> **so that** awareness stays current across the certification cycle and we evidence
> ongoing (not one-time) training to surveillance auditors.

## Context

Certification involves annual **surveillance audits** and a 3-yearly recertification; ISO
expects awareness to be ongoing, with mandatory on-hire training and re-training after
incidents or significant changes. The platform owns the trigger/cadence engine; this story
supplies the ISO cadence rules and the post-incident trigger.

## Acceptance criteria

1. **Given** a configured cadence, **when** a user's awareness certification reaches the
   interval (≥ annual), **then** a refresher is issued before expiry and the user/manager is
   notified.
2. **Given** an `on_hire` trigger, **when** an in-scope person is created, **then** required
   awareness training is auto-assigned.
3. **Given** a security incident or significant change, **when** the manager triggers
   retraining, **then** the affected population is re-assigned (existing completions stay
   pinned).
4. **Given** any auto-assignment, **when** it fires, **then** the trigger type is recorded in
   the audit log.

## Reuses (platform / cross-framework)

- Trigger/cadence engine shared with [US-HIPAA-0005](../hipaa/US-HIPAA-0005-onhire-policy-change-triggers.md)
  and [US-FCPA-0010](../fcpa/US-FCPA-0010-refresher-cadence-reassignment-trigger.md).

## Out of scope / notes

- Incident-management integration that emits "incident" events is upstream; this consumes it.

## Traceability

- Cadence expectations: `framework_iso27001.md` §3.3; Clause 7.3 `#awareness`.
