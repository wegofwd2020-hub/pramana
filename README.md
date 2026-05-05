# Pramana

> *Pramāṇa* (प्रमाण) — Sanskrit: "proof", "valid means of knowledge".
> The system that produces evidence of compliance training completion.

A compliance training and tracking platform built by **WeGoFwd**.

---

## What this repository currently contains

This is the **specification phase** of the Pramana project. The repository contains the requirements analysis, locked design decisions, and regulatory framework references that will drive the build. No application code yet — that comes next.

## Documentation

All design documents live under [`docs/`](./docs).

| Document | Purpose |
|---|---|
| [`docs/01_initial_analysis.md`](./docs/01_initial_analysis.md) | Initial robustness analysis of the original 8 requirements; identifies gaps and ambiguities |
| [`docs/02_resolved_decisions.md`](./docs/02_resolved_decisions.md) | Locked specification after stakeholder clarifications; canonical reference for v1 design |
| [`docs/frameworks/regulatory_frameworks_index.md`](./docs/frameworks/regulatory_frameworks_index.md) | Master index for regulatory framework support; overlaps and conflicts |
| [`docs/frameworks/framework_sox.md`](./docs/frameworks/framework_sox.md) | SOX (in scope for v1) |
| [`docs/frameworks/framework_hipaa.md`](./docs/frameworks/framework_hipaa.md) | HIPAA reference (target v2) |
| [`docs/frameworks/framework_gdpr.md`](./docs/frameworks/framework_gdpr.md) | GDPR reference (target v4) |
| [`docs/frameworks/framework_iso27001.md`](./docs/frameworks/framework_iso27001.md) | ISO/IEC 27001 reference (target v3) |
| [`docs/frameworks/framework_pci_dss.md`](./docs/frameworks/framework_pci_dss.md) | PCI DSS reference (target v5) |

## Project status

| Phase | Status |
|---|---|
| Requirements & spec | ✅ Complete (this repo) |
| API specification (OpenSpec) | ⏳ Next |
| Data model (SQLAlchemy + Alembic) | ⏳ Next |
| FastAPI service scaffold | ⏳ |
| v1 MVP implementation | ⏳ |

## Target stack (per resolved decisions)

- **Language:** Python 3.12+
- **Web framework:** FastAPI
- **ORM:** SQLAlchemy 2.x with Alembic migrations
- **Database:** PostgreSQL
- **Background jobs:** Celery + Redis
- **Auth:** SSO via SAML/OIDC (provider TBD: Auth0 / Clerk / WorkOS)
- **Object storage:** AWS S3 (Object Lock for audit log archive)
- **Testing:** pytest, pytest-asyncio, factory_boy, hypothesis

## v1 scope summary

Single-tenant deployment for John Thomas Corporate, scoped to **SOX (Sarbanes-Oxley)** compliance training. See [`docs/02_resolved_decisions.md`](./docs/02_resolved_decisions.md) for full scope, locked requirements, and assignment-state machine.

## License

Proprietary — All Rights Reserved. © WeGoFwd.

---

*Generated as part of the design phase. To regenerate or extend documentation, see the conversation history with the design assistant.*
