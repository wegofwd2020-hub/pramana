---
id: US-FCPA-0008
title: Facilitation-payment policy attestation
framework: fcpa
domain: [compliance]
industries: [cross-industry]
persona: employee
priority: should
status: draft
also_satisfies: []
traces_to:
  - docs/02_resolved_decisions.md
  - docs/03_ai_drafted_human_approved_content.md
---

# US-FCPA-0008 — Facilitation-payment policy attestation

## Story

> **As an** employee in a role that interacts with officials, customs, or permits,
> **I want** to be trained on the company's facilitation-payment position and to
> attest that I understand it,
> **so that** there is a record I was told the company prohibits "grease payments"
> even where a narrow statutory exception might exist.

## Context

The FCPA has a narrow exception for *facilitating or expediting* routine
governmental action, but most companies prohibit such payments outright by policy
because the exception is easy to misjudge and not recognised in most other
jurisdictions' anti-bribery laws. The point of this story is the explicit
**attestation**: capturing that the employee was informed of the company's stricter
position, as defensible evidence.

## Acceptance criteria

1. **Given** the facilitation-payment module, **when** the employee completes it,
   **then** they are presented with the company's policy statement and must record
   an explicit attestation to proceed.
2. **Given** a recorded attestation, **when** it is saved, **then** the audit log
   captures the employee, the exact policy/content version attested to, and the
   timestamp.
3. **Given** an employee who has not attested, **when** the compliance officer
   reviews coverage, **then** the gap is visible alongside other FCPA training gaps.
4. **Given** the policy text changes, **when** a new content version is approved and
   published, **then** prior attestations remain pinned to the version actually
   attested (and re-attestation can be required — see US-FCPA-0010).

## Out of scope / notes

- This story does not implement a payment-approval workflow; it is awareness +
  attestation only.

## Traceability

- Attestation as evidence & version pinning: `docs/02_resolved_decisions.md`.
- Approved, version-pinned policy content: `docs/03_…`.
