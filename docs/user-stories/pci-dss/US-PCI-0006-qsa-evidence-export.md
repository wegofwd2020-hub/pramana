---
id: US-PCI-0006
title: QSA / RoC-SAQ evidence export
framework: pci-dss
domain: [compliance, regulatory]
industries: [retail, financial-services, cross-industry]
persona: auditor
priority: must
status: draft
also_satisfies: [sox, hipaa, gdpr, iso27001, fcpa]
traces_to:
  - docs/frameworks/framework_pci_dss.md#security-awareness-program
  - docs/02_resolved_decisions.md
  - US-ISO-0006
---

# US-PCI-0006 — QSA / RoC-SAQ evidence export

## Story

> **As a** QSA (or internal assessor preparing an SAQ),
> **I want** to export the PCI training-evidence binder for CDE personnel and period, mapped
> to the relevant PCI requirements,
> **so that** I can complete the Report on Compliance / SAQ sections for Req 12.6 and 6.2.2
> from the tamper-evident audit log.

## Context

QSAs/acquirers request the CDE personnel roster, awareness-program documentation, per-person
completion, acknowledgement records, secure-development training records (Req 6.2.2), and a
program change log — and the RoC/SAQ has specific sections these must map to. This is the
**same Auditor export** as every other framework's evidence story, with a PCI lens: group by
`Course.pci_requirements` and align to RoC/SAQ sections.

## Acceptance criteria

1. **Given** a CDE population and period, **when** the assessor runs the PCI export, **then**
   they receive, per person: assignments, attempts/scores, completion, the exact content
   version, certificate, and acknowledgement.
2. **Given** the requirement mapping, **when** the export renders, **then** evidence is
   groupable by PCI requirement (12.6 awareness; 6.2.2 secure development) and aligned to
   RoC/SAQ sections.
3. **Given** the multi-method context, **when** the export is produced, **then** it is labelled
   as the **formal-training** evidence (one method), per US-PCI-0007.
4. **Given** an assessor account, **when** they access evidence, **then** access is read-only
   and itself logged.

## Reuses (platform / existing)

- Reuses the shared `Auditor` role + `/exports/*` endpoints — **no new surface** (PCI
  requirement grouping + RoC/SAQ alignment is a view over the same data).
- Same capability as [US-ISO-0006](../iso27001/US-ISO-0006-certification-audit-evidence-export.md) /
  [US-HIPAA-0008](../hipaa/US-HIPAA-0008-ocr-evidence-export.md) /
  [US-SOX-0006](../sox/US-SOX-0006-auditor-404-evidence-binder.md) /
  [US-GDPR-0007](../gdpr/US-GDPR-0007-dpa-evidence-export.md) /
  [US-FCPA-0006](../fcpa/US-FCPA-0006-audit-evidence-export.md).

## Out of scope / notes

- RoC/SAQ section-specific **template** is a later refinement on the shared export.

## Traceability

- Req 12.6 / 6.2.2 evidence & RoC/SAQ mapping: `framework_pci_dss.md` §6.
