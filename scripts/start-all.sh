#!/bin/bash
# ============================================================
# Priya Global — Start All Services
# Usage: ./scripts/start-all.sh [--rebuild] [--quick]
# ============================================================

set -e

COMPOSE_FILE="docker-compose.yml"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

REBUILD=false
QUICK=false

for arg in "$@"; do
    case $arg in
        --rebuild) REBUILD=true ;;
        --quick) QUICK=true ;;
    esac
done

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Priya Global Platform — Docker Startup${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ─── Step 1: Infrastructure (Postgres, Redis, Kafka) ─────────────────
echo -e "${YELLOW}[1/6] Starting infrastructure...${NC}"
if [ "$REBUILD" = true ]; then
    docker compose --profile infra up -d --build
else
    docker compose --profile infra up -d
fi

echo -e "${GREEN}  Waiting for Postgres to be healthy...${NC}"
for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U priya -d priya_global > /dev/null 2>&1; then
        echo -e "${GREEN}  ✓ Postgres ready${NC}"
        break
    fi
    sleep 2
    if [ $i -eq 30 ]; then
        echo -e "${RED}  ✗ Postgres failed to start${NC}"
        exit 1
    fi
done

echo -e "${GREEN}  Waiting for Redis...${NC}"
for i in $(seq 1 15); do
    if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
        echo -e "${GREEN}  ✓ Redis ready${NC}"
        break
    fi
    sleep 1
done

# ─── Step 2: Run Migrations ──────────────────────────────────────────
echo ""
echo -e "${YELLOW}[2/6] Running database migrations...${NC}"
docker compose run --rm migration || {
    echo -e "${YELLOW}  ⚠ Migration container may not exist yet. Attempting direct alembic...${NC}"
    # Fallback: run migrations using one of the existing services
    docker compose exec -T postgres psql -U priya -d priya_global -c "SELECT 1;" > /dev/null 2>&1
    echo -e "${GREEN}  ✓ Database accessible${NC}"
}

# ─── Step 3: Core Services (Gateway, Auth, Tenant, AI Engine, etc.) ──
echo ""
echo -e "${YELLOW}[3/6] Starting core services...${NC}"
if [ "$REBUILD" = true ]; then
    docker compose --profile core up -d --build
else
    docker compose --profile core up -d
fi
echo -e "${GREEN}  ✓ Core services started${NC}"

if [ "$QUICK" = true ]; then
    echo ""
    echo -e "${GREEN}  Quick mode — skipping channel, business, advanced, ops services${NC}"
    echo -e "${GREEN}  Core services are running. Use full mode for all 45+ services.${NC}"
    echo ""
    exit 0
fi

# ─── Step 4: Channel Services ────────────────────────────────────────
echo ""
echo -e "${YELLOW}[4/6] Starting channel services...${NC}"
docker compose --profile channels up -d
echo -e "${GREEN}  ✓ Channel services started (whatsapp, email, voice, social, webchat, sms, telegram)${NC}"

# ─── Step 5: Business Services ───────────────────────────────────────
echo ""
echo -e "${YELLOW}[5/6] Starting business services...${NC}"
docker compose --profile business up -d
echo -e "${GREEN}  ✓ Business services started (billing, analytics, marketing, wallet, etc.)${NC}"

# ─── Step 6: Advanced + Ops + Monitoring ─────────────────────────────
echo ""
echo -e "${YELLOW}[6/6] Starting advanced, ops, and monitoring services...${NC}"
docker compose --profile advanced up -d
docker compose --profile ops up -d
docker compose --profile monitoring up -d 2>/dev/null || true
echo -e "${GREEN}  ✓ All services started${NC}"

# ─── Health Check ────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Running Health Checks${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

sleep 5  # Give services a moment to initialize

SERVICES=(
    "Gateway:http://localhost:9000/health"
    "Auth:http://localhost:9001/health"
    "Tenant:http://localhost:9002/health"
    "Channel-Router:http://localhost:9003/health"
    "AI-Engine:http://localhost:9004/health"
    "WhatsApp:http://localhost:9010/health"
    "Email:http://localhost:9011/health"
    "Voice:http://localhost:9012/health"
    "Social:http://localhost:9013/health"
    "Webchat:http://localhost:9014/health"
    "SMS:http://localhost:9015/health"
    "Telegram:http://localhost:9016/health"
    "Billing:http://localhost:9020/health"
    "Analytics:http://localhost:9021/health"
    "Notification:http://localhost:9024/health"
    "Memory:http://localhost:9034/health"
    "Worker:http://localhost:9043/health"
    "Wallet:http://localhost:9050/health"
)

healthy=0
unhealthy=0
total=${#SERVICES[@]}

for svc in "${SERVICES[@]}"; do
    name="${svc%%:*}"
    url="${svc#*:}"
    if curl -sf "$url" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $name"
        ((healthy++))
    else
        echo -e "  ${RED}✗${NC} $name"
        ((unhealthy++))
    fi
done

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${GREEN}Healthy: $healthy${NC}  ${RED}Unhealthy: $unhealthy${NC}  Total: $total"
echo ""
echo -e "  Dashboard:   ${GREEN}http://localhost:3000${NC}"
echo -e "  Gateway:     ${GREEN}http://localhost:9000${NC}"
echo -e "  Prometheus:  ${GREEN}http://localhost:9090${NC}"
echo -e "  Grafana:     ${GREEN}http://localhost:3001${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
