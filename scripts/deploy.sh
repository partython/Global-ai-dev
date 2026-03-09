#!/usr/bin/env bash
# ============================================================
# Priya Global Platform — Kubernetes Deploy Script
#
# Usage:
#   ./scripts/deploy.sh <environment> <image_tag> [services]
#
# Examples:
#   ./scripts/deploy.sh staging sha-abc123
#   ./scripts/deploy.sh production sha-abc123 "gateway,auth,tenant"
#   ./scripts/deploy.sh staging latest "dashboard"
# ============================================================

set -euo pipefail

# ─── Arguments ───
ENVIRONMENT="${1:?Usage: deploy.sh <environment> <image_tag> [services]}"
IMAGE_TAG="${2:?Image tag required}"
SERVICES="${3:-all}"

# ─── Configuration ───
ECR_REGISTRY="${ECR_REGISTRY:?ECR_REGISTRY env var required}"
IMAGE_PREFIX="${IMAGE_PREFIX:-priya-global}"

# Service → Namespace mapping
declare -A NAMESPACE_MAP=(
  # Core
  ["gateway"]="priya-core"
  ["auth"]="priya-core"
  ["tenant"]="priya-core"
  ["channel_router"]="priya-core"
  ["ai_engine"]="priya-core"
  ["tenant_config"]="priya-core"
  ["dashboard"]="priya-core"
  # Channels
  ["whatsapp"]="priya-channels"
  ["email"]="priya-channels"
  ["voice"]="priya-channels"
  ["social"]="priya-channels"
  ["webchat"]="priya-channels"
  ["sms"]="priya-channels"
  ["telegram"]="priya-channels"
  # Business
  ["billing"]="priya-business"
  ["analytics"]="priya-business"
  ["marketing"]="priya-business"
  ["ecommerce"]="priya-business"
  ["notification"]="priya-business"
  ["plugins"]="priya-business"
  ["handoff"]="priya-business"
  ["leads"]="priya-business"
  # Advanced
  ["conversation_intel"]="priya-advanced"
  ["appointments"]="priya-advanced"
  ["knowledge"]="priya-advanced"
  ["voice_ai"]="priya-advanced"
  ["video"]="priya-advanced"
  ["rcs"]="priya-advanced"
  ["workflows"]="priya-advanced"
  ["advanced_analytics"]="priya-advanced"
  ["ai_training"]="priya-advanced"
  ["marketplace"]="priya-advanced"
  # Ops
  ["compliance"]="priya-ops"
  ["health_monitor"]="priya-ops"
  ["cdn_manager"]="priya-ops"
  ["deployment"]="priya-ops"
)

# All services list
ALL_SERVICES="gateway,auth,tenant,channel_router,ai_engine,tenant_config,whatsapp,email,voice,social,webchat,sms,telegram,billing,analytics,marketing,ecommerce,notification,plugins,handoff,leads,conversation_intel,appointments,knowledge,voice_ai,video,rcs,workflows,advanced_analytics,ai_training,marketplace,compliance,health_monitor,cdn_manager,deployment,dashboard"

# ─── Functions ───

log() { echo "[$(date '+%H:%M:%S')] $*"; }
err() { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; }

deploy_service() {
  local svc="$1"
  local tag="$2"
  local ns="${NAMESPACE_MAP[$svc]:-priya-core}"
  local deploy_name="priya-${svc//_/-}"
  local image="${ECR_REGISTRY}/${IMAGE_PREFIX}/${svc}:${tag}"

  log "Deploying $deploy_name → $ns (image: $image)"

  # Check deployment exists
  if ! kubectl get deployment "$deploy_name" -n "$ns" &>/dev/null; then
    err "Deployment $deploy_name not found in namespace $ns — skipping"
    return 1
  fi

  # Set image
  kubectl set image deployment/"$deploy_name" \
    "${deploy_name}=${image}" \
    -n "$ns" \
    --record=false

  # Add deploy annotations
  kubectl annotate deployment/"$deploy_name" \
    -n "$ns" \
    --overwrite \
    "deploy.priya.io/image-tag=${tag}" \
    "deploy.priya.io/deployed-at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "deploy.priya.io/deployed-by=${GITHUB_ACTOR:-manual}" \
    "deploy.priya.io/environment=${ENVIRONMENT}"

  log "✓ $deploy_name image updated"
}

# ─── Main ───

log "═══════════════════════════════════════"
log "Priya Global — Deploy to ${ENVIRONMENT}"
log "Image tag: ${IMAGE_TAG}"
log "═══════════════════════════════════════"

# Resolve service list
if [ "$SERVICES" = "all" ]; then
  SERVICE_LIST="$ALL_SERVICES"
else
  SERVICE_LIST="$SERVICES"
fi

# Deploy order: core first, then channels, business, advanced, ops, dashboard last
DEPLOY_ORDER=(
  gateway auth tenant channel_router ai_engine tenant_config
  whatsapp email voice social webchat sms telegram
  billing analytics marketing ecommerce notification plugins handoff leads
  conversation_intel appointments knowledge voice_ai video rcs workflows advanced_analytics ai_training marketplace
  compliance health_monitor cdn_manager deployment
  dashboard
)

DEPLOYED=0
FAILED=0
SKIPPED=0

for svc in "${DEPLOY_ORDER[@]}"; do
  # Check if service is in the requested list
  if ! echo ",$SERVICE_LIST," | grep -q ",$svc,"; then
    continue
  fi

  if deploy_service "$svc" "$IMAGE_TAG"; then
    ((DEPLOYED++))
  else
    ((FAILED++))
  fi
done

log ""
log "═══════════════════════════════════════"
log "Deploy Summary"
log "  Deployed: $DEPLOYED"
log "  Failed:   $FAILED"
log "  Skipped:  $SKIPPED"
log "═══════════════════════════════════════"

if [ "$FAILED" -gt 0 ]; then
  err "Some services failed to deploy"
  exit 1
fi

log "✅ All services deployed successfully"
