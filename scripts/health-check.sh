#!/bin/bash
# ============================================================
# Priya Global — Health Check for All Services
# Usage: ./scripts/health-check.sh
# ============================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Priya Global — Service Health Check${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Infrastructure
echo -e "${YELLOW}Infrastructure:${NC}"
docker compose exec -T postgres pg_isready -U priya -d priya_global > /dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} PostgreSQL" || echo -e "  ${RED}✗${NC} PostgreSQL"
docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG && echo -e "  ${GREEN}✓${NC} Redis" || echo -e "  ${RED}✗${NC} Redis"
docker compose exec -T kafka kafka-topics.sh --bootstrap-server localhost:9092 --list > /dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} Kafka" || echo -e "  ${RED}✗${NC} Kafka"
echo ""

# All service ports and names
declare -A SERVICES=(
    # Core
    ["Gateway"]=9000
    ["Auth"]=9001
    ["Tenant"]=9002
    ["Channel-Router"]=9003
    ["AI-Engine"]=9004
    ["Memory"]=9010
    ["Tenant-Config"]=9016
    ["Worker"]=9016
    # Channels
    ["WhatsApp"]=9011
    ["Email"]=9012
    ["Voice"]=9013
    ["SMS"]=9014
    ["Webchat"]=9015
    ["Social"]=9017
    ["Telegram"]=9018
    # Business
    ["Billing"]=9020
    ["Analytics"]=9021
    ["Marketing"]=9022
    ["Ecommerce"]=9023
    ["Notification"]=9024
    ["Plugins"]=9025
    ["Handoff"]=9026
    ["Leads"]=9027
    ["Wallet"]=9050
    # Advanced
    ["Conversation-Intel"]=9028
    ["Appointments"]=9029
    ["Knowledge"]=9030
    ["Voice-AI"]=9031
    ["Video"]=9032
    ["RCS"]=9033
    ["Translation"]=9044
    ["REST-Connector"]=9038
    ["Developer-Portal"]=9039
    ["Workflows"]=9045
    ["Advanced-Analytics"]=9046
    ["AI-Training"]=9047
    ["Marketplace"]=9043
    # Ops
    ["Compliance"]=9040
    ["Health-Monitor"]=9041
    ["CDN-Manager"]=9042
)

# Group services for display
echo -e "${YELLOW}Core Services:${NC}"
for name in Gateway Auth Tenant Channel-Router AI-Engine Memory Worker; do
    port=${SERVICES[$name]}
    if [ -n "$port" ]; then
        if curl -sf "http://localhost:$port/health" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $name (port $port)"
        else
            echo -e "  ${RED}✗${NC} $name (port $port)"
        fi
    fi
done
echo ""

echo -e "${YELLOW}Channel Services:${NC}"
for name in WhatsApp Email Voice SMS Webchat Social Telegram; do
    port=${SERVICES[$name]}
    if [ -n "$port" ]; then
        if curl -sf "http://localhost:$port/health" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $name (port $port)"
        else
            echo -e "  ${RED}✗${NC} $name (port $port)"
        fi
    fi
done
echo ""

echo -e "${YELLOW}Business Services:${NC}"
for name in Billing Analytics Marketing Ecommerce Notification Plugins Handoff Leads Wallet; do
    port=${SERVICES[$name]}
    if [ -n "$port" ]; then
        if curl -sf "http://localhost:$port/health" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $name (port $port)"
        else
            echo -e "  ${RED}✗${NC} $name (port $port)"
        fi
    fi
done
echo ""

echo -e "${YELLOW}Advanced Services:${NC}"
for name in Conversation-Intel Appointments Knowledge Voice-AI Video RCS Translation REST-Connector Developer-Portal Workflows Advanced-Analytics AI-Training Marketplace; do
    port=${SERVICES[$name]}
    if [ -n "$port" ]; then
        if curl -sf "http://localhost:$port/health" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $name (port $port)"
        else
            echo -e "  ${RED}✗${NC} $name (port $port)"
        fi
    fi
done
echo ""

echo -e "${YELLOW}Ops Services:${NC}"
for name in Compliance Health-Monitor CDN-Manager; do
    port=${SERVICES[$name]}
    if [ -n "$port" ]; then
        if curl -sf "http://localhost:$port/health" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $name (port $port)"
        else
            echo -e "  ${RED}✗${NC} $name (port $port)"
        fi
    fi
done
echo ""

# Dashboard
echo -e "${YELLOW}Frontend:${NC}"
curl -sf "http://localhost:3000" > /dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} Dashboard (port 3000)" || echo -e "  ${RED}✗${NC} Dashboard (port 3000)"
echo ""

# Docker container summary
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
RUNNING=$(docker compose ps --format json 2>/dev/null | grep -c '"running"' || docker compose ps 2>/dev/null | grep -c "Up")
echo -e "  Docker containers running: ${GREEN}$RUNNING${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
