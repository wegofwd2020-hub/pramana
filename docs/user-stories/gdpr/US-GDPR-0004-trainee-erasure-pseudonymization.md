---
id: US-GDPR-0004
title: Trainee right-to-erasure (pseudonymization)
framework: gdpr
domain: [compliance, regulatory, governance]
industries: [cross-industry]
persona: compliance-officer
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_gdpr.md#right-to-erasure
  - docs/api/openapi.yaml            # POST /users/{user_id}/pseudonymize
  - pramana/db/models/identity.py    # User.pseudonymized_at
---

# US-GDPR-0004 — Trainee right-to-erasure (pseudonymization)

## Story

> **As a** Data Protection Officer (compliance officer) handling an erasure request,
> **I want** to pseudonymize a workforce member's personal data while **retaining** the
> administrative training-evidence records,
> **so that** I honour the Article 17 erasure right without breaching the SOX/HIPAA
> retention obligations the same records are subject to.

## Context

This is the GDPR property no other framework has: **GDPR applies to the training data
itself.** A trainee is also a data subject and can request erasure, which collides head-on
with multi-year retention. The v1 model already resolved this — pseudonymize PII
(`email`, names), keep evidence rows linked to the immutable `user_id` — relying on
Article 17(3)(b) (retention required by law). This story **reuses the existing
`POST /users/{id}/pseudonymize` endpoint** as the GDPR erasure fulfilment; no new
mechanism is built.

## Acceptance criteria

1. **Given** an erasure request for a workforce member, **when** the DPO fulfils it,
   **then** the user's PII is pseudonymized (`status = pseudonymized`,
   `pseudonymized_at` set) while assignments, attempts, certificates, and audit rows are
   **retained** under the immutable `user_id`.
2. **Given** a pseudonymized user, **when** their training history is viewed or exported,
   **then** PII is redacted (e.g. display name shows `[redacted]`) but the evidence remains
   for audit.
3. **Given** the legal basis, **when** erasure is fulfilled, **then** the audit log records
   the request, the Article 17(3)(b) retention basis, and the actor.
4. **Given** retention has fully elapsed (≥7 years, the stricter SOX standard), **when**
   sweeping occurs, **then** even administrative records may be deleted.

## Reuses (platform / existing)

- **Existing endpoint** `POST /users/{user_id}/pseudonymize` and the `User.pseudonymized_at`
  model field — **no new surface built**.
- The same pseudonymization pattern that resolves the SOX/HIPAA retention tension.

## Out of scope / notes

- General DSR intake/SLA tracking (`DataSubjectRequest`) is a separate planned capability;
  this story is specifically the **erasure fulfilment** for training data.

## Traceability

- Article 17 + 17(3)(b): `framework_gdpr.md#right-to-erasure`, §7 retention resolution.
- Implementation hooks: `POST /users/{id}/pseudonymize`, `pramana/db/models/identity.py`.
