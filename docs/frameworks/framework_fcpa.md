# Framework Reference: FCPA (Foreign Corrupt Practices Act)

**Status:** 🚧 Candidate (first GRC framework with a user-story backlog — see `docs/user-stories/fcpa/`)
**Jurisdiction:** United States (extraterritorial reach)
**Primary regulator:** Department of Justice (DOJ — criminal, anti-bribery) and Securities and Exchange Commission (SEC — civil, accounting provisions)

> ⚠️ **Disclaimer:** This is an engineering reference, not legal advice. Confirm framework interpretation with the customer's compliance counsel before treating any of this as binding. Authoritative guidance: the DOJ/SEC *FCPA Resource Guide (2nd ed., 2020)* and the DOJ *Evaluation of Corporate Compliance Programs*.

---

## 1. Framework Overview

The **Foreign Corrupt Practices Act of 1977** (amended 1988 and 1998) is a US federal law enacted after the discovery of widespread foreign bribery by US companies. It has **two distinct pillars**, jointly enforced by the **DOJ** (criminal) and the **SEC** (civil). It reaches **issuers** (companies with securities registered with, or required to file reports with, the SEC), **domestic concerns** (US persons and businesses), and certain **foreign persons/agents** acting within US territory — and it makes a company liable for the corrupt acts of its **third-party intermediaries**.

The statute does not contain an explicit "training requirement." The training obligation emerges from the regulators' definition of an **effective compliance program**: the FCPA Resource Guide and DOJ's compliance-program guidance treat **risk-based training**, **third-party management**, **certifications/attestations**, and **M&A due diligence** as hallmarks a prosecutor weighs when deciding whether to charge and how to resolve a matter.

The two pillars — the clauses the rest of this document and the FCPA user stories cite:

### Anti-bribery

Prohibits offering, promising, paying, or authorizing **anything of value** to a **foreign official** (including employees of state-owned enterprises and, in practice, their relatives/agents) **corruptly**, to **obtain or retain business** or secure an improper advantage. Liability extends to payments made **through third parties** under a "knew or should have known" standard. Narrow carve-outs exist — a **facilitating-payments** exception for routine governmental action, and affirmative defenses for payments lawful under the **written** local law or *bona fide* reasonable promotional expenses — but most companies prohibit facilitation payments by policy because the exception is easy to misjudge.

### Books and records

Applies to **issuers**: maintain books, records, and accounts that, **in reasonable detail, accurately and fairly reflect** transactions and dispositions of assets. Its purpose is to make concealed bribery (off-book funds, mischaracterized expenses) detectable. This overlaps heavily with **SOX** §§302/404.

### Internal controls

Applies to **issuers**: devise and maintain a system of **internal accounting controls** sufficient to provide **reasonable assurance** that transactions are authorized and recorded as needed to permit preparation of conformant financial statements and to maintain accountability for assets. Again, strong overlap with SOX 404.

---

## 2. Why It Matters for Compliance Training Systems

When the DOJ or SEC evaluates a company (during an investigation or a self-disclosure), training is judged by its **evidence**, not its existence. Regulators ask:

- Was training **risk-based** — deeper and more frequent for high-exposure roles and geographies, not a blanket click-through?
- Were **third parties / intermediaries** (the single largest source of FCPA enforcement) trained and made to **attest**?
- Did each in-scope person actually complete the training, and is the completion record **tamper-evident**?
- After an **acquisition**, was the acquired population promptly trained (successor liability)?

A program that can't produce this evidence weakens the company's position in a declination or settlement negotiation and can affect penalty size and the imposition of a monitor.

---

## 3. Training Requirements Imposed by FCPA

Not statutory, but expected of an effective program. Common FCPA-relevant training (mapped to the FCPA user-story backlog):

- **Anti-bribery fundamentals** — foreign officials, "anything of value", obtain/retain business ([US-FCPA-0001](../user-stories/fcpa/US-FCPA-0001-anti-bribery-training-assignment.md)).
- **Gifts, travel & hospitality** — scenario-based judgement ([US-FCPA-0002](../user-stories/fcpa/US-FCPA-0002-gifts-travel-hospitality-scenarios.md)).
- **Third-party / intermediary risk** + attestation ([US-FCPA-0003](../user-stories/fcpa/US-FCPA-0003-third-party-intermediary-training.md)).
- **Books & records / internal controls** for finance roles ([US-FCPA-0004](../user-stories/fcpa/US-FCPA-0004-books-records-internal-controls.md)).
- **Facilitation-payment policy** attestation ([US-FCPA-0008](../user-stories/fcpa/US-FCPA-0008-facilitation-payment-attestation.md)).

Cadence: **annual** is the convention, plus **on-hire**, **on-role/geography-change**, and **on-acquisition** triggers.

---

## 4. System Design Implications

| Requirement | Implementation |
|---|---|
| Risk-based targeting | Risk tier derived from `User` geography + role drives course variant and cadence ([US-FCPA-0007](../user-stories/fcpa/US-FCPA-0007-high-risk-geography-targeting.md)) |
| Demonstrate completion per individual | `Certificate` per `(user_id, course_id, course_version_id)` with timestamp + attestation |
| Train **external** third parties | Lightweight external-recipient enrolment + attestation, distinct from full `User` provisioning ([US-FCPA-0003](../user-stories/fcpa/US-FCPA-0003-third-party-intermediary-training.md)) |
| Prompt post-acquisition training | M&A cohort auto-assignment trigger ([US-FCPA-0009](../user-stories/fcpa/US-FCPA-0009-ma-successor-liability-trigger.md)) |
| Ongoing program | Annual cadence + re-assignment on material content change ([US-FCPA-0010](../user-stories/fcpa/US-FCPA-0010-refresher-cadence-reassignment-trigger.md)) |
| Accurate, trustworthy content | AI-drafted FCPA content is human-approved before assignment (ADR-011 / [US-FCPA-0005](../user-stories/fcpa/US-FCPA-0005-human-approved-fcpa-content.md)) |
| Tamper-evident records | Append-only `AuditLog` hash chain; immutable storage export |
| Cover the right topics | `topic_tags` taxonomy so auditors filter "all FCPA anti-bribery training in 2026" |
| Board oversight | Aggregate, minimal-PII program dashboard ([US-FCPA-0011](../user-stories/fcpa/US-FCPA-0011-board-program-dashboard.md)) |

---

## 5. Data Model Implications

Beyond the v1 base model, FCPA-specific additions:

- `Course.framework_tags` includes `"fcpa"`; `topic_tags` such as `fcpa.anti_bribery`, `fcpa.gifts_hospitality`, `fcpa.third_party`, `fcpa.facilitation`, `fcpa.books_records`, `fcpa.internal_controls`.
- `User` risk attributes — geography/country and role risk tier (low/medium/high) so assignment can target by exposure.
- **External recipient** representation for third parties/intermediaries (not full employee accounts) with attestation rows.
- **Cohort** marker for M&A onboarding groups (distinct remediation population).
- Reuses existing `ContentDraft` provenance + `content_hash` (ADR-011) so each FCPA package is traceable to the clause anchors in §1.

---

## 6. Audit Trail & Evidence Requirements

A regulator or internal/external auditor (via the `Auditor` role, [US-FCPA-0006](../user-stories/fcpa/US-FCPA-0006-audit-evidence-export.md)) will request:

1. **Population list** — all users in scope for FCPA in the period, by risk tier.
2. **Training matrix** — per in-scope user, which FCPA-tagged courses were completed.
3. **Third-party attestations** — intermediaries enrolled and their attestation evidence.
4. **M&A remediation** — acquired-cohort training completion.
5. **Sample testing** — full evidence package (assignment, attempts, certificate, attestation, the exact content version) for a sampled user.
6. **Exception report** — overdue/blocked/expired and remediation status.

All produced as CSV + PDF audit-binder exports, sourced from the append-only audit log so retired content versions remain represented.

---

## 7. Retention Requirements

- **Statute of limitations:** generally **5 years** for anti-bribery; the accounting provisions can reach further (and conspiracy/related charges extend exposure). Evidence is typically retained well beyond the limitations period.
- **Implementation:** align FCPA evidence retention to the **≥7-year** SOX standard already in the v1 model (the accounting pillar overlaps SOX), so a single retention policy covers both.
- **Deletion before retention end:** requires explicit Compliance Admin override with an audit-log entry stating the reason; any such override is itself a finding.

---

## 8. User Rights & Access Controls

| Role | Access |
|---|---|
| Trainee (employee) | Own assignments, attempts, certificates |
| Manager | Direct reports' completion status; not attempt detail |
| Compliance Admin | All users' status; create/cancel assignments; cannot edit historical records |
| Content Author | FCPA course content; cannot assign or self-approve (SoD) |
| Third-party Manager | Enrol/track intermediaries; view third-party attestation status |
| Auditor | Read-only across all data; CSV/PDF export |
| Governance / Board | Aggregate, minimal-PII program dashboard only |

Role enforcement is checked at every API boundary, not just the UI.

---

## 9. Conflicts with Other Frameworks

| Other framework | Conflict / overlap | Resolution |
|---|---|---|
| **SOX** §§302/404 | Strong **overlap** (accounting pillar) — not a conflict | Build the books-&-records / internal-controls module once for the stricter requirement; tag the completion for both (`also_satisfies`) |
| **GDPR** Article 17 (erasure) | Conflicts with multi-year retention | Pseudonymize PII while retaining evidence rows linked to immutable `user_id` (already in v1) |

FCPA is otherwise broadly compatible with HIPAA, ISO 27001, and PCI DSS.

---

## 10. Implementation Checklist

- [ ] `framework_tags` includes `fcpa`; FCPA `topic_tags` taxonomy defined
- [ ] `User` geography + role **risk tier** attributes and derivation rule
- [ ] External **third-party recipient** model + attestation capture
- [ ] M&A **cohort** trigger for auto-assignment
- [ ] Annual cadence + re-assignment on material content change
- [ ] FCPA content authored via Mentible and **human-approved** before assignment (ADR-011)
- [ ] `Auditor` evidence export covering third-party + M&A populations
- [ ] Governance/board aggregate dashboard (minimal PII)
- [ ] Clause anchors (`#anti-bribery`, `#books-and-records`, `#internal-controls`) kept stable — they are cited by Mentible package `source_definitions`

---

*End of FCPA framework reference.*
