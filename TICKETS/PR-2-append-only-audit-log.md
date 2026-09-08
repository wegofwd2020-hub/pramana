# PR-2 — Append-only, tamper-evident audit log

**Labels:** P0, security, compliance
**Refs:** SECURITY.md §3/§4

## Acceptance criteria

- [x] **Audit log is append-only; entries are attributable (who/what/when).**
      `0001` triggers block UPDATE/DELETE; `0011` blocks TRUNCATE, which those
      row triggers never covered (see PR-1). Rows carry `actor_user_id`,
      `occurred_at`, `entity_type`/`entity_id` and `event_type`.
      `actor_user_id` is deliberately NULL for system events — the one such
      path, HMAC package ingest, records its provenance (package id, version,
      content hash, engine/model/provider) in the payload instead.
- [x] **Tampering attempts are detectable; tested with mock audit events.**
      `verify_chain` recomputes every row hash and follows the links;
      `GET /audit/verify` exposes it to auditors; unit and integration tests
      cover a tampered row.
- [~] **Archive uses WORM/Object-Lock.** The code is complete and correct —
      `storage.py` writes with `ObjectLockMode="COMPLIANCE"` and a retention
      date — but **no deployment has ever run it.** See "Not closed" below.

## Found while closing this: nothing ever looked for a dropped segment

`segments_are_contiguous` exists precisely to detect a *missing archive
segment*, and `domain/audit_archive.py` says the manifests make "a missing
segment as detectable as a missing row". **It was called from nothing but its
own tests.** The capability was built and the check was never run — so an
archive with a hole in it would have reported as healthy.

Added:

- `verify_segment_continuity()` (pure) — walks a whole archive, reports every
  gap, distinguishes an id jump from a broken hash link (ids alone are
  forgeable; only a segment that genuinely follows carries the right hash).
- `services.audit_archive.verify_archive()` — runs it over the recorded
  segments.
- **`scripts/verify_audit.py` / `make verify-audit`** — the missing operational
  answer to "has this been tampered with?", from a shell, needing only
  `DATABASE_URL`. Deliberately not only an API route: when the question is
  whether the evidence has been altered, the answer should not depend on the
  application under suspicion still being healthy and honest. Exits non-zero on
  a break; `--strict-archive` also fails on archival lag, for scheduling.

Verified end to end against a real database: dropped the append-only trigger,
edited one row, and the script named the row and both hashes and exited 1.

## Not closed

**WORM archival has never run in production.** Checked on the box:
`S3_BUCKET_AUDIT_ARCHIVE`, `S3_ENDPOINT_URL` and `AWS_ACCESS_KEY_ID` are all
empty, there is no cron or systemd timer, and `audit_archive_segment` holds
**0 rows**. So the archive that exists to survive the database being lost or
disputed currently protects nothing.

Closing this needs, in order:
1. An S3 bucket **created with Object Lock enabled** — S3 cannot enable it on an
   existing bucket, and `put_object` with a retention header fails without it.
2. Those settings in `.env.deploy`, then recreate `api`.
3. `make archive-audit` on a schedule, and `make verify-audit --strict-archive`
   alongside it so a silent stop is noticed.
