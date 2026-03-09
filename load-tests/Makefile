# K6 Load Testing Suite - Priya Global Platform
# Comprehensive load testing for 36-microservice SaaS platform

.PHONY: help test-all test-gateway test-auth test-conversations test-tenant test-websocket test-spike test-soak test-international install clean report

# Default variables
K6_VERSION ?= latest
RESULTS_DIR ?= ./results
K6_HOME ?= /tmp/k6
BASE_URL ?= http://localhost:9001
WS_URL ?= ws://localhost:9001
VENV_DIR ?= ./venv

# Tenant tokens (set these from environment or .env file)
TENANT_1_TOKEN ?= $(shell echo "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOiJ0ZW5hbnQtbG9hZC0wMDEiLCJ1c2VyX2lkIjoiMTAwIiwicGxhbiI6InByb2Zlc3Npb25hbCIsImV4cCI6OTk5OTk5OTk5OX0.test")
TENANT_2_TOKEN ?= $(shell echo "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOiJ0ZW5hbnQtbG9hZC0wMDIiLCJ1c2VyX2lkIjoiMjAwIiwicGxhbiI6Imdyb3d0aCIsImV4cCI6OTk5OTk5OTk5OX0.test")
TENANT_3_TOKEN ?= $(shell echo "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOiJ0ZW5hbnQtbG9hZC0wMDMiLCJ1c2VyX2lkIjoiMzAwIiwicGxhbiI6InN0YXJ0ZXIiLCJleHAiOjk5OTk5OTk5OTl9.test")
TENANT_4_TOKEN ?= $(shell echo "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOiJ0ZW5hbnQtbG9hZC0wMDQiLCJ1c2VyX2lkIjoiNDAwIiwicGxhbiI6ImVudGVycHJpc2UiLCJleHAiOjk5OTk5OTk5OTl9.test")

# Color output
BLUE := \033[0;36m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help:
	@echo "$(BLUE)Priya Global Platform - K6 Load Testing Suite$(NC)"
	@echo ""
	@echo "$(YELLOW)Usage:$(NC)"
	@echo "  make install                - Install k6 and dependencies"
	@echo "  make test-all               - Run all load tests sequentially"
	@echo "  make test-gateway           - Test gateway routing (200 VUs)"
	@echo "  make test-auth              - Test authentication flows (300 VUs)"
	@echo "  make test-conversations     - Test conversation lifecycle (500 VUs)"
	@echo "  make test-tenant            - Test multi-tenant isolation (50 VUs)"
	@echo "  make test-websocket         - Test WebSocket connections (1000 VUs)"
	@echo "  make test-spike             - Test spike/stress behavior (1000 VUs)"
	@echo "  make test-soak              - Test stability over 30 minutes (100 VUs)"
	@echo "  make test-international     - Test global traffic patterns (200 VUs)"
	@echo "  make report                 - Generate HTML summary report"
	@echo "  make clean                  - Clean up results and artifacts"
	@echo ""
	@echo "$(YELLOW)Environment Variables:$(NC)"
	@echo "  BASE_URL          - API gateway URL (default: http://localhost:9001)"
	@echo "  WS_URL            - WebSocket URL (default: ws://localhost:9001)"
	@echo "  RESULTS_DIR       - Results output directory (default: ./results)"
	@echo "  TENANT_*_TOKEN    - Auth tokens for test tenants"

install:
	@echo "$(BLUE)Installing K6...$(NC)"
	@command -v k6 >/dev/null 2>&1 || { \
		echo "$(YELLOW)K6 not found. Please install from: https://k6.io/docs/getting-started/installation$(NC)"; \
		exit 1; \
	}
	@mkdir -p $(RESULTS_DIR)
	@echo "$(GREEN)K6 installed successfully$(NC)"

clean:
	@echo "$(YELLOW)Cleaning up test artifacts...$(NC)"
	@rm -rf $(RESULTS_DIR)/*
	@rm -f *.html *.json
	@echo "$(GREEN)Cleanup complete$(NC)"

# Common test execution function
define run_test
	@echo "$(BLUE)Running $(1) test...$(NC)"
	BASE_URL=$(BASE_URL) \
	WS_URL=$(WS_URL) \
	TENANT_1_TOKEN=$(TENANT_1_TOKEN) \
	TENANT_2_TOKEN=$(TENANT_2_TOKEN) \
	TENANT_3_TOKEN=$(TENANT_3_TOKEN) \
	TENANT_4_TOKEN=$(TENANT_4_TOKEN) \
	k6 run --out json=$(RESULTS_DIR)/$(1)-results.json \
	       --vus-max 1000 \
	       --summary-export=$(RESULTS_DIR)/$(1)-summary.json \
	       k6/scenarios/$(1).js
	@echo "$(GREEN)$(1) test completed$(NC)"
	@echo "Results: $(RESULTS_DIR)/$(1)-results.json"
endef

test-gateway: install
	$(call run_test,gateway-routing)

test-auth: install
	$(call run_test,auth-flow)

test-conversations: install
	$(call run_test,conversation-lifecycle)

test-tenant: install
	$(call run_test,multi-tenant-isolation)

test-websocket: install
	$(call run_test,websocket-load)

test-spike: install
	$(call run_test,spike-test)

test-soak: install
	@echo "$(BLUE)Running soak test (30 minutes)...$(NC)"
	BASE_URL=$(BASE_URL) \
	WS_URL=$(WS_URL) \
	TENANT_1_TOKEN=$(TENANT_1_TOKEN) \
	TENANT_2_TOKEN=$(TENANT_2_TOKEN) \
	TENANT_3_TOKEN=$(TENANT_3_TOKEN) \
	TENANT_4_TOKEN=$(TENANT_4_TOKEN) \
	k6 run --out json=$(RESULTS_DIR)/soak-test-results.json \
	       --vus-max 100 \
	       --summary-export=$(RESULTS_DIR)/soak-test-summary.json \
	       k6/scenarios/soak-test.js
	@echo "$(GREEN)Soak test completed$(NC)"

test-international: install
	$(call run_test,international-load)

test-all: clean install
	@echo "$(BLUE)Running complete load test suite...$(NC)"
	@echo "$(YELLOW)This will take approximately 45 minutes$(NC)"
	@echo ""
	$(MAKE) test-gateway
	@sleep 10
	$(MAKE) test-auth
	@sleep 10
	$(MAKE) test-conversations
	@sleep 10
	$(MAKE) test-tenant
	@sleep 10
	$(MAKE) test-websocket
	@sleep 10
	$(MAKE) test-spike
	@sleep 10
	$(MAKE) test-international
	@echo ""
	@echo "$(GREEN)All tests completed!$(NC)"
	@echo "$(BLUE)Generating summary report...$(NC)"
	@$(MAKE) report

report:
	@echo "$(BLUE)Generating test summary report...$(NC)"
	@python3 -c "\
	import json\
	import os\
	import glob\
	\
	results_dir = '$(RESULTS_DIR)'\
	summary_files = glob.glob(os.path.join(results_dir, '*-summary.json'))\
	\
	print('<html><head><title>Load Test Results</title>')\
	print('<style>body{font-family:Arial;margin:20px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px;text-align:left}th{background-color:#4CAF50;color:white}tr:nth-child(even){background-color:#f2f2f2}.pass{color:green;font-weight:bold}.fail{color:red;font-weight:bold}</style>')\
	print('</head><body>')\
	print('<h1>Priya Global Platform - Load Test Results</h1>')\
	print('<table>')\
	print('<tr><th>Test</th><th>Status</th><th>P95 Latency</th><th>P99 Latency</th><th>Success Rate</th></tr>')\
	\
	for summary_file in sorted(summary_files):\
	    with open(summary_file) as f:\
	        data = json.load(f)\
	        test_name = os.path.basename(summary_file).replace('-summary.json', '')\
	        status = 'PASS' if data.get('state') == 'passed' else 'FAIL'\
	        status_class = 'pass' if status == 'PASS' else 'fail'\
	        print(f'<tr><td>{test_name}</td><td class=\"{status_class}\">{status}</td><td>N/A</td><td>N/A</td><td>N/A</td></tr>')\
	\
	print('</table>')\
	print('<p>Report generated at $(RESULTS_DIR)</p>')\
	print('</body></html>')" > $(RESULTS_DIR)/report.html
	@echo "$(GREEN)Report generated: $(RESULTS_DIR)/report.html$(NC)"

# Performance benchmarking targets
bench: test-all
	@echo "$(BLUE)Performance benchmark complete$(NC)"

# Debug target for troubleshooting
debug: install
	@echo "$(BLUE)Running gateway test in debug mode...$(NC)"
	BASE_URL=$(BASE_URL) \
	WS_URL=$(WS_URL) \
	TENANT_1_TOKEN=$(TENANT_1_TOKEN) \
	k6 run -v k6/scenarios/gateway-routing.js

# CI/CD integration target
ci: install test-gateway test-auth test-conversations test-tenant test-international
	@echo "$(GREEN)CI/CD test suite completed successfully$(NC)"
