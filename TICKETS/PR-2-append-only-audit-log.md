# PR-2 — Append-only, tamper-evident audit log

**Labels:** P0, security, compliance
**Refs:** SECURITY.md §3/§4

## Acceptance criteria
- Audit log is append-only; entries are attributable (who/what/when).
- Archive uses WORM/Object-Lock (e.g. S3 Object Lock) per resolved decisions.
- Tampering attempts are detectable; tested with mock audit events.
