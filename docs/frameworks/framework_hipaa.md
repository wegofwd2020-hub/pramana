# Framework Reference: HIPAA

**Status:** ⏳ Future phase (target v2)
**Jurisdiction:** United States
**Primary regulator:** US Department of Health and Human Services, Office for Civil Rights (HHS OCR)

> ⚠️ **Disclaimer:** This is an engineering reference, not legal advice. Confirm framework interpretation with John Thomas Corporate's compliance counsel before treating any of this as binding.

---

## 1. Framework Overview

The **Health Insurance Portability and Accountability Act of 1996** (HIPAA), as amended by the HITECH Act of 2009 and the Omnibus Rule of 2013, governs the protection of Protected Health Information (PHI) in the United States.

Three rules drive training requirements:

- **Privacy Rule** (45 CFR §164.530(b)) — Covered Entities must train all workforce members on PHI policies and procedures.
- **Security Rule** (45 CFR §164.308(a)(5)) — Covered Entities and Business Associates must implement a security awareness and training program.
- **Breach Notification Rule** (45 CFR §164.400-414) — Workforce must be trained to recognize and report breaches.

HIPAA applies to **Covered Entities** (healthcare providers, health plans, healthcare clearinghouses) and **Business Associates** (vendors that handle PHI on behalf of Covered Entities).

---

## 2. Why It Matters for Compliance Training Systems

HHS OCR conducts both proactive audits and breach-triggered investigations. When investigating, they request training records as evidence of "reasonable safeguards." Civil monetary penalties for HIPAA violations range from $137 to $68,928 per violation (2024 figures, indexed annually), with annual caps up to $2.06 million per violation category.

A training system that cannot produce HIPAA-grade evidence puts the customer at direct financial and reputational risk.

---

## 3. Training Requirements Imposed by HIPAA

### 3.1 Privacy Rule training

- **Who:** all workforce members (employees, volunteers, trainees, contractors).
- **When:**
  - To each new workforce member within a reasonable period after hire.
  - To each existing member whose functions are affected by a material change in PHI policies.
  - Periodically thereafter (annual is the de facto standard, though not statutorily fixed).

### 3.2 Security Rule training

- Must be a **program**, not a one-time event.
- Required topics include:
  - Security reminders (periodic updates).
  - Protection from malicious software.
  - Log-in monitoring.
  - Password management.

### 3.3 Breach awareness training

- Workforce must be trained on what constitutes a breach and how to report.
- Recipients of breach notifications (OCR, affected individuals, sometimes media) and timelines (60 days) must be understood by relevant staff.

### 3.4 Role-based variation

HIPAA explicitly allows training to be tailored to function. Clinical staff, billing staff, IT, and executive staff need different content. The system must support **role-based training paths**, not one-size-fits-all.

---

## 4. System Design Implications

| Requirement | Implementation |
|---|---|
| New-hire training trigger | Need an `assignment_trigger` mechanism: on user creation with role X, auto-create assignments for courses tagged for that role |
| Material policy change retraining | Need a "material change" event on `CourseVersion` that re-triggers assignment for all in-scope users |
| Role-based paths | `Course.applicable_roles` array; assignment-creation rules filter on this |
| Periodic refresh | `Course.cooldown_days` already supports this |
| Topic tagging for HIPAA | `Course.framework_tags` includes `"hipaa"`, with sub-tags like `hipaa.privacy`, `hipaa.security`, `hipaa.breach` |
| Tracking who has access to PHI | Beyond the training system: link `User.phi_access_level` to required training path |
| Sanction policy | HIPAA requires sanction policy for non-compliance; system must capture sanction events linked to training failures |

---

## 5. Data Model Implications

Additions on top of v1 base model:

- `Course.applicable_roles` — array; an assignment-creation rule filters courses by role.
- `Course.framework_tags` — extended to include HIPAA tags.
- `User.phi_access_level` — enum (`none` | `limited` | `full`); drives required training path.
- `AssignmentTrigger` — entity describing automatic assignment rules: `trigger_type` (`on_hire`, `on_role_change`, `on_policy_update`, `periodic`), `course_id`, `role_filter`, `phi_access_filter`.
- `CourseVersion.is_material_change` — boolean; if true on publish, system re-assigns to all in-scope users.
- `SanctionEvent` — entity recording disciplinary action linked to training failures or PHI mishandling. `user_id`, `event_date`, `description`, `recorded_by`.

---

## 6. Audit Trail & Evidence Requirements

OCR investigators typically request, on a timeline of 30–60 days:

1. **Workforce roster** during the period under review, with PHI access classifications.
2. **Training program documentation** — what topics, what cadence, what tailoring by role.
3. **Completion records** for each workforce member.
4. **Sanction policy documentation** and any sanction events.
5. **Material change log** — when policies changed and how training responded.

Evidence must be producible for any historical date (not just current state). The system's audit trail must support point-in-time queries.

---

## 7. Retention Requirements

- **Source:** 45 CFR §164.530(j) requires Covered Entities to retain documentation of policies, procedures, and required actions/activities/assessments for **6 years** from creation or last effective date, whichever is later.
- **Implementation:** Apply same 7-year retention as SOX (the stricter standard); satisfies HIPAA automatically.

---

## 8. User Rights & Access Controls

HIPAA does not give individuals a right to delete training records about themselves (those are administrative records, not PHI). However, organizational practice should permit:

- Workforce member views their own training history (HIPAA does not require, but is best practice).
- Manager views direct reports' status.
- Privacy Officer role (typically maps to `ComplianceAdmin`) views all training data.
- HHS OCR investigator access (typically via export, not direct system access) — the `Auditor` role with export covers this.

---

## 9. Conflicts with Other Frameworks

| Other framework | Conflict | Resolution |
|---|---|---|
| **GDPR** Article 17 | If a workforce member is also an EU data subject (e.g., a remote employee in the EU), tension between erasure right and HIPAA retention | Pseudonymize PII; retain administrative training records |
| **SOX** | None substantive — building for SOX evidence quality satisfies HIPAA's evidence quality |

---

## 10. Implementation Checklist for HIPAA Support (Post-v1)

- [ ] Add `framework_tags` HIPAA values: `hipaa.privacy`, `hipaa.security`, `hipaa.breach`
- [ ] Add `Course.applicable_roles` and `User.phi_access_level`
- [ ] Build `AssignmentTrigger` engine for `on_hire`, `on_role_change`, `on_policy_update`
- [ ] Add `CourseVersion.is_material_change` flag and re-assignment workflow
- [ ] Add `SanctionEvent` entity
- [ ] Extend `Auditor` export to produce HIPAA-format evidence binder
- [ ] Build "point-in-time" query capability so auditors can ask "what was training status of user X on date Y"
- [ ] Document the program in customer-facing form (HIPAA Security Awareness Program description)
- [ ] Privacy Officer role mapping documented
- [ ] Breach reporting training course included in default content library

---

*End of HIPAA framework reference.*
