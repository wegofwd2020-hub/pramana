---
id: US-SOX-0006
title: External-auditor §404 evidence binder
framework: sox
domain: [compliance, regulatory, governance]
industries: [cross-industry]
persona: auditor
priority: must
status: draft
also_satisfies: [fcpa]
traces_to:
  - docs/frameworks/framework_sox.md#section-404
  - docs/frameworks/framework_sox.md#section-802
  - docs/02_resolved_decisions.md
---

# US-SOX-0006 — External-auditor §404 evidence binder

## Story

> **As an** external auditor (CPA firm) assessing §404 controls,
> **I want** to export the SOX training-evidence binder for the in-scope population
> and audit period,
> **so that** I can perform sample testing — "who was trained on what, when, did they
> pass?" — from the tamper-evident audit log, without trusting current state.

## Context

This is the canonical audit case the product exists for. §404 assessment requires the
auditor to obtain the population list, training matrix, sample evidence packages, and
the exception report — all sourced from the append-only audit log (so retired content
versions remain represented). It is the **same Auditor export capability** as
FCPA-0006; SOX is simply its first and primary consumer, so it carries
`also_satisfies: [fcpa]`.

## Acceptance criteria

1. **Given** an in-scope population and period, **when** the auditor runs the SOX
   export, **then** they receive per user: assignments, attempts/scores, completion
   status, the exact content version, certificate, and attestation.
2. **Given** §802 retention, **when** the export covers historical periods, **then**
   evidence is available for the full retention window (≥7 years).
3. **Given** an auditor account, **when** they access evidence, **then** access is
   read-only and itself logged (auditors cannot mutate records).
4. **Given** sample testing, **when** the auditor selects users, **then** a full
   per-user audit binder (PDF) is produced.

## Reuses (platform / existing)

- Reuses the shared `Auditor` role + export already specced for SOX in the API
  (`/exports/*`, `/exports/users/{id}/audit-binder`) — **no new surface**.
- Same capability as [US-FCPA-0006](../fcpa/US-FCPA-0006-audit-evidence-export.md).

## Out of scope / notes

- Framework-specific binder **templates** (SOX vs FCPA layout) are a later refinement.

## Traceability

- §404 assessment & §802 retention: `docs/frameworks/framework_sox.md#section-404`,
  `#section-802`.
- Audit log & Auditor role: `docs/02_resolved_decisions.md`.
