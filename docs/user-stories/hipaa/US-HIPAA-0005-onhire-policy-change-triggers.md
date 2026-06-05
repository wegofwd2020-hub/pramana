---
id: US-HIPAA-0005
title: On-hire & material-change training triggers
framework: hipaa
domain: [compliance, regulatory]
industries: [healthcare]
persona: compliance-officer
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_hipaa.md#privacy-rule
  - US-FCPA-0009
  - US-PLATFORM-0001
---

# US-HIPAA-0005 — On-hire & material-change training triggers

## Story

> **As a** Privacy Officer,
> **I want** HIPAA training to be auto-assigned when a workforce member is hired and
> re-assigned when PHI policies materially change,
> **so that** we meet §164.530(b)(2)'s "within a reasonable time of hire" and
> "after material change" duties without relying on someone to remember.

## Context

HIPAA is unusual in **mandating** training on specific events: new hire and material
policy change (plus periodic refresh). The framework doc proposes an `AssignmentTrigger`
engine (`on_hire`, `on_role_change`, `on_policy_update`, `periodic`) and a
`CourseVersion.is_material_change` flag. This generalizes the FCPA M&A trigger; the
platform owns the trigger mechanism, this story supplies the HIPAA trigger rules and
timeliness.

## Acceptance criteria

1. **Given** a configured `on_hire` trigger, **when** a workforce member is created in a
   role, **then** their required HIPAA courses are auto-assigned with a due date that
   reflects "reasonable time after hire."
2. **Given** a published `CourseVersion` flagged `is_material_change`, **when** it
   publishes, **then** the affected in-scope population is re-assigned the new version
   (existing completions stay pinned to the prior version — no history rewrite).
3. **Given** a role / PHI-access change (US-HIPAA-0004), **when** it occurs, **then** the
   member's required-training delta is auto-assigned.
4. **Given** any auto-assignment, **when** it fires, **then** the trigger type is recorded
   in the audit log.

## Reuses (platform)

- Assignment + library surfaces: [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md).
- Trigger pattern generalizes [US-FCPA-0009](../fcpa/US-FCPA-0009-ma-successor-liability-trigger.md);
  cadence shared with [US-FCPA-0010](../fcpa/US-FCPA-0010-refresher-cadence-reassignment-trigger.md).

## Out of scope / notes

- The HRIS integration that emits "hire"/"role-change" events is upstream; this story
  consumes those events.

## Traceability

- §164.530(b)(2) timeliness: `framework_hipaa.md` §3.1, `#privacy-rule`.
