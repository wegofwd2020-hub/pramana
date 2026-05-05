# Framework Reference: GDPR

**Status:** ⏳ Future phase (target v4)
**Jurisdiction:** European Union / European Economic Area (with extraterritorial reach)
**Primary regulator:** Member-state Data Protection Authorities, coordinated by the European Data Protection Board (EDPB)

> ⚠️ **Disclaimer:** This is an engineering reference, not legal advice. GDPR interpretation is highly jurisdiction-dependent and evolving via DPA decisions and CJEU rulings. Confirm with John Thomas Corporate's data protection counsel before treating any of this as binding.

---

## 1. Framework Overview

The **General Data Protection Regulation** (Regulation (EU) 2016/679), in force since 25 May 2018, governs the processing of personal data of natural persons in the EU/EEA. Its territorial scope (Article 3) makes it applicable to any organization processing EU residents' data, regardless of where the organization is located.

Unlike SOX or HIPAA, GDPR does **not have a dedicated training mandate**. Training requirements are inferred from:

- **Article 5(2)** — Accountability principle: the controller must demonstrate compliance.
- **Article 24** — Responsibility of the controller.
- **Article 32** — Security of processing, requiring "appropriate technical and organisational measures."
- **Article 39(1)(b)** — Data Protection Officer's task to monitor compliance, including "awareness-raising and training of staff involved in processing operations."
- **Article 47** — Binding Corporate Rules require training as a content element.

In practice, regulators expect documented, periodic training as part of the accountability evidence trail.

---

## 2. Why It Matters for Compliance Training Systems

GDPR has the highest financial penalties of any framework in this set: **up to €20 million or 4% of global annual turnover**, whichever is higher. DPAs increasingly audit organizations and request evidence of training as part of accountability reviews after data breaches.

The system must support GDPR not only as a topic to be trained on but also as a regulatory regime that **applies to the training data itself** (since training records contain personal data of trainees).

---

## 3. Training Requirements Implied by GDPR

Common GDPR-relevant training topics:

- **Data protection principles** (lawfulness, purpose limitation, data minimisation, etc. — Article 5).
- **Lawful bases for processing** (consent, contract, legitimate interests, etc. — Article 6).
- **Data subject rights** (access, rectification, erasure, portability, objection — Articles 15–22).
- **Breach detection and 72-hour notification** (Article 33).
- **Records of processing activities** (Article 30).
- **Cross-border data transfer rules** (Articles 44–49).
- **Privacy by design and default** (Article 25).
- **Role-specific training** for DPO, marketing (consent), HR (employee data), engineering (PbD).

Cadence: no fixed cadence in the regulation. Annual is the typical convention; on-hire and on-role-change are best practice.

---

## 4. System Design Implications

GDPR creates two categories of requirement:

### 4.1 GDPR as a topic (training content)

Same pattern as other frameworks: tagged courses, role-based paths, evidence retention.

### 4.2 GDPR as a regime applying to the system

This is the harder part. The training system processes personal data of trainees. Therefore:

| Requirement | Implementation |
|---|---|
| Lawful basis for processing | Document the basis (typically: legitimate interests under Article 6(1)(f) or legal obligation under 6(1)(c) when training is mandated) |
| Privacy notice to trainees | UI surface at first login showing what data is collected and why |
| Right of access (Art 15) | API endpoint or admin workflow to export all data about a specific user |
| Right to rectification (Art 16) | User can update their own profile fields |
| Right to erasure (Art 17) | Pseudonymization workflow (cannot fully delete due to retention obligations) |
| Right to data portability (Art 20) | Export in machine-readable format (JSON) |
| Right to object (Art 21) | Mechanism to record an objection — typically referred to manual review |
| Data minimisation (Art 5(1)(c)) | Don't collect what's not needed; e.g., avoid gratuitous browser fingerprinting |
| Storage limitation (Art 5(1)(e)) | Retention periods documented and enforced; pseudonymization after retention period |
| Cross-border transfer (Art 44+) | If hosted outside EEA, need Standard Contractual Clauses or equivalent; ideally offer EU-region deployment |
| Records of processing (Art 30) | Document what processing the system performs (this doc partially serves that purpose) |
| Breach notification (Art 33) | If the training system itself is breached, controller must be notified within timelines |

---

## 5. Data Model Implications

Additions on top of v1 base model:

- `User.consent_records` — entity tracking what consents were given, when, and for what purpose.
- `DataSubjectRequest` — entity for tracking access / rectification / erasure / portability / objection requests: `user_id`, `request_type`, `received_at`, `due_at` (typically request_received + 30 days), `status`, `resolution_notes`.
- `User.gdpr_jurisdiction` — boolean or country code; drives whether GDPR rules apply.
- `User.pseudonymized_at` — timestamp; supports erasure-with-retention pattern.
- `ProcessingActivity` — entity documenting Article 30 records of processing activities (this can be a static config, not a runtime entity).
- `DataExport` — record of every data subject access request fulfilment, for audit.

---

## 6. Audit Trail & Evidence Requirements

DPAs investigating an organization will request:

1. **Training program documentation** (Article 30 record of processing activity for the training program itself).
2. **Completion records** with evidence of attestation.
3. **DPO oversight** — evidence the DPO monitors the program.
4. **DSR (Data Subject Request) log** — every request received, responded to, with timing.
5. **Breach response training evidence** — given the 72-hour notification rule, trainees in breach-response roles must be demonstrably trained.

---

## 7. Retention Requirements

GDPR does **not** specify retention periods. Storage limitation principle (Article 5(1)(e)) requires data to be kept "no longer than is necessary."

**Tension with SOX:** SOX requires 7-year retention. If a trainee is also an EU data subject (e.g., a US company's EU-based employee), this creates a real conflict.

**Resolution:** The legal-obligation lawful basis (Article 6(1)(c)) and Article 17(3)(b) erasure exemption allow retention when required by law. The training system should:

- Distinguish between PII (eligible for pseudonymization) and administrative training records (retained).
- After SOX retention period (7 years) elapses, even administrative records may be deleted.
- Document the retention policy explicitly so DPAs see the legitimate basis.

---

## 8. User Rights & Access Controls

GDPR introduces user-side rights not present in SOX or HIPAA:

- **Right of access** — user can request all data about themselves.
- **Right to rectification** — user can correct their data.
- **Right to erasure** — pseudonymization workflow.
- **Right to data portability** — JSON export.
- **Right to object** — to processing based on legitimate interests.
- **Rights related to automated decision-making** (Article 22) — the training system probably does not engage in this, but document the position.

These should be exposed both via self-service UI (where possible) and via DPO/admin workflows for complex cases.

---

## 9. Conflicts with Other Frameworks

| Other framework | Conflict | Resolution |
|---|---|---|
| **SOX** retention | Direct conflict between erasure and 7-year retention | Pseudonymization on erasure; rely on Article 6(1)(c) and Article 17(3)(b) |
| **HIPAA** retention | Same as SOX, slightly less acute (6 years) | Same resolution |
| **Cross-border transfer** (US-hosted system + EU users) | Transfer mechanism required | SCCs at minimum; ideally EU-region deployment option in v4+ |

---

## 10. Implementation Checklist for GDPR Support (Post-v1)

- [ ] Privacy notice surface at trainee first login
- [ ] `DataSubjectRequest` entity and admin workflow with 30-day SLA
- [ ] Self-service "Download my data" feature (JSON export)
- [ ] Self-service profile editing for rectification
- [ ] Pseudonymization workflow for erasure (already designed for SOX)
- [ ] Article 30 records of processing activity document (static)
- [ ] DPO role added to RBAC (overlaps with `ComplianceAdmin` but distinct legally)
- [ ] EU-region deployment option (or documented SCCs for non-EU deployment)
- [ ] Consent tracking entity for opt-in features
- [ ] Breach notification process documented and trained
- [ ] `User.gdpr_jurisdiction` flag and conditional logic for GDPR-applicable users
- [ ] Default content library includes GDPR awareness, DSR handling, breach response courses

---

*End of GDPR framework reference.*
