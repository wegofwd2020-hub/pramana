# SOX — Sarbanes-Oxley Act (Epic)

**Framework code:** `SOX`
**Domain(s):** regulatory · compliance · governance
**Status:** 🚧 In progress (v1 in-scope framework)

> ⚠️ **Disclaimer:** Engineering/product reference, **not legal advice.** Confirm
> SOX interpretation with the customer's compliance counsel and external auditor.

---

## 1. Overview

The **Sarbanes-Oxley Act of 2002** governs US public companies. It has no explicit
"training requirement"; the obligation emerges from **§404** (management assessment
of internal control over financial reporting). Training *is* one of those controls —
and when external auditors assess §404, they ask for **evidence** that the right
people were trained and that the records are reliable and tamper-evident. SOX is the
canonical case for this product: assign → quiz → certify → **prove**.

See the definitions doc [`docs/frameworks/framework_sox.md`](../../frameworks/framework_sox.md)
(citable sections: [§302](../../frameworks/framework_sox.md#section-302) ·
[§404](../../frameworks/framework_sox.md#section-404) ·
[§806](../../frameworks/framework_sox.md#section-806) ·
[§802](../../frameworks/framework_sox.md#section-802)).

## 2. Reuse, don't rebuild — the platform surfaces

SOX adds **content + targeting + evidence**; it does **not** add new UI. Every SOX
story rides the framework-agnostic [`platform/`](../platform/README.md) surfaces:

| Need | Reused platform surface |
|---|---|
| Commission SOX content from a § | [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) |
| Human-approve before assignment | [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md) / [-0005](../platform/US-PLATFORM-0005-regenerate-with-updated-parameters.md) |
| Learner library + player | [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md) / [-0002](../platform/US-PLATFORM-0002-course-player.md) |

So a SOX story specifies *which §, which audience, which evidence* — and points at the
surface that delivers it.

## 3. Overlap with FCPA (build once)

The accounting pillar overlaps: FCPA books-&-records / internal-controls
([US-FCPA-0004](../fcpa/US-FCPA-0004-books-records-internal-controls.md)) and the
auditor evidence binder ([US-FCPA-0006](../fcpa/US-FCPA-0006-audit-evidence-export.md))
are the same capability seen from SOX. Such stories carry `also_satisfies` so one
completion / one export serves both frameworks.

## 4. Story index

| ID | Title | Persona | Priority | Section(s) | Status |
|---|---|---|---|---|---|
| [US-SOX-0001](US-SOX-0001-icfr-controls-awareness-training.md) | §404 internal-controls (ICFR) awareness training | compliance-officer | must | §404 | draft |
| [US-SOX-0002](US-SOX-0002-code-of-conduct-attestation.md) | Annual Code of Conduct & ethics attestation | employee | must | §404 | draft |
| [US-SOX-0003](US-SOX-0003-fraud-whistleblower-training.md) | Fraud awareness, reporting & whistleblower (§806) | employee | must | §806 | draft |
| [US-SOX-0004](US-SOX-0004-insider-trading-reg-fd.md) | Insider trading / Reg FD for MNPI holders | employee | should | §404 | draft |
| [US-SOX-0005](US-SOX-0005-disclosure-controls-officer-certification.md) | Disclosure controls & officer certification (§302/§906) | compliance-officer | should | §302 | draft |
| [US-SOX-0006](US-SOX-0006-auditor-404-evidence-binder.md) | External-auditor §404 evidence binder | auditor | must | §404, §802 | draft |
| [US-SOX-0007](US-SOX-0007-human-approved-sox-content.md) | Human-approved SOX content before assignment | content-author | must | all | draft |

### Planned (not yet written)

- SOX-in-scope **population designation** (`User.in_scope_for_sox` derivation).
- **Annual cadence** + on-role-change / material-change re-training (reuses platform; §802 retention).
- **IT general controls (ITGC)** awareness for IT/security staff.
- **Audit-committee SOX dashboard** (`governance-board`, reuses the FCPA-0011 pattern).

## 5. Traceability

- Definitions: `docs/frameworks/framework_sox.md`.
- Content authoring & approval: `docs/03_ai_drafted_human_approved_content.md`, **ADR-011**.
- Delivery & evidence model: `docs/02_resolved_decisions.md`.
