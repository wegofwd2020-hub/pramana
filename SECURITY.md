# Pramana — Security Policy & Threat Model

**Status:** Draft v0.1 (2026-06-11) · **Owner:** WeGoFwd2020 · **Review:** before v1 pilot and on any change to data flow or auth.

> Pramana is a **compliance** product — it produces audit-grade evidence that mandated training was completed. For a compliance product, security *is* the product: customers buy it precisely because they trust its records. This document states the security policy and an initial threat model. It is intentionally written now, in the spec phase, so the v1 build is secure by design rather than retrofitted.

---

## 1. Assets to protect

| Asset | Why it matters |
|---|---|
| Training assignment & completion records | The core evidence; must be accurate and tamper-evident |
| Audit log | Regulatory proof (SOX v1); integrity is paramount |
| Employee/user PII | Names, roles, identifiers tied to records |
| Authn/authz config, secrets | Compromise undermines all of the above |
| Generated/approved content | Defines what "trained" means |

## 2. Security principles
1. **Integrity over convenience** — audit and completion records are append-only and tamper-evident; no silent edits.
2. **Least privilege** — roles grant the minimum needed; admin actions are themselves audited.
3. **Defense in depth** — auth, RLS/row scoping, encryption, and audit each stand alone.
4. **Secure by default** — the safe configuration is the default; insecure options are not silently available.
5. **Auditability** — every state change to an assignment is attributable (who, what, when).

## 3. Controls (target for v1)

**Authentication & access**
- SSO via SAML/OIDC (provider TBD per resolved decisions); no local passwords for end users where SSO is available.
- RBAC with explicit roles (employee, manager, compliance admin, auditor).
- Admin and auditor actions are logged.

**Data protection**
- Encryption in transit (TLS) and at rest.
- PII minimized to what compliance reporting requires.
- Tenant/data isolation enforced at the query layer (row scoping).

**Audit log integrity**
- Append-only audit log; consider WORM/Object-Lock storage (the resolved decisions note AWS S3 Object Lock for audit archive).
- The application role must **not** hold DELETE/UPDATE on the audit table — enforce via DB grants (`REVOKE`). *(Note: the sister Thittam review flagged an audit_log REVOKE as an open item; do not repeat that here — make it a v1 acceptance test.)*

**Application security**
- Input validation; parameterized queries only (no string-built SQL) to prevent injection.
- Explicit exception handling; never leak stack traces or secrets in errors (matches WeGoFwd coding standards).
- Secrets from a secret manager / env, never in source.

## 4. Threat model (STRIDE-lite)

| Threat | Example | Mitigation |
|---|---|---|
| **Spoofing** | Attacker impersonates a manager to mark training complete | SSO, RBAC, audited admin actions |
| **Tampering** | Editing completion/audit records to fake compliance | Append-only audit log, DB-level REVOKE on audit table, tamper-evident storage |
| **Repudiation** | User denies an action | Attributable, timestamped audit entries |
| **Information disclosure** | Cross-tenant or unauthorized PII access | Row scoping, least privilege, encryption |
| **Denial of service** | Flood endpoints | Rate limiting, async job isolation (Celery) |
| **Elevation of privilege** | Employee gains admin/auditor rights | Strict RBAC, server-side authorization checks, audited role changes |

## 5. Compliance linkage
v1 is scoped to **SOX**. The audit log and completion evidence are the SOX control artifacts; their integrity controls (§3, §4) are therefore compliance controls, not just security ones. Later frameworks (HIPAA, ISO 27001, GDPR, PCI DSS) will add requirements — see `docs/frameworks/`.

## 6. Vulnerability reporting
Report suspected vulnerabilities privately to WeGoFwd2020 (insert security contact before pilot). Do not file security issues as public tickets.

## 7. Pre-pilot security checklist (open items → tickets)
- [ ] Enforce DB-level `REVOKE` on the audit table (app role cannot UPDATE/DELETE); add an acceptance test.
- [ ] Implement append-only audit log + tamper-evident/WORM archive.
- [ ] Wire SSO (SAML/OIDC) and RBAC with audited admin actions.
- [ ] Encryption at rest + in transit verified.
- [ ] Injection-safe data layer (parameterized queries) + tests.
- [ ] Secret manager integration; no secrets in source.
- [ ] Define security contact + vulnerability disclosure path.

*Internal draft; not legal advice.*
