---
id: US-ISO-0007
title: Management-review oversight & continual-improvement dashboard
framework: iso27001
domain: [governance, compliance]
industries: [cross-industry]
persona: governance-board
priority: should
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_iso27001.md#awareness
  - US-FCPA-0011
  - US-ISO-0006
---

# US-ISO-0007 — Management-review oversight & continual-improvement dashboard

## Story

> **As** ISMS top management (governance / management-review attendee),
> **I want** an aggregate, read-only dashboard of training-program health and trends,
> **so that** I can review awareness/competence performance at the Clause 9.3 management
> review and evidence continual improvement to auditors.

## Context

ISO Clause 9.3 requires periodic **management review** of the ISMS, and Clause 10 requires
**continual improvement**. Training metrics — completion rate, fail rate, time-to-completion,
year-over-year trends — are exactly the inputs that review needs, presented as oversight (not
individual PII). This reuses the board/oversight dashboard pattern (FCPA-0011) with an ISO
continual-improvement lens.

## Acceptance criteria

1. **Given** a `governance-board`/management user, **when** they open the ISO dashboard,
   **then** they see aggregate metrics (awareness & competence coverage, fail rate,
   time-to-completion, trend) without individual PII.
2. **Given** continual improvement, **when** the dashboard renders, **then** it shows
   period-over-period trends suitable for the management-review record.
3. **Given** consistency, **when** figures are shown, **then** they match the audit-sourced
   export (US-ISO-0006) — the review view cannot diverge from auditor evidence.
4. **Given** a review cycle, **when** management reviews, **then** the dashboard can be
   snapshotted as Clause 9.3 evidence.

## Reuses (platform / cross-framework)

- Reuses the oversight-dashboard pattern from [US-FCPA-0011](../fcpa/US-FCPA-0011-board-program-dashboard.md).
- Consistent evidence source: [US-ISO-0006](US-ISO-0006-certification-audit-evidence-export.md).

## Out of scope / notes

- Reporting/oversight only — no assignment or content actions from this surface.

## Traceability

- Clause 9.3 management review / Clause 10 continual improvement: `framework_iso27001.md` §6,
  §3.3.
