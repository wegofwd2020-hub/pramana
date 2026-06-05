---
id: US-FCPA-0004
title: Books & records / internal-controls training (accounting pillar)
framework: fcpa
domain: [compliance, regulatory]
industries: [cross-industry, financial-services]
persona: employee
priority: should
status: draft
also_satisfies: [sox]
traces_to:
  - docs/frameworks/framework_sox.md
  - docs/03_ai_drafted_human_approved_content.md
---

# US-FCPA-0004 — Books & records / internal-controls training (accounting pillar)

## Story

> **As an** employee in finance, accounting, or expense-approval roles,
> **I want** training on FCPA's books-and-records and internal-controls
> requirements,
> **so that** I record transactions accurately and recognise the red flags
> (off-book funds, mischaracterized expenses) that signal concealed bribery.

## Context

FCPA's *second* pillar — the accounting provisions — applies to issuers and
requires accurate books in reasonable detail plus a system of internal accounting
controls. It overlaps strongly with **SOX** §§302/404, so a single well-designed
module can satisfy both (build once for the stricter requirement). This story
targets the finance population specifically, distinct from the broad anti-bribery
assignment.

## Acceptance criteria

1. **Given** the accounting-pillar module, **when** it is assigned to finance/
   expense-approver roles, **then** completion is tracked the same way as any other
   FCPA course and counts toward both FCPA and SOX training evidence.
2. **Given** a story tagged `also_satisfies: [sox]`, **when** a compliance officer
   reviews coverage, **then** the same completion record is attributable to both
   frameworks without double-assigning the learner.
3. **Given** the module includes red-flag recognition, **when** the learner is
   assessed, **then** questions test identification of mischaracterized-expense and
   off-book-funds scenarios.

## Out of scope / notes

- This is training only — it does not implement the *financial controls themselves*
  (that's the SOX controls domain).
- Cross-framework credit mechanics (one completion → two frameworks) may need a
  data-model decision; flagged here, resolved in the assignment/reporting design.

## Traceability

- SOX overlap & controls context: `docs/frameworks/framework_sox.md`.
- Approved, version-pinned content: `docs/03_…`, ADR-011.
