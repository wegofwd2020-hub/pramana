---
id: US-FCPA-0006
title: FCPA audit-evidence export for a regulator/auditor
framework: fcpa
domain: [compliance, regulatory, governance]
industries: [cross-industry]
persona: auditor
priority: must
status: draft
also_satisfies: [sox, hipaa, gdpr, iso27001, pci-dss]
traces_to:
  - docs/02_resolved_decisions.md
  - docs/frameworks/regulatory_frameworks_index.md
---

# US-FCPA-0006 — FCPA audit-evidence export for a regulator/auditor

## Story

> **As an** auditor (internal, external, or a regulator with read access),
> **I want** to export a complete FCPA training-evidence binder for a defined
> population and period,
> **so that** I can answer "who was trained on what, when, and did they pass?"
> without trusting the current state — backed by the tamper-evident audit log.

## Context

When the DOJ or SEC evaluates a compliance program, training is only as good as the
**evidence** of it. The product's append-only, hash-chained audit log already tells
the *history* (not just current state); this story exposes it as an FCPA-scoped,
exportable binder. A single `Auditor` role with read + export covers FCPA and the
other frameworks (per the frameworks index), so this capability is broadly shared.

## Acceptance criteria

1. **Given** a population and date range, **when** the auditor runs an FCPA evidence
   export, **then** they receive, per user: assignments, attempts/scores, completion
   status, the **exact content version** trained on, certificate, and attestation.
2. **Given** the export, **when** it is produced, **then** it draws from the
   append-only audit log (history), so retired/superseded content versions are still
   represented for users trained on them.
3. **Given** an auditor account, **when** they access evidence, **then** their access
   is itself read-only and logged (auditors cannot mutate records).
4. **Given** a request, **when** the export completes, **then** it is available as a
   structured file (CSV/PDF) suitable for an audit binder.

## Out of scope / notes

- Framework-specific binder *templates* (FCPA vs SOX layout) are a later refinement;
  v1 is a single export covered by the shared `Auditor` role.
- Real-time regulator portals are out of scope — export-on-demand only.

## Traceability

- Audit log (append-only, hash chain) & Auditor role: `docs/02_resolved_decisions.md`.
- Shared auditor access across frameworks: `docs/frameworks/regulatory_frameworks_index.md` §5.4.
