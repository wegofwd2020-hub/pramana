---
id: US-FCPA-0011
title: Board / audit-committee FCPA program dashboard
framework: fcpa
domain: [governance, compliance]
industries: [cross-industry]
persona: governance-board
priority: should
status: draft
also_satisfies: [sox]
traces_to:
  - docs/02_resolved_decisions.md
  - US-FCPA-0001
  - US-FCPA-0006
---

# US-FCPA-0011 — Board / audit-committee FCPA program dashboard

## Story

> **As a** board / audit-committee member,
> **I want** a high-level, read-only view of FCPA training-program health,
> **so that** I can exercise the **oversight** the governance pillar requires and
> attest that the board is informed — without access to individual records I
> shouldn't see.

## Context

FCPA sits at the **governance** layer too: boards and audit committees are expected
to oversee the compliance program, and DOJ guidance asks whether senior leadership
and the board are genuinely engaged. This story gives that audience a curated,
aggregate dashboard — coverage, overdue, blocked, third-party completion, trend over
time — distinct from the operational compliance-officer view and the granular
auditor export (US-FCPA-0006). It is **read-only and minimal-PII** by design.

## Acceptance criteria

1. **Given** a `governance-board` user, **when** they open the FCPA program
   dashboard, **then** they see aggregate metrics (completion %, overdue, blocked,
   third-party coverage, trend) for the organization — not individual learner PII.
2. **Given** the dashboard, **when** it renders, **then** figures are consistent with
   the underlying audit-sourced evidence (the same source as US-FCPA-0006), so the
   board view cannot diverge from what an auditor would find.
3. **Given** a board user, **when** they attempt to drill into an individual's record,
   **then** access is denied (or limited per role) and the attempt is logged.
4. **Given** a reporting period, **when** the board reviews the program, **then** the
   dashboard can be exported/snapshotted as minutes-ready evidence of oversight.

## Out of scope / notes

- This is **reporting/oversight only** — no assignment or content actions from this
  surface.
- Cross-framework board rollup (FCPA + SOX + …) is a natural extension once more
  frameworks exist; this story scopes the FCPA view.

## Traceability

- Roles & reporting: `docs/02_resolved_decisions.md`.
- Consistent evidence source: [US-FCPA-0006](US-FCPA-0006-audit-evidence-export.md).
