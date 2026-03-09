#!/usr/bin/env bash
# ============================================================
# Priya Global Platform — Local Dev Boot Script
#
# Usage:
#   ./scripts/dev-boot.sh           — Start core (gateway, auth, tenant, dashboard)
#   ./scripts/dev-boot.sh full      — Start ALL services
#   ./scripts/dev-boot.sh infra     — Start only infrastructure
#   ./scripts/dev-boot.sh channels  — Start core + channel services
#   ./scripts/dev-boot.sh status    — Show running services
#   ./scripts/dev-boot.sh stop      — Stop everything
#   ./scripts/dev-boot.sh logs      — Tail all logs
#   ./scripts/dev-boot.sh clean     — Stop + remove volumes (DESTRUCTIVE)
# ============================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# ─── Helpers ───

banner() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${CYAN}  Priya Global Platform — Local Dev${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
info() { echo -e "  ${BLUE}→${NC} $1"; }

# ─── Pre-flight checks ───

preflight() {
    echo -e "${BOLD}Pre-flight checks...${NC}"

    # Docker
    if ! command -v docker &>/dev/null; then
        fail "Docker not installed. Install from https://docker.com"
        exit 1
    fi
    if ! docker info &>/dev/null 2>&1; then
        fail "Docker daemon not running. Start Docker Desktop first."
        exit 1
    fi
    ok "Docker running"

    # Docker Compose
    if ! docker compose version &>/dev/null 2>&1; then
        fail "Docker Compose v2 not found. Update Docker Desktop."
        exit 1
    fi
    ok "Docker Compose v2"

    # .env file
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        fail ".env file not found!"
        echo ""
        info "Create it from the example:"
        echo "    cp .env.example .env"
        echo "    # Then edit .env with your values"
        exit 1
    fi
    ok ".env file exists"

    # Required env vars (set -a exports all sourced vars)
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
    local missing=0
    for var in POSTGRES_PASSWORD; do
        if [ -z "${!var}" ]; then
            fail "$var not set in .env"
            missing=1
        fi
    done
    if [ $missing -eq 1 ]; then
        exit 1
    fi
    ok "Required env vars set"

    # Check ports
    for port in 5432 6379 9092 9000 3000; do
        if lsof -Pi :$port -sTCP:LISTEN -t &>/dev/null; then
            warn "Port $port already in use (may conflict)"
        fi
    done

    echo ""
}

# ─── Build base image if needed ───

build_base() {
    if ! docker image inspect priya-global/python-base:latest &>/dev/null 2>&1; then
        echo -e "${BOLD}Building Python base image (first time only)...${NC}"
        docker build -f Dockerfile.python-base -t priya-global/python-base:latest .
        ok "Python base image built"
        echo ""
    else
        ok "Python base image exists"
    fi
}

# ─── Wait for service health ───

wait_healthy() {
    local container=$1
    local max_wait=${2:-60}
    local elapsed=0

    while [ $elapsed -lt $max_wait ]; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "not_found")
        case "$status" in
            healthy) return 0 ;;
            not_found) return 1 ;;
        esac
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

# ─── Commands ───

cmd_infra() {
    banner
    preflight

    echo -e "${BOLD}Starting infrastructure...${NC}"
    docker compose --profile infra up -d

    info "Waiting for PostgreSQL..."
    if wait_healthy priya-postgres 30; then
        ok "PostgreSQL ready (port 5432)"
    else
        fail "PostgreSQL failed to start"
        docker compose logs postgres | tail -10
        exit 1
    fi

    info "Waiting for Redis..."
    if wait_healthy priya-redis 15; then
        ok "Redis ready (port 6379)"
    else
        fail "Redis failed to start"
    fi

    info "Waiting for Kafka..."
    if wait_healthy priya-kafka 45; then
        ok "Kafka ready (port 9092)"
    else
        warn "Kafka still starting (may take 30-60s)"
    fi

    echo ""
    ok "Infrastructure is UP"
    echo ""
}

cmd_core() {
    cmd_infra
    build_base

    echo -e "${BOLD}Starting core services...${NC}"
    docker compose --profile core up -d

    info "Services starting up (may take 15-30s)..."
    sleep 5

    # Check each core service
    for svc in gateway auth tenant; do
        container="priya-${svc}"
        if docker ps --format '{{.Names}}' | grep -q "$container"; then
            ok "$svc running"
        else
            warn "$svc may still be starting"
        fi
    done

    echo ""
    echo -e "${BOLD}Starting dashboard...${NC}"
    docker compose up -d dashboard 2>/dev/null || warn "Dashboard not in compose (may need separate npm start)"

    echo ""
    echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}${BOLD}  Local dev is UP!${NC}"
    echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  ${CYAN}Gateway:${NC}   http://localhost:9000"
    echo -e "  ${CYAN}Auth:${NC}      http://localhost:9001"
    echo -e "  ${CYAN}Dashboard:${NC} http://localhost:3000"
    echo -e "  ${CYAN}Postgres:${NC}  localhost:5432 (user: priya)"
    echo -e "  ${CYAN}Redis:${NC}     localhost:6379"
    echo -e "  ${CYAN}Kafka:${NC}     localhost:9092"
    echo ""
    echo -e "  ${YELLOW}Next steps:${NC}"
    echo -e "    Run migrations: ${BOLD}./scripts/migrate.sh upgrade${NC}"
    echo -e "    View logs:      ${BOLD}docker compose logs -f${NC}"
    echo -e "    Status:         ${BOLD}./scripts/dev-boot.sh status${NC}"
    echo -e "    Stop:           ${BOLD}./scripts/dev-boot.sh stop${NC}"
    echo ""
}

cmd_channels() {
    cmd_core

    echo -e "${BOLD}Starting channel services...${NC}"
    docker compose --profile channels up -d
    ok "Channel services starting (whatsapp, email, voice, social, sms, telegram)"
    echo ""
}

cmd_full() {
    banner
    preflight
    build_base

    echo -e "${BOLD}Starting ALL services (this will take a minute)...${NC}"
    docker compose \
        --profile infra \
        --profile core \
        --profile channels \
        --profile business \
        --profile advanced \
        --profile ops \
        up -d

    echo ""
    info "Waiting for infrastructure health..."
    wait_healthy priya-postgres 30 && ok "PostgreSQL ready" || warn "PostgreSQL still starting"
    wait_healthy priya-redis 15 && ok "Redis ready" || warn "Redis still starting"

    echo ""
    info "All services launching. Check status with:"
    echo "    docker compose ps"
    echo "    ./scripts/dev-boot.sh status"
    echo ""
}

cmd_status() {
    banner
    echo -e "${BOLD}Service Status:${NC}"
    echo ""
    docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || docker compose ps
    echo ""

    running=$(docker compose ps --status running -q 2>/dev/null | wc -l | tr -d ' ')
    total=$(docker compose ps -q 2>/dev/null | wc -l | tr -d ' ')
    echo -e "  ${CYAN}$running / $total${NC} services running"
    echo ""
}

cmd_stop() {
    banner
    echo -e "${BOLD}Stopping all services...${NC}"
    docker compose down
    ok "All services stopped"
    echo ""
}

cmd_logs() {
    docker compose logs -f --tail=50
}

cmd_clean() {
    banner
    echo -e "${RED}${BOLD}WARNING: This will remove ALL data (database, redis, kafka)!${NC}"
    read -p "Are you sure? (yes/no): " -r
    if [[ $REPLY == "yes" ]]; then
        docker compose down -v --remove-orphans
        ok "All containers and volumes removed"
    else
        warn "Cancelled"
    fi
    echo ""
}

# ─── Main ───

case "${1:-core}" in
    infra)    cmd_infra ;;
    core|"")  cmd_core ;;
    channels) cmd_channels ;;
    full)     cmd_full ;;
    status)   cmd_status ;;
    stop)     cmd_stop ;;
    logs)     cmd_logs ;;
    clean)    cmd_clean ;;
    *)
        echo "Usage: ./scripts/dev-boot.sh [infra|core|channels|full|status|stop|logs|clean]"
        echo ""
        echo "  infra     — PostgreSQL + Redis + Kafka only"
        echo "  core      — Infrastructure + Gateway + Auth + Tenant + Dashboard (default)"
        echo "  channels  — Core + WhatsApp, Email, Voice, Social, SMS, Telegram"
        echo "  full      — ALL 36 services"
        echo "  status    — Show running services"
        echo "  stop      — Stop everything"
        echo "  logs      — Tail all logs"
        echo "  clean     — Stop + remove all volumes (DESTRUCTIVE)"
        ;;
esac
