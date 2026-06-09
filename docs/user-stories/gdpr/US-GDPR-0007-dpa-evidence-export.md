---
id: US-GDPR-0007
title: GDPR training-evidence export for a DPA
framework: gdpr
domain: [compliance, regulatory, governance]
industries: [cross-industry]
persona: auditor
priority: must
status: draft
also_satisfies: [sox, fcpa, hipaa]
traces_to:
  - docs/frameworks/framework_gdpr.md
  - docs/02_resolved_decisions.md
  - US-HIPAA-0008
---

# US-GDPR-0007 — GDPR training-evidence export for a DPA

## Story

> **As an** auditor (or supervisory-authority / DPA reviewer via export),
> **I want** to export the GDPR training-evidence binder for processing staff and period,
> **so that** I can demonstrate **accountability** (Article 5(2)) — documented, periodic
> awareness training and DPO oversight — from the tamper-evident audit log.

## Context

DPAs investigating after a breach or in an accountability review request training-program
documentation, completion records, DSR logs, and evidence of DPO oversight. This is the
**same Auditor export capability** as SOX-0006 / HIPAA-0008 / FCPA-0006, with GDPR-specific
emphasis (accountability narrative, processing-staff scope). Pseudonymized users appear
with redacted PII but retained evidence (US-GDPR-0004).

## Acceptance criteria

1. **Given** a processing-staff population and period, **when** the auditor runs the GDPR
   export, **then** they receive, per member: assignments, attempts/scores, completion, the
   exact content version, certificate, and attestation — with PII redacted for pseudonymized
   users.
2. **Given** the accountability ask, **when** the export is produced, **then** it includes
   the program documentation and DPO-oversight evidence (ties to US-GDPR-0005).
3. **Given** an auditor account, **when** they access evidence, **then** access is read-only
   and itself logged.
4. **Given** a request, **when** the export completes, **then** it is a structured file
   (CSV/PDF) suitable for a DPA submission.

## Reuses (platform / existing)

- Reuses the shared `Auditor` role + `/exports/*` endpoints — **no new surface**.
- Same capability as [US-HIPAA-0008](../hipaa/US-HIPAA-0008-ocr-evidence-export.md) /
  [US-SOX-0006](../sox/US-SOX-0006-auditor-404-evidence-binder.md) /
  [US-FCPA-0006](../fcpa/US-FCPA-0006-audit-evidence-export.md).

## Out of scope / notes

- DPA-format binder template is a later refinement on the shared export.

## Traceability

- Accountability evidence asks: `framework_gdpr.md` §6; redaction: [US-GDPR-0004](US-GDPR-0004-trainee-erasure-pseudonymization.md).
