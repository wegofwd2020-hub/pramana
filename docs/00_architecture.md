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

Three independent layers, each sufficient to detect (or prevent) tampering alone:

1. **Application** — no code path issues `UPDATE` or `DELETE` on `audit_log`.
2. **Database** — a `BEFORE UPDATE` trigger (`audit_log_no_update`, created in
   [`alembic/versions/0001_initial.py`](../alembic/versions/0001_initial.py)) rejects
   mutation. The application role is additionally intended to hold no `UPDATE`/`DELETE`
   grant on the table (see `SECURITY.md` §3; tracked as `TICKETS/PR-1`).
3. **Cryptographic** — the chain makes any mutation that *did* somehow land detectable
   after the fact.

Layers 1 and 2 prevent. Layer 3 is what you rely on when you assume 1 and 2 failed —
including the case where the operator is the adversary.

`audit_id` is `BIGINT IDENTITY(always)` so ordering is database-assigned and monotonic;
the chain cannot be reordered by clock skew or a lying client.

### 2.4 Planned: WORM archival

Rows mirror to S3 with Object Lock for immutable off-database archival. Designed, not yet
built — see the status table in [`../README.md`](../README.md).

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

## 4. Extensibility: how a new regulatory domain is added

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

### 4.1 What extensibility does *not* mean

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

## 5. The pure-domain pattern

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

## 6. Content pipeline

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
chain. That chain is what §7 then makes checkable.

---

## 7. Proving it: verification and evidence export

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

All four are gated to the `auditor` and `compliance_admin` roles
(`require_roles` in [`pramana/api/dependencies.py`](../pramana/api/dependencies.py)).

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

## 8. Version pinning throughout

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

## 9. Stack

| Concern | Choice |
|---|---|
| Language | Python 3.12+ |
| Web | FastAPI |
| Persistence | PostgreSQL 16+, SQLAlchemy 2.x, Alembic (`0001`→`0006`) |
| Background jobs | Celery + Redis |
| Auth | OIDC / SAML SSO (OIDC bearer-token verification implemented) |
| Object storage | AWS S3 (Object Lock for audit archive — planned) |
| Testing | pytest, pytest-asyncio, factory_boy, Hypothesis; integration layer against real Postgres |

Multi-tenant readiness: `tenant_id` is carried on the data model from day one, but
row-level isolation enforcement is deliberately deferred past v1 (single-tenant
deployment). The column exists so that adding RLS later is a policy change, not a
migration of every table.

---

## 10. Current state

Everything described above is built. The loop closes end to end — a regulation is
commissioned, manufactured, human-approved, published, assigned, played, graded,
certified, and the resulting evidence can be independently verified — and it is
covered by tests, including an integration layer against real Postgres.

Deliberately not built yet: WORM archival to S3 Object Lock (§2.4), certificate
PDF rendering, aggregate CSV reporting, and per-tenant verifiable exports (§7.3).

**Authoritative status lives in
[`../project-status.yaml`](../project-status.yaml)**, which a dashboard reads and
which is therefore kept current; [`../README.md`](../README.md) mirrors it for
readers. This section is prose and will drift — trust the manifest.

---

## 11. Related documents

| Document | Purpose |
|---|---|
| [`01_initial_analysis.md`](./01_initial_analysis.md) | Robustness analysis of the original 8 requirements |
| [`02_resolved_decisions.md`](./02_resolved_decisions.md) | Locked v1 specification |
| [`03_ai_drafted_human_approved_content.md`](./03_ai_drafted_human_approved_content.md) | AI-drafted / human-approved content workflow |
| [`../SECURITY.md`](../SECURITY.md) | Security policy and STRIDE-lite threat model |
| [`frameworks/`](./frameworks) | Per-framework references and the definitions library source |
| [`user-stories/`](./user-stories) | Framework-first user-story library + Package Request contract |
| [`api/`](./api) | OpenAPI specification |
