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
- Append-only audit log, enforced by the `audit_log_no_update` and `audit_log_no_delete` triggers, and detectable by the SHA-256 hash chain if both were somehow bypassed.
- **WORM archival is implemented.** Segments mirror to the `S3_BUCKET_AUDIT_ARCHIVE` bucket under Object Lock in `COMPLIANCE` mode, retained for `DEFAULT_RECORD_RETENTION_YEARS` (7). Run `make archive-audit` on a schedule; it is idempotent and resumable. See `docs/00_architecture.md` §2.4.

*Deployment prerequisites — neither can be done by application code:*

1. **The archive bucket must be created with Object Lock enabled.** S3 does not allow enabling it on an existing bucket. Without it, `put_object` with a retention header fails, and archival will error rather than silently storing unprotected objects.
2. **Two database roles.** The application should connect as a role that does *not* own the schema, with `APP_DB_ROLE` set to that role's name; migration `0009` then grants it `SELECT, INSERT` on `audit_log` and revokes `UPDATE, DELETE`.

   This matters more than it looks. In Postgres **an object's owner keeps its privileges regardless of `REVOKE`.** In a single-role deployment — where migrations and the application use the same role, which is the default here — the revoke is a no-op and the control does not exist, whatever the migration reports. `APP_DB_ROLE` is empty by default and the migration skips cleanly, so this is opt-in and must be adopted deliberately at deploy time.

   Suggested topology:

   ```
   pramana_owner  -- owns the schema, runs migrations, not used at runtime
   pramana_app    -- APP_DB_ROLE; SELECT/INSERT on audit_log, no UPDATE/DELETE
   ```

   *Status: `TICKETS/PR-1` stays open until a deployment actually adopts this. The code side is done; the control is only real once the roles are split.*

**Application security**
- Input validation; parameterized queries only (no string-built SQL) to prevent injection.
- Explicit exception handling; never leak stack traces or secrets in errors (matches WeGoFwd coding standards).
- Secrets from a secret manager / env, never in source.

## 3a. Wiring an identity provider (OIDC)

Pramana **verifies** tokens; it never issues them. There is no login route and no
authorization-code flow — `SSO_CLIENT_ID`/`SSO_CLIENT_SECRET` exist in config but
no code reads them. An IdP must therefore be configured before anyone can use the
API at all.

Set three values and check them with `python scripts/check_oidc.py`, which
reports *which* step failed rather than leaving you with an opaque 401:

```
SSO_ISSUER_URL=https://<tenant>.auth0.com/
JWT_AUDIENCE=<the API identifier you register>
OIDC_EMAIL_CLAIM=https://pramana.mambakkam.net/email
```

### The Auth0 trap: access tokens carry no email

First login binds an IdP `sub` to an existing user **by email**. Auth0 access
tokens for a custom API do not include `email` — that is on the *ID* token. An
API access token carries `iss`, `sub`, `aud`, `iat`, `exp`, `scope`, `azp`.

Without the claim, every first login fails with *"the token carries no email to
match it"*, and since users must be pre-provisioned, nobody can ever bind.

Auth0 also **silently drops custom claims that are not namespaced**, so the claim
must look like a URL. Add a post-login Action:

```js
exports.onExecutePostLogin = async (event, api) => {
  const ns = "https://pramana.mambakkam.net/";
  if (event.authorization) {
    api.accessToken.setCustomClaim(ns + "email", event.user.email);
    api.accessToken.setCustomClaim(ns + "email_verified", event.user.email_verified);
  }
};
```

Then set `OIDC_EMAIL_CLAIM` to that namespaced name. There is deliberately **no
fallback** to plain `email`: a deployment that believes it reads a namespaced
claim must not silently match on whatever else the token happens to carry.

### Setup steps (Auth0 console — cannot be automated from here)

1. Create a tenant.
2. **Applications → APIs → Create API.** The *Identifier* you choose becomes
   `JWT_AUDIENCE`; use a URI such as `https://pramana.mambakkam.net/api`. Signing
   algorithm **RS256**.
3. Create an application for whatever will obtain tokens, authorised for that API.
4. **Actions → Library → Build Custom**, post-login trigger, body above. Deploy
   it and add it to the Login flow.
5. Run `scripts/check_oidc.py --token "<a real token>"`. It must report the email
   claim present.

### Before the first login works

Authentication **never creates users** (§3, and `docs/00_architecture.md` §4.1).
A validly-signed token for an unknown email is refused. So:

1. Seed user rows whose `email` matches the IdP identities.
2. `make grant-role email=you@example.com` for the first compliance admin —
   without it every privileged route refuses everyone, including the route that
   grants roles.

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
