# FCPA — Foreign Corrupt Practices Act (Epic)

**Framework code:** `FCPA`
**Domain(s):** regulatory · compliance · governance
**Status:** 🚧 In progress

> ⚠️ **Disclaimer:** Engineering/product reference, **not legal advice**. Confirm
> all FCPA interpretation with the customer's compliance counsel.

---

## 1. Overview

The **Foreign Corrupt Practices Act of 1977** is a US federal law with two pillars,
jointly enforced by the **DOJ** (criminal) and the **SEC** (civil):

1. **Anti-bribery provisions** — prohibit offering, paying, or authorizing anything
   of value to a **foreign official** to obtain or retain business or secure an
   improper advantage. Reaches *issuers*, *domestic concerns*, and certain foreign
   persons/agents acting in US territory — and crucially extends to acts by
   **third-party intermediaries** (agents, distributors, consultants, JV partners).
2. **Accounting provisions** (apply to *issuers*) — (a) **books & records**: keep
   accurate records in reasonable detail; (b) **internal accounting controls**:
   maintain a system giving reasonable assurance over transactions. These overlap
   heavily with **SOX** §§302/404.

**Why a GRC training tool cares:** DOJ's *Evaluation of Corporate Compliance
Programs* treats **risk-based training**, **third-party management**, and
**documented attestations** as hallmarks of an effective program — and a regulator
will ask to *see the evidence*. That maps directly onto what this product does:
assign → deliver → quiz → attest → certify → **audit trail**, with content that is
AI-drafted and **human-approved** before it is ever assignable (see ADR-011 /
`docs/03_ai_drafted_human_approved_content.md`).

## 2. Primary FCPA risk areas (what training must cover)

| Risk area | Why it's high-risk |
|---|---|
| Third-party intermediaries | The single largest source of FCPA enforcement actions |
| Gifts, travel & hospitality (G&H) | Easy to cross the line; needs concrete thresholds/scenarios |
| Facilitation payments | Narrow statutory exception, broadly prohibited by company policy |
| High-risk geographies | Exposure varies sharply by country/government touchpoints |
| Government interactions | Licences, permits, customs, state-owned enterprises |
| Charitable & political contributions | Can mask improper payments |
| M&A / successor liability | Acquirer inherits target's FCPA exposure |
| Books & records / controls | Off-book funds, mischaracterized expenses (accounting pillar) |

## 3. Personas in play

`compliance-officer` · `employee` · `manager` · `content-author` ·
`third-party-manager` · `auditor` · `governance-board`
(definitions in [`../README.md` §4](../README.md)).

## 4. Story index

| ID | Title | Persona | Priority | Provisions | Status |
|---|---|---|---|---|---|
| [US-FCPA-0001](US-FCPA-0001-anti-bribery-training-assignment.md) | Risk-based anti-bribery training assignment & completion | compliance-officer | must | anti-bribery | draft |
| [US-FCPA-0002](US-FCPA-0002-gifts-travel-hospitality-scenarios.md) | Gifts, travel & hospitality scenario assessment | employee | must | anti-bribery | draft |
| [US-FCPA-0003](US-FCPA-0003-third-party-intermediary-training.md) | Third-party / intermediary FCPA training & attestation | third-party-manager | must | anti-bribery | draft |
| [US-FCPA-0004](US-FCPA-0004-books-records-internal-controls.md) | Books & records / internal-controls training (accounting pillar) | employee | should | accounting | draft |
| [US-FCPA-0005](US-FCPA-0005-human-approved-fcpa-content.md) | Human-approved FCPA content before assignment | content-author | must | both | draft |
| [US-FCPA-0006](US-FCPA-0006-audit-evidence-export.md) | FCPA audit-evidence export for a regulator/auditor | auditor | must | both | draft |

### Planned (not yet written)

- High-risk geography targeting (assign by country/role risk tier).
- Facilitation-payment policy attestation.
- M&A successor-liability onboarding training trigger.
- Annual refresher cadence + policy-change re-assignment trigger.
- Board / audit-committee FCPA program dashboard (`governance-board`).

## 5. Traceability

- Product spec: `docs/02_resolved_decisions.md` (FR1–FR9, assignment state machine).
- Content authoring & approval: `docs/03_ai_drafted_human_approved_content.md`, **ADR-011**.
- Accounting-pillar overlap: `docs/frameworks/framework_sox.md`.
