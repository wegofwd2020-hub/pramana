# ISO/IEC 27001 — Information Security Management (Epic)

**Framework code:** `ISO27001`
**Domain(s):** compliance · governance
**Status:** 🚧 In progress (target v3)

> ⚠️ **Disclaimer:** Engineering/product reference, **not legal advice.** Confirm scope and
> interpretation with the customer's certification body.

---

## 1. Overview

ISO/IEC 27001:2022 is the international ISMS standard; certification is voluntary but a
common **B2B procurement gate**. Its training requirements are explicit:

- **Competence** ([Clause 7.2](../../frameworks/framework_iso27001.md#competence)) — ensure personnel are competent (education/training/experience).
- **Awareness** ([Clause 7.3](../../frameworks/framework_iso27001.md#awareness)) — personnel aware of the ISMS policy and their role.
- **Awareness training control** ([Annex A.6.3](../../frameworks/framework_iso27001.md#awareness-training-control)) — an awareness, education and training program for all personnel.

Certification bodies test A.6.3 by sampling personnel for **awareness-training evidence**;
a major nonconformity can **suspend certification**. ISO is broadly additive to the other
frameworks. Definitions:
[`docs/frameworks/framework_iso27001.md`](../../frameworks/framework_iso27001.md).

**Two ISO-specific twists** shape the backlog:

1. **Awareness vs. competence** — ISO distinguishes broad *awareness* from role-specific
   *competence* (the framework doc adds `Course.training_type`).
2. **Annex A control mapping + continual improvement** — the auditor export must group
   evidence **by Annex A control**, and management review (Clause 9.3) wants completion/fail
   trends over time.

## 2. Reuse, don't rebuild — the platform surfaces

ISO adds **content + the awareness/competence distinction + Annex-A-mapped evidence**; it
adds **no new UI**. Every story rides [`platform/`](../platform/README.md):

| Need | Reused surface |
|---|---|
| Commission ISO content from a clause/control | [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) |
| Human-approve before assignment | [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md) |
| Learner library + player | [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md) / [-0002](../platform/US-PLATFORM-0002-course-player.md) |

## 3. Cross-framework reuse

- **Security awareness** ([US-ISO-0001](US-ISO-0001-security-awareness-training.md)) is the security-awareness twin of [US-HIPAA-0002](../hipaa/US-HIPAA-0002-security-awareness-program.md) and [US-GDPR-0001](../gdpr/US-GDPR-0001-data-protection-awareness-training.md) (mutual `also_satisfies`).
- **Certification evidence export** ([US-ISO-0006](US-ISO-0006-certification-audit-evidence-export.md)) is the same Auditor export as [US-SOX-0006](../sox/US-SOX-0006-auditor-404-evidence-binder.md) / [US-HIPAA-0008](../hipaa/US-HIPAA-0008-ocr-evidence-export.md) / [US-GDPR-0007](../gdpr/US-GDPR-0007-dpa-evidence-export.md), plus an Annex-A mapping view.
- **Cadence / triggers** ([US-ISO-0004](US-ISO-0004-surveillance-cadence-retraining.md)) reuse the shared trigger/cadence engine ([US-HIPAA-0005](../hipaa/US-HIPAA-0005-onhire-policy-change-triggers.md), [US-FCPA-0010](../fcpa/US-FCPA-0010-refresher-cadence-reassignment-trigger.md)).

## 4. Story index

| ID | Title | Persona | Priority | Clause/Control | Status |
|---|---|---|---|---|---|
| [US-ISO-0001](US-ISO-0001-security-awareness-training.md) | Information security awareness training | compliance-officer | must | 7.3 / A.6.3 | draft |
| [US-ISO-0002](US-ISO-0002-role-based-competence-training.md) | Role-based competence training & evidence | compliance-officer | must | 7.2 | draft |
| [US-ISO-0003](US-ISO-0003-acceptable-use-information-handling.md) | Acceptable use & information-handling awareness | employee | should | A.6.3 | draft |
| [US-ISO-0004](US-ISO-0004-surveillance-cadence-retraining.md) | Surveillance-cycle cadence & post-incident retraining | compliance-officer | must | 7.3 | draft |
| [US-ISO-0005](US-ISO-0005-human-approved-iso-content.md) | Human-approved ISO content before assignment | content-author | must | all | draft |
| [US-ISO-0006](US-ISO-0006-certification-audit-evidence-export.md) | Certification-audit evidence export (Annex A mapping) | auditor | must | A.6.3 | draft |
| [US-ISO-0007](US-ISO-0007-management-review-dashboard.md) | Management-review oversight & continual-improvement dashboard | governance-board | should | 9.3 | draft |

### Planned (not yet written)

- **Secure-coding** competence path for developers (OWASP/ASVS) under Clause 7.2.
- **Disciplinary linkage** (Annex A.6.4) — surface "was trained" evidence for `SanctionEvent`.
- **Annex A control-coverage** report (which controls are satisfied by which courses).

## 5. Traceability

- Definitions: `docs/frameworks/framework_iso27001.md`.
- Content authoring & approval: `docs/03_ai_drafted_human_approved_content.md`, **ADR-011**.
- Awareness/competence, Annex A mapping, metrics: `framework_iso27001.md` §3–§6.
