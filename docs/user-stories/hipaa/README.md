# HIPAA — Health Insurance Portability and Accountability Act (Epic)

**Framework code:** `HIPAA`
**Domain(s):** regulatory · compliance
**Status:** 🚧 In progress (target v2)

> ⚠️ **Disclaimer:** Engineering/product reference, **not legal advice.** Confirm HIPAA
> interpretation with the customer's compliance counsel and Privacy/Security Officer.

---

## 1. Overview

HIPAA protects Protected Health Information (PHI) and — unlike SOX/FCPA — **explicitly
requires workforce training**:

- **Privacy Rule** ([§164.530(b)](../../frameworks/framework_hipaa.md#privacy-rule)) — train all workforce members on PHI policies.
- **Security Rule** ([§164.308(a)(5)](../../frameworks/framework_hipaa.md#security-rule)) — a security awareness and training **program** (reminders, malware, log-in monitoring, passwords).
- **Breach Notification Rule** ([§164.400-414](../../frameworks/framework_hipaa.md#breach-notification-rule)) — recognise and report breaches.

HHS **OCR** audits and breach-triggered investigations request **training records as
evidence**. HIPAA mandates training **on hire, after material policy change**, and
allows **role-based** tailoring — so it exercises the platform's targeting and trigger
capabilities harder than any framework so far. Definitions:
[`docs/frameworks/framework_hipaa.md`](../../frameworks/framework_hipaa.md).

## 2. Reuse, don't rebuild — the platform surfaces

HIPAA adds **content + targeting + triggers + evidence**; it adds **no new UI**. Every
HIPAA story rides the framework-agnostic [`platform/`](../platform/README.md) surfaces:

| Need | Reused platform surface |
|---|---|
| Commission HIPAA content from a rule | [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) |
| Human-approve before assignment | [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md) |
| Learner library + player | [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md) / [-0002](../platform/US-PLATFORM-0002-course-player.md) |

## 3. Cross-framework reuse

- **Business-Associate training** ([US-HIPAA-0006](US-HIPAA-0006-business-associate-training.md)) reuses the third-party pattern from [US-FCPA-0003](../fcpa/US-FCPA-0003-third-party-intermediary-training.md).
- **OCR evidence export** ([US-HIPAA-0008](US-HIPAA-0008-ocr-evidence-export.md)) is the same Auditor export as [US-SOX-0006](../sox/US-SOX-0006-auditor-404-evidence-binder.md) / [US-FCPA-0006](../fcpa/US-FCPA-0006-audit-evidence-export.md).
- **On-hire / material-change triggers** ([US-HIPAA-0005](US-HIPAA-0005-onhire-policy-change-triggers.md)) generalize the FCPA M&A trigger ([US-FCPA-0009](../fcpa/US-FCPA-0009-ma-successor-liability-trigger.md)).

## 4. Story index

| ID | Title | Persona | Priority | Rule | Status |
|---|---|---|---|---|---|
| [US-HIPAA-0001](US-HIPAA-0001-privacy-rule-workforce-training.md) | Privacy Rule workforce training | compliance-officer | must | Privacy | draft |
| [US-HIPAA-0002](US-HIPAA-0002-security-awareness-program.md) | Security awareness & training program | employee | must | Security | draft |
| [US-HIPAA-0003](US-HIPAA-0003-breach-recognition-reporting.md) | Breach recognition & reporting training | employee | must | Breach | draft |
| [US-HIPAA-0004](US-HIPAA-0004-role-based-training-paths.md) | Role-based training paths by PHI access | compliance-officer | must | Privacy/Security | draft |
| [US-HIPAA-0005](US-HIPAA-0005-onhire-policy-change-triggers.md) | On-hire & material-change training triggers | compliance-officer | must | Privacy | draft |
| [US-HIPAA-0006](US-HIPAA-0006-business-associate-training.md) | Business Associate training & attestation | third-party-manager | should | BAs | draft |
| [US-HIPAA-0007](US-HIPAA-0007-human-approved-hipaa-content.md) | Human-approved HIPAA content before assignment | content-author | must | all | draft |
| [US-HIPAA-0008](US-HIPAA-0008-ocr-evidence-export.md) | HIPAA training-evidence export for OCR | auditor | must | all | draft |

### Planned (not yet written)

- **Sanction-event** capture linked to training failure / PHI mishandling (§164.530(e)).
- **Point-in-time** training-status query ("status of user X on date Y") for OCR.
- **Minimum-necessary** focused module for high-PHI-access roles.
- **Privacy/Security Officer dashboard** (reuses the FCPA-0011 pattern).

## 5. Traceability

- Definitions: `docs/frameworks/framework_hipaa.md`.
- Content authoring & approval: `docs/03_ai_drafted_human_approved_content.md`, **ADR-011**.
- Triggers / role paths / retention: `framework_hipaa.md` §4–§7.
