# PR-4 — Injection-safe data layer + secrets + encryption verification

**Labels:** P0, security
**Refs:** SECURITY.md §3

## Acceptance criteria
- All DB access parameterized (no string-built SQL); injection tests pass.
- Secrets sourced from a secret manager/env, never in source.
- Encryption in transit + at rest verified; errors never leak secrets/stack traces.
