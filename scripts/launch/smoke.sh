#!/usr/bin/env bash
# =============================================================================
# scripts/launch/smoke.sh — post-deploy smoke check for Pramana
#
# Curl-based end-to-end smoke. Run after every deploy (CI calls it against the
# public URL; deploy.sh calls it locally; the operator can run it by hand).
#
# Usage:
#   bash scripts/launch/smoke.sh                                  # 127.0.0.1:8000
#   bash scripts/launch/smoke.sh https://mambakkam.net/pramana
#   bash scripts/launch/smoke.sh -k https://mambakkam.net/pramana # tolerate self-signed
#
# The prefix is baked into BASE_URL, so the same paths work locally (the
# container serves bare paths) and through the /pramana mount (nginx strips the
# prefix). Exit 0 = every check passed; 1 = at least one failed.
#
# Checks (~3s):
#   - GET /health              200 + {"status":"ok"}      (liveness)
#   - GET /health/ready        200 + database "ok"        (DB reachable)
#   - GET /certificates/verify/<bogus>  200 + valid:false (public data path works)
#   - GET /docs                404                         (proves prod gating)
#   - GET /assignments         401                         (proves auth gate is on)
# =============================================================================

set -uo pipefail   # not -e: collect failures, do not abort on the first

INSECURE_FLAG=()
POSITIONAL=()
for arg in "$@"; do
  case "$arg" in
    -k|--insecure) INSECURE_FLAG=(-k) ;;
    -h|--help)     sed -n '2,25p' "$0"; exit 0 ;;
    *)             POSITIONAL+=("$arg") ;;
  esac
done
[[ "${SMOKE_INSECURE:-0}" == "1" ]] && INSECURE_FLAG=(-k)

BASE_URL="${POSITIONAL[0]:-http://127.0.0.1:8000}"
BASE_URL="${BASE_URL%/}"   # strip trailing slash

bold="\033[1m"; green="\033[0;32m"; red="\033[0;31m"; reset="\033[0m"
declare -a FAILURES=()
pass() { echo -e "  ${green}\xE2\x9C\x93${reset} $1"; }
fail() { echo -e "  ${red}\xE2\x9C\x97${reset} $1 \xE2\x80\x94 $2"; FAILURES+=("$1: $2"); }

# Emits body + '::status::<code>'. Times out at 10s. Does not follow redirects:
# a compliance API should answer directly, and /assignments must 401 rather than
# bounce to a login.
http_get() {
  curl -s "${INSECURE_FLAG[@]}" -m 10 -w '::status::%{http_code}' \
    -A 'pramana-smoke/1.0' "$1" 2>&1
}
extract_status() { local s="$1"; printf '%s' "${s##*::status::}"; }
extract_body()   { local s="$1"; printf '%s' "${s%::status::*}"; }

echo ""
echo -e "${bold}=== pramana smoke check ===${reset}"
echo "    target: $BASE_URL"
echo ""

# ── Liveness ─────────────────────────────────────────────────────────────────
# Assert on the body, not just the 200: a stray service on :8000 has answered a
# health probe convincingly before. Only Pramana returns {"status":"ok"}.
RESP=$(http_get "$BASE_URL/health"); STATUS=$(extract_status "$RESP"); BODY=$(extract_body "$RESP")
if [[ "$STATUS" == "200" ]] && grep -q '"status"' <<<"$BODY" && grep -q '"ok"' <<<"$BODY"; then
  pass "GET /health -> 200 + {\"status\":\"ok\"}"
else
  fail "GET /health" "status=$STATUS body=${BODY:0:80}"
fi

# ── Readiness (database reachable) ───────────────────────────────────────────
RESP=$(http_get "$BASE_URL/health/ready"); STATUS=$(extract_status "$RESP"); BODY=$(extract_body "$RESP")
if [[ "$STATUS" == "200" ]] && grep -qi 'ok\|ready' <<<"$BODY"; then
  pass "GET /health/ready -> 200 + database ok"
else
  fail "GET /health/ready" "status=$STATUS body=${BODY:0:80} (503 = DB unreachable)"
fi

# ── Public verification route works end-to-end (no auth, hits the DB) ────────
BOGUS="smoke$(date +%s)notarealverificationcode"
RESP=$(http_get "$BASE_URL/certificates/verify/$BOGUS"); STATUS=$(extract_status "$RESP"); BODY=$(extract_body "$RESP")
if [[ "$STATUS" == "200" ]] && grep -qi 'valid' <<<"$BODY" && grep -qi 'false' <<<"$BODY"; then
  pass "GET /certificates/verify/<bogus> -> 200 + valid:false"
else
  fail "GET /certificates/verify/<bogus>" "status=$STATUS body=${BODY:0:80}"
fi

# ── /docs is gated in production ─────────────────────────────────────────────
# A 200 here means ENVIRONMENT is not 'production' — the compliance API's whole
# surface would be public.
RESP=$(http_get "$BASE_URL/docs"); STATUS=$(extract_status "$RESP")
if [[ "$STATUS" == "404" ]]; then
  pass "GET /docs -> 404 (docs disabled in production)"
else
  fail "GET /docs" "status=$STATUS (expected 404; is ENVIRONMENT=production?)"
fi

# ── Auth gate is on ──────────────────────────────────────────────────────────
# An unauthenticated privileged route must be refused. A 200 means the gate is
# off; a 500 means something is broken behind it.
RESP=$(http_get "$BASE_URL/assignments"); STATUS=$(extract_status "$RESP")
if [[ "$STATUS" == "401" ]]; then
  pass "GET /assignments -> 401 (auth required)"
else
  fail "GET /assignments" "status=$STATUS (expected 401)"
fi

echo ""
if [[ ${#FAILURES[@]} -eq 0 ]]; then
  echo -e "${green}${bold}== all smoke checks passed ==${reset}"
  exit 0
else
  echo -e "${red}${bold}== ${#FAILURES[@]} smoke check(s) failed ==${reset}"
  for f in "${FAILURES[@]}"; do echo -e "  ${red}\xE2\x80\xA2${reset} $f"; done
  exit 1
fi
