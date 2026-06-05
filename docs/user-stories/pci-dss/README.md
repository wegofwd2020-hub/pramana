# PCI DSS — Payment Card Industry Data Security Standard (Epic)

**Framework code:** `PCIDSS` (story IDs `US-PCI-…`)
**Domain(s):** compliance · regulatory
**Status:** 🚧 In progress (target v5)

> ⚠️ **Disclaimer:** Engineering/product reference, **not legal advice.** PCI DSS scope
> depends on merchant level / acquirer; confirm with the customer's QSA.

---

## 1. Overview

PCI DSS v4.0.1 is a contractual standard for any organization that stores, processes, or
transmits payment-card data. Its training requirements are explicit and **CDE-scoped**:

- **Security awareness program** ([Req 12.6](../../frameworks/framework_pci_dss.md#security-awareness-program)) — all personnel with access to the cardholder-data environment (CDE), on-hire / annually / on material change.
- **Secure development training** ([Req 6.2.2](../../frameworks/framework_pci_dss.md#secure-development-training)) — software-development personnel, at least annually.
- **Acknowledgement** ([Req 12.8](../../frameworks/framework_pci_dss.md#acknowledgement)) — personnel acknowledge the security policy.

QSAs (Level 1) and SAQs assess these; failure risks card-brand fines and loss of processing
privileges. Definitions: [`docs/frameworks/framework_pci_dss.md`](../../frameworks/framework_pci_dss.md).

**Two PCI-specific twists** shape the backlog:

1. **CDE scoping** — training targets only personnel with `User.cde_access`, not everyone.
2. **Multi-method program** — v4.0 requires awareness via *multiple* methods; this product is
   the **formal-training leg**, so reporting must not overclaim full Req 12.6 coverage.

## 2. Reuse, don't rebuild — the platform surfaces

PCI adds **content + CDE targeting + RoC/SAQ-mapped evidence**; it adds **no new UI**. Every
story rides [`platform/`](../platform/README.md):

| Need | Reused surface |
|---|---|
| Commission PCI content from a requirement | [US-PLATFORM-0003](../platform/US-PLATFORM-0003-commission-training-content.md) |
| Human-approve before assignment | [US-PLATFORM-0004](../platform/US-PLATFORM-0004-ingestion-review-queue.md) |
| Learner library + player | [US-PLATFORM-0001](../platform/US-PLATFORM-0001-learner-training-library.md) / [-0002](../platform/US-PLATFORM-0002-course-player.md) |

## 3. Cross-framework reuse

- **Secure development** ([US-PCI-0002](US-PCI-0002-secure-development-training.md)) overlaps ISO 27001 developer competence ([US-ISO-0002](../iso27001/US-ISO-0002-role-based-competence-training.md)) — one course, both frameworks via `also_satisfies`.
- **Security awareness** ([US-PCI-0001](US-PCI-0001-cde-security-awareness-training.md)) joins the security-awareness family (ISO-0001 / HIPAA-0002 / GDPR-0001).
- **RoC/SAQ evidence export** ([US-PCI-0006](US-PCI-0006-qsa-evidence-export.md)) is the same Auditor export as every other framework's `*-0006/0007/0008`, with a requirement-mapped view.
- **Cadence / triggers** ([US-PCI-0004](US-PCI-0004-cde-cadence-retraining.md)) reuse the shared engine (HIPAA-0005, ISO-0004, FCPA-0010).

## 4. Story index

| ID | Title | Persona | Priority | Requirement | Status |
|---|---|---|---|---|---|
| [US-PCI-0001](US-PCI-0001-cde-security-awareness-training.md) | CDE security awareness training | compliance-officer | must | 12.6 | draft |
| [US-PCI-0002](US-PCI-0002-secure-development-training.md) | Secure development training for developers | compliance-officer | must | 6.2.2 | draft |
| [US-PCI-0003](US-PCI-0003-security-policy-acknowledgement.md) | Security-policy acknowledgement | employee | should | 12.8 | draft |
| [US-PCI-0004](US-PCI-0004-cde-cadence-retraining.md) | On-hire & annual cadence + material-change retraining | compliance-officer | must | 12.6 | draft |
| [US-PCI-0005](US-PCI-0005-human-approved-pci-content.md) | Human-approved PCI content before assignment | content-author | must | all | draft |
| [US-PCI-0006](US-PCI-0006-qsa-evidence-export.md) | QSA / RoC-SAQ evidence export | auditor | must | 12.6, 6.2.2 | draft |
| [US-PCI-0007](US-PCI-0007-multi-method-program-reporting.md) | Multi-method program coverage reporting | compliance-officer | should | 12.6 | draft |

### Planned (not yet written)

- CDE-access **designation** (`User.cde_access`) and required-path derivation.
- Incident-response training (Req 12.10) for CDE responders.
- Service-provider vs merchant **scoping** variants.

## 5. Traceability

- Definitions: `docs/frameworks/framework_pci_dss.md`.
- Content authoring & approval: `docs/03_ai_drafted_human_approved_content.md`, **ADR-011**.
- CDE targeting, RoC/SAQ mapping, multi-method: `framework_pci_dss.md` §3–§6.
