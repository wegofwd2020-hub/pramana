# Framework Reference: SOX (Sarbanes-Oxley Act)

**Status:** ✅ In scope for v1
**Jurisdiction:** United States
**Primary regulator:** Securities and Exchange Commission (SEC), Public Company Accounting Oversight Board (PCAOB)

> ⚠️ **Disclaimer:** This is an engineering reference, not legal advice. Confirm framework interpretation with John Thomas Corporate's compliance counsel and external SOX auditor before treating any of this as binding.

---

## 1. Framework Overview

The Sarbanes-Oxley Act of 2002 was enacted in response to corporate accounting scandals (Enron, WorldCom). It applies to all US public companies and any non-US company listed on a US exchange. SOX itself does not have a "training requirement" written into the statute. The training requirement emerges through **Section 404** ("Management Assessment of Internal Controls"), which requires companies to maintain and assess internal controls over financial reporting.

Compliance training is one of those controls — companies train employees on financial controls, ethics, fraud prevention, and code of conduct, then must produce evidence that the training occurred when external auditors assess controls.

The relevant standards governing how auditors assess these controls are **PCAOB Auditing Standard 2201** (formerly AS 5).

---

## 2. Why It Matters for Compliance Training Systems

External auditors (Big Four / regional CPA firms) verify Section 404 controls annually. For training-related controls, they ask:

- Did the company's training program cover the right topics for in-scope financial-reporting personnel?
- Did each in-scope person actually complete the training?
- Is the evidence of completion reliable and tamper-evident?
- Were any deficiencies (failed completions, expired certifications) tracked and remediated?

A weak training-evidence system can lead to a **material weakness finding**, which must be disclosed publicly in the company's 10-K.

---

## 3. Training Requirements Imposed by SOX

SOX itself does not enumerate training topics. The COSO Framework (typically the chosen control framework) drives the topics. Common SOX-relevant training:

- **Code of Conduct / Ethics** (annual)
- **Fraud awareness and reporting** (annual)
- **Insider trading and Regulation FD** (annual for employees with material non-public information)
- **Whistleblower protections** (Section 806)
- **Anti-bribery / FCPA** (annual for relevant roles)
- **Financial controls and SOX 404 awareness** (for finance, IT, internal audit)
- **Disclosure controls** (for executives and SEC filers)

Cadence: **annual** is the convention; some topics on-hire and on-role-change.

---

## 4. System Design Implications

| Requirement | Implementation |
|---|---|
| Demonstrate completion per individual | `Certificate` row per `(user_id, course_id, course_version_id)` with timestamp |
| Demonstrate the right people were trained | `Assignment` rows with `assigned_by_user_id`, `due_at`, plus role/department metadata on `User` |
| Demonstrate failed completions were remediated | `BLOCKED` state must trigger manager workflow; remediation evidence stored |
| Tamper-evident records | Append-only `AuditLog`, immutable storage export, optional chain-of-custody hash |
| Cover the right topics | Course taxonomy with `topic_tags` so auditors can filter "show me all FCPA training in 2026" |
| User attestation | Required at certificate issuance |
| Separation of duties | A user cannot be `ContentAuthor` and `Trainee` on the same course |
| Annual cadence enforcement | `cooldown_days = 365` for SOX-tagged courses; auto-create next assignment when cooldown expires |

---

## 5. Data Model Implications

Beyond the v1 base model, SOX-specific additions:

- `Course.topic_tags` — array of taxonomy tags (e.g., `sox.ethics`, `sox.fcpa`, `sox.insider_trading`).
- `Course.framework_tags` — array (`["sox"]` for SOX-relevant courses) so a single course can satisfy multiple frameworks.
- `Certificate.attestation_text_version` — points to a versioned attestation statement for audit traceability.
- `AuditLog.prev_audit_hash` — chain-of-custody hash field, hashing the previous row to make insertion/deletion detectable.
- `User.in_scope_for_sox` (boolean, derived from role/department) — enables auditor queries like "show all SOX-in-scope users and their completion status."

---

## 6. Audit Trail & Evidence Requirements

External auditors (typically working with internal audit and compliance) will request:

1. **Population list** — all users in scope for SOX during the audit period.
2. **Training matrix** — for each in-scope user, which SOX-tagged courses were completed in the period.
3. **Sample testing** — auditors pick a sample of users and request the full evidence package: assignment, attempts, certificate, attestation.
4. **Exception report** — list of overdue, blocked, or expired assignments and remediation status.
5. **System control documentation** — how the system enforces what it claims (this document plus an auditor-walkthrough demo).

The system must be able to produce all of these as exports (CSV + PDF binder format).

---

## 7. Retention Requirements

- **Source:** SOX Section 802 amended 18 USC § 1520 to require auditors to retain audit work papers for **7 years**. Companies typically apply the same standard to underlying compliance evidence.
- **Implementation:** All `Attempt`, `AttemptAnswer`, `Certificate`, and `AuditLog` rows retained ≥7 years from creation.
- **Deletion before 7 years:** Requires explicit Compliance Admin override with audit-log entry stating reason. Any such override is itself an audit finding.

---

## 8. User Rights & Access Controls

| Role | Access |
|---|---|
| Trainee | Own assignments, attempts, certificates |
| Manager | Direct reports' completion status; cannot see attempt details |
| Compliance Admin | All users' status; can create/cancel assignments; cannot edit historical records |
| Content Author | Course content; cannot assign or self-certify |
| Auditor | Read-only across all data; export to CSV/PDF |

Role enforcement is checked at every API boundary, not just UI.

---

## 9. Conflicts with Other Frameworks

| Other framework | Conflict | Resolution |
|---|---|---|
| **GDPR** Article 17 (right to erasure) | Conflicts with 7-year retention | Pseudonymize PII while retaining evidence rows linked to immutable `user_id` |
| **CCPA** | Same as GDPR | Same resolution |

Otherwise, SOX is broadly compatible with HIPAA, ISO 27001, and PCI DSS — building for SOX retention and audit-trail strength satisfies most of those frameworks' equivalents.

---

## 10. Implementation Checklist for v1

- [ ] `Course.framework_tags` and `Course.topic_tags` arrays in schema
- [ ] `User.in_scope_for_sox` derivation rule documented
- [ ] Append-only `AuditLog` table with `prev_audit_hash` field (initially nullable; populate in v2 if not v1)
- [ ] S3 Object Lock bucket for daily audit-log export
- [ ] PDF certificate template includes attestation statement, attestation timestamp, and verification code
- [ ] `Auditor` role with read-only API surface
- [ ] CSV export for population list, training matrix, exception report
- [ ] PDF audit-binder export per user (assignment + attempts + certificate)
- [ ] Manager workflow on `BLOCKED` state with remediation tracking
- [ ] Annual `cooldown_days = 365` default for SOX-tagged courses
- [ ] Documented control narrative ("how the system enforces what it claims") for auditor walkthrough

---

*End of SOX framework reference.*
