# Consumer Subscription & Lesson-Tracking — Design

**Date:** 2026-09-03
**Status:** Approved design; pending implementation plan.
**Author:** Pramana team (brainstormed with Claude Code).

## 1. Purpose

Add a **consumer self-serve** mode to Pramana, running **alongside** the existing
B2B manager-assigned compliance training. A consumer buys a *package* (one of
`fcpa`, `gdpr`, `hipaa`, `iso27001`, `pci-dss`, `platform`, `sox`), is shown the
lessons in that package, and for each lesson watches a video/audio story and then
takes a quiz. The system tracks, per user per lesson: how many times the lesson was
viewed, how many times the quiz was completed with every question correct, and the
date/time/duration of each interaction.

The B2B compliance product — its audited, hash-chained `Assignment` runtime with
cooldown, attestation, and certificate machinery — is **not modified**.

## 2. Locked decisions

These were settled during brainstorming and are inputs, not open questions:

| Decision | Choice |
|---|---|
| Product shape | Consumer mode **alongside** B2B (both live) |
| Payment | **Admin-granted** entitlement now; payment processor deferred, wired through the same grant path later |
| Consumer identity | Admin **creates the consumer `User` and grants the package** in one flow; no self-registration surface yet; reuse existing auth for consumer login |
| Completion rule | One quiz attempt scoring **100%** (every question correct). **Unlimited** retakes, **no cooldown**, **full question set** every attempt (no replay-only-wrong) |
| Package → lessons | **Explicit** `package` entity + `package_course` membership join (not derived from `framework_tags`) |
| Runtime bridge | **A′** — parallel consumer tables that reuse shared content (`Course`/`CourseVersion`/`Question`/`AnswerOption`) and the pure grader (`domain/scoring.py`); B2B `Assignment` untouched |
| Counters | **Denormalized** `view_count`/`completion_count` on `enrollment` + a recompute check that reconciles against the event tables |
| Quiz ≤5 questions | **Soft authoring guideline**, not a hard DB/structural cap |
| Admin role for grants | Reuse **`compliance_admin`** for v1 (a dedicated `catalog_admin` is a later split) |

### 2.1 Why A′ (parallel tables) rather than extending `Assignment`

The `assignment` table's CHECK constraints (`attempts_used <= max_attempts + 1`,
`cooldown_until_consistent`, `terminal_at_consistent`) are the teeth of the
compliance audit story. Consumer mode requires *unlimited* attempts and *no*
cooldown, which those checks forbid. Bolting a "consumer mode" onto `assignment`
would force mode-gating those CHECKs, weakening the guarantee for the audited rows
too. A parallel table keeps the invariants pristine and duplicates only thin
orchestration — content and grading are shared.

## 3. Data model

Seven new tables. All carry `tenant_id` (consumers live under one seeded **Consumer
tenant**). No existing table is altered.

### 3.1 `package` — the sellable unit

- `id` UUID PK, `tenant_id` FK
- `slug` (e.g. `sox`) — unique per tenant
- `title`, `description`, `cover_key` (nullable S3 key)
- `price_cents` (nullable — null = not yet priced), `currency` (default `usd`)
- `is_published` bool, `display_order` int
- timestamps, soft-delete

### 3.2 `package_course` — membership (many-to-many)

- `id` PK, `package_id` FK, `course_id` FK
- `display_order` int (lesson order within the package)
- `UNIQUE(package_id, course_id)`

A `Course` may belong to multiple packages; membership is curated, independent of
`framework_tags`.

### 3.3 `entitlement` — "user holds a package"

- `id` PK, `tenant_id`, `user_id` FK, `package_id` FK
- `status`: `active` | `revoked` | `expired`
- `granted_at`, `granted_by_user_id` (admin), `source`: `manual` | `stripe`
- `external_ref` (nullable — future payment/session id)
- `expires_at` (nullable — null = perpetual), `revoked_at` (nullable), `revoked_reason` (nullable)
- **Partial-unique index** on `(user_id, package_id) WHERE status = 'active'` — at most
  one active entitlement per user per package.

The grant path is the single seam a future Stripe webhook calls; manual grant and
paid grant differ only by `source`/`external_ref`.

### 3.4 `enrollment` — per-(user, lesson) progress anchor

Lazily created the first time a consumer opens a lesson they are entitled to.
Holds denormalized progress for a cheap lesson-list screen.

- `id` PK, `tenant_id`, `user_id` FK, `course_id` FK
- `entitlement_id` FK (provenance of access at first open)
- `first_accessed_at`, `last_accessed_at`
- `view_count` int default 0, `completion_count` int default 0
- `best_score_pct` float nullable
- `UNIQUE(user_id, course_id)`

`enrollment` is **progress state, not an access grant** — access is always checked
against a live `entitlement`. If the entitlement is later revoked, the enrollment row
remains as history but access is denied.

### 3.5 `play_session` — one lesson view (the "# times viewed" event)

- `id` PK, `tenant_id`, `enrollment_id` FK
- `course_version_id` FK (pinned at creation)
- `media_kind`: `video` | `audio`
- `started_at`, `ended_at` (nullable while in flight)
- `duration_seconds` int (active watch time)
- `max_watched_pct` smallint (0–100, furthest position this session)

One row per view. `COUNT(play_session)` per enrollment is the view count;
`SUM(duration_seconds)` is total watch time. This is the append-only history the
current single `assignment.watched_pct` scalar cannot provide.

### 3.6 `consumer_attempt` — one quiz sitting

- `id` PK, `tenant_id`, `enrollment_id` FK, `course_version_id` FK (pinned)
- `started_at`, `submitted_at` (nullable)
- `score_pct` float nullable, `is_all_correct` bool
- `question_count` int, `correct_count` int
- `total_active_seconds` int nullable
- CHECK `score_pct IS NULL OR score_pct BETWEEN 0 AND 100`
- CHECK `is_all_correct = (score_pct = 100)` (when submitted)

No `max_attempts` cap, no cooldown, always the full question set.

### 3.7 `consumer_attempt_answer` — per-question answer

- `id` PK, `consumer_attempt_id` FK
- `question_id` FK, `selected_option_ids` UUID[]
- `is_correct` bool nullable, `time_spent_seconds` int nullable, `answered_at`
- `UNIQUE(consumer_attempt_id, question_id)`

### 3.8 Metrics derivation

| Metric (user request) | Source |
|---|---|
| # times a user views a lesson | `COUNT(play_session)` per enrollment → denormalized `enrollment.view_count` |
| # times completed answering all questions correctly | `COUNT(consumer_attempt WHERE is_all_correct)` → denormalized `enrollment.completion_count` |
| date/time/duration per lesson | `play_session` rows (watch side) + `consumer_attempt` rows (quiz side) — per-lesson timeline |

Denormalized counters are maintained transactionally on write; a recompute check
(script + test) reconciles `enrollment.view_count`/`completion_count`/`best_score_pct`
against the event tables and reports drift.

## 4. Isolation boundaries

**Shared, unchanged:** `Course`, `CourseVersion`, `Question`, `AnswerOption`, the pure
`domain/scoring.py` grader, `User`, `Tenant`, the video/asset signer seam.

**New consumer code:**
- `domain/consumer/` — pure logic: the completion rule (`is_all_correct`), view/counter
  aggregation. No I/O.
- `services/consumer/` — `entitlements.py`, `enrollment.py`, `play.py`, `quiz.py`
  (async DB/HTTP shells; call the pure domain + shared grader).
- `db/models/consumer.py` — the seven ORM models above.
- `api/` — consumer routers (`packages`, `lessons`, `me`) + `admin/consumers`.

**Untouched:** B2B `Assignment`/`Attempt`/`Certificate` and their CHECK constraints.

This follows the repo's established pure-domain / thin-shell layering (see
`docs/00_architecture.md` and ADR-011 consumer path).

## 5. Access flow

1. **Admin grant** — `POST /admin/consumers` (role `compliance_admin`): create the
   consumer `User` under the Consumer tenant + create `entitlement(active,
   source=manual, granted_by)`. Idempotent on `(user, package)` active. Appends
   `entitlement.granted` to the hash-chained audit log via `services/audit.py`.
2. **Consumer login** — existing auth. `GET /me/packages` returns active entitlements
   and their packages.
3. **Browse** — `GET /packages/{id}/lessons`: courses via `package_course`, each
   annotated with the caller's `enrollment` progress (`view_count`, `completion_count`,
   `best_score_pct`). Gated by `require_entitlement`.
4. **Open lesson** — `POST /lessons/{course_id}/views` starts a `play_session`, lazily
   mints the `enrollment` if absent, returns the media manifest (reuse the player
   signer seam). `PATCH /lessons/{course_id}/views/{id}` on end records
   `duration_seconds` + `max_watched_pct` and bumps `view_count` + `last_accessed_at`.
5. **Quiz** — `POST /lessons/{course_id}/quiz/start` creates a `consumer_attempt` over
   the full active-version question set. `POST .../quiz/submit` grades via
   `domain/scoring.py`, sets `score_pct`/`is_all_correct`; if 100%, bumps
   `completion_count` and updates `best_score_pct`.

### 5.1 Authorization

New dependency `require_entitlement(course_id)`: the caller must hold an **active,
unexpired** entitlement for **some** package that contains this course. This is the
consumer analog of the B2B role gate. It gets a table-driven **denial** test
(mirroring `tests/api/test_rbac.py`) — a forgotten gate leaks paid content silently,
so the denial direction is tested explicitly.

## 6. Tenancy & roles

All consumers live under one seeded **Consumer tenant** (`short_code = consumer`),
reusing the `tenant_id` pattern and keeping the corporate tenant separate. Consumer
routes authorize by **entitlement**, not by RBAC role. Consumer users hold no
compliance roles. Admin grants reuse `compliance_admin` in v1; a dedicated
`catalog_admin` role is a clean later split, out of scope here.

## 7. Migrations & audit

- **One migration `0010`** (current head is `0009`): the seven tables, the Consumer-
  tenant seed row, all indexes and CHECK constraints (per §3), the partial-unique
  active-entitlement index, and the `enrollment` uniqueness.
- CHECK constraint naming must pass the suffix to both `create`/`drop` (the
  `db/base.py` naming convention prefixes `ck_<table>_`; a resolved name double-
  prefixes — a known repo gotcha).
- **Audit scope:** `entitlement.granted` / `entitlement.revoked` append to the
  hash-chained compliance log (they are access-control events). High-volume
  `play_session` / `consumer_attempt` events do **not** enter the compliance chain;
  they live in their own tables as product telemetry.

## 8. Edge cases

- **Version change while enrolled** — `play_session` and `consumer_attempt` pin
  `course_version_id` at creation, so a mid-flight change does not retroactively alter
  what was watched/tested; `enrollment` spans versions.
- **Entitlement revoked/expired** — new view/quiz requests are denied; an in-flight
  sitting may finish (checked at start, not mid-request).
- **Course in two owned packages** — `enrollment` is per-(user, course), so view and
  completion counts aggregate across packages; access is valid if *any* active
  entitlement covers the course.
- **Course shared with B2B** — content is shared; tracking is entirely separate
  (`consumer_attempt` vs `attempt`), so the two products never interfere.

## 9. Testing

- **Pure unit (no DB):** completion rule (`is_all_correct`), counter/view aggregation.
- **Services:** entitlement grant/revoke idempotency; access gate matrix
  (holds / expired / revoked / none); lazy enrollment creation; `play_session`
  lifecycle; quiz grading + transactional counter sync; recompute-check reconciliation.
- **API:** entitlement **denial** table (the direction a forgotten gate breaks
  silently).
- **Integration (real Postgres):** full flow grant → view → quiz → counters;
  partial-unique active entitlement enforcement; cross-package count aggregation.

## 10. Deferred (YAGNI)

- Payment processor (Stripe): webhook → the same `entitlement` grant path.
- Consumer self-registration / auth surface.
- Consumer certificates or completion badges (no SOX attestation/cooldown for
  consumers).
- Coupons, bundles, discounts, refunds.
- Audio-distinct media pipeline — `media_kind` is the only structural nod now; audio
  reuses the video asset seam.
- Real S3 presigning (shared existing pass-through stub).
- `catalog_admin` role.

## 11. Open questions for the plan phase

None blocking. During planning, confirm: exact router paths/verbs, whether
`admin/consumers` is one combined endpoint or create + grant split, and the recompute
check's delivery (standalone script + `make` target vs test-only).
