# Deploying Pramana

Pramana runs as its own Docker Compose stack on the `mambakkam.net` box, behind
the host nginx `/pramana` path mount. It is a **separate, operator-managed stack**
— the mambakkam.net auto-deploy only rebuilds the Astro site container.

```
Internet → Cloudflare (TLS, "Full (strict)") → host nginx :443
        → location /pramana/ → 127.0.0.1:8000 → pramana-api container
                                                 ├─ pramana-postgres (own volume)
                                                 └─ pramana-migrate (one-shot)
```

## Files

| File | Role |
|---|---|
| `compose.deploy.yaml` | Production stack: own Postgres (persistent volume), one-shot `migrate`, loopback-bound `api`. Secrets come from `.env.deploy`. |
| `scripts/launch/deploy.sh` | Run on the box: git pull → compose build/up → local smoke. |
| `scripts/launch/smoke.sh` | Curl smoke; works against `http://127.0.0.1:8000` or `https://mambakkam.net/pramana`. |
| `.github/workflows/deploy-pramana.yml` | Auto-deploy on push to `main`, gated by the `PRAMANA_DEPLOY_ENABLED` repo variable. |
| `deploy/nginx/pramana.conf` | Reference copy of the host nginx block; the live copy lives in `mambakkam-net/infra/nginx/mambakkam.net.conf`. |

## `.env.deploy` (create by hand on the box — never commit)

This file is the whole runtime configuration. Compose reads it two ways: as
`--env-file` for `${VAR}` interpolation, and as each service's `env_file` so the
app reads its settings from it. Keys:

```dotenv
# --- Core ---
ENVIRONMENT=production
SECRET_KEY=<64+ random chars>            # openssl rand -hex 48
PUBLIC_BASE_URL=https://mambakkam.net/pramana

# --- Database (own Postgres container) ---
POSTGRES_PASSWORD=<strong random>        # passed to the app via PGPASSWORD (not the URL),
                                         # so any characters are safe — no URL-escaping needed.
# API_PORT defaults to 8000; only set to change the loopback port nginx proxies to.

# --- Auth / OIDC (Auth0 — deploy task 3) ---
SSO_ISSUER_URL=https://<tenant>.auth0.com/
JWT_AUDIENCE=https://pramana.mambakkam.net/api
JWT_ALGORITHM=RS256
OIDC_EMAIL_CLAIM=https://pramana.mambakkam.net/email   # namespaced custom claim

# --- Mentible handoff (ADR-011) ---
MENTIBLE_PACKAGE_HMAC_SECRET=<shared secret>
MENTIBLE_WEBHOOK_HMAC_SECRET=<shared secret>

# --- Object storage (S3) — required for archival/assets ---
S3_BUCKET_AUDIT_ARCHIVE=...
S3_BUCKET_CERTIFICATES=...
S3_BUCKET_VIDEO=...
AWS_REGION=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# --- LLM / video generation seams (managed keys) ---
LLM_API_KEY=...
VIDEO_API_KEY=...
```

The full, authoritative list of settings and their defaults is `.env.example`
(validated by `tests/test_config.py`). Anything not set here falls back to the
default in `pramana/config.py`; secrets left empty fail closed.

## First bring-up (Day 0)

```bash
# On the box, as the deploy user:
sudo git clone <repo> /opt/pramana && cd /opt/pramana
$EDITOR .env.deploy                       # fill in the keys above
bash scripts/launch/deploy.sh             # build, migrate, start, local smoke

# Seed identities — auth NEVER creates users (see SECURITY.md §3a):
#   1. Insert user rows whose emails match the IdP.
#   2. Grant the first admin from outside the request path:
sudo docker compose -f compose.deploy.yaml --env-file .env.deploy \
  run --rm api python -m scripts.grant_role email=<you@…> role=compliance_admin

# Install the nginx block (from the mambakkam-net checkout) and reload:
sudo cp /opt/mambakkam/infra/nginx/mambakkam.net.conf /etc/nginx/sites-available/mambakkam.net.conf
sudo nginx -t && sudo systemctl reload nginx

# Verify end-to-end through Cloudflare:
bash scripts/launch/smoke.sh https://mambakkam.net/pramana
```

## Enabling auto-deploy

Once the box is provisioned and `.env.deploy` is in place, set the three repo
secrets (`PRAMANA_VPS_HOST`, `PRAMANA_VPS_USER`, `PRAMANA_VPS_SSH_KEY`) and the
repo variable `PRAMANA_DEPLOY_ENABLED=true`. Until then the workflow skips
cleanly, keeping the badge green.
