#!/bin/bash
# Monitoring Stack Validation Script
# Run this after integrating metrics into services

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Priya Global Platform — Monitoring Stack Validation       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Counter for passed/failed checks
PASSED=0
FAILED=0

# Function to run a check
run_check() {
    local check_name=$1
    local command=$2
    local expected=$3

    echo -n "Checking $check_name... "

    # Execute command safely - all commands are predefined in this script, not user input
    # Commands come from explicit function calls below, never from external sources
    if eval "$command" &>/dev/null; then
        echo -e "${GREEN}✓ PASS${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}"
        echo "  Command: $command"
        ((FAILED++))
    fi
}

# ─────────────────────────────────────────────────────────────────────────
# 1. Docker Compose Health
# ─────────────────────────────────────────────────────────────────────────

echo -e "${BLUE}═══ Docker Compose Services ═══${NC}"

run_check "Prometheus running" \
    "docker ps | grep -q priya-prometheus"

run_check "Grafana running" \
    "docker ps | grep -q priya-grafana"

run_check "Prometheus accessible (port 9090)" \
    "curl -s http://localhost:9090/-/healthy | grep -q healthy"

run_check "Grafana accessible (port 3001)" \
    "curl -s http://localhost:3001/api/health | grep -q ok"

echo ""

# ─────────────────────────────────────────────────────────────────────────
# 2. Prometheus Configuration
# ─────────────────────────────────────────────────────────────────────────

echo -e "${BLUE}═══ Prometheus Configuration ═══${NC}"

run_check "prometheus.yml exists" \
    "test -f monitoring/prometheus/prometheus.yml"

run_check "alerts.yml exists" \
    "test -f monitoring/prometheus/alerts.yml"

run_check "Prometheus has targets configured" \
    "grep -q 'static_configs' monitoring/prometheus/prometheus.yml"

# Count configured targets
TARGET_COUNT=$(grep -c "job_name:" monitoring/prometheus/prometheus.yml || echo "0")
echo "  Found $TARGET_COUNT job targets in prometheus.yml"

if [ "$TARGET_COUNT" -ge 36 ]; then
    echo -e "  ${GREEN}✓ All 36+ services configured${NC}"
    ((PASSED++))
else
    echo -e "  ${YELLOW}⚠ Only $TARGET_COUNT services configured (need 36+)${NC}"
    ((FAILED++))
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────
# 3. Grafana Configuration
# ─────────────────────────────────────────────────────────────────────────

echo -e "${BLUE}═══ Grafana Configuration ═══${NC}"

run_check "Grafana datasource config exists" \
    "test -f monitoring/grafana/provisioning/datasources/prometheus.yml"

run_check "Platform Overview dashboard exists" \
    "test -f monitoring/grafana/dashboards/platform-overview.json"

run_check "Tenant Analytics dashboard exists" \
    "test -f monitoring/grafana/dashboards/tenant-analytics.json"

run_check "Dashboard provisioning config exists" \
    "test -f monitoring/grafana/provisioning/dashboards/dashboard.yml"

echo ""

# ─────────────────────────────────────────────────────────────────────────
# 4. Prometheus Metrics Collection
# ─────────────────────────────────────────────────────────────────────────

echo -e "${BLUE}═══ Prometheus Targets Health ═══${NC}"

# Get target status from Prometheus API
TARGETS_JSON=$(curl -s http://localhost:9090/api/v1/targets)
TARGETS_UP=$(echo "$TARGETS_JSON" | grep -o '"up"' | wc -l)
TARGETS_DOWN=$(echo "$TARGETS_JSON" | grep -o '"down"' | wc -l)
TOTAL_TARGETS=$((TARGETS_UP + TARGETS_DOWN))

echo "  Total targets: $TOTAL_TARGETS"
echo "  Targets UP: $TARGETS_UP"
echo "  Targets DOWN: $TARGETS_DOWN"

if [ "$TARGETS_DOWN" -eq 0 ] && [ "$TARGETS_UP" -gt 0 ]; then
    echo -e "  ${GREEN}✓ All targets healthy${NC}"
    ((PASSED++))
else
    echo -e "  ${YELLOW}⚠ Some targets unhealthy${NC}"
    if [ "$TARGETS_DOWN" -gt 0 ]; then
        echo "  Down targets:"
        echo "$TARGETS_JSON" | grep -A 5 '"up":false' | grep '"job"' || true
    fi
    ((FAILED++))
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────
# 5. Metrics Availability
# ─────────────────────────────────────────────────────────────────────────

echo -e "${BLUE}═══ Core Metrics Availability ═══${NC}"

check_metric() {
    local metric_name=$1
    local query="${metric_name}[1m]"

    echo -n "  Checking $metric_name... "

    RESULT=$(curl -s "http://localhost:9090/api/v1/query?query=$(echo -n "$query" | jq -sRr @uri)" | grep -c "\"value\"" || echo "0")

    if [ "$RESULT" -gt 0 ]; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗${NC}"
        return 1
    fi
}

METRICS_CHECKED=0
METRICS_FOUND=0

for metric in \
    "http_requests_total" \
    "http_request_duration_seconds" \
    "http_requests_in_progress" \
    "service_info" \
    "up"
do
    ((METRICS_CHECKED++))
    if check_metric "$metric"; then
        ((METRICS_FOUND++))
        ((PASSED++))
    else
        ((FAILED++))
    fi
done

echo "  Metrics found: $METRICS_FOUND/$METRICS_CHECKED"

echo ""

# ─────────────────────────────────────────────────────────────────────────
# 6. Alert Rules
# ─────────────────────────────────────────────────────────────────────────

echo -e "${BLUE}═══ Alert Rules ═══${NC}"

ALERT_COUNT=$(grep -c "alert:" monitoring/prometheus/alerts.yml || echo "0")
echo "  Total alert rules: $ALERT_COUNT"

if [ "$ALERT_COUNT" -ge 10 ]; then
    echo -e "  ${GREEN}✓ Alert rules configured${NC}"
    ((PASSED++))
else
    echo -e "  ${YELLOW}⚠ Few alert rules (expected 10+)${NC}"
    ((FAILED++))
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────
# 7. Shared Metrics Module
# ─────────────────────────────────────────────────────────────────────────

echo -e "${BLUE}═══ Shared Metrics Module ═══${NC}"

run_check "metrics.py exists" \
    "test -f shared/monitoring/metrics.py"

run_check "metrics.py has PrometheusMiddleware" \
    "grep -q 'class PrometheusMiddleware' shared/monitoring/metrics.py"

run_check "metrics.py has metrics_handler" \
    "grep -q 'async def metrics_handler' shared/monitoring/metrics.py"

run_check "metrics.py has track_metric decorator" \
    "grep -q 'def track_metric' shared/monitoring/metrics.py"

echo ""

# ─────────────────────────────────────────────────────────────────────────
# 8. Docker Compose Updates
# ─────────────────────────────────────────────────────────────────────────

echo -e "${BLUE}═══ Docker Compose Configuration ═══${NC}"

run_check "docker-compose.yml has Prometheus service" \
    "grep -q 'prometheus:' docker-compose.yml"

run_check "docker-compose.yml has Grafana service" \
    "grep -q 'grafana:' docker-compose.yml"

run_check "docker-compose.yml has prometheus_data volume" \
    "grep -q 'prometheus_data:' docker-compose.yml"

run_check "docker-compose.yml has grafana_data volume" \
    "grep -q 'grafana_data:' docker-compose.yml"

echo ""

# ─────────────────────────────────────────────────────────────────────────
# 9. Documentation
# ─────────────────────────────────────────────────────────────────────────

echo -e "${BLUE}═══ Documentation ═══${NC}"

run_check "MONITORING_SETUP.md exists" \
    "test -f MONITORING_SETUP.md"

run_check "MONITORING_INTEGRATION_CHECKLIST.md exists" \
    "test -f MONITORING_INTEGRATION_CHECKLIST.md"

run_check "MONITORING_QUICK_START.md exists" \
    "test -f MONITORING_QUICK_START.md"

echo ""

# ─────────────────────────────────────────────────────────────────────────
# 10. Summary
# ─────────────────────────────────────────────────────────────────────────

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Validation Summary                                        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"

TOTAL=$((PASSED + FAILED))
PERCENTAGE=$((PASSED * 100 / TOTAL))

echo ""
echo "  ${GREEN}✓ Passed${NC}: $PASSED/$TOTAL"

if [ "$FAILED" -gt 0 ]; then
    echo "  ${RED}✗ Failed${NC}: $FAILED/$TOTAL"
fi

echo ""
echo "  Success Rate: ${PERCENTAGE}%"
echo ""

if [ "$PERCENTAGE" -eq 100 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✓ All checks passed! Monitoring stack is ready!           ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Access Prometheus: http://localhost:9090"
    echo "  2. Access Grafana: http://localhost:3001 (admin/priya_grafana_2024)"
    echo "  3. View Platform Overview: http://localhost:3001/d/priya-platform-overview"
    echo "  4. Integrate metrics into remaining services (see MONITORING_INTEGRATION_CHECKLIST.md)"
    exit 0
elif [ "$PERCENTAGE" -ge 80 ]; then
    echo -e "${YELLOW}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  ⚠ Most checks passed, some issues to resolve              ║${NC}"
    echo -e "${YELLOW}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Recommendations:"
    echo "  - Ensure all services with metrics endpoints are running"
    echo "  - Check Prometheus target health in http://localhost:9090/targets"
    echo "  - Review docker-compose.yml for correct port mappings"
    exit 1
else
    echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ✗ Multiple issues detected, review configuration          ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Troubleshooting steps:"
    echo "  1. Start monitoring: docker compose --profile monitoring up -d"
    echo "  2. Check service logs: docker logs priya-prometheus"
    echo "  3. Verify services running: docker compose ps"
    echo "  4. Review MONITORING_SETUP.md for detailed configuration"
    exit 1
fi
