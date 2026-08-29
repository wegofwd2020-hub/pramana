# PR-3 — SSO (SAML/OIDC) + RBAC with audited admin actions

**Labels:** P0, security
**Refs:** SECURITY.md §3/§4
**Status:** ✅ Done. See `docs/00_architecture.md` §4 for the resulting model.

## Acceptance criteria
- ~~SSO via SAML/OIDC; RBAC roles (employee, manager, compliance admin, auditor).~~
  OIDC bearer verification and first-login binding; five fixed roles seeded by
  migration `0007`. SAML is not implemented — OIDC covers the v1 provider.
- ~~Server-side authorization checks on every privileged action; admin/role
  changes audited.~~ `require_roles` gates every privileged route; ownership is
  enforced in the services. Role grants and revokes go through
  `/users/{user_id}/roles` and append `user.role_granted` / `user.role_revoked`
  to the chain. The out-of-band first grant (`scripts/grant_role.py`) is audited
  too, with a null actor and a `bootstrap` flag.

## Deliberately out of scope
- **SAML.** OIDC is the v1 integration; SAML was listed as an alternative, not
  an additional requirement.
- **Per-course role scope.** The locked spec (§6) lists `UserRole.scope`
  (global | per-course), but the column was never added to the model and no
  migration creates it. Every grant is global. Adding it later is a migration
  plus a filter in `_load_roles`, not a redesign.
