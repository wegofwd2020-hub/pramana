#!/usr/bin/env bash
# =============================================================================
# scripts/launch/deploy.sh — pull, migrate, rebuild, restart, smoke
#
# Run on the box (as the `deploy` user). Called by:
#   - .github/workflows/deploy-pramana.yml on every push to main
#   - the operator manually for a forced redeploy
#
# Usage:
#   bash /opt/pramana/scripts/launch/deploy.sh
#
# The migration ordering is handled by compose: the `migrate` service runs
# `alembic upgrade head` to completion and `api` waits on
# service_completed_successfully, so the app never starts against an unmigrated
# schema. This script does not run alembic itself.
#
# Exit codes:
#   0 — deploy + local smoke green
#   1 — git pull failed
#   2 — docker compose build/up failed
#   3 — local smoke failed (containers up but not serving correctly)
# =============================================================================

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/pramana}"
COMPOSE_FILE="${COMPOSE_FILE:-$INSTALL_DIR/compose.deploy.yaml}"
ENV_FILE="${ENV_FILE:-$INSTALL_DIR/.env.deploy}"
LOCAL_URL="${LOCAL_URL:-http://127.0.0.1:8000}"

bold="\033[1m"; green="\033[0;32m"; red="\033[0;31m"; reset="\033[0m"
log() { echo -e "${bold}[$(date -u +%H:%M:%S)]${reset} $*"; }
ok()  { echo -e "  ${green}\xE2\x9C\x93${reset} $*"; }
err() { echo -e "  ${red}\xE2\x9C\x97${reset} $*" >&2; }

compose() { sudo docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }

cd "$INSTALL_DIR"

# The env file is the whole configuration — fail early and clearly if it is
# absent, rather than surfacing as a confusing compose interpolation error.
if [[ ! -f "$ENV_FILE" ]]; then
  err "missing $ENV_FILE — see deploy/README.md for the required keys"
  exit 2
fi

# ── 1. git pull ──────────────────────────────────────────────────────────────
log "1/4  git fetch + reset --hard origin/main"
if sudo git -C "$INSTALL_DIR" fetch origin main && \
   sudo git -C "$INSTALL_DIR" reset --hard origin/main; then
  HEAD_SHA="$(git -C "$INSTALL_DIR" rev-parse --short HEAD)"
  ok "now at $HEAD_SHA"
else
  err "git pull failed"
  exit 1
fi

# ── 2. docker compose up (builds image, runs migrate, then api) ──────────────
log "2/4  docker compose build + up -d"
if compose up -d --build --remove-orphans; then
  ok "compose up -d succeeded"
else
  err "compose up -d failed"
  exit 2
fi

# ── 3. wait for the api healthcheck to settle ────────────────────────────────
log "3/4  waiting 15s for the healthcheck to settle"
sleep 15
compose ps

# ── 4. local smoke ───────────────────────────────────────────────────────────
log "4/4  local smoke ($LOCAL_URL)"
if bash "$INSTALL_DIR/scripts/launch/smoke.sh" "$LOCAL_URL"; then
  ok "local smoke passed"
else
  err "local smoke failed — containers are up but not serving correctly"
  exit 3
fi

log "deploy complete (HEAD=$HEAD_SHA)"
