# GDPR — General Data Protection Regulation (Epic)

**Framework code:** `GDPR`
**Domain(s):** regulatory · compliance · governance
**Status:** 🚧 In progress (target v4)

> ⚠️ **Disclaimer:** Engineering/product reference, **not legal advice.** GDPR is highly
> jurisdiction-dependent; confirm with the customer's data-protection counsel / DPO.

---

## 1. Overview

GDPR (Regulation (EU) 2016/679) governs processing of EU/EEA residents' personal data,
with extraterritorial reach. It has **no dedicated training mandate**, but training is
expected accountability evidence (Articles 5(2), 24, 32, **39(1)(b)** — the DPO's duty to
run staff awareness/training). Penalties are the highest in this set (up to €20M or 4% of
global turnover).

**GDPR is unique in two ways** that shape the backlog:

1. **It also governs the training data itself** — trainee records contain personal data,
   so the *system* must honour data-subject rights (notably **erasure**, reconciled with
   SOX/HIPAA retention via **pseudonymization** — already in the v1 model).
2. **The DPO** is a distinct oversight actor (Article 39).

Definitions: [`docs/frameworks/framework_gdpr.md`](../../frameworks/framework_gdpr.md)
(citable articles: [awareness](../../frameworks/framework_gdpr.md#data-protection-awareness) ·
[DSR](../../frameworks/framework_gdpr.md#data-subject-rights) ·
[breach](../../frameworks/framework_gdpr.md#breach-notification) ·
[erasure](../../frameworks/framework_gdpr.md#right-to-erasure)).

## 2. Reuse, don't rebuild — the platform surfaces

GDPR adds **content + targeting + evidence**, and reuses an **existing delivery
endpoint** for erasure. No new UI. Every story rides [`platform/`](../platform/README.md):

| Need | Reused surface |
|---|---|
| Commission GDPR content from an article | [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) |
| Human-approve before assignment | [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md) |
| Learner library + player | [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md) / [-0002](../platform/US-PLATFORM-0002-course-player.md) |
| Erasure of trainee PII | **existing** `POST /users/{id}/pseudonymize` + `User.pseudonymized_at` |

## 3. Cross-framework reuse

- **Breach training** ([US-GDPR-0002](US-GDPR-0002-breach-notification-training.md)) reuses the breach pattern from [US-HIPAA-0003](../hipaa/US-HIPAA-0003-breach-recognition-reporting.md).
- **DPA evidence export** ([US-GDPR-0007](US-GDPR-0007-dpa-evidence-export.md)) is the same Auditor export as [US-SOX-0006](../sox/US-SOX-0006-auditor-404-evidence-binder.md) / [US-HIPAA-0008](../hipaa/US-HIPAA-0008-ocr-evidence-export.md).
- **Erasure** ([US-GDPR-0004](US-GDPR-0004-trainee-erasure-pseudonymization.md)) reuses the SOX/GDPR pseudonymization already built into the data model.

## 4. Story index

| ID | Title | Persona | Priority | Article(s) | Status |
|---|---|---|---|---|---|
| [US-GDPR-0001](US-GDPR-0001-data-protection-awareness-training.md) | Data protection awareness training | compliance-officer | must | 32, 39 | draft |
| [US-GDPR-0002](US-GDPR-0002-breach-notification-training.md) | Personal-data breach (72-hour) training | employee | must | 33 | draft |
| [US-GDPR-0003](US-GDPR-0003-data-subject-rights-training.md) | Data subject rights handling training | employee | should | 15-22 | draft |
| [US-GDPR-0004](US-GDPR-0004-trainee-erasure-pseudonymization.md) | Trainee right-to-erasure (pseudonymization) | compliance-officer | must | 17 | draft |
| [US-GDPR-0005](US-GDPR-0005-dpo-oversight-dashboard.md) | DPO program oversight & awareness monitoring | governance-board | should | 39 | draft |
| [US-GDPR-0006](US-GDPR-0006-human-approved-gdpr-content.md) | Human-approved GDPR content before assignment | content-author | must | all | draft |
| [US-GDPR-0007](US-GDPR-0007-dpa-evidence-export.md) | GDPR training-evidence export for a DPA | auditor | must | 5(2), 39 | draft |

### Planned (not yet written)

- Lawful-basis & **consent** module (Article 6); marketing/HR role variants.
- **Cross-border transfer** awareness (Articles 44-49).
- **Records of processing** (Article 30) for the training program itself.
- Data-subject **"download my data"** portability self-service (Article 20).

## 5. Traceability

- Definitions: `docs/frameworks/framework_gdpr.md`.
- Content authoring & approval: `docs/03_ai_drafted_human_approved_content.md`, **ADR-011**.
- Erasure/retention model: `framework_gdpr.md` §7, `pramana/db/models/identity.py` (`pseudonymized_at`).
