#!/bin/bash

##############################################################################
# K6 Load Tests - Run All Scenarios
#
# Executes all load test scenarios sequentially:
# 1. Conversation flow load test
# 2. API gateway load test
# 3. AI engine load test
#
# Outputs results in JSON format for Grafana visualization
#
# Usage:
#   ./run_all.sh
#   BASE_URL=http://staging:9000 ./run_all.sh
#   BASE_URL=http://prod:9000 ./run_all.sh [--dry-run]
#
##############################################################################

set -e  # Exit on first error

# ─────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIOS_DIR="$SCRIPT_DIR/scenarios"
RESULTS_DIR="${RESULTS_DIR:-.}/load-test-results"
LOG_DIR="${LOG_DIR:-.}/load-test-logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# API configuration
BASE_URL="${BASE_URL:-http://localhost:9000}"
API_GATEWAY="${API_GATEWAY:-$BASE_URL}"
DRY_RUN="${1}"

# K6 configuration
K6_VUS="${K6_VUS:-50}"
K6_DURATION="${K6_DURATION:-8m}"
K6_RAMP_UP="${K6_RAMP_UP:-2m}"
K6_HOLD="${K6_HOLD:-5m}"
K6_RAMP_DOWN="${K6_RAMP_DOWN:-1m}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # No Color

# ─────────────────────────────────────────────────────────
# Functions
# ─────────────────────────────────────────────────────────

print_header() {
  echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}$1${NC}"
  echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
}

print_info() {
  echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

validate_environment() {
  print_header "Validating Environment"

  # Check if k6 is installed
  if ! command -v k6 &> /dev/null; then
    print_error "k6 is not installed. Please install k6 first: https://k6.io/docs/getting-started/installation/"
    exit 1
  fi

  print_info "K6 version: $(k6 version)"

  # Check if BASE_URL is accessible
  if ! curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health" &> /dev/null; then
    print_warning "Cannot connect to $BASE_URL - tests may fail"
  else
    print_info "API accessible at $BASE_URL"
  fi

  # Check if scenarios exist
  if [ ! -d "$SCENARIOS_DIR" ]; then
    print_error "Scenarios directory not found: $SCENARIOS_DIR"
    exit 1
  fi

  print_info "Found test scenarios in $SCENARIOS_DIR"
}

setup_directories() {
  print_info "Setting up output directories..."
  mkdir -p "$RESULTS_DIR"
  mkdir -p "$LOG_DIR"
  print_info "Results will be saved to: $RESULTS_DIR"
  print_info "Logs will be saved to: $LOG_DIR"
}

run_scenario() {
  local scenario_name=$1
  local scenario_file=$2
  local result_file="$RESULTS_DIR/${scenario_name}_${TIMESTAMP}.json"
  local log_file="$LOG_DIR/${scenario_name}_${TIMESTAMP}.log"

  print_header "Running: $scenario_name"

  # Export environment variables for k6
  export BASE_URL
  export API_GATEWAY

  # Prepare k6 options
  local k6_options=(
    "--stage" "1m:10"  # Ramp-up: 10 VUs over 1 minute
    "--stage" "3m:50"  # Ramp-up: 50 VUs over 3 minutes
    "--stage" "5m:50"  # Hold: 50 VUs for 5 minutes
    "--stage" "1m:0"   # Ramp-down: 0 VUs over 1 minute
    "-o" "json=$result_file"
  )

  if [ "$DRY_RUN" == "--dry-run" ]; then
    print_warning "DRY RUN MODE - No load will be generated"
    k6_options+=("--vus" "1" "--duration" "10s")
  fi

  print_info "Scenario: $scenario_file"
  print_info "VUs: $K6_VUS"
  print_info "Duration: $K6_DURATION"
  print_info "Results: $result_file"

  # Run the scenario
  if k6 run \
      "${k6_options[@]}" \
      "$scenario_file" \
      2>&1 | tee "$log_file"; then
    print_info "✓ $scenario_name completed successfully"
    return 0
  else
    print_error "✗ $scenario_name failed"
    return 1
  fi
}

process_results() {
  local result_file=$1
  local scenario_name=$2

  print_info "Processing results for $scenario_name..."

  if [ ! -f "$result_file" ]; then
    print_warning "Result file not found: $result_file"
    return 1
  fi

  # Extract key metrics using jq
  local p95=$(jq '.metrics.http_req_duration.values.p95' "$result_file" 2>/dev/null || echo "N/A")
  local p99=$(jq '.metrics.http_req_duration.values.p99' "$result_file" 2>/dev/null || echo "N/A")
  local error_rate=$(jq '.metrics.http_req_failed.values.rate' "$result_file" 2>/dev/null || echo "N/A")
  local requests=$(jq '.metrics.http_reqs.values.count' "$result_file" 2>/dev/null || echo "N/A")

  echo "  p95: ${p95}ms"
  echo "  p99: ${p99}ms"
  echo "  Error Rate: ${error_rate}%"
  echo "  Total Requests: ${requests}"
}

generate_summary_report() {
  print_header "Load Test Summary"

  local summary_file="$RESULTS_DIR/summary_${TIMESTAMP}.md"

  cat > "$summary_file" << EOF
# Load Test Results - $TIMESTAMP

## Environment
- Base URL: $BASE_URL
- VUs: $K6_VUS
- Duration: $K6_DURATION

## Scenarios Executed

### 1. Conversation Flow Load Test
- **File**: conversation_load.js
- **Purpose**: Tests conversation creation and message sending
- **Metrics**: See conversation_load_${TIMESTAMP}.json

### 2. API Gateway Load Test
- **File**: api_gateway_load.js
- **Purpose**: Tests mixed read/write workload (70/30)
- **Endpoints**: Auth, Conversations, Search, Billing
- **Metrics**: See api_gateway_load_${TIMESTAMP}.json

### 3. AI Engine Load Test
- **File**: ai_engine_load.js
- **Purpose**: Tests AI inference latency and throughput
- **Operations**: Intent classification, Entity extraction, Response generation
- **Metrics**: See ai_engine_load_${TIMESTAMP}.json

## Performance Targets
- p95 latency: <500ms (API), <3000ms (AI)
- p99 latency: <1000ms (API), <5000ms (AI)
- Error rate: <1%
- Throughput: >100 rps

## Next Steps
1. Review JSON results in $RESULTS_DIR
2. Import results into Grafana for visualization
3. Compare against baseline metrics
4. Identify bottlenecks and optimization opportunities

## Files Generated
- Results: $RESULTS_DIR
- Logs: $LOG_DIR
- Summary: $summary_file

EOF

  print_info "Summary report generated: $summary_file"
  cat "$summary_file"
}

create_grafana_dashboard_json() {
  local dashboard_file="$RESULTS_DIR/grafana_dashboard_${TIMESTAMP}.json"

  print_info "Creating Grafana dashboard template..."

  cat > "$dashboard_file" << 'EOF'
{
  "dashboard": {
    "title": "Priya Global Load Test Results",
    "tags": ["k6", "load-test", "priya"],
    "timezone": "browser",
    "panels": [
      {
        "title": "Response Time p95",
        "targets": [
          {
            "expr": "http_req_duration_p95"
          }
        ]
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "http_req_failed_rate"
          }
        ]
      },
      {
        "title": "Requests Per Second",
        "targets": [
          {
            "expr": "http_reqs_rate"
          }
        ]
      },
      {
        "title": "AI Inference Latency",
        "targets": [
          {
            "expr": "ai_inference_latency_p95"
          }
        ]
      }
    ]
  }
}
EOF

  print_info "Grafana dashboard template: $dashboard_file"
}

# ─────────────────────────────────────────────────────────
# Main Execution
# ─────────────────────────────────────────────────────────

main() {
  print_header "Priya Global - K6 Load Test Suite"
  echo ""
  echo "Timestamp: $(date)"
  echo "Base URL: $BASE_URL"
  echo ""

  # Validate and setup
  validate_environment
  setup_directories
  echo ""

  # Track results
  local failed_scenarios=()
  local successful_scenarios=()

  # Run each scenario
  for scenario_file in "$SCENARIOS_DIR"/*.js; do
    scenario_name=$(basename "$scenario_file" .js)

    if run_scenario "$scenario_name" "$scenario_file"; then
      successful_scenarios+=("$scenario_name")
      result_file="$RESULTS_DIR/${scenario_name}_${TIMESTAMP}.json"
      if [ -f "$result_file" ]; then
        process_results "$result_file" "$scenario_name"
      fi
    else
      failed_scenarios+=("$scenario_name")
    fi

    echo ""
    sleep 5  # Cool-down between scenarios
  done

  # Generate reports
  generate_summary_report
  create_grafana_dashboard_json

  # Final summary
  print_header "Test Execution Summary"
  echo "Successful: ${#successful_scenarios[@]}"
  for scenario in "${successful_scenarios[@]}"; do
    echo "  ✓ $scenario"
  done

  if [ ${#failed_scenarios[@]} -gt 0 ]; then
    echo ""
    echo "Failed: ${#failed_scenarios[@]}"
    for scenario in "${failed_scenarios[@]}"; do
      echo "  ✗ $scenario"
    done
    print_error "Some tests failed. Review logs in $LOG_DIR"
    exit 1
  fi

  print_info "All load tests completed successfully!"
  print_info "Results: $RESULTS_DIR"
  print_info "Logs: $LOG_DIR"
}

# Run main function
main
