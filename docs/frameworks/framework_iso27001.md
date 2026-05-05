# Framework Reference: ISO/IEC 27001

**Status:** ⏳ Future phase (target v3)
**Jurisdiction:** International (voluntary certification)
**Primary "regulator":** Accredited certification bodies (BSI, Schellman, A-LIGN, etc.)

> ⚠️ **Disclaimer:** This is an engineering reference. Confirm scope and interpretation with the customer's certification body.

---

## 1. Framework Overview

**ISO/IEC 27001** is the international standard for Information Security Management Systems (ISMS). The current version is **ISO/IEC 27001:2022**, which superseded the 2013 edition. Certification is voluntary but commonly required by enterprise B2B customers.

Training requirements are imposed via:

- **Clause 7.2 — Competence:** the organization must determine necessary competence for personnel and ensure they are competent through education, training, or experience.
- **Clause 7.3 — Awareness:** personnel must be aware of the information security policy and their contribution to the ISMS.
- **Annex A.6.3 (2022) — Information security awareness, education and training** (renumbered from A.7.2.2 in the 2013 edition).

ISO/IEC 27002 provides implementation guidance for the Annex A controls.

---

## 2. Why It Matters for Compliance Training Systems

Certification bodies conduct annual surveillance audits and a full recertification audit every three years. Auditors test Annex A.6.3 by sampling personnel and asking for evidence of awareness training completion. Failure produces a **nonconformity** (minor or major); major nonconformities can suspend certification.

For SaaS providers, ISO 27001 certification is often a procurement gate. Losing certification means losing customers.

---

## 3. Training Requirements Imposed by ISO 27001

### 3.1 Awareness training (Annex A.6.3)

- All personnel (and relevant interested parties) must receive awareness training.
- Topics typically include:
  - Information security policy.
  - Acceptable use.
  - Password and authentication hygiene.
  - Phishing and social engineering.
  - Incident reporting.
  - Data classification and handling.
  - Clean desk / clear screen.
  - Removable media policy.
  - Mobile device and remote work security.

### 3.2 Role-based competence (Clause 7.2)

- Specific roles need deeper training:
  - Developers: secure coding (OWASP Top 10, ASVS).
  - Sysadmins: hardening, patching, monitoring.
  - Incident response team: IR procedures, forensics.
  - Internal auditors: ISMS audit training.

### 3.3 Cadence

- Awareness: at minimum annual; on-hire mandatory.
- After incidents or significant changes, re-training is expected.

### 3.4 Annex A.6.4 — Disciplinary process

- Linked to training: failure to comply with security policy after training may invoke the disciplinary process. The training system needs to evidence that the user *was* trained, so disciplinary action is defensible.

---

## 4. System Design Implications

| Requirement | Implementation |
|---|---|
| Demonstrate competence (not just exposure) | Score-based pass with attestation already in v1 satisfies this |
| Awareness vs. competence distinction | `Course.training_type` enum (`awareness` | `competence`) |
| Role-based competence training | `Course.applicable_roles` (same field as HIPAA needs) |
| Annual cadence | `cooldown_days = 365` |
| Map courses to Annex A controls | `Course.annex_a_controls` array (e.g., `["A.6.3", "A.5.10"]`) |
| Training matrix evidence | Auditor export grouped by Annex A control |
| Continual improvement | Training program metrics: completion rates, fail rates, time-to-completion. Trends over years. |
| Training records linked to ISMS scope | `User.in_iso_scope` flag |
| On-hire trigger | Same `AssignmentTrigger` mechanism as HIPAA |
| Disciplinary linkage | Same `SanctionEvent` entity as HIPAA |

---

## 5. Data Model Implications

Additions on top of v1 base model (much overlap with HIPAA):

- `Course.framework_tags` includes `iso27001` with sub-tags per Annex A control.
- `Course.annex_a_controls` — array of control identifiers.
- `Course.training_type` — `awareness` | `competence`.
- `User.in_iso_scope` — boolean.
- `AssignmentTrigger` — shared with HIPAA.
- `SanctionEvent` — shared with HIPAA.
- `TrainingMetric` — periodic aggregates (completion rate, average score, time-to-completion) per course per period; supports continual improvement evidence.

---

## 6. Audit Trail & Evidence Requirements

Certification body auditors will request:

1. **ISMS scope statement** showing which personnel are in scope.
2. **Awareness training program documentation** (topics, cadence, delivery method).
3. **Training matrix:** per-person, per-course, per-period completion.
4. **Sample testing:** auditor picks 5–15 people and asks for full evidence packs.
5. **Continual improvement evidence:** metrics trending, what was changed in response.
6. **Annex A control mapping:** which courses satisfy which controls.

The system should produce all of these as exports, with the Annex A mapping being the most ISO-specific element.

---

## 7. Retention Requirements

ISO 27001 does not specify training-record retention. Common practice is **3 years minimum** (covering the certification cycle). Most organizations apply the longest retention from any applicable framework — so SOX's 7 years dominates if SOX also applies.

---

## 8. User Rights & Access Controls

ISO 27001 does not grant individual rights but does require RBAC and the principle of least privilege as ISMS controls. The system's role model already satisfies this.

---

## 9. Conflicts with Other Frameworks

ISO 27001 is broadly compatible with all other frameworks in this set. Building for ISO 27001's training matrix is **additive**, not conflicting.

---

## 10. Implementation Checklist for ISO 27001 Support (Post-v1)

- [ ] `Course.framework_tags` ISO values with Annex A sub-tags
- [ ] `Course.annex_a_controls` array
- [ ] `Course.training_type` enum
- [ ] `User.in_iso_scope` flag
- [ ] `AssignmentTrigger` engine (shared with HIPAA)
- [ ] `SanctionEvent` entity (shared with HIPAA)
- [ ] `TrainingMetric` aggregation (nightly batch job)
- [ ] Annex A control coverage report (which controls are satisfied by which courses)
- [ ] Training matrix export grouped by Annex A control
- [ ] Continual improvement evidence: year-over-year trends report
- [ ] Default content library includes ISO 27001 awareness courses mapped to Annex A.6.3, A.5.10, A.6.7, A.8.1

---

*End of ISO/IEC 27001 framework reference.*
