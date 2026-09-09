# PR-4 — Injection-safe data layer + secrets + encryption verification

**Labels:** P0, security
**Refs:** SECURITY.md §3

## Acceptance criteria
- [x] All DB access parameterized (no string-built SQL); injection tests pass.
      — held already; now enforced. `tests/test_no_string_built_sql.py` walks
      `pramana/`, `scripts/` and `alembic/` with `ast` and fails on SQL built by
      f-string, `+`, `%` or `.format()`. `tests/integration/test_injection_safety.py`
      drives hostile payloads through `search_audit` against a real Postgres.
- [x] Secrets sourced from a secret manager/env, never in source.
      — held already; now enforced. `tests/test_secret_hygiene.py` requires every
      credential-shaped setting to be `SecretStr`, requires `SECRET_KEY` to have
      no default, and asserts secret values do not survive `repr(Settings)`.
- [ ] Encryption in transit + at rest verified; errors never leak secrets/stack traces.
      — the error half is fixed (below). **In transit: verified good.**
      **At rest: verified ABSENT.** See *Encryption, verified* below.

## Found while closing this: errors returned PII, the SQL, and the DB password

Two places turned a raw driver failure into a `DatabaseError`, and both handed
the driver's own text to the HTTP client. `pramana/api/errors.py` renders
`exc.message` and `exc.context` verbatim, which is correct for messages we
author and wrong for text SQLAlchemy authored.

**1. `session_scope` interpolated the driver error into the message.** Every
DB-backed route runs inside it, and it wraps *every* unexpected exception, so
this was the default behaviour rather than an edge case. SQLAlchemy's `str()`
on a `DBAPIError` carries `[SQL: ...]` and `[parameters: (...)]`. Reproduced —
a unique-violation returned this in a 502 body:

```
duplicate key value violates unique constraint "user_email_key"
DETAIL:  Key (email)=(ceo@acme-client.example) already exists.
[SQL: INSERT INTO "user" (email, sso_subject, full_name) VALUES ($1, $2, $3)]
[parameters: ('ceo@acme-client.example', 'auth0|64f1c0deadbeef', 'Jane Doe')]
```

An email, an Auth0 subject identifier, a full name, the constraint and the
statement — to whoever triggered the error.

**2. `get_engine` put `settings.database_url` into `context`.** That is the DSN,
password included, and `context` is rendered into the response body. Reproduced
with a malformed DSN — the password came back in a 502. A malformed DSN is
exactly when this fires.

Both are CWE-209. Fixed by giving the caller a fixed message and an
`incident_id`, and sending the detail to the structlog record under that id, so
support can still answer "what happened" without the body carrying it. The
`from exc` chain is kept, so the id points at a real traceback.

Checked and found clean while here: `ObjectStorageError` and
`EmailDeliveryError` have no equivalent wrap; auth errors are deliberately terse
and never echo a token; a connection failure surfaces only `[Errno 111]`, so the
DSN password does not leak on that path.

## Known gap, deliberately not fixed here

`database_url` is a plain `str`, so its password survives `repr(Settings)` and
`model_dump()`. Nothing renders settings today, and the one path that put the
DSN into a response body is fixed, so this is latent rather than live. Typing it
`SecretStr` means touching every consumer including `alembic/env.py` — a
deliberate change, not a drive-by. Recorded as a strict `xfail` in
`tests/test_secret_hygiene.py`: when it is fixed the test starts passing and the
strict xfail fails the run, forcing the marker to be removed.

## Encryption, verified 2026-09-09

### In transit — PASS

Measured against `mambakkam.net` from outside the box:

| check | result |
|---|---|
| TLS 1.0 / 1.1 | rejected |
| TLS 1.2 / 1.3 | accepted, `ECDHE-ECDSA-CHACHA20-POLY1305` |
| plain HTTP `/pramana/health` | `301` to `https://` |
| HSTS | `max-age=31536000; includeSubDomains` |
| other headers | `x-content-type-options: nosniff`, `x-frame-options: SAMEORIGIN` |
| certificate | Let's Encrypt, `CN=mambakkam.net`, valid to 2026-10-13 |

Also confirmed on the box: `pramana-api` binds `127.0.0.1:8000` and the
Postgres container publishes no host port, so neither is reachable except
through nginx.

### At rest — FAIL

**There is no encryption at rest, and the audit evidence is what sits on that
disk.** Observed on the box:

```
sda1  part ext4  76G  /          <- plain ext4, no dm-crypt
/dev/mapper/                      <- contains only `control`; no LUKS mapping
volume pramana_pramana-pgdata -> /var/lib/docker/volumes/.../_data  (on /dev/sda1)
```

So the hash-chained `audit_log` — the table PR-1 and PR-2 spent their effort
making tamper-evident — is stored in cleartext. The hash chain proves nobody
*altered* the rows; it does nothing to stop somebody *reading* them from a
snapshot, a copied image, or a recovered disk. (This says nothing about what
the hypervisor does underneath; it is what the guest can verify, and any
guest-level snapshot or backup is cleartext.)

Options, roughly in increasing order of effort:

1. **Accept and document the residual risk**, on the grounds that the threat is
   physical/snapshot access to the VPS. Honest, and a decision someone has to
   actually take rather than inherit by default.
2. **LUKS-backed volume for `pgdata`.** Protects against disk removal, image
   copy and snapshot theft. It does not protect against a root compromise,
   because the key must be available to the box at boot — on a VPS that means
   either a key file on the same disk (weak) or remote unlock (operationally
   painful).
3. **Managed Postgres with at-rest encryption**, moving the problem to a
   provider that solves it properly.
4. **Column-level encryption** (`pgcrypto`) for the sensitive fields. Heaviest,
   and it would break the audit query filters this PR just hardened.

Whichever is chosen, it is a deployment change, not a code change.

## Status

**Code and tests: done** for injection safety, secret hygiene, and error
leakage. Three properties that were true but unenforced now have tests that fail
if they stop being true; one live defect is fixed.

**The ticket stays open on encryption at rest.** Both halves were checked on
2026-09-09; one passes and one does not.

Same shape as PR-1's two-role topology and PR-2's WORM bucket: the code side is
finished and the ticket closes on a deployment fact.
