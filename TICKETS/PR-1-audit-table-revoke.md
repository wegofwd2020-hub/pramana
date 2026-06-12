# PR-1 — DB-level REVOKE on audit table (app role cannot UPDATE/DELETE) + test

**Labels:** P0, security, compliance
**Refs:** SECURITY.md §3/§7

## Why
The sister Thittam review left an `audit_log` REVOKE open; make it an acceptance test here so it never ships open.

## Acceptance criteria
- Migration revokes UPDATE/DELETE on the audit table from the application role.
- An acceptance test asserts the app role cannot modify/delete audit rows.
