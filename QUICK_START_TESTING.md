# Quick Start: E2E and Load Testing

Fast reference guide to get testing immediately.

## Setup (2 minutes)

```bash
# Install E2E dependencies
pip install pytest httpx pyjwt pytest-asyncio

# Install Load Test tool (k6)
brew install k6  # macOS
# or visit https://k6.io/docs/getting-started/installation/

# Verify installations
pytest --version
k6 version
```

## Environment Setup

```bash
# Set API URL (default: localhost:9000)
export API_BASE_URL=http://localhost:9000

# Set JWT secret if needed
export JWT_SECRET_KEY="your-secret-key"
```

## Run E2E Tests

```bash
# Run all E2E tests
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global
pytest tests/e2e/ -v

# Run specific test file
pytest tests/e2e/test_auth_flow.py -v

# Run with more detail on failures
pytest tests/e2e/ -vv

# Run and stop on first failure
pytest tests/e2e/ -x

# Run with coverage report
pytest tests/e2e/ --cov=services --cov-report=html
```

## Run Load Tests

```bash
# Run all load tests sequentially
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/load-tests/k6
./run_all.sh

# Dry run (test config without load)
./run_all.sh --dry-run

# Run single scenario
k6 run scenarios/conversation_load.js

# Run with more VUs (virtual users)
k6 run --vus 100 --duration 10m scenarios/conversation_load.js

# Export results as JSON
k6 run -o json=results.json scenarios/conversation_load.js
```

## Test Files Overview

### E2E Tests (172+ tests)

| File | Purpose | Test Count |
|------|---------|-----------|
| `test_auth_flow.py` | Authentication & JWT | 32 |
| `test_conversation_flow.py` | Conversation lifecycle | 42 |
| `test_billing_flow.py` | Subscriptions & billing | 32 |
| `test_knowledge_base.py` | Document management | 31 |
| `test_security.py` | Security controls | 35 |

### Load Tests (3 scenarios)

| File | Purpose | Focus |
|------|---------|-------|
| `conversation_load.js` | Conversation throughput | Create & message 50 VUs |
| `api_gateway_load.js` | API performance | Mixed 70/30 read/write |
| `ai_engine_load.js` | AI inference | Intent, entity, response |

## Common Test Scenarios

### Test Authentication
```bash
pytest tests/e2e/test_auth_flow.py::TestUserRegistration -v
pytest tests/e2e/test_auth_flow.py::TestLogin -v
pytest tests/e2e/test_auth_flow.py::TestMultiTenantIsolation -v
```

### Test Conversations
```bash
pytest tests/e2e/test_conversation_flow.py::TestConversationCreation -v
pytest tests/e2e/test_conversation_flow.py::TestSendMessage -v
pytest tests/e2e/test_conversation_flow.py::TestConversationSearch -v
```

### Test Security
```bash
pytest tests/e2e/test_security.py::TestTenantIsolation -v
pytest tests/e2e/test_security.py::TestSQLInjectionPrevention -v
pytest tests/e2e/test_security.py::TestXSSPrevention -v
```

### Test Performance
```bash
k6 run -o json=conversation.json load-tests/k6/scenarios/conversation_load.js
k6 run -o json=gateway.json load-tests/k6/scenarios/api_gateway_load.js
k6 run -o json=ai.json load-tests/k6/scenarios/ai_engine_load.js
```

## Troubleshooting

### E2E Tests Won't Run
```bash
# Check pytest is installed
pip install pytest httpx pyjwt pytest-asyncio

# Check API is accessible
curl http://localhost:9000/health

# Run with verbose output
pytest tests/e2e/ -vv --tb=short
```

### Load Tests Won't Run
```bash
# Check k6 is installed
k6 version

# Check BASE_URL is correct
BASE_URL=http://localhost:9000 k6 run load-tests/k6/scenarios/conversation_load.js

# Run in verbose mode
k6 run -v load-tests/k6/scenarios/conversation_load.js
```

## Performance Targets

```
API Endpoints
  p95 latency: <500ms ✓
  p99 latency: <1000ms ✓
  Error rate: <1% ✓

AI Endpoints
  p95 latency: <3000ms ✓
  p99 latency: <5000ms ✓
  Error rate: <2% ✓

Overall
  Throughput: >100 rps ✓
```

## Output Files

### E2E Tests
```
Console output (detailed results)
HTML coverage report (--cov-report=html)
```

### Load Tests
```
/tmp/k6-summary.json          (test results)
load-test-results/            (all results)
load-test-logs/               (execution logs)
Grafana dashboard template    (for visualization)
```

## Common Commands

```bash
# Run everything
pytest tests/e2e/ && ./load-tests/k6/run_all.sh

# Just security tests
pytest tests/e2e/test_security.py -v

# Just auth tests
pytest tests/e2e/test_auth_flow.py -v

# Performance baseline
k6 run load-tests/k6/scenarios/conversation_load.js

# Spike test
k6 run --vus 500 --duration 3m load-tests/k6/scenarios/conversation_load.js

# Quick sanity check
pytest tests/e2e/ -k "test_register_new_user or test_login_valid"
```

## Integration Examples

### GitHub Actions
```yaml
- name: E2E Tests
  run: pytest tests/e2e/ -v

- name: Load Tests
  run: cd load-tests/k6 && ./run_all.sh --dry-run
```

### Local Pre-commit
```bash
# Add to .git/hooks/pre-commit
pytest tests/e2e/ -q || exit 1
```

## Tips & Tricks

```bash
# Stop on first failure
pytest tests/e2e/ -x

# Show print statements
pytest tests/e2e/ -s

# Only failed tests
pytest tests/e2e/ --lf

# Run last failed test
pytest tests/e2e/ --ff

# Filter by name
pytest tests/e2e/ -k "security"

# Show slowest tests
pytest tests/e2e/ --durations=10

# Parallel execution (requires pytest-xdist)
pytest tests/e2e/ -n auto
```

## Resources

- E2E Test Documentation: `/tests/E2E_AND_LOAD_TESTING.md`
- Creation Summary: `/TESTING_SUITE_CREATION_SUMMARY.md`
- K6 Docs: https://k6.io/docs/
- Pytest Docs: https://docs.pytest.org/

## What's Tested

✓ User Registration & Login
✓ Multi-tenant Isolation
✓ Conversation Lifecycle
✓ Message Sending
✓ Billing & Subscriptions
✓ Knowledge Base Search
✓ Security (SQL injection, XSS, etc.)
✓ Rate Limiting
✓ JWT Validation
✓ API Performance
✓ AI Inference Latency

## File Locations

```
/tests/e2e/                           # E2E tests
/tests/e2e/conftest.py                # Pytest fixtures
/load-tests/k6/                       # Load tests
/load-tests/k6/scenarios/             # Test scenarios
/load-tests/k6/load_config.js         # k6 config
/load-tests/k6/run_all.sh             # Master script
/tests/E2E_AND_LOAD_TESTING.md        # Full documentation
```

---

**Next Step**: Run `pytest tests/e2e/ -v` to execute all E2E tests!
