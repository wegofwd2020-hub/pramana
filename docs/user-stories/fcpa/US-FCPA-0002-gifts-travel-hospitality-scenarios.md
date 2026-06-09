---
id: US-FCPA-0002
title: Gifts, travel & hospitality scenario assessment
framework: fcpa
domain: [compliance]
industries: [cross-industry]
persona: employee
priority: must
status: draft
also_satisfies: []
traces_to:
  - docs/03_ai_drafted_human_approved_content.md
---

# US-FCPA-0002 — Gifts, travel & hospitality scenario assessment

## Story

> **As an** employee in a customer-facing or government-touching role,
> **I want** to work through realistic gifts/travel/hospitality (G&H) scenarios and
> answer judgment questions,
> **so that** I can recognise where a courtesy becomes an improper benefit and act
> within policy.

## Context

G&H is where well-meaning employees most often stumble into FCPA exposure — a
lavish dinner, business-class flights for a regulator, a "customary" gift in a
local market. Rote rules don't transfer to the field; **scenario-based** assessment
does. The product already supports quizzes with a pass threshold; this story is
about FCPA-specific G&H content (scenarios + decision questions) delivered through
that mechanism.

## Acceptance criteria

1. **Given** the G&H module, **when** the employee takes the assessment, **then**
   each question presents a concrete scenario and the system scores their selected
   judgment against the approved answer key.
2. **Given** an employee who selects an answer that reflects a policy violation,
   **when** they submit, **then** the result records the miss for remediation
   (feedback shown per the course's review settings) without revealing the key
   in a way that lets them game a retake.
3. **Given** a completed assessment at or above threshold, **when** scoring
   finalizes, **then** completion counts toward the employee's FCPA training record.
4. **Given** content updated with a new scenario, **when** a new content version is
   approved and published, **then** existing completion records remain pinned to the
   version the employee actually answered (no silent rewrite).

## Out of scope / notes

- The *content* (specific scenarios, thresholds) is authored upstream and must be
  human-approved before assignment — see US-FCPA-0005.
- Localized thresholds per market are a future content concern, not a system change.

## Traceability

- Quiz/attempt scoring & version pinning: `docs/02_resolved_decisions.md`.
- Content provenance & approval: `docs/03_…`, ADR-011.
