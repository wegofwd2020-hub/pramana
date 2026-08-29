# Pramana — Architecture

**Document type:** Architectural thesis and system overview
**Audience:** Engineers, auditors, and technical evaluators
**Status:** Living document — describes both what is built and what is designed

> Read this first. `01_initial_analysis.md` and `02_resolved_decisions.md` record how
> the requirements were arrived at; this document records *why the system is shaped the
> way it is*.

---

## 1. Thesis: compliance is an architectural concern, not a bolt-on feature

Most training platforms treat compliance as reporting: run the courses, then generate a
spreadsheet at audit time. That inverts the problem. If the evidence is assembled *after*
the fact from mutable application state, the evidence is only as trustworthy as the
weakest write path in the system — and nobody, including the vendor, can prove a record
was not edited.

Pramana starts from the opposite premise: **the evidence is the primary artifact, and the
training experience is what produces it.** Every design decision below follows from that
inversion.

The practical consequences:

| Conventional approach | Pramana |
|---|---|
| Audit report generated on demand from current state | Append-only hash-chained log written *as events occur*; reports are derived from it |
| Content is edited in place | Content is version-pinned and frozen at approval; publishing materialises an immutable `CourseVersion` |
| Quiz answers stored as "was it right" | Each `AttemptAnswer` snapshots the question version, the selection, *and* the then-correct answer |
| A new regulation means a new codebase branch | A new regulation means a new reference document; the engine is regulation-agnostic |
| "Trust us, we didn't change it" | Recompute the chain and check |

---

## 2. Core: the tamper-evident audit trail

The audit log is the spine of the system. It is not a debugging aid — it is the
deliverable.

### 2.1 Hash chain

Each row in `audit_log` carries `prev_audit_hash` (the previous row's hash) and
`audit_hash` (SHA-256 of its own canonical form, which *includes* the previous hash).

```
row N-1:  audit_hash = H(canonical(N-1) ‖ prev=H(N-2))
row N:    audit_hash = H(canonical(N)   ‖ prev=H(N-1))
```

Canonicalisation is deliberate and pinned: JSON with `sort_keys=True` and
`separators=(",", ":")`, so the same logical event always hashes identically regardless of
dict ordering. See `compute_audit_hash()` in
[`pramana/services/audit.py`](../pramana/services/audit.py).

Altering any historical row changes its hash, which breaks every subsequent link. Detection
requires only a recomputation pass — no external notary, no third party.

### 2.2 Why the hash function is a *pure* function

`compute_audit_hash()` takes no session, touches no I/O, and returns a string.
`append_audit()` is a thin async shell around it that reads the chain head and inserts.

This split is not stylistic. Verification tooling — the thing an auditor most needs to
trust — must be able to recompute hashes from exported rows without a database, without
the application, and ideally in a different language. A pure function is the only shape
that permits an independent re-implementation to agree.

### 2.3 Defence in depth on immutability

Four independent layers, each sufficient to detect (or prevent) tampering alone:

1. **Application** — no code path issues `UPDATE` or `DELETE` on `audit_log`.
2. **Database** — two triggers, `audit_log_no_update` and `audit_log_no_delete`
   (created in [`alembic/versions/0001_initial.py`](../alembic/versions/0001_initial.py)),
   raise on any `UPDATE` or `DELETE`. Both matter: forbidding edits while permitting
   deletes would leave the log trivially rewritable by excision. Migration `0009`
   additionally narrows the application role to `SELECT`/`INSERT` — but only when
   `APP_DB_ROLE` names a role separate from the schema owner. In a single-role
   deployment it cannot be applied at all, because a Postgres owner keeps its
   privileges regardless of `REVOKE`. That makes it a deployment topology question;
   see `SECURITY.md` §3 and `TICKETS/PR-1`.
3. **Cryptographic** — the chain makes any mutation that *did* somehow land detectable
   after the fact.
4. **Off-database** — segments are mirrored to WORM storage (§2.4), so a log that is
   dropped or rolled back to an older copy is still recoverable and still checkable.

Layers 1 and 2 prevent. Layer 3 is what you rely on when you assume 1 and 2 failed —
including the case where the operator is the adversary. Layer 4 is what you rely on when
the database itself is gone or disputed.

`audit_id` is `BIGINT IDENTITY(always)` so ordering is database-assigned and monotonic;
the chain cannot be reordered by clock skew or a lying client.

### 2.4 WORM archival

The chain proves the log has not been *altered where it sits*. It says nothing about a log
that has been dropped, restored from an older backup, or lost with the database. Mirroring
to write-once storage answers that, and it is the defence that survives losing the
database entirely.

Rows are mirrored to S3 under Object Lock in **segments**: an NDJSON object of rows
carrying their own hashes — the same shape `verify_chain` consumes — plus a manifest
recording the id range, the row count, the hash the segment *follows*, and the hash it
*ends on*.

That last pair is the point. Verifying rows alone would prove each object internally
intact while saying nothing about whether an object had been quietly dropped. Because each
manifest pins both boundaries, **consecutive segments link exactly the way consecutive rows
do**, and a missing segment is as detectable as a missing row.
[`pramana/domain/audit_archive.py`](../pramana/domain/audit_archive.py) is pure, for the
same reason the hash function is: an auditor holding only the objects must be able to
re-verify them without running Pramana.

Retention is `COMPLIANCE` mode, not `GOVERNANCE`. Under governance a principal with the
right permission can shorten or remove the lock, which makes the archive exactly as
trustworthy as whoever holds that permission; compliance mode cannot be overridden by
anyone, including the account root, until the retention date passes. The irreversibility
*is* the control.

Archival runs as an idempotent, resumable operation
([`scripts/archive_audit.py`](../scripts/archive_audit.py), `make archive-audit`) rather
than a background job — there is no Celery app in this repo, and one is not needed for
work that is safe to run twice. Scheduling is left to the deployment.

Two limits worth stating:

- **The bucket must be created with Object Lock enabled.** It cannot be turned on
  afterwards, and no code here can do it. See `SECURITY.md`.
- **Archival lags.** Between a row being written and its segment being stored, that row
  exists only in the database. The window is the schedule interval; the triggers and the
  chain cover it, but WORM does not.

---

## 3. Trust boundaries

Pramana ingests AI-generated content but never trusts it. Three boundaries are enforced in
code:

### 3.1 External content is untrusted on arrival

A *Mentible Consumable Package* arriving at `/consumer-library/packages` is verified before
it becomes anything at all:

- **Signature** — `hex(HMAC-SHA256(secret, canonical_manifest_bytes))`, compared in
  constant time ([`pramana/services/package_signing.py`](../pramana/services/package_signing.py)).
- **Content hash** — the payload must hash to what the manifest claims.

Failure quarantines the package. Success creates a draft in state `RECEIVED` — which is
still an *untrusted* state. Verification proves provenance and integrity, not correctness.

The domain layer defines a `SignatureVerifier` *protocol* and deliberately holds no keys;
key custody lives at the infrastructure edge. Swapping HMAC for asymmetric signing later
touches one module.

### 3.2 The human approval gate

AI drafts are a drafting aid, never the source of truth. Nothing is assignable until a
human approves it and it is published.

```
RECEIVED ─┐
          ├─submit─▶ IN_REVIEW ──approve──▶ APPROVED ──publish──▶ PUBLISHED
DRAFT ────┘             │  └────reject────▶ REJECTED (terminal)
  ▲                     │
  └───request_changes───┘
```

Two rules in [`pramana/domain/content_approval.py`](../pramana/domain/content_approval.py)
carry regulatory weight:

- **Separation of duties** — the approver must not be the user who generated the draft
  (`SeparationOfDutiesError`). This is the control an auditor asks about first.
- **Approval is evidence** — approving records the approver, the timestamp, and a
  `content_hash` of exactly what was approved, frozen thereafter. "Approved" is
  meaningless unless it is pinned to specific bytes.

### 3.3 Commissioning is constrained by the definitions library

You cannot request content for a regulation the system has no definition of. Enforced as
AC4 — *"no definition, no request"* — in
[`pramana/services/definitions_library.py`](../pramana/services/definitions_library.py).

---

## 4. Who may do what: the authorization model

§3 is about trusting *content*. This section is about trusting *callers*.

### 4.1 Authentication: OIDC, and it never creates users

A request carries an OIDC bearer token. `get_principal`
([`pramana/api/dependencies.py`](../pramana/api/dependencies.py)) extracts it,
verifies signature plus `iss`/`aud`/`exp` against the issuer's JWKS, and maps the
`sub` claim to a Pramana user.

The property worth stating loudly: **a validly-signed token is not enough to get
an account.** On a first login, `_provision_by_email`
([`pramana/services/auth.py`](../pramana/services/auth.py)) binds `sub` to a user
that must *already exist*, and refuses if the token carries no email claim, the
email is explicitly marked unverified, no unique user matches it, the matched
user is already bound to a different identity, or the user is not active.

This is deliberately narrower than the usual just-in-time provisioning, which
creates an account for anyone the IdP will vouch for. In a compliance system the
user list is part of the evidence — "who was required to take this training" is a
question with a definite answer — so account creation is an administrative act,
not a side effect of someone logging in.

The bind itself is audited as `user.sso_bound`. Gaining authenticated access is
an access-control event, and the SOX trail should show who acquired access and
when, not only what they did afterwards.

### 4.2 Machine-to-machine: HMAC, no principal

Two routes are not called by people and have no principal at all:

| Route | Secret |
|---|---|
| `POST /consumer-library/packages` (ingest) | `MENTIBLE_PACKAGE_HMAC_SECRET` |
| `POST /webhooks/mentible/progress` | `MENTIBLE_WEBHOOK_HMAC_SECRET` |

The secrets are **separate on purpose**, so the two rotate independently
([`config.py`](../pramana/config.py)). The separation also bounds a compromise:
the channels carry very different authority — one delivers content that will
become training material, the other only moves a progress percentage — so leaking
the low-value secret must not confer the high-value capability.

Neither route resolves a `Principal`, so neither is subject to §4.3. Their
authorization *is* the signature check.

### 4.3 Three layers, answering three different questions

Authorization is not one check. Three distinct questions are asked in three
distinct places:

| Question | Mechanism | Lives in |
|---|---|---|
| May you do this *kind* of thing? | `require_roles` | router |
| Is this *yours*? | `_load_owned`, `get_assignment_for_reader` | service |
| Does this violate a *control*? | `SeparationOfDutiesError` | pure domain |

None of the three subsumes another, which is why all three exist:

- A **role** check cannot answer "is this yours". Every trainee holds the same
  role; the difference between reading your own training record and reading a
  colleague's is data, not vocabulary.
- An **ownership** check cannot answer "should a content author approve the draft
  they generated". Both users are legitimate actors on that draft. What is wrong
  is the *combination*, which is a rule about the transition, not about the
  caller.
- A **domain control** cannot be enforced at the router, because the router does
  not know who generated the draft without loading it.

Each check also lives where it cannot be skipped by the layer above forgetting.
Ownership sits next to the data load rather than in the handler — the learner
endpoints are safe precisely because `_load_owned` is the only way they obtain an
assignment. When two read endpoints bypassed it and called `get_assignment`
directly, they leaked across users until `get_assignment_for_reader` gave them an
ownership-aware door of their own.

Separation of duties lives in the pure domain
([`content_approval.py`](../pramana/domain/content_approval.py)) for the same
reason the hash function does: it is the control an auditor asks about first, and
it should be provable by exhaustive test without a database, an HTTP layer, or a
configured role table.

Note what this means for the service layer: `get_assignment_for_reader` takes
`may_read_others: bool`, not a `Principal`. The router decides *whether the caller
is staff*; the service only knows *whether this caller may see other people's
records*. Role vocabulary stays at the edge, so changing the role names later
touches routers only.

### 4.4 Roles

Five fixed roles, seeded in the database and loaded onto the `Principal`
(`Role`/`UserRole` in [`identity.py`](../pramana/db/models/identity.py)):

| Role | May |
|---|---|
| `trainee` | Take their own assigned training; read their own records |
| `manager` | Assign and cancel training; read across users |
| `content_author` | Commission content, submit drafts for review, regenerate |
| `compliance_admin` | Everything authoring, plus **approve / reject / publish**, and role administration |
| `auditor` | Read the audit chain, verify it, export evidence; read the review queue and role grants |

Approval and publication are `compliance_admin` only. Separation of duties would
already stop an author approving *their own* draft, but restricting the role is a
second, independent line: peer approval among authors is a defensible policy, and
it is not the one this deployment chose.

Learner self-service routes (`/assignments/me`, attempts, submit, player,
progress) carry **no** role requirement. They are ownership-gated instead, so a
user with no roles at all can still complete assigned training — which matters,
because roles are granted separately (§4.6).

### 4.5 Public by design

`GET /certificates/verify/{code}` is unauthenticated, deliberately. The
verification code *is* the credential, and the response carries only the minimal
non-PII facts an external verifier needs — validity, course version, issue and
expiry. A regulator or counterparty checking a certificate should not need an
account in the system that issued it.

### 4.6 Administering roles

Granting authority is itself a privileged act, and it is audited like any other.
`/users/{user_id}/roles` supports listing, granting, and revoking; the mutating
routes are compliance-admin only, while auditors may read, because who holds
which role — and since when, and granted by whom — is access-control evidence.
Every change appends `user.role_granted` or `user.role_revoked` to the chain
alongside the actions those roles authorise.

Two rules in [`pramana/services/roles.py`](../pramana/services/roles.py) are
worth naming, since both encode a control rather than a convenience:

- **No self-modification.** An administrator may not change their own roles.
  Self-escalation is the failure §3.2's separation-of-duties rule exists to
  prevent, and the same reasoning applies to the roles that gate it: any change
  takes two people.
- **The last compliance admin cannot be revoked.** Otherwise the deployment
  re-enters the bootstrap problem below and needs database access to recover.

### 4.7 Bootstrapping the first administrator

A fresh deployment holds no grants, and the route that creates one requires
already being an administrator. Something has to break that circle from outside
the request path.

[`scripts/grant_role.py`](../scripts/grant_role.py) does, run by an operator with
database access. It is deliberately *not* a special case of the API path — the
self-modification rule must hold unconditionally for anything reachable over
HTTP — and the audit entry it writes records the difference: a null
`actor_user_id` and a `bootstrap` flag, so a reviewer can tell an operator's
out-of-band act from a user's request at a glance.

The five roles themselves are reference data, seeded by migration `0007`. They
are duplicated in `ROLE_DESCRIPTIONS` because the integration suite builds its
schema from the ORM metadata and never runs Alembic; a test asserts the two
agree and that both cover `RoleName`.

### 4.8 Known gap

- **Tenant isolation is query-level, not enforced by the database.** Every read
  filters on `tenant_id=caller.tenant_id`, but nothing stops a future query from
  omitting it. Row-level security is deferred past v1 (single-tenant). The
  `tenant_id` column exists on every table from day one so enabling RLS is a
  policy change rather than a migration of the whole schema.

---

## 5. Extensibility: how a new regulatory domain is added

The claim is that business teams can define training for a new regulatory domain without
core reengineering. Concretely, the mechanism is this:

**`docs/frameworks/framework_<code>.md` is not documentation — it is data.**

The definitions library parses each framework file and treats its `###` headings as
**citable clause anchors**. Those anchors are what a Package Request's
`source_definitions[].ref` must resolve against. So:

1. Author `docs/frameworks/framework_<code>.md`, following the shared 10-section structure
   (overview → training requirements → design implications → data model → evidence →
   retention → access → conflicts → checklist).
2. Its `###` clauses become selectable in the `/frameworks` "law" picker automatically.
3. Content can now be commissioned against those clauses; every generated draft carries a
   citation back to a real anchor.
4. Approval, publishing, assignment, grading, and audit logging are already
   regulation-agnostic — they operate on courses and events, not on SOX.

Six framework references exist today: SOX, FCPA, HIPAA, GDPR, ISO 27001, PCI DSS. Only SOX
is in v1 scope; the rest are authored so the engine can be exercised against them. See
[`docs/frameworks/regulatory_frameworks_index.md`](./frameworks/regulatory_frameworks_index.md).

### 5.1 What extensibility does *not* mean

Stated plainly, because overclaiming here is how compliance products lose credibility:

- Adding a framework doc gives you commissioning, citation, and traceability. It does
  **not** auto-generate a framework-specific evidence export (an OCR binder for HIPAA, a
  QSA package for PCI DSS). Those are per-framework deliverables — see the export user
  stories under [`docs/user-stories/`](./user-stories).
- Frameworks **conflict**. GDPR erasure rights and SOX seven-year retention pull in
  opposite directions. §9 of each framework doc catalogues these; resolution is a product
  decision, not something the architecture can settle on its own.
- Retention periods, cadence rules, and role taxonomies differ per framework and are
  configuration, not code — but they still require someone to configure them.

---

## 6. The pure-domain pattern

Business rules live in `pramana/domain/` as pure modules: no database, no HTTP, no I/O.
Each is a function over an immutable snapshot dataclass:

```
(snapshot, event_args) -> new_snapshot   |   raises DomainError
```

`assignment_state.py` (cooldowns, attempts, pass/fail) and `content_approval.py`
(the approval lifecycle) both follow this shape.

Why it matters *for a compliance product* specifically: these rules are the ones an auditor
will interrogate. "Can a user retry before the cooldown expires?" must have an answer that
is provable, not merely tested against a happy path. Pure functions over immutable
snapshots are exhaustively testable with property-based tests (Hypothesis) — see
`tests/domain/`. The rules can be re-derived and re-verified without standing up
PostgreSQL, Redis, or the API.

The service layer (`pramana/services/`) holds the I/O shells. The API layer
(`pramana/api/`) holds transport concerns only.

---

## 7. Content pipeline

```
Create ──────────▶ Manufacture ──────▶ Approve ─────────▶ Present
/content-requests  /consumer-library    /content-drafts    publish
                   /packages
```

| Stage | What happens | Trust state |
|---|---|---|
| **Create** | Package Request built and validated against the definitions library, pushed to Mentible | N/A — a request, not content |
| **Manufacture** | Signed package ingested; signature + content hash verified, else quarantined | `RECEIVED` — verified provenance, untrusted content |
| **Approve** | Human review queue drives the approval state machine; separation of duties, attestation, audit entries | `APPROVED` — trusted, hash-pinned |
| **Present** | Draft's quiz materialised into the `CourseVersion`'s `Question`/`AnswerOption` rows | `PUBLISHED` — immutable, assignable |

While Mentible manufactures a package, it reports progress back through an
HMAC-signed webhook (`POST /webhooks/mentible/progress`, a dedicated secret,
machine-to-machine like ingestion): `REQUESTED → GENERATING` with an optional
completion percent, or `→ FAILED` if generation is abandoned. The transitions
are idempotent and never regress — a progress event that races behind the
package's arrival is dropped, and the reported percent is monotonic — so
duplicate or out-of-order delivery is safe.

The pipeline hands off to the learner runtime: an assignment pins the course
version, the player gates the quiz on watch progress, submission grades
server-side and issues a certificate, and every transition appends to the audit
chain. That chain is what §8 then makes checkable.

---

## 8. Proving it: verification and evidence export

§2 argues that hash-chaining makes tampering detectable. This section is where
that claim is cashed: a chain nobody can check is a claim, not a control.

### 7.1 Chain verification

`verify_chain()` in
[`pramana/domain/audit_verification.py`](../pramana/domain/audit_verification.py)
walks the chain in ascending `audit_id` order and checks two independent things
per row:

- **Link continuity** — the row's stored `prev_audit_hash` must equal the actual
  predecessor's hash. A failure means rows were deleted, reordered, or inserted:
  `broken_link`.
- **Content integrity** — recomputing the row's hash from its own fields must
  reproduce the stored `audit_hash`. A failure means a row's contents were
  edited: `hash_mismatch`.

The two catch different attacks, which is why both exist. Editing a row's payload
trips the second; excising a row entirely trips the first.

Verification returns at the **first** break rather than collecting all of them.
Once continuity is lost, every subsequent row mismatches as a consequence, so a
full list would report one tampering event as thousands of findings and bury the
row that actually matters. The interesting fact is *where the chain first stops
being trustworthy*.

Like the hash function it builds on, `verify_chain` is **pure** — it takes a
sequence of rows and returns a verdict, with no session and no I/O. An auditor
can run it over an export, in their own process, without the application.

### 7.2 The auditor surface

| Endpoint | Purpose |
|---|---|
| `GET /audit/verify` | Recompute and verify the stored chain; reports intact, or the first break and its reason |
| `GET /audit` | Search the log by entity, event type, actor, or time window |
| `GET /audit/export` | Export rows **with their hashes**, as JSON or CSV, for independent re-verification |
| `GET /evidence/{user_id}` | Assemble a per-user binder: assignments, attempts, certificates, and the audit entries behind them |

All four are gated to the `auditor` and `compliance_admin` roles (§4.3).

Two details that matter for a compliance product:

- **Export is itself audited.** Pulling evidence appends an `audit.exported`
  entry. Who read the records is part of the record — an auditor's own access is
  as attributable as anyone else's.
- **Export carries the hashes.** Exporting the rows without them would produce a
  document that has to be taken on trust, which is precisely what the
  architecture exists to avoid. With hashes attached, the recipient can re-run
  the verification themselves.

### 7.3 Known limit: the chain is global

There is one chain per deployment, not one per tenant. In the single-tenant v1
that is exactly right. Multi-tenant, it is not: a per-tenant export cannot be
independently re-verified, because the rows it omits are load-bearing links in
the chain it came from.

The fix is per-tenant chains or Merkle inclusion proofs, and it is a v2 concern —
recorded here rather than discovered later by whoever first tries to hand one
tenant a verifiable export.

---

## 9. Version pinning throughout

A recurring pattern worth naming, because it is the second-order defence behind the audit
chain: **nothing that has been used as evidence can be changed underneath it.**

- `AttemptAnswer` snapshots the question version, the selected option(s), and the
  then-correct option(s). Editing a question tomorrow does not retroactively make a past
  attempt wrong — or right.
- Approval freezes a `content_hash`.
- Publishing creates an immutable `CourseVersion` rather than mutating a course.
- Users have a synthetic immutable `user_id`; email and name are mutable attributes, so an
  employee changing their surname does not orphan five years of training records.

An audit trail that points at mutable rows is not an audit trail. Hash-chaining the log
without version-pinning what it references would be a lock on a door with no wall.

---

## 10. Stack

| Concern | Choice |
|---|---|
| Language | Python 3.12+ |
| Web | FastAPI |
| Persistence | PostgreSQL 16+, SQLAlchemy 2.x, Alembic (`0001`→`0009`) |
| Background jobs | Celery + Redis |
| Auth | OIDC / SAML SSO (OIDC bearer-token verification implemented) |
| Object storage | AWS S3 (Object Lock for audit archive — planned) |
| Testing | pytest, pytest-asyncio, factory_boy, Hypothesis; integration layer against real Postgres |

Multi-tenant readiness: `tenant_id` is carried on the data model from day one, but
row-level isolation enforcement is deliberately deferred past v1 (single-tenant
deployment). The column exists so that adding RLS later is a policy change, not a
migration of every table.

---

## 11. Current state

Everything described above is built. The loop closes end to end — a regulation is
commissioned, manufactured, human-approved, published, assigned, played, graded,
certified, and the resulting evidence can be independently verified — and it is
covered by tests, including an integration layer against real Postgres.

Deliberately not built yet: certificate
PDF rendering, aggregate CSV reporting, and per-tenant verifiable exports (§8.3).

**Authoritative status lives in
[`../project-status.yaml`](../project-status.yaml)**, which a dashboard reads and
which is therefore kept current; [`../README.md`](../README.md) mirrors it for
readers. This section is prose and will drift — trust the manifest.

---

## 12. Related documents

| Document | Purpose |
|---|---|
| [`01_initial_analysis.md`](./01_initial_analysis.md) | Robustness analysis of the original 8 requirements |
| [`02_resolved_decisions.md`](./02_resolved_decisions.md) | Locked v1 specification |
| [`03_ai_drafted_human_approved_content.md`](./03_ai_drafted_human_approved_content.md) | AI-drafted / human-approved content workflow |
| [`../SECURITY.md`](../SECURITY.md) | Security policy and STRIDE-lite threat model |
| [`frameworks/`](./frameworks) | Per-framework references and the definitions library source |
| [`user-stories/`](./user-stories) | Framework-first user-story library + Package Request contract |
| [`api/`](./api) | OpenAPI specification |
