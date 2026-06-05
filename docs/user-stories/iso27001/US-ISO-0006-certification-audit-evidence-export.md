---
id: US-ISO-0006
title: Certification-audit evidence export (Annex A mapping)
framework: iso27001
domain: [compliance, governance]
industries: [cross-industry]
persona: auditor
priority: must
status: draft
also_satisfies: [sox, hipaa, gdpr, fcpa]
traces_to:
  - docs/frameworks/framework_iso27001.md#awareness-training-control
  - docs/02_resolved_decisions.md
  - US-HIPAA-0008
---

# US-ISO-0006 — Certification-audit evidence export (Annex A mapping)

## Story

> **As a** certification-body auditor,
> **I want** to export the ISMS training-evidence binder for in-scope personnel and period,
> **grouped by Annex A control**,
> **so that** I can sample personnel and confirm each control's awareness/competence
> training was completed — and see continual-improvement evidence.

## Context

ISO auditors request the ISMS scope, the awareness program documentation, a training matrix
(per-person, per-course, per-period), sample evidence packs, **continual-improvement
metrics**, and — most ISO-specific — the **Annex A control mapping** (which courses satisfy
which controls). This is the **same Auditor export** as the other frameworks, with an ISO
lens: group by `Course.annex_a_controls`.

## Acceptance criteria

1. **Given** an in-scope population and period, **when** the auditor runs the ISO export,
   **then** they receive, per person: assignments, attempts/scores, completion, the exact
   content version, certificate, and attestation.
2. **Given** the Annex A mapping, **when** the export renders, **then** evidence is groupable
   **by Annex A control** (e.g. all training satisfying A.6.3).
3. **Given** continual improvement, **when** requested, **then** completion/fail-rate and
   time-to-completion trends across periods are included.
4. **Given** an auditor account, **when** they access evidence, **then** access is read-only
   and itself logged.

## Reuses (platform / existing)

- Reuses the shared `Auditor` role + `/exports/*` endpoints — **no new surface** (Annex A
  grouping + metrics are an ISO view over the same data).
- Same capability as [US-HIPAA-0008](../hipaa/US-HIPAA-0008-ocr-evidence-export.md) /
  [US-SOX-0006](../sox/US-SOX-0006-auditor-404-evidence-binder.md) /
  [US-GDPR-0007](../gdpr/US-GDPR-0007-dpa-evidence-export.md) /
  [US-FCPA-0006](../fcpa/US-FCPA-0006-audit-evidence-export.md).

## Out of scope / notes

- The `TrainingMetric` aggregation job that powers trends is a shared platform enhancement
  (flagged in `framework_iso27001.md` §5).

## Traceability

- A.6.3 evidence, Annex A mapping, metrics: `framework_iso27001.md` §6.
