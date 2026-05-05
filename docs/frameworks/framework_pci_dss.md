# Framework Reference: PCI DSS

**Status:** ⏳ Future phase (target v5)
**Jurisdiction:** Global (industry standard, not legislation)
**Primary "regulator":** PCI Security Standards Council; enforced by acquiring banks and card brands (Visa, Mastercard, Amex, Discover, JCB)

> ⚠️ **Disclaimer:** This is an engineering reference, not legal advice. PCI DSS interpretation depends on merchant level and acquirer requirements. Confirm with John Thomas Corporate's QSA (Qualified Security Assessor) before treating any of this as binding.

---

## 1. Framework Overview

The **Payment Card Industry Data Security Standard** (PCI DSS) is a contractual standard imposed on any organization that stores, processes, or transmits payment card data. The current version is **PCI DSS v4.0.1** (June 2024), which fully replaces v3.2.1.

Training requirements are imposed via:

- **Requirement 12.6** — Security awareness program, mandating periodic training for all personnel with access to the cardholder data environment (CDE).
- **Requirement 6.2.2** (for v4.0) — Software development personnel must be trained on secure development.

---

## 2. Why It Matters for Compliance Training Systems

Non-compliance with PCI DSS can result in card-brand fines (typically passed through by acquiring banks), increased transaction fees, mandatory forensic investigations after breaches, and ultimately loss of card-processing privileges. For a merchant or service provider, that is an existential risk.

PCI DSS audits are conducted by Qualified Security Assessors (QSAs) for Level 1 merchants/service providers, and via Self-Assessment Questionnaires (SAQ) for lower levels.

---

## 3. Training Requirements Imposed by PCI DSS

### 3.1 Requirement 12.6 — Security awareness program

- **Who:** all personnel with access to the CDE.
- **When:**
  - Upon hire.
  - At least annually.
  - When the threat environment or policy changes materially.
- **How (multi-method):** PCI DSS v4.0 requires the program to use **multiple methods** of communication (e.g., posters, emails, briefings, formal training). The compliance training system covers the formal-training leg.
- **Topics required:**
  - Acceptable use of end-user technologies.
  - Threats and vulnerabilities affecting CDE.
  - Phishing and social engineering.
  - Reporting suspicious incidents.

### 3.2 Requirement 6.2.2 — Secure development training

- **Who:** software development personnel.
- **When:** at least annually.
- **Topics:**
  - Software security relevant to the developer's role.
  - Secure software design.
  - Common vulnerabilities (OWASP Top 10 or equivalent).
  - Tools used for secure development.

### 3.3 Acknowledgement requirement

- PCI DSS Requirement 12.8 (for personnel) historically required personnel to acknowledge having read and understood the security policy. The system's attestation mechanism satisfies this.

---

## 4. System Design Implications

| Requirement | Implementation |
|---|---|
| Identify CDE-access personnel | `User.cde_access` flag — drives required training path |
| Multi-method evidence | The training system covers formal training; reporting must indicate this is one of multiple methods, not the entire program |
| Annual cadence | `cooldown_days = 365`; on-hire trigger |
| Material change re-training | Same `is_material_change` mechanism as HIPAA |
| Acknowledgement / attestation | Already in v1 |
| Secure development sub-track | `Course.applicable_roles` includes `developer`; separate course tagged for Requirement 6.2.2 |
| Threat environment updates | Periodic course content updates with version increment; users see updated content on next refresh cycle |

---

## 5. Data Model Implications

Additions on top of v1 base model (much overlap with HIPAA and ISO 27001):

- `Course.framework_tags` includes `pci_dss` with sub-tags `pci.12_6` and `pci.6_2_2`.
- `Course.pci_requirements` — array of PCI DSS requirement identifiers.
- `User.cde_access` — boolean (or enum if more granularity is needed: `none`, `view`, `process`, `admin`).
- `User.role_developer` — boolean (or derived from job title); drives Requirement 6.2.2 path.
- `AssignmentTrigger` — shared with HIPAA / ISO 27001.

---

## 6. Audit Trail & Evidence Requirements

QSAs and acquirers will request:

1. **CDE personnel roster** during the audit period.
2. **Awareness training program documentation.**
3. **Per-person completion records** for in-scope personnel.
4. **Acknowledgement records** (attestation rows).
5. **Secure development training records** for development personnel (Req 6.2.2).
6. **Change log** for the program — when content was updated and why.

The PCI DSS Report on Compliance (RoC) or SAQ has specific sections for these — exports should map to those sections cleanly.

---

## 7. Retention Requirements

PCI DSS requires audit trail retention of **at least 1 year, with 3 months immediately available** (Requirement 10.5.1). For training records specifically, the convention is to retain for the longer of:

- The current audit cycle (1 year minimum).
- The retention period of any other applicable framework (typically SOX's 7 years dominates).

---

## 8. User Rights & Access Controls

PCI DSS does not introduce individual rights but does require strict access control. The v1 RBAC model satisfies this.

---

## 9. Conflicts with Other Frameworks

PCI DSS is generally additive — building for PCI DSS does not conflict with SOX, HIPAA, GDPR, or ISO 27001. The main interaction:

| Other framework | Interaction |
|---|---|
| **ISO 27001** | PCI DSS Req 6.2.2 secure development training overlaps with ISO 27001 competence (Clause 7.2) for developers — a single course can satisfy both with appropriate tagging |
| **GDPR** | If CDE personnel are EU residents, GDPR rights apply to their training records — same pseudonymization approach |
| **SOX** | Often co-applicable (public retailer with card-processing). Building for SOX evidence quality satisfies PCI DSS evidence needs |

---

## 10. Implementation Checklist for PCI DSS Support (Post-v1)

- [ ] `Course.framework_tags` PCI values with sub-tags
- [ ] `Course.pci_requirements` array
- [ ] `User.cde_access` flag
- [ ] `User.role_developer` flag (or derive from role taxonomy)
- [ ] On-hire and annual `AssignmentTrigger` for CDE-access users
- [ ] Material-change re-training workflow
- [ ] Default content library: Req 12.6 awareness course, Req 6.2.2 secure development course (OWASP Top 10 baseline)
- [ ] PCI-format evidence export aligned to RoC / SAQ sections
- [ ] Documentation of how the system fits into the customer's broader awareness program (multi-method requirement)
- [ ] QSA-friendly walkthrough materials

---

*End of PCI DSS framework reference.*
