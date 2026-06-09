---
id: US-PCI-0007
title: Multi-method program coverage reporting
framework: pci-dss
domain: [compliance, regulatory]
industries: [retail, financial-services, cross-industry]
persona: compliance-officer
priority: should
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_pci_dss.md#security-awareness-program
  - US-PCI-0006
---

# US-PCI-0007 — Multi-method program coverage reporting

## Story

> **As a** security/compliance officer,
> **I want** the product to present its training as the **formal-training method** within a
> larger multi-method awareness program, not as the whole program,
> **so that** we accurately represent Req 12.6 coverage to a QSA and don't over-claim
> compliance from course completion alone.

## Context

PCI DSS v4.0 requires the awareness program to use **multiple methods** (posters, emails,
briefings, formal training). This product covers the **formal-training** leg only. This is a
PCI-distinctive *reporting* concern: dashboards and exports must frame completion as one
method, and let the officer reference the other methods so the program record is honest and
audit-defensible.

## Acceptance criteria

1. **Given** the PCI dashboard/export, **when** they render, **then** training completion is
   labelled as the **formal-training method** of a multi-method program — not full Req 12.6
   coverage.
2. **Given** the program record, **when** the officer documents it, **then** they can note the
   other methods in use (so a QSA sees the complete picture).
3. **Given** the export (US-PCI-0006), **when** produced, **then** it carries the same
   "one method of several" framing.

## Reuses (platform)

- Reporting/dashboard + export surfaces — **no new mechanism**; this is framing/labelling on
  the shared reporting, consistent with [US-PCI-0006](US-PCI-0006-qsa-evidence-export.md).

## Out of scope / notes

- Delivering the *other* methods (posters, emails) is out of product scope — this story is
  about not misrepresenting coverage.

## Traceability

- Req 12.6 multi-method: `framework_pci_dss.md#security-awareness-program`, §3.1.
