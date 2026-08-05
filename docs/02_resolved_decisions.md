# Compliance Training & Tracking System — Resolved Decisions

**Document type:** Locked specification (post-clarification)
**Stage:** Locked — build in progress
**Supersedes:** `compliance_training_system_analysis.md` (Sections 4 & 8)
**Status:** Decisions below are locked and still authoritative. The data model, audit
chain, and state machines described here are implemented; see
[`../README.md`](../README.md) for build status and
[`00_architecture.md`](./00_architecture.md) for how these decisions became architecture.

> **Reading note.** This document records *what was decided and why*, at the time it was
> decided. It is not updated as code ships — that is the README's job. Where it says
> "future" or "out of scope for v1", read that as v1 *deployment* scope, not as a statement
> about what the system can represent.

---

## 1. Executive Summary

A compliance training and tracking system for **John Thomas Corporate**, scoped initially to **SOX (Sarbanes-Oxley)** compliance training. Single-tenant deployment. Users (employees and contractors) are assigned video-based training courses with quiz assessments, scored against a configurable pass threshold. The system tracks attempts, time, answers (right and wrong), enforces a per-course cooldown, and issues SOX-grade audit-evidence trails and completion certificates.

---

## 2. Scope & Deployment Model

| Decision | Value |
|---|---|
| Tenancy | **Single-tenant** for John Thomas Corporate |
| Multi-tenant readiness | Data model carries `tenant_id` from day one (defence against future re-platforming) but RLS / tenant-isolation enforcement is **not** built in v1 |
| Regulatory framework (v1) | **SOX (Sarbanes-Oxley) Section 404** |
| Future frameworks | FCPA / HIPAA / GDPR / ISO 27001 / PCI DSS — out of v1 *deployment* scope, design must not preclude. Reference documents for all six are authored under [`frameworks/`](./frameworks) and are live inputs to the definitions library; no domain rule is SOX-specific. See [`00_architecture.md` §4](./00_architecture.md#4-extensibility-how-a-new-regulatory-domain-is-added) |
| Deployment | Cloud-hosted (recommended: Railway or AWS, consistent with existing WeGoFwd patterns) |

---

## 3. Resolved Functional Requirements

Each original requirement is restated below with its locked-in clarification.

### FR1 — User identity

- Primary key: synthetic immutable `user_id` (UUID).
- `email`, `first_name`, `last_name` are mutable attributes; `email` is unique within the tenant.
- Attributes captured: `user_type` (`employee` | `contractor`), `department`, `manager_user_id`, `status` (`active` | `inactive` | `on_leave`).
- Email change does not break historical records.

### FR2 — Quiz result tracking

- Every quiz attempt records each question-answer pair.
- Each `AttemptAnswer` snapshots the **question version** at time of attempt, the **selected option(s)**, the **correct option(s) at that time**, the **outcome** (correct | incorrect | partial), and **time spent on question** (server-validated).
- Question types in scope for v1: single-select multiple-choice, true/false. Multi-select and free-text deferred to v2.

### FR3 — Wrong + correct answers captured

- Server stores both the user's selection and the canonical correct answer per `AttemptAnswer` row.
- Both are version-pinned; updates to question content do not retroactively alter historical records.

### FR4 — Ranking model

- **Score-based** (no percentile or band).
- Score = `(correct_question_weight_sum / total_question_weight_sum) * 100`, expressed as a percentage.
- Weights default to 1 (equal weight) but are configurable per question.
- **Pass threshold** is configurable per course; system default 80%.

### FR5 — Retry policy

- On a failed attempt, a retry is generated containing **only the wrongly-answered questions** from the previous attempt.
- The user passes the assignment when their **cumulative correct-answer set** crosses the pass threshold.
- Video re-watch is **not mandatory** before retry, but the UI exposes a "Review video" action for the user to invoke voluntarily.

### FR6 — Time and attempt tracking

- Each attempt records `started_at`, `submitted_at`, `total_active_seconds` (excluding tab-blur idle time).
- Each `AttemptAnswer` records `time_spent_seconds` per question.
- `attempt_number` is monotonic per assignment.

### FR7 — Concurrent assignment rule

- Refined from the original: **a user may have multiple assignments in `ASSIGNED` state, but only one in `IN_PROGRESS` state at a time.**
- Starting attempt N+1 on a new assignment is blocked while another assignment is `IN_PROGRESS`.
- Rationale: real compliance environments routinely require overlapping assignments (new-hire stack, annual refreshers, role-change triggers); restricting *active engagement* preserves UX simplicity without breaking real workflows.

### FR8 — Cooldown rule

- **Configurable per course** via `Course.cooldown_days`.
- Applies after the assignment reaches a **terminal state** — either `PASSED` or `BLOCKED` (both attempts exhausted, failed).
- Detailed semantics in Section 4 below.

### FR9 (new) — Maximum attempts

- `max_attempts = 2` per assignment (system constant for v1; could be made per-course in future).
- Reaching the max-attempts ceiling without passing transitions the assignment to `BLOCKED` and notifies the user's manager.
- A `BLOCKED` assignment can only be resolved by manager / compliance admin intervention (e.g., a new assignment created after the cooldown).

---

## 4. Cooldown & Retry Semantics — Locked (Scenario B)

The interaction between max-attempts and cooldown is the trickiest piece of the spec. The agreed model is:

### 4.1 Within an assignment

- Attempt 1 fails → user may immediately start attempt 2 (subject to FR7: no other assignment is `IN_PROGRESS`).
- Attempt 2 retries only the questions wrongly answered in attempt 1.
- The user passes if their cumulative correct set reaches the pass threshold.
- No cooldown applies between attempts of the same assignment.

### 4.2 At assignment terminal state

- Assignment terminal states: `PASSED`, `BLOCKED`, `CANCELLED`, `EXPIRED`.
- Cooldown begins at the timestamp of terminal-state transition for `PASSED` and `BLOCKED`.
- During cooldown, **no new assignment for the same course** can be created for that user.

### 4.3 Cooldown duration semantics

- `cooldown_days` is set per course.
- Applies identically to both `PASSED` and `BLOCKED` outcomes (matches the answered policy).
- Suggested defaults:
  - SOX annual refresher courses: 365 days.
  - High-risk topical courses: 90 days.
  - Remedial/short courses: 30 days.

### 4.4 Worked example flows

**Flow A — Pass on first attempt:**
`ASSIGNED → IN_PROGRESS (attempt 1) → SUBMITTED → PASSED → certificate issued → cooldown timer starts → next assignment allowed after cooldown_days`

**Flow B — Fail then pass:**
`ASSIGNED → IN_PROGRESS (attempt 1) → SUBMITTED → FAILED → IN_PROGRESS (attempt 2, wrong-questions-only) → SUBMITTED → PASSED → certificate issued → cooldown starts`

**Flow C — Both attempts fail:**
`ASSIGNED → IN_PROGRESS (attempt 1) → SUBMITTED → FAILED → IN_PROGRESS (attempt 2) → SUBMITTED → FAILED → BLOCKED → manager notified → cooldown starts → no re-assignment until cooldown elapses`

---

## 5. SOX Compliance Requirements (Baked Into Spec)

These are non-negotiable given SOX framework selection.

| Requirement | Implementation |
|---|---|
| **Tamper-evident audit trail** | Append-only `AuditLog` table; every state transition writes a row. Periodic export to immutable storage (S3 Object Lock, retention-locked bucket). Optional chain-of-custody hash linking sequential rows. |
| **User attestation at completion** | At certificate issuance, user must explicitly check: *"I attest that I completed this training myself and understand the material."* Captured: timestamp, IP, browser fingerprint, attestation text version. |
| **Separation of duties** | A user with the `ContentAuthor` role on a course **cannot** be a `Trainee` on the same course. Enforced at assignment-creation time. |
| **7-year record retention** | All `Attempt`, `AttemptAnswer`, `Certificate`, and `AuditLog` rows retained ≥7 years from creation. Deletion before that requires explicit compliance-admin override with audit log entry. |
| **Auditor read-only access** | Dedicated `Auditor` role: read-only access to attempts, certificates, audit log. Exportable to CSV and PDF (audit-binder format). |
| **User-deletion conflict resolution** | On user departure or erasure request: pseudonymize PII fields (`email`, `first_name`, `last_name`) by replacing with hashes; retain all training records linked to immutable `user_id`. |

---

## 6. Data Model — Locked Entity List

Entities for v1 (multi-tenant-ready columns included even though tenancy is not enforced):

- **Tenant** — `tenant_id`, `name`. Single row in v1; reserved for future.
- **User** — `user_id` (UUID), `tenant_id`, `email`, `first_name`, `last_name`, `user_type`, `department`, `manager_user_id`, `status`, `pseudonymized` (bool), `created_at`, `updated_at`.
- **Role** — `role_id`, `name` (Trainee | Manager | ContentAuthor | ComplianceAdmin | Auditor).
- **UserRole** — `user_id`, `role_id`, `scope` (global | per-course).
- **Course** — `course_id`, `tenant_id`, `title`, `description`, `current_version_id`, `cooldown_days`, `pass_threshold_pct`, `created_at`, `archived_at`.
- **CourseVersion** — `version_id`, `course_id`, `version_number`, `published_at`, `published_by_user_id`, `video_asset_id`, `min_watch_pct` (default 0 for v1, available for v2 hardening), `is_active`.
- **Question** — `question_id`, `course_version_id`, `question_text`, `question_type`, `weight`, `version_number`.
- **AnswerOption** — `option_id`, `question_id`, `option_text`, `is_correct`, `display_order`.
- **Assignment** — `assignment_id`, `user_id`, `course_id`, `course_version_id` (snapshot at assignment time), `assigned_at`, `assigned_by_user_id`, `due_at`, `status`, `terminal_at` (nullable), `cooldown_until` (nullable, computed at terminal transition).
- **Attempt** — `attempt_id`, `assignment_id`, `attempt_number`, `started_at`, `submitted_at`, `score_pct`, `outcome`, `total_active_seconds`.
- **AttemptAnswer** — `attempt_answer_id`, `attempt_id`, `question_id`, `question_version`, `selected_option_ids` (array), `correct_option_ids_snapshot` (array), `is_correct`, `time_spent_seconds`.
- **Certificate** — `certificate_id`, `user_id`, `course_id`, `course_version_id`, `issued_at`, `expires_at` (= `issued_at + cooldown_days`), `verification_code`, `pdf_asset_id`, `attestation_text_version`, `attestation_ip`, `attestation_timestamp`.
- **AuditLog** — `audit_id` (sequence), `tenant_id`, `actor_user_id`, `entity_type`, `entity_id`, `event_type`, `payload_json`, `occurred_at`, `prev_audit_hash` (optional chain-of-custody field).

---

## 7. Assignment State Machine — Locked

```
                                    ┌────────────────────┐
                                    │                    │
                                    ▼                    │
   ┌─────────┐    start    ┌─────────────┐  submit   ┌───────────┐
   │ASSIGNED │────────────▶│ IN_PROGRESS │──────────▶│ SUBMITTED │
   └─────────┘             └─────────────┘           └───────────┘
        │                                                  │
        │ cancel                                           │ score
        ▼                                                  ▼
   ┌─────────┐                                    ┌────────────────┐
   │CANCELLED│                                    │ pass?          │
   └─────────┘                                    └────────────────┘
                                                    │           │
                                              pass  │           │  fail
                                                    ▼           ▼
                                            ┌────────┐   ┌──────────────┐
                                            │ PASSED │   │ attempts<max?│
                                            └────────┘   └──────────────┘
                                                  │       yes │     │ no
                                            cooldown          │     ▼
                                                  ▼           │  ┌─────────┐
                                           [re-assignable]    │  │ BLOCKED │
                                                              │  └─────────┘
                                                              │       │
                                                              │       │ cooldown
                                                              ▼       ▼
                                                        (back to ASSIGNED)  [re-assignable]
                                                       creating attempt N+1
                                                       restricted to wrong
                                                       questions
```

State transition triggers:
- `ASSIGNED → IN_PROGRESS`: user starts the attempt (FR7 single-active-assignment guard applies here).
- `IN_PROGRESS → SUBMITTED`: user submits or timeout fires.
- `SUBMITTED → PASSED | (back to IN_PROGRESS) | BLOCKED`: deterministic on score and attempt count.
- `PASSED → cooldown`: writes `terminal_at`, computes `cooldown_until`.
- `BLOCKED → cooldown + manager notification`: writes `terminal_at`, computes `cooldown_until`, fires notification job.

Every transition writes an `AuditLog` row.

---

## 8. v1 Scope & Integrations

### 8.1 In scope for v1

- User CRUD (manual + CSV bulk upload).
- Course + CourseVersion + Question CRUD via admin UI.
- Video upload and playback.
- Assignment creation (manual + CSV bulk).
- Quiz attempt + retry-on-wrong-questions flow.
- Score-based pass/fail with configurable threshold.
- Cooldown enforcement.
- Certificate generation (PDF) with attestation.
- Audit log (append-only, queryable).
- Role-based access control.
- Trainee, Manager, Compliance Admin, Auditor dashboards (basic).

### 8.2 Required integrations for v1

| Integration | Purpose | Recommendation |
|---|---|---|
| SMTP / email | Notifications, reminders, escalations | AWS SES or SendGrid |
| SSO | Authentication | Auth0 / Clerk / WorkOS — supports SAML and OIDC for John Thomas's existing IdP |
| Object storage | Video assets, certificate PDFs | AWS S3 (with Object Lock for audit log archive bucket) |

### 8.3 Out of scope for v1 (queued for later phases)

- HRIS auto-assignment (Workday / BambooHR sync).
- SCORM / xAPI export for LMS interoperability.
- Multi-language localisation.
- WCAG 2.1 AA accessibility audit pass.
- Anti-cheating signals (tab-blur logging, copy-paste blocking, browser fingerprinting beyond attestation).
- Question bank and randomisation.
- Multi-select / free-text question types.
- Video minimum-watch-percentage enforcement.

---

## 9. Phased Roadmap

| Phase | Focus | Key deliverables |
|---|---|---|
| **v1** | MVP core loop | Sections 8.1 + 8.2 |
| **v2** | Compliance hardening | Question bank + randomisation, anti-cheat signals, video min-watch %, multi-select questions |
| **v3** | Integrations | HRIS auto-assign, SCORM/xAPI export |
| **v4** | Multi-tenancy enablement | Postgres RLS, tenant onboarding flows, billing |
| **v5** | Scale & polish | Localisation, accessibility audit, mobile app, advanced reporting |

---

## 10. Assumptions

The following assumptions are baked into this specification. Flag any that are wrong:

1. **"John Thomas" refers to a specific corporate client** (John Thomas Corporate). If this is a placeholder for a generic corporate customer, the deployment model becomes multi-tenant from v1 and Section 2 changes.
2. **US-only deployment.** No GDPR / CCPA exposure in v1. (Pseudonymization design is still included as forward-protection.)
3. **English-only content** in v1.
4. **Desktop browser primary.** Mobile web supported but not mobile-app-native.
5. **Video content is pre-recorded** and uploaded by content authors. No live-session training in scope.
6. **Quiz questions are authored manually**, not generated from video transcripts.
7. **Certificates do not require external notarization** — internal verification code suffices for SOX.
8. **John Thomas's existing IdP supports SAML or OIDC.** If they're on a legacy auth system, SSO scope expands.

---

## 11. Open Items (Not Blocking, But Track)

- Pass threshold default — proposed 80%, awaiting compliance officer confirmation.
- Cooldown defaults per course — proposed 365/90/30 day tiers, awaiting confirmation.
- Manager-notification escalation cadence (T-7d / T-1d / T+0 / T+7d) — confirm with stakeholders.
- Certificate PDF template and branding — design pass needed.
- Audit log immutability mechanism — Postgres-only append-only vs. S3 Object Lock vs. chain-of-custody hashing — pick one based on operational complexity tolerance.

---

## 12. Next Steps

1. Stakeholder sign-off on this document.
2. Resolve the assumptions in Section 10 (especially #1 — John Thomas).
3. Generate the **OpenSpec API specification** for the v1 surface area.
4. Generate the **SQLAlchemy data model** (Python) with Alembic migrations from Section 6.
5. Scaffold the FastAPI service with Section 7's state machine encoded as a guarded transition module.
6. Write pytest test suite covering state-machine invariants (with `hypothesis` for property-based tests on the transition graph).

---

*End of resolved decisions document.*
