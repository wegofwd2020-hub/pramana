# Pramana API — v1

This directory contains the OpenAPI 3.1 specification for the Pramana v1 API.

| File | Purpose |
|---|---|
| [`openapi.yaml`](./openapi.yaml) | Canonical OpenAPI 3.1 specification |

---

## Viewing the spec

The YAML can be rendered with any OpenAPI-compatible tool:

```bash
# Swagger UI in a browser
docker run -p 8080:8080 \
  -e SWAGGER_JSON=/spec/openapi.yaml \
  -v "$PWD/docs/api:/spec" \
  swaggerapi/swagger-ui

# Or Redoc
npx @redocly/cli preview-docs docs/api/openapi.yaml

# Or generate static HTML
npx @redocly/cli build-docs docs/api/openapi.yaml -o docs/api/index.html
```

When the FastAPI service runs, it serves Swagger UI at `/docs` and ReDoc at `/redoc` automatically.

---

## Endpoint overview

The v1 surface area is organised into eight tag groups:

| Tag | Resource | Notes |
|---|---|---|
| Health | `/health`, `/health/ready` | Liveness and readiness probes (no auth) |
| Users | `/users`, `/users/me`, `/users/{user_id}/...` | Identity, lifecycle, bulk import, GDPR-style pseudonymization |
| Courses | `/courses`, `/courses/{course_id}/versions/...` | Course CRUD and version publishing |
| Questions | `/courses/{course_id}/versions/{version_id}/questions`, `/questions/{question_id}` | Quiz authoring (only on draft versions) |
| Assignments | `/assignments`, `/assignments/me`, `/assignments/{assignment_id}/...` | Assignment lifecycle |
| Attempts | `/assignments/{assignment_id}/attempts`, `/attempts/{attempt_id}/...` | Quiz attempts, autosave, submission |
| Certificates | `/certificates`, `/certificates/{id}/pdf`, `/certificates/verify/{code}` | Issued certificates and public verification |
| Audit | `/audit` | Audit-log search |
| Exports | `/exports/...` | Auditor evidence exports (CSV / PDF) |

---

## Authentication

All endpoints require a JWT in the `Authorization: Bearer <token>` header, except:

- `GET /health` and `GET /health/ready` — public
- `GET /certificates/verify/{verification_code}` — public (third-party verification)

The JWT is issued by the customer's IdP (OIDC). The token's `sub` claim is mapped to a Pramana `user_id` at first login.

---

## Authorisation

Role checks are documented per-endpoint. Roles (defined in `docs/02_resolved_decisions.md`):

| Role | Typical access |
|---|---|
| `trainee` | Own assignments, attempts, certificates |
| `manager` | Direct reports' status (no attempt detail) |
| `content_author` | Course and question authoring; cannot self-assign |
| `compliance_admin` | Full system access except audit-log immutability |
| `auditor` | Read-only across all data; export endpoints |

---

## Idempotency

Two endpoints support `Idempotency-Key` header for safe client retries:

- `PUT /attempts/{attempt_id}/answers` — autosave is idempotent per `(attempt_id, question_id)`
- `POST /attempts/{attempt_id}/submit` — submission is idempotent; resubmitting returns the original result

`POST /assignments/{assignment_id}/attempts` is *naturally* idempotent — if an `IN_PROGRESS` attempt already exists, it is returned (HTTP 200 instead of 201).

---

## Pagination

List endpoints accept `page` (default 1) and `page_size` (default 50, max 200) query parameters, and return a `pagination` envelope:

```json
{
  "items": [...],
  "pagination": { "page": 1, "page_size": 50, "total": 137 }
}
```

---

## Error format

All error responses share this shape:

```json
{
  "code": "cooldown_active",
  "message": "Cooldown is active until 2027-01-15.",
  "context": { "course_id": "...", "cooldown_until": "2027-01-15T00:00:00Z" }
}
```

The `code` values are stable and machine-readable. They mirror `Pramana*Error` exception class codes from `pramana/exceptions.py`. Validation errors include an additional `errors` array.

---

## Status code conventions

| Code | Meaning |
|---|---|
| 200 | Success with body |
| 201 | Resource created |
| 204 | Success with no body |
| 400 | Validation error |
| 401 | Missing or invalid credentials |
| 403 | Authenticated but forbidden |
| 404 | Resource does not exist |
| 409 | State / uniqueness conflict (cooldown active, max attempts exceeded, etc.) |
| 503 | Service not ready (`/health/ready` only) |

---

## Out of v1 scope (deferred)

- Multi-select and free-text question types (v2)
- Anti-cheat fingerprinting endpoints (v2)
- HRIS sync webhooks (v3)
- SCORM / xAPI export (v3)
- Multi-tenant tenant management endpoints (v4)
