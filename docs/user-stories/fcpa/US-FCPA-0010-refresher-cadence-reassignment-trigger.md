---
id: US-FCPA-0010
title: Annual refresher cadence + policy-change re-assignment trigger
framework: fcpa
domain: [compliance, regulatory]
industries: [cross-industry]
persona: compliance-officer
priority: must
status: draft
also_satisfies: [sox, hipaa]
traces_to:
  - docs/02_resolved_decisions.md      # cooldown_days, FR8
  - docs/frameworks/regulatory_frameworks_index.md
  - US-FCPA-0007
---

# US-FCPA-0010 — Annual refresher cadence + policy-change re-assignment trigger

## Story

> **As a** compliance officer,
> **I want** FCPA training to recur on a cadence and to re-issue automatically when
> the policy/content materially changes,
> **so that** training stays current and no one's certification silently lapses —
> the "ongoing" expectation regulators have of a living program.

## Context

FCPA programs are expected to be **continuous**, not one-and-done. Most frameworks
default to an **annual** cadence (per the frameworks overlap matrix), and material
changes (a policy update, a regulation change, a new content version) should trigger
**re-training** of the affected population. The product already has per-course
`cooldown_days`; this story turns that into proactive re-assignment and ties cadence
to the risk tiers from US-FCPA-0007.

## Acceptance criteria

1. **Given** a course with a configured cadence, **when** a user's certification
   reaches the cadence interval, **then** a refresher assignment is issued before
   expiry and the user/manager is notified.
2. **Given** risk tiers (US-FCPA-0007), **when** cadence is configured, **then** a
   higher-risk tier can carry a shorter interval than lower tiers.
3. **Given** a **materially** changed and newly-published FCPA content version,
   **when** it is published, **then** the affected trained population is flagged for
   re-assignment (and existing completion records remain pinned to the prior version).
4. **Given** automatic re-assignment runs, **when** it fires, **then** each
   re-assignment event is recorded in the audit log with its trigger (cadence vs
   policy-change).

## Out of scope / notes

- Defining what counts as a **material** change is a policy/authoring decision
  (the content-approval flow marks it); this story consumes that signal.
- Notification channels (email/in-app) follow the platform's existing mechanisms.

## Traceability

- Cooldown / re-assignment (FR8): `docs/02_resolved_decisions.md`.
- Annual cadence norm across frameworks: `docs/frameworks/regulatory_frameworks_index.md` §5.2.
- Tier-driven cadence: [US-FCPA-0007](US-FCPA-0007-high-risk-geography-targeting.md).
