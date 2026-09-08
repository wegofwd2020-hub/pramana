# PR-1 — DB-level REVOKE on audit table (app role cannot UPDATE/DELETE) + test

**Labels:** P0, security, compliance
**Refs:** SECURITY.md §3/§7

## Why
The sister Thittam review left an `audit_log` REVOKE open; make it an acceptance test here so it never ships open.

## Acceptance criteria
- [x] Migration revokes UPDATE/DELETE on the audit table from the application role.
      — `0009_audit_log_grants`, applied when `APP_DB_ROLE` names a non-owning role.
- [x] An acceptance test asserts the app role cannot modify/delete audit rows.
      — `tests/integration/test_audit_role_privileges.py`, against a real Postgres
      with a real second role. Asserts the refusal is SQLSTATE **42501**
      (`InsufficientPrivilege`) and *not* **P0001** (the `0001` trigger); a test
      that accepted either would pass with no grants applied at all.

## Found while closing this: TRUNCATE bypassed append-only

The `0001` triggers are `FOR EACH ROW`, and row triggers do not fire on TRUNCATE.
Verified on Postgres 16: `UPDATE`/`DELETE` blocked (P0001), **`TRUNCATE`
succeeded — every row gone.** The hash chain cannot detect this; it proves rows
were not altered, and an empty table has no chain to check.

`0011_audit_log_no_truncate` adds `BEFORE TRUNCATE ... FOR EACH STATEMENT`
triggers to `audit_log` and `audit_archive_segment`. Statement triggers fire for
**every** role including the owner, so unlike `0009` this holds in the
single-role topology every deployment actually runs.

## Status

**Code and tests: done.** The privilege control is proven, and the TRUNCATE hole
is closed for all topologies.

**The ticket stays open on one point:** no deployment has adopted the two-role
split, so `APP_DB_ROLE` is still empty in production and `0009` still skips. See
`SECURITY.md` §3. Adopting it means creating `pramana_owner`/`pramana_app` and
re-pointing `DATABASE_URL` on a live database — a deployment change, not a code
change.
