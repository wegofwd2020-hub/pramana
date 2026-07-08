<p align="center">
  <img src="assets/logo.png" alt="Pramana" width="400">
</p>

# Pramana

> *Pramāṇa* (प्रमाण) — Sanskrit: "proof", "valid means of knowledge".
> The system that produces evidence of compliance training completion.

A compliance training and tracking platform built by **WeGoFwd**.

[![CI](https://github.com/wegofwd2020-hub/pramana/actions/workflows/ci.yml/badge.svg)](https://github.com/wegofwd2020-hub/pramana/actions/workflows/ci.yml)

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
| [`docs/01_initial_analysis.md`](./docs/01_initial_analysis.md) | Initial robustness analysis of the original 8 requirements |
| [`docs/02_resolved_decisions.md`](./docs/02_resolved_decisions.md) | Locked v1 specification |
| [`docs/03_ai_drafted_human_approved_content.md`](./docs/03_ai_drafted_human_approved_content.md) | AI-drafted / human-approved content workflow |
| [`docs/api/`](./docs/api) | OpenAPI specification for the full pipeline |
| [`docs/frameworks/`](./docs/frameworks) | Per-framework references (SOX, FCPA, HIPAA, GDPR, ISO 27001, PCI DSS) |
| [`docs/user-stories/`](./docs/user-stories) | Framework-first user-story library + Package Request contract |

---

## Project status

| Phase | Deliverable | Status |
|---|---|---|
| Spec | Requirements & design decisions | ✅ Complete |
| C | Repo scaffolding | ✅ Complete |
| A | OpenAPI specification | ✅ Complete |
| D | Assignment state machine | ✅ Complete |
| B | SQLAlchemy data model + Alembic baseline | ✅ Complete |
| — | OIDC auth (bearer-token → principal, first-login provisioning) | ✅ Complete |
| — | Content pipeline (Create → Manufacture → Approve → Present) | 🚧 In progress |
| Next | Assignment / player / certificate runtime | ⏳ |

The **content pipeline** is the focus of the current work — commissioning content
from a regulation, ingesting Mentible Consumable Packages, the human review &
approval gate, and publishing to immutable course versions:

- **Create** — `/content-requests` builds a Package Request (validated against the
  definitions library) and pushes it to Mentible; `/frameworks` feeds the "law" picker.
- **Manufacture** — `/consumer-library/packages` ingests a signed package as an
  untrusted `RECEIVED` draft (signature + content-hash verified, else quarantined).
- **Approve** — `/content-drafts` review queue drives the approval state machine
  (separation of duties, attestation, tamper-evident audit log).
- **Present** — publishing materialises the draft's quiz into the course version's
  `Question`/`AnswerOption` rows so it is assignable and gradeable.

Database schema is managed by Alembic migrations `0001`→`0004`.

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

---

## License

Proprietary — All Rights Reserved. © WeGoFwd.
