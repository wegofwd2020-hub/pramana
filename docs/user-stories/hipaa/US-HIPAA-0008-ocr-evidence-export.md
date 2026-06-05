---
id: US-HIPAA-0008
title: HIPAA training-evidence export for OCR
framework: hipaa
domain: [compliance, regulatory, governance]
industries: [healthcare]
persona: auditor
priority: must
status: draft
also_satisfies: [sox, fcpa]
traces_to:
  - docs/frameworks/framework_hipaa.md
  - docs/02_resolved_decisions.md
  - US-SOX-0006
---

# US-HIPAA-0008 — HIPAA training-evidence export for OCR

## Story

> **As an** auditor (or HHS OCR investigator via export),
> **I want** to export the HIPAA training-evidence binder for the workforce and period,
> including PHI-access classification and role tailoring,
> **so that** I can answer "was the workforce trained on the right topics, when?" from
> the tamper-evident audit log — on OCR's 30–60 day timeline.

## Context

OCR audits and breach investigations request the workforce roster (with PHI access),
training-program documentation, completion records, and the material-change log. This is
the **same Auditor export capability** as SOX-0006 / FCPA-0006, with HIPAA-specific
columns (PHI access, role path). It must support **point-in-time** queries (status of a
user on a past date), so retired versions remain represented.

## Acceptance criteria

1. **Given** a workforce population and period, **when** the auditor runs the HIPAA
   export, **then** they receive, per member: PHI-access level, role path, assignments,
   attempts/scores, completion, the exact content version, certificate, and attestation.
2. **Given** OCR's point-in-time need, **when** a historical date is queried, **then** the
   export reports each member's training status **as of that date**.
3. **Given** an auditor account, **when** they access evidence, **then** access is
   read-only and itself logged.
4. **Given** a request, **when** the export completes, **then** it is available as a
   structured file (CSV/PDF) suitable for an OCR submission.

## Reuses (platform / existing)

- Reuses the shared `Auditor` role + `/exports/*` endpoints — **no new surface**.
- Same capability as [US-SOX-0006](../sox/US-SOX-0006-auditor-404-evidence-binder.md) /
  [US-FCPA-0006](../fcpa/US-FCPA-0006-audit-evidence-export.md).

## Out of scope / notes

- The **point-in-time** query capability is a shared platform enhancement (flagged in
  `framework_hipaa.md` §10) — this story depends on it.
- HIPAA-format binder template is a later refinement on the shared export.

## Traceability

- OCR evidence asks & retention: `framework_hipaa.md` §6–§7.
- Audit log & Auditor role: `docs/02_resolved_decisions.md`.
