<p align="center">
  <img src="assets/logo.png" alt="Pramana" width="400">
</p>

# Pramana

> *Pramāṇa* (प्रमाण) — Sanskrit: "proof", "valid means of knowledge".
> The system that produces evidence of compliance training completion.

A generalisable framework for **auditable compliance training** across regulatory
domains — SOX, FCPA, HIPAA, GDPR, ISO 27001, PCI DSS — built by **WeGoFwd**.

[![CI](https://github.com/wegofwd2020-hub/pramana/actions/workflows/ci.yml/badge.svg)](https://github.com/wegofwd2020-hub/pramana/actions/workflows/ci.yml)

---

## Why Pramana

Most training platforms treat compliance as reporting: run the courses, then assemble a
spreadsheet at audit time. That inverts the problem — evidence assembled after the fact
from mutable state is only as trustworthy as the weakest write path in the system.

**Pramana treats compliance as an architectural concern, not a bolt-on feature.** The
evidence is the primary artifact; the training experience is what produces it.

Three consequences shape the whole system:

- **Tamper-evident by construction.** Every state change is appended to a hash-chained
  audit log — each row's SHA-256 covers its own canonical form *and* the previous row's
  hash. Altering any historical entry breaks every subsequent link, detectable by
  recomputation alone. No external notary required.
- **Nothing that has served as evidence can change underneath it.** Quiz attempts pin the
  question version *and* the then-correct answer; approval freezes a content hash;
  publishing creates an immutable `CourseVersion`.
- **The engine is regulation-agnostic.** A new regulatory domain is a new reference
  document, not a new codebase branch — see [Extending to a new framework](#extending-to-a-new-framework).

Full rationale: [`docs/00_architecture.md`](./docs/00_architecture.md).

### Defence in depth on the audit log

| Layer | Mechanism | Fails to… |
|---|---|---|
| Application | No code path issues `UPDATE`/`DELETE` on `audit_log` | prevent a compromised operator |
| Database | `BEFORE UPDATE` trigger `audit_log_no_update` (migration `0001`); app role holds no mutate grant | prevent a superuser |
| Cryptographic | SHA-256 hash chain over canonical JSON | *nothing* — it detects what the other two missed |

The hash function ([`compute_audit_hash`](./pramana/services/audit.py)) is deliberately
**pure** — no session, no I/O — so an auditor can recompute hashes from exported rows
without the database, without the application, and in a different language if they wish.

### Extending to a new framework

`docs/frameworks/framework_<code>.md` is not documentation — it is **data**. The
definitions library parses each file and treats its `###` headings as citable clause
anchors. Those anchors are what content requests must resolve against, enforced as
*"no definition, no request"*.

So adding a regulatory domain means: author the framework reference following the shared
10-section structure → its clauses appear in the `/frameworks` picker → content can be
commissioned against them with citations back to real anchors → approval, publishing,
assignment, grading, and audit logging already work, because none of them know what SOX is.

What this does *not* give you for free: framework-specific evidence exports (a HIPAA OCR
binder, a PCI DSS QSA package) remain per-framework deliverables, and genuine conflicts
between frameworks — GDPR erasure versus SOX seven-year retention — are product decisions
the architecture cannot settle on its own. Each framework doc catalogues them in §9.

---

## Repository contents

| Path | Purpose |
|---|---|
| `docs/` | Specification, design decisions, regulatory framework references |
| `pramana/` | Application package (Python 3.12+) |
| `tests/` | Test suite (pytest) |
| `alembic/` | Database migrations |
| `pyproject.toml` | Project metadata, dependencies, tool config |
| `.github/workflows/ci.yml` | CI: lint, type-check, test, security scan |
| `Makefile` | Common dev commands (`make help`) |

---

## Documentation

All design documents live under [`docs/`](./docs).

| Document | Purpose |
|---|---|
| [`docs/00_architecture.md`](./docs/00_architecture.md) | **Start here** — architectural thesis, audit chain, trust boundaries, authorization model, extensibility |
| [`docs/01_initial_analysis.md`](./docs/01_initial_analysis.md) | Initial robustness analysis of the original 8 requirements |
| [`docs/02_resolved_decisions.md`](./docs/02_resolved_decisions.md) | Locked v1 specification |
| [`docs/03_ai_drafted_human_approved_content.md`](./docs/03_ai_drafted_human_approved_content.md) | AI-drafted / human-approved content workflow |
| [`docs/api/`](./docs/api) | OpenAPI specification for the full pipeline |
| [`docs/frameworks/`](./docs/frameworks) | Per-framework references (SOX, FCPA, HIPAA, GDPR, ISO 27001, PCI DSS) |
| [`docs/user-stories/`](./docs/user-stories) | Framework-first user-story library + Package Request contract |

---

## Project status

> **Maturity: pre-release, feature-complete on the core loop.** A regulation goes in
> one end and cryptographically verifiable proof of training comes out the other:
> commission → ingest → human approval → publish → assign → play → grade → certify →
> **verify**. That loop works end to end and is covered by tests against real Postgres.
> First release is scoped to **SOX** for a single named client, and it is **not yet
> deployed**. What remains is follow-on work — WORM archival, certificate PDFs, aggregate
> reporting — not core capability.

> **The table below is generated** from [`project-status.yaml`](./project-status.yaml),
> which is the single source of truth. Edit the manifest, then run `make status`; a test
> fails if the two drift, so this can no longer go stale by itself.

<!-- BEGIN GENERATED: status -->

| Deliverable | Status |
|---|---|
| Locked requirements (v1 single-tenant, SOX scope) | ✅ Complete |
| Repo scaffolding (CI, lint, type-check, security scan) | ✅ Complete |
| OpenAPI specification for the full pipeline | ✅ Complete |
| SQLAlchemy 2.x data model + Alembic baseline (0001→0006) | ✅ Complete |
| Tamper-evident audit log (SHA-256 hash chain + append-only DB trigger) | ✅ Complete |
| Assignment state machine (pure domain, property-based tests) | ✅ Complete |
| Content approval state machine (separation of duties, hash-pinned attestation) | ✅ Complete |
| Framework definitions library (6 references, clause-anchor resolution) | ✅ Complete |
| OIDC auth (bearer-token to principal, first-login provisioning) | ✅ Complete |
| FastAPI service layer (content-requests, consumer-library, content-drafts, frameworks) | ✅ Complete |
| Consumable Package ingestion (HMAC signature + content-hash verification) | ✅ Complete |
| wegofwd-video integration for training content (ADR-026) | ✅ Complete |
| In-process quiz generation | ✅ Complete |
| Content pipeline end-to-end (Create → Manufacture → Approve → Present) | ✅ Complete |
| Assignment / player / certificate runtime | ✅ Complete |
| Audit-chain verification tooling and evidence export | ✅ Complete |
| S3 Object Lock (WORM) archival of the audit log | ⏳ Planned |
| Certificate PDF render + framework binder templates | ⏳ Planned |
| Aggregate CSV reports (population, training matrix, exceptions) | ⏳ Planned |

<!-- END GENERATED: status -->

### The loop

**Create → Manufacture → Approve → Present** — turning a regulation into an assignable
course:

- **Create** — `/content-requests` builds a Package Request (validated against the
  definitions library) and pushes it to Mentible; `/frameworks` feeds the "law" picker.
  `/webhooks/mentible/progress` tracks generation.
- **Manufacture** — `/consumer-library/packages` ingests a signed package as an
  untrusted `RECEIVED` draft (signature + content-hash verified, else quarantined).
- **Approve** — `/content-drafts` review queue drives the approval state machine
  (separation of duties, attestation, tamper-evident audit log).
- **Present** — publishing materialises the draft's quiz into the course version's
  `Question`/`AnswerOption` rows so it is assignable and gradeable.

**Assign → Play → Grade → Prove** — turning that course into evidence:

- **Assign** — `/assignments` pins the active course version to a user; the state machine
  enforces cooldowns, attempt limits, and one active assignment per course.
- **Play** — `/assignments/{id}/player` serves the pinned manifest and
  `/progress` records monotonic watch progress, gating the quiz on `min_watch_pct`.
- **Grade** — `/assignments/{id}/submit` grades server-side, carrying prior correct
  answers forward on a retry so the client cannot inflate a score by omitting questions.
  A pass issues a certificate, verifiable publicly at `/certificates/verify/{code}`.
- **Prove** — `/audit/verify` recomputes the whole hash chain, `/audit/export` emits rows
  with their hashes for independent re-verification, and `/evidence/{user_id}` assembles a
  per-user binder. Auditor / compliance-admin only. Pulling an export is itself audited.
  See [`docs/00_architecture.md` §8](./docs/00_architecture.md#8-proving-it-verification-and-evidence-export).

Database schema is managed by Alembic migrations `0001`→`0006`.

---

## Development setup

### Prerequisites

- Python **3.12+**
- PostgreSQL 16+ (for integration tests; unit tests run without it)
- Redis 7+ (for Celery; unit tests run without it)
- `make` (optional but recommended)

### Quick start

```bash
# Clone and enter the repo
git clone git@github.com:wegofwd2020-hub/pramana.git
cd pramana

# Create a virtualenv (Python 3.12+)
python3.12 -m venv .venv
source .venv/bin/activate

# Install runtime + dev dependencies, plus pre-commit hooks
make dev-install

# Copy the env template and edit values
cp .env.example .env

# Run the test suite
make test
```

### Common commands

```bash
make help            # Show all available targets
make format          # Auto-format and auto-fix lints
make lint            # Lint without fixing
make type-check      # Run mypy
make test            # Run pytest
make test-cov        # Tests with coverage report
make check           # Lint + type-check + tests (CI equivalent)
make pre-commit      # Run all pre-commit hooks against all files
make migrate         # Apply Alembic migrations (alembic upgrade head)
make run             # Start the FastAPI app on :8000 with auto-reload
```

---

## Target stack

- **Language:** Python 3.12+
- **Web framework:** FastAPI
- **ORM:** SQLAlchemy 2.x with Alembic
- **Database:** PostgreSQL 16+
- **Background jobs:** Celery + Redis
- **Auth:** OIDC / SAML SSO (OIDC bearer-token verification implemented)
- **Object storage:** AWS S3 (Object Lock for audit log archive)
- **Testing:** pytest, pytest-asyncio, factory_boy, hypothesis

---

## v1 scope summary

Single-tenant deployment for John Thomas Corporate, scoped to **SOX (Sarbanes-Oxley)**
compliance training. See [`docs/02_resolved_decisions.md`](./docs/02_resolved_decisions.md)
for the full specification.

v1 is deliberately narrow in *deployment* scope but not in *architectural* scope: the data
model carries `tenant_id` from day one, six framework references are authored, and no
domain rule is SOX-specific. The constraint is what has been validated with a client, not
what the engine can represent.

Deferred past v1 by decision (not by omission): row-level tenant isolation enforcement,
multi-select and free-text question types, S3 Object Lock archival, and framework-specific
evidence exports beyond SOX.

---

## License

Proprietary — All Rights Reserved. © WeGoFwd.
