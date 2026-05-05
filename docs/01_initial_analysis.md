# Compliance Training & Tracking System — Robustness Analysis

**Document type:** Requirements critique & enhancement proposal
**Stage:** Pre-design / scoping
**Audience:** Product owner, engineering lead, compliance stakeholders

---

## 1. Executive Summary

The eight stated requirements form a workable skeleton for a compliance training system, but several are under-specified in ways that will cause production pain — undefined scoring semantics, ambiguous cooldown rules, and a single-assignment constraint that conflicts with real-world compliance scheduling. Critical concerns are also entirely absent from the brief: question versioning, video watch verification, certificate expiry, audit trail, and multi-tenancy.

This document walks through each stated requirement, identifies gaps, lists ambiguities the team must resolve before design, and proposes a more robust target architecture.

---

## 2. Point-by-Point Review of Stated Requirements

### R1 — Email as unique user ID + first/last name

**Concerns:**
- Emails change (marriage, rebranding, contractor moving between agencies). Using email as the **primary key** locks identity to a mutable attribute. Use a synthetic immutable `user_id` (UUID) and treat email as a unique-but-mutable lookup key.
- No concept of **user type** (employee vs contractor). Compliance reporting almost always requires this split.
- No **org/department/manager** linkage — managers need to see their reports' compliance status.
- No **active/inactive** status. What happens when someone leaves mid-training?
- No **multi-tenancy** consideration. If WeGoFwd sells this as SaaS, tenant isolation must be in the model from day one — not retrofitted.

### R2 — Track quiz results per question

**Concerns:**
- "Result" is binary (right/wrong) only? What about **multi-select**, **fill-in-the-blank**, **drag-and-drop**, **partial credit**?
- No concept of **question versioning**. If a question is updated post-deployment, historical attempts must remain attached to the version answered, not the current version. This is a compliance audit requirement.
- No **question bank / randomization**. Ten users taking the same quiz with the same questions in the same order is a cheating vector.
- No **time-per-question** capture (only total time per attempt is implied).

### R3 — Capture every wrong + correct answer

**Concerns:**
- "Correct answer" — captured per attempt or per question definition? Both, ideally, because the canonical correct answer can change over time as content is updated.
- No mention of capturing the **answer the user actually selected** (only "wrong/correct"). For audit and analytics, you want the full selection, not just the boolean outcome.

### R4 — Ranking based on correct/wrong answers

**Critical ambiguity:** "Ranking" is undefined. This needs a stakeholder decision before any design work:
- Is it a **score** (% correct)?
- Is it a **letter grade** / band (Pass / Merit / Distinction)?
- Is it a **percentile rank** relative to other learners (genuine ranking)?
- Are questions **weighted** by difficulty or topic criticality?

Most compliance platforms use a simple pass-mark threshold (e.g., ≥80%) rather than ranking. Real ranking creates perverse incentives in a compliance context.

### R5 — Repeat wrong questions until pass threshold

**Concerns:**
- **Infinite-loop risk**: what's the max-attempts ceiling? Without one, a user can grind indefinitely until they memorise the answer key — defeating the purpose.
- Does "repeat" mean **only the wrongly-answered questions** or **a fresh quiz**? The former encourages memorisation; the latter is fairer but harder.
- Should the user be required to **re-watch the video** (or the relevant segment) before retry? Best practice says yes.
- What if the same question is wrong on N consecutive retries? Escalate to manager? Force video re-watch?

### R6 — Track time and number of attempts

**Concerns:**
- "Time" — total elapsed wall-clock, or active engagement time (excluding tab-switching)? These differ by an order of magnitude in real data.
- What constitutes an "attempt"? Started? Submitted? Quiz opened but abandoned? Browser crashed mid-quiz?
- No mention of **session resume** behaviour if the user disconnects mid-quiz.

### R7 — Only 1 training assigned at a time

**This rule is likely wrong as written.**

Real compliance environments routinely require concurrent assignments:
- New hires get 5–10 mandatory courses in week one.
- Annual refreshers (harassment, security, data privacy) often overlap.
- Role changes trigger new training while old training is still pending.

Suggested reframe: **Only one *active in-progress* training session at a time** (i.e., the user can have many *assigned*, but is only working on one right now). This preserves UX simplicity without breaking real workflows.

### R8 — 60-day cooldown after previous attempt

**Critical ambiguity:** Cooldown after a *passed* attempt or *any* attempt?
- After **pass** → makes sense (don't re-train someone who just certified).
- After **fail** → makes no sense (someone who failed yesterday should be re-trained sooner, not blocked for two months).

Also: "60 days" should be a **policy parameter** per course, not a system-wide constant. Some regulations require annual (365-day), some quarterly (90-day), some 30-day for high-risk topics.

---

## 3. Critical Gaps (Not in the Brief at All)

| Gap | Why it matters |
|---|---|
| **Video watch verification** | If you can't prove the user actually watched the video, the quiz score is meaningless for compliance. Need heartbeat tracking, anti-skip, and minimum-watch-percentage. |
| **Course/content versioning** | Regulations change. When the SOX content updates, you need to know which users were certified on which version. |
| **Certificate generation & expiry** | Compliance requires a tangible artefact (PDF certificate) with issue date, expiry date, and verification ID. |
| **Audit trail (immutable log)** | Every state transition (assigned, started, answered, passed, certificate issued) must be logged tamper-evident for regulators. |
| **Multi-tenancy** | If this is SaaS, tenant isolation must be in the data model from day one. |
| **Role-based access control** | Trainee, Manager, Compliance Admin, Auditor, Content Author — minimum five roles. |
| **Notifications & escalation** | Due-date reminders, overdue alerts to manager, escalation to skip-level after N days. |
| **Reporting & dashboards** | Manager view of team status, compliance officer view of org status, regulator-ready exports. |
| **Anti-cheating signals** | Tab-switch detection, copy-paste blocking, time-per-question outliers, browser fingerprinting. |
| **Data retention & GDPR** | How long are training records kept? Right-to-erasure vs. compliance-record-retention conflict. |
| **Integrations** | SSO (SAML/OIDC), HRIS sync (Workday, BambooHR) for auto-assignment on hire, LMS standards (SCORM/xAPI). |
| **Accessibility (WCAG 2.1 AA)** | Often a compliance requirement *of* the compliance training itself. |
| **Localisation** | Multi-language video + quiz support if the org is non-US. |
| **Idempotency on quiz submission** | Network retries must not double-submit answers. |
| **Concurrency on attempts** | Two browser tabs submitting different answers — needs server-side attempt locking. |

---

## 4. Ambiguities Requiring Stakeholder Decisions

Before any design or coding, get explicit answers to these:

1. **What is "rank"?** Score, percentile, or band?
2. **Does the 60-day cooldown apply after pass, fail, or both?**
3. **Is the cooldown global (60 days) or configurable per course?**
4. **On retry, does the user redo only wrong questions, or a fresh quiz?**
5. **Is there a max-attempt ceiling? What happens at the ceiling?**
6. **Is "one training at a time" about assignment or active engagement?**
7. **Must the user re-watch the video before retrying the quiz?**
8. **How long are records retained? What's the deletion policy?**
9. **Is this single-tenant (internal tool) or multi-tenant (SaaS product)?**
10. **What integrations are in scope for v1 (SSO at minimum)?**

---

## 5. Recommended Enhancements

### 5.1 Data Model (Conceptual)

Core entities and the relationships you'll want from day one:

- **Tenant** — root of the isolation tree (if SaaS).
- **User** — `user_id` (UUID, immutable), `email` (unique within tenant, mutable), `first_name`, `last_name`, `user_type` (employee/contractor), `department`, `manager_id`, `status` (active/inactive/on_leave), `tenant_id`.
- **Course** — `course_id`, `title`, `current_version_id`, `cooldown_days`, `pass_threshold_pct`, `max_attempts`, `requires_video_rewatch_on_retry` (bool).
- **CourseVersion** — `version_id`, `course_id`, `version_number`, `published_at`, `video_asset_id`, `min_watch_pct`, `is_active`.
- **Question** — `question_id`, `course_version_id`, `question_text`, `question_type` (single/multi/tf/fill), `weight`, `version_number`.
- **AnswerOption** — `option_id`, `question_id`, `option_text`, `is_correct`.
- **Assignment** — `assignment_id`, `user_id`, `course_id`, `course_version_id` (snapshot at assignment time), `assigned_at`, `due_at`, `assigned_by`, `status` (assigned/in_progress/passed/failed/expired/cancelled).
- **Attempt** — `attempt_id`, `assignment_id`, `attempt_number`, `started_at`, `submitted_at`, `score_pct`, `outcome` (pass/fail), `total_active_seconds`.
- **AttemptAnswer** — `attempt_id`, `question_id`, `question_version` (snapshot), `selected_option_ids`, `is_correct`, `time_spent_seconds`.
- **VideoWatchEvent** — heartbeat records of watch progress (`attempt_id` or `assignment_id`, `position_seconds`, `event_type`, `timestamp`).
- **Certificate** — `certificate_id`, `user_id`, `course_version_id`, `issued_at`, `expires_at`, `verification_code`, `pdf_asset_id`.
- **AuditLog** — append-only, every state transition.

### 5.2 Assignment State Machine

```
ASSIGNED → IN_PROGRESS → SUBMITTED → PASSED  → (CERTIFICATE_ISSUED) → EXPIRED (after cert lifetime)
                                  ↘ FAILED   → ASSIGNED (retry, if attempts remaining)
                                             → BLOCKED (max attempts reached, manager intervention)
            ↘ CANCELLED (user left org, course retired, etc.)
```

Every transition writes an `AuditLog` row. Transitions are guarded by server-side validators (e.g., `IN_PROGRESS → SUBMITTED` requires `min_watch_pct` met).

### 5.3 Cooldown Rule (Refined)

Replace "60 days from previous attempt" with:
> A user cannot be re-assigned to course C if they have a **passing** attempt for C with `(now - passed_at) < course.cooldown_days`. Failed attempts do not trigger cooldown — the user should retry promptly.

Configurable per course; default to 365 days for annual compliance topics.

### 5.4 Retry Policy (Refined)

On fail:
1. If `attempt_number >= course.max_attempts` → state = `BLOCKED`, notify manager.
2. Otherwise, generate a new attempt scoped to **wrong-answered questions only**, optionally re-shuffled with sibling questions from a question pool to prevent pure memorisation.
3. If `course.requires_video_rewatch_on_retry`, gate the attempt on watching the relevant video segment(s) tagged to the wrong questions.

### 5.5 Anti-Cheating Hardening

- Server-issued question order and option order (never trust the client).
- Time budget per question, server-validated on submission.
- Heartbeat from video player; mark `IN_PROGRESS` invalid if heartbeat gaps exceed threshold.
- Tab-blur and copy-paste events logged (not blocking, but flagged for review).
- IP / device fingerprint logged per attempt for audit.

### 5.6 Notification & Escalation

- T-7d before due date: reminder to user.
- T-1d: reminder to user + cc manager.
- T+0 (overdue): user + manager.
- T+7d overdue: skip-level + compliance officer.
- All driven by a scheduled job (Celery/RQ/APScheduler) reading from `Assignment.due_at`.

### 5.7 Reporting Surface

Minimum dashboards:
- **Trainee:** my assignments, my certificates, due dates.
- **Manager:** team status, overdue list, drill into individual.
- **Compliance Admin:** org-wide status by course, overdue heatmap, export (CSV/PDF) for regulators.
- **Auditor (read-only):** audit log search, certificate verification.

### 5.8 Multi-Tenancy

Given WeGoFwd's existing multi-tenant pattern (Thittam), recommend the same approach here: `tenant_id` foreign key on every domain table, enforced at the ORM/repository layer with row-level filters. Do **not** rely on application logic alone — use Postgres row-level security (RLS) as defence-in-depth.

---

## 6. Suggested Tech Stack (Python-aligned)

| Layer | Recommendation |
|---|---|
| Web framework | FastAPI (async, OpenAPI-native — aligns with your OpenSpec doc preference) |
| ORM | SQLAlchemy 2.x with Alembic migrations |
| DB | PostgreSQL (RLS for tenancy, JSONB for flexible quiz answer storage) |
| Background jobs | Celery + Redis, or RQ for simpler footprint |
| Video storage / streaming | S3 + CloudFront signed URLs, or Mux / Cloudflare Stream for built-in DRM and watch analytics |
| Auth | Auth0 / Clerk / WorkOS for SSO out of the box |
| PDF certificates | WeasyPrint or ReportLab |
| Audit log | Append-only Postgres table + periodic export to immutable storage (S3 Object Lock) |
| Testing | pytest + pytest-asyncio + factory_boy for mock data + hypothesis for property-based tests on state machine transitions |
| Observability | Structured logs (structlog), OpenTelemetry, Sentry |

---

## 7. Recommended Phased Delivery

**Phase 1 — MVP (single-tenant, core loop):**
User CRUD, course CRUD, video upload, single quiz attempt, pass/fail, basic dashboard.

**Phase 2 — Compliance hardening:**
Audit log, certificate generation, cooldown enforcement, retry policy, max attempts, video watch verification.

**Phase 3 — Multi-tenancy + integrations:**
Tenant isolation, SSO, HRIS auto-assignment, manager dashboards.

**Phase 4 — Anti-cheating + advanced reporting:**
Question pools, randomisation, anti-cheat signals, regulator exports, scheduled compliance reports.

**Phase 5 — Scale & polish:**
Localisation, accessibility audit, SCORM/xAPI export, mobile app.

---

## 8. Open Questions Block (for product owner)

> Please answer before design work begins. These are blocking, not nice-to-have.

1. Single-tenant internal tool, or multi-tenant SaaS?
2. Define "rank" precisely (score / percentile / band).
3. Cooldown applies after pass only, or pass + fail?
4. Is cooldown configurable per course?
5. Max-attempts ceiling — what's the number, and what happens at ceiling?
6. On retry, only wrong questions or full fresh quiz?
7. Is video re-watch mandatory before retry?
8. Record retention period, and policy on user-deletion requests?
9. Required integrations for v1?
10. Target regulatory frameworks (SOX, HIPAA, GDPR, ISO 27001)? Each has specific evidence requirements.

---

*End of analysis.*
