---
id: US-GDPR-0005
title: DPO program oversight & awareness monitoring
framework: gdpr
domain: [governance, compliance]
industries: [cross-industry]
persona: governance-board
priority: should
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_gdpr.md#data-protection-awareness
  - US-FCPA-0011
  - US-GDPR-0007
---

# US-GDPR-0005 — DPO program oversight & awareness monitoring

## Story

> **As a** Data Protection Officer,
> **I want** an aggregate, read-only view of training-program health,
> **so that** I can exercise my Article 39 duty to **monitor** awareness across processing
> staff and evidence that oversight to a supervisory authority.

## Context

Article 39(1)(b) makes the DPO responsible for monitoring staff awareness/training. That is
an **oversight** view — coverage, overdue, trend by processing population — distinct from
the operational DPO actions and the granular DPA export (US-GDPR-0007). It reuses the
board/oversight dashboard pattern introduced for FCPA (governance-board), with a DPO lens.

## Acceptance criteria

1. **Given** a `governance-board`/DPO user, **when** they open the GDPR program dashboard,
   **then** they see aggregate metrics (awareness coverage %, overdue, breach-training
   coverage, trend) without individual PII.
2. **Given** the dashboard, **when** it renders, **then** figures are consistent with the
   audit-sourced evidence behind US-GDPR-0007 (board view cannot diverge from the export).
3. **Given** a DPO user, **when** they attempt to drill into an individual's record,
   **then** access is limited per role and the attempt is logged.
4. **Given** an oversight period, **when** reviewed, **then** the dashboard can be
   snapshotted as evidence of DPO monitoring.

## Reuses (platform / cross-framework)

- Reuses the oversight-dashboard pattern from [US-FCPA-0011](../fcpa/US-FCPA-0011-board-program-dashboard.md).
- Consistent evidence source: [US-GDPR-0007](US-GDPR-0007-dpa-evidence-export.md).

## Out of scope / notes

- No assignment/content actions from this surface — reporting/oversight only.

## Traceability

- Article 39 DPO monitoring: `framework_gdpr.md#data-protection-awareness`, §6.
