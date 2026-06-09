---
id: US-FCPA-0007
title: High-risk geography & role risk-tier targeting
framework: fcpa
domain: [compliance, regulatory]
industries: [cross-industry]
persona: compliance-officer
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/02_resolved_decisions.md
  - US-FCPA-0001
---

# US-FCPA-0007 — High-risk geography & role risk-tier targeting

## Story

> **As a** compliance officer,
> **I want** to assign FCPA training intensity based on each employee's
> geography and role risk tier,
> **so that** high-exposure staff (government-facing roles, high-risk markets) get
> deeper, more frequent training while low-risk staff aren't over-burdened — the
> risk-based approach regulators expect.

## Context

DOJ guidance explicitly rewards **risk-based** programs over one-size-fits-all
training. FCPA exposure varies sharply by country (e.g. corruption-perception
indices, prevalence of state-owned enterprises) and by role (sales, customs,
licensing, government affairs). This story builds the targeting layer on top of the
core assignment flow (US-FCPA-0001): tag the population by risk tier and drive
*which* course variant and *what* cadence each tier receives.

## Acceptance criteria

1. **Given** users carry a geography and role attribute, **when** the compliance
   officer defines risk tiers (e.g. low/medium/high) with mapping rules, **then**
   each user resolves to a tier deterministically and the mapping is auditable.
2. **Given** risk tiers exist, **when** the officer assigns FCPA training, **then**
   they can target by tier (e.g. "all high-risk") rather than enumerating users.
3. **Given** a high-risk tier, **when** training is assigned, **then** the tier can
   carry a stricter cadence/threshold than lower tiers (feeds US-FCPA-0010).
4. **Given** a user whose geography or role changes tier, **when** the change is
   recorded, **then** the officer is notified that their training requirement may
   need re-evaluation.

## Out of scope / notes

- The **risk-scoring methodology** (which countries are "high") is a policy/content
  input maintained by compliance, not hard-coded logic.
- Automatic re-assignment on tier change is covered by US-FCPA-0010.

## Traceability

- Assignment targeting & user attributes: `docs/02_resolved_decisions.md`.
- Builds on core assignment: [US-FCPA-0001](US-FCPA-0001-anti-bribery-training-assignment.md).
