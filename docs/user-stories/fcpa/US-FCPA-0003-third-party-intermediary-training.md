---
id: US-FCPA-0003
title: Third-party / intermediary FCPA training & attestation
framework: fcpa
domain: [compliance, governance]
industries: [cross-industry]
persona: third-party-manager
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/02_resolved_decisions.md
  - docs/03_ai_drafted_human_approved_content.md
---

# US-FCPA-0003 — Third-party / intermediary FCPA training & attestation

## Story

> **As a** third-party / procurement manager,
> **I want** to require FCPA training and a written attestation from agents,
> distributors, consultants, and JV partners who act on our behalf,
> **so that** we can show due diligence over the intermediaries that are the
> single largest source of FCPA liability.

## Context

A company is liable for bribes paid by its third parties when it knew or should
have known. Regulators expect intermediaries to be risk-assessed, trained, and
made to **attest** that they understand and will comply. The challenge: third
parties are often *not* internal `User` accounts. This story covers extending
assignment/attestation to external recipients and capturing their attestation as
first-class audit evidence.

## Acceptance criteria

1. **Given** a third-party contact, **when** the manager enrolls them for FCPA
   training, **then** the recipient can complete the training and record an
   attestation without needing full internal-employee provisioning.
2. **Given** a completed third-party attestation, **when** it is recorded, **then**
   the audit log captures the party, the content version, timestamp, and the
   attestation text as tamper-evident evidence.
3. **Given** an intermediary who has not completed required training, **when** the
   manager views the third-party roster, **then** that party is flagged as a gap
   (and, per policy, can block onboarding/renewal).
4. **Given** an attestation on record, **when** an auditor requests third-party
   evidence, **then** it appears in the FCPA audit export (see US-FCPA-0006).

## Out of scope / notes

- Full third-party **due-diligence questionnaires / risk scoring** are a separate
  capability; this story is training + attestation only.
- External-recipient identity model (lightweight vs full account) is a design
  question to resolve with the identity domain.

## Traceability

- Attestation as audit evidence: `docs/02_resolved_decisions.md` (audit log).
- Separation-of-duties & approved content: `docs/03_…`, ADR-011.
