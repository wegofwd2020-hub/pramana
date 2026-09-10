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

## Verified in production 2026-09-10

`verify_audit.py` had never been run against the real database. It has now, on
the box, at deployed commit `2460956`:

```
  ok  row chain: 2 row(s), unbroken
  --    archive: nothing archived yet
  --    2 row(s) pending archival (archived through 0)

  evidence intact                                            EXIT=0
```

So the operational half of this ticket is proven end to end where it matters:
the tool ships in the running image, reads the production chain, and reports
honestly — including that the archive is empty rather than pretending otherwise.
`archive_audit.py --status` agrees: *archived through audit_id 0; 2 row(s)
pending*.

That is the strongest statement available while the archive is unconfigured, and
it is worth having: the row chain is intact, and the gap is known and named.

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

**Step 1 was put to the product owner on 2026-09-10 and deliberately deferred.**
No bucket is being provisioned yet, so this ticket stays open with the archive
protecting nothing — stated plainly rather than left implicit.

The provider choice is a real constraint, not a preference, because
`services/storage.py:107` writes `ObjectLockMode="COMPLIANCE"` with a
7-year `ObjectLockRetainUntilDate`. `COMPLIANCE` is deliberate: under
`GOVERNANCE` a sufficiently privileged principal can delete anyway, which
defeats the control. Options weighed:

- **AWS S3** — the only one with first-class, well-tested Object Lock COMPLIANCE
  support and a legal-hold story auditors recognise. Pennies at this volume.
- **Hetzner Object Storage** — already the box's provider, but its S3
  compatibility does not reliably cover Object Lock COMPLIANCE. If it does not,
  `put_object` fails and archival silently cannot run, which is worse than not
  having it. Verify before committing.
- **MinIO on the box** — supports Object Lock, but would put the archive on the
  same disk as the database it exists to outlive. Useful only as a local test of
  the archive path.

Note the irreversibility: in COMPLIANCE mode not even the account root can delete
an object before its retention expires. That is the point, and it is also why the
bucket should be created deliberately and named unambiguously.
