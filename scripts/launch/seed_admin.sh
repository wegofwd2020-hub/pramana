#!/usr/bin/env bash
# =============================================================================
# scripts/launch/seed_admin.sh — bootstrap the first compliance admin on the box
#
# Auth never creates users (_provision_by_email binds to a pre-existing, unbound,
# active user), so a fresh deployment has no one who can log in and no admin to
# grant roles over HTTP. This creates the tenant + user row and grants
# compliance_admin, both from outside the request path. Idempotent.
#
# Usage:
#   bash scripts/launch/seed_admin.sh                         # wegofwd2020@gmail.com
#   bash scripts/launch/seed_admin.sh someone@example.com
#   bash scripts/launch/seed_admin.sh someone@example.com auditor
#
# The email MUST match the address the person logs in with via the IdP; the row
# waits and its sso_subject binds on first login. Logins still require the Auth0
# tenant (deploy task 3) before this admin can actually authenticate.
# =============================================================================

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/pramana}"
COMPOSE_FILE="${COMPOSE_FILE:-$INSTALL_DIR/compose.deploy.yaml}"
ENV_FILE="${ENV_FILE:-$INSTALL_DIR/.env.deploy}"
EMAIL="${1:-wegofwd2020@gmail.com}"
ROLE="${2:-compliance_admin}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE — see deploy/README.md" >&2
  exit 1
fi

# --no-deps: postgres is already up from deploy.sh; skip re-running the migrate
# one-shot on every invocation.
run() { sudo docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" run --rm --no-deps api "$@"; }

echo "==> Seeding user row for $EMAIL"
run python scripts/seed_user.py --email "$EMAIL"

echo "==> Granting $ROLE to $EMAIL"
run python scripts/grant_role.py --email "$EMAIL" --role "$ROLE"

echo "Done. $EMAIL now holds $ROLE."
echo "Note: login requires the Auth0 tenant (deploy task 3) before this admin can authenticate."
