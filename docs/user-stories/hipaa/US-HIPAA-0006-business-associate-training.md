---
id: US-HIPAA-0006
title: Business Associate training & attestation
framework: hipaa
domain: [compliance, governance]
industries: [healthcare]
persona: third-party-manager
priority: should
status: draft
also_satisfies: []
traces_to:
  - docs/frameworks/framework_hipaa.md#business-associates
  - US-FCPA-0003
  - US-PLATFORM-0002
---

# US-HIPAA-0006 — Business Associate training & attestation

## Story

> **As a** vendor / third-party manager,
> **I want** to require HIPAA training and a written attestation from Business
> Associates who handle PHI on our behalf,
> **so that** we evidence due diligence over BAs — whose mishandling of PHI is our
> exposure under the Business Associate Agreement.

## Context

Business Associates are bound by the Security Rule and a BAA, and a Covered Entity can be
exposed when a BA mishandles PHI. BAs are typically **external** (not internal `User`
accounts). This is the HIPAA instance of the third-party training + attestation pattern
already written for FCPA intermediaries (US-FCPA-0003) — same external-recipient
mechanism, HIPAA content.

## Acceptance criteria

1. **Given** a Business Associate contact, **when** the manager enrolls them, **then**
   the BA can complete HIPAA training and record an attestation without full internal
   provisioning.
2. **Given** a completed BA attestation, **when** recorded, **then** the audit log
   captures the party, content version, timestamp, and attestation text.
3. **Given** a BA who has not completed required training, **when** the manager views the
   BA roster, **then** the gap is flagged (and per policy can block onboarding/renewal).
4. **Given** a BA attestation, **when** OCR requests BA evidence, **then** it appears in
   the HIPAA evidence export (US-HIPAA-0008).

## Reuses (platform / cross-framework)

- External-recipient training + attestation: reuses the pattern from
  [US-FCPA-0003](../fcpa/US-FCPA-0003-third-party-intermediary-training.md).
- Player: [US-PLATFORM-0002](../platform/US-PLATFORM-0002-course-player.md).

## Out of scope / notes

- BAA contract lifecycle management is out of scope — this is training + attestation.

## Traceability

- Business Associates: `docs/frameworks/framework_hipaa.md#business-associates`.
