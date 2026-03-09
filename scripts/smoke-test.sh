#!/usr/bin/env bash
# ============================================================
# Priya Global Platform — Smoke Tests
#
# Post-deploy health verification for all services.
# Tests critical paths to ensure the platform is functional.
#
# Usage:
#   ./scripts/smoke-test.sh <environment>
#   ./scripts/smoke-test.sh staging
#   ./scripts/smoke-test.sh production
#
# Env vars:
#   BASE_URL       — API gateway URL (default: http://localhost:9000)
#   DASHBOARD_URL  — Dashboard URL (default: http://localhost:3000)
#   TIMEOUT        — Request timeout in seconds (default: 10)
# ============================================================

set -euo pipefail

ENVIRONMENT="${1:?Usage: smoke-test.sh <environment>}"

# ─── Configuration ───

case "$ENVIRONMENT" in
  production)
    BASE_URL="${BASE_URL:-https://api.currentglobal.com}"
    DASHBOARD_URL="${DASHBOARD_URL:-https://app.currentglobal.com}"
    ;;
  staging)
    BASE_URL="${BASE_URL:-https://staging-api.currentglobal.com}"
    DASHBOARD_URL="${DASHBOARD_URL:-https://staging.currentglobal.com}"
    ;;
  *)
    BASE_URL="${BASE_URL:-http://localhost:9000}"
    DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:3000}"
    ;;
esac

TIMEOUT="${TIMEOUT:-10}"
PASSED=0
FAILED=0
WARNINGS=0

# ─── Functions ───

log()  { echo "[$(date '+%H:%M:%S')] $*"; }
pass() { echo "[$(date '+%H:%M:%S')] ✅ $*"; ((PASSED++)); }
fail() { echo "[$(date '+%H:%M:%S')] ❌ $*"; ((FAILED++)); }
warn() { echo "[$(date '+%H:%M:%S')] ⚠️  $*"; ((WARNINGS++)); }

check_endpoint() {
  local name="$1"
  local url="$2"
  local expected_status="${3:-200}"

  local status
  status=$(curl -s -o /dev/null -w '%{http_code}' \
    --max-time "$TIMEOUT" \
    --connect-timeout 5 \
    "$url" 2>/dev/null) || status="000"

  if [ "$status" = "$expected_status" ]; then
    pass "$name → $status"
  elif [ "$status" = "000" ]; then
    fail "$name → TIMEOUT/UNREACHABLE"
  else
    fail "$name → $status (expected $expected_status)"
  fi
}

check_json_field() {
  local name="$1"
  local url="$2"
  local field="$3"

  local response
  response=$(curl -s --max-time "$TIMEOUT" --connect-timeout 5 "$url" 2>/dev/null) || response=""

  if [ -z "$response" ]; then
    fail "$name → No response"
    return
  fi

  if echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '$field' in d" 2>/dev/null; then
    pass "$name → field '$field' present"
  else
    fail "$name → field '$field' missing"
  fi
}

# ─── Smoke Tests ───

log "═══════════════════════════════════════════════"
log "Priya Global — Smoke Tests ($ENVIRONMENT)"
log "API:       $BASE_URL"
log "Dashboard: $DASHBOARD_URL"
log "═══════════════════════════════════════════════"
log ""

# ── 1. Gateway Health ──
log "── Gateway & Core ──"
check_endpoint "Gateway health" "$BASE_URL/health"
check_endpoint "Gateway readiness" "$BASE_URL/ready"
check_json_field "Gateway status" "$BASE_URL/health" "status"

# ── 2. Auth Service ──
log ""
log "── Auth Service ──"
check_endpoint "Auth health" "$BASE_URL/api/v1/auth/health"
check_endpoint "Auth login (expect 422 without body)" "$BASE_URL/api/v1/auth/login" "422"

# ── 3. Tenant Service ──
log ""
log "── Tenant Service ──"
check_endpoint "Tenant health" "$BASE_URL/api/v1/tenants/health"

# ── 4. AI Engine ──
log ""
log "── AI Engine ──"
check_endpoint "AI Engine health" "$BASE_URL/api/v1/ai/health"

# ── 5. Channel Router ──
log ""
log "── Channel Router ──"
check_endpoint "Channel Router health" "$BASE_URL/api/v1/channels/health"

# ── 6. Channel Services ──
log ""
log "── Channel Services ──"
for channel in whatsapp email voice social webchat sms telegram; do
  check_endpoint "$channel health" "$BASE_URL/api/v1/${channel}/health"
done

# ── 7. Business Services ──
log ""
log "── Business Services ──"
for svc in billing analytics marketing ecommerce notification plugins handoff leads; do
  check_endpoint "$svc health" "$BASE_URL/api/v1/${svc}/health"
done

# ── 8. Advanced Services ──
log ""
log "── Advanced Services ──"
for svc in conversations appointments knowledge voice-ai video rcs workflows advanced-analytics ai-training marketplace; do
  check_endpoint "$svc health" "$BASE_URL/api/v1/${svc}/health"
done

# ── 9. Ops Services ──
log ""
log "── Ops Services ──"
for svc in compliance health-monitor cdn deployment; do
  check_endpoint "$svc health" "$BASE_URL/api/v1/${svc}/health"
done

# ── 10. Tenant Config ──
log ""
log "── Tenant Config ──"
check_endpoint "Tenant Config health" "$BASE_URL/api/v1/tenant-config/health"

# ── 11. Dashboard ──
log ""
log "── Dashboard ──"
check_endpoint "Dashboard home" "$DASHBOARD_URL" "200"
check_endpoint "Dashboard login page" "$DASHBOARD_URL/login" "200"

# ── 12. Critical Paths ──
log ""
log "── Critical Path Tests ──"

# Test CORS headers
log "Checking CORS headers..."
CORS=$(curl -s -I -X OPTIONS \
  -H "Origin: https://app.currentglobal.com" \
  -H "Access-Control-Request-Method: POST" \
  --max-time "$TIMEOUT" \
  "$BASE_URL/api/v1/auth/login" 2>/dev/null | grep -i "access-control" || true)

if [ -n "$CORS" ]; then
  pass "CORS headers present"
else
  warn "CORS headers not detected (may be OK if handled by ALB)"
fi

# Test rate limiting headers
log "Checking rate limiting..."
RATE=$(curl -s -I --max-time "$TIMEOUT" "$BASE_URL/health" 2>/dev/null | grep -i "x-ratelimit\|retry-after" || true)
if [ -n "$RATE" ]; then
  pass "Rate limiting headers present"
else
  warn "Rate limiting headers not detected"
fi

# Test security headers
log "Checking security headers..."
SECURITY_HEADERS=$(curl -s -I --max-time "$TIMEOUT" "$DASHBOARD_URL" 2>/dev/null)

for header in "x-frame-options" "x-content-type-options" "strict-transport-security"; do
  if echo "$SECURITY_HEADERS" | grep -qi "$header"; then
    pass "Security header: $header"
  else
    warn "Missing security header: $header"
  fi
done

# ─── Summary ───

log ""
log "═══════════════════════════════════════════════"
log "Smoke Test Results ($ENVIRONMENT)"
log "  ✅ Passed:   $PASSED"
log "  ❌ Failed:   $FAILED"
log "  ⚠️  Warnings: $WARNINGS"
log "═══════════════════════════════════════════════"

if [ "$FAILED" -gt 0 ]; then
  log ""
  log "❌ SMOKE TESTS FAILED — $FAILED endpoints are down"
  exit 1
elif [ "$WARNINGS" -gt 3 ]; then
  log ""
  log "⚠️  SMOKE TESTS PASSED WITH WARNINGS — review above"
  exit 0
else
  log ""
  log "✅ ALL SMOKE TESTS PASSED"
  exit 0
fi
