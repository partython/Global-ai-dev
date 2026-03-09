# K6 Load Testing Suite - Priya Global Platform

Comprehensive load testing suite for the Priya Global Platform, a 36-microservice multi-tenant SaaS platform. This suite validates performance, scalability, and reliability across authentication, conversations, real-time messaging, and multi-tenant isolation.

## Overview

The suite includes 10 specialized load test scenarios designed to stress-test different aspects of the platform:

| Test | Duration | Peak VUs | Focus | Typical Pass Criteria |
|------|----------|----------|-------|----------------------|
| Gateway Routing | 17 min | 200 | Proxy performance, routing latency | p95 < 200ms |
| Authentication | 17 min | 300 | Auth flows, token refresh, rate limits | p95 < 1s |
| Conversations | 18 min | 500 | Core business logic, all channels | p95 < 1.5s |
| Multi-Tenant | 14 min | 50 | Tenant isolation, data safety | No data leakage |
| WebSocket | 17 min | 1000 | Real-time connections, messaging | Connect < 1s |
| Spike Test | 10 min | 1000 | Sudden load increase, recovery | p95 < 2s (spike) |
| Soak Test | 34 min | 100 | Long-duration stability, memory | < 20% degradation |
| International | 12 min | 200 | Regional patterns, multi-currency | Same SLA all regions |

## Prerequisites

### Required
- **K6**: Latest version (https://k6.io/docs/getting-started/installation)
- **Node.js 14+**: For running scripts
- **Access to Priya API Gateway**: Running on port 9001 (or configured BASE_URL)

### Optional
- **Docker**: For containerized execution
- **Python 3.8+**: For result analysis scripts
- **jq**: For JSON query and result inspection

## Installation

### 1. Install K6

**macOS (Homebrew)**
```bash
brew install k6
```

**Linux (Debian/Ubuntu)**
```bash
sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6-stable.list
sudo apt-get update
sudo apt-get install k6
```

**Linux (RHEL/CentOS)**
```bash
sudo yum install https://dl.k6.io/rpm/repo.rpm
sudo yum install k6
```

**Windows**
```bash
choco install k6
```

### 2. Clone and Setup

```bash
cd load-tests
make install
```

## Configuration

### Environment Variables

Create a `.env` file or export variables:

```bash
# API Gateway
export BASE_URL="http://localhost:9001"
export WS_URL="ws://localhost:9001"

# Test tenant authentication tokens (JWT)
# Replace with actual tokens from your platform
export TENANT_1_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
export TENANT_2_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
export TENANT_3_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
export TENANT_4_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Results
export RESULTS_DIR="./results"
```

### Getting Test Tokens

Generate JWT tokens for test tenants:

```bash
# Using your auth service
curl -X POST http://localhost:9001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant-load-001" \
  -d '{
    "email": "test@priya.local",
    "password": "TestPassword123!"
  }' | jq '.access_token'
```

## Running Tests

### Quick Start - Single Test

```bash
# Test gateway routing
make test-gateway

# Test authentication
make test-auth

# Test conversation lifecycle
make test-conversations
```

### Complete Test Suite

```bash
# Run all tests sequentially (45-60 minutes)
make test-all

# Or run individual test categories
make test-gateway      # 17 min
make test-auth         # 17 min
make test-conversations # 18 min
make test-tenant       # 14 min
make test-websocket    # 17 min
make test-spike        # 10 min
make test-soak         # 34 min (30 min load + setup)
make test-international # 12 min
```

### Manual K6 Execution

For more control, run directly:

```bash
# Basic run
k6 run k6/scenarios/gateway-routing.js

# With custom VUs and duration
k6 run -u 100 -d 10m k6/scenarios/gateway-routing.js

# With environment variables
BASE_URL=https://staging.api.priyaai.com k6 run k6/scenarios/gateway-routing.js

# With JSON output for analysis
k6 run --out json=results.json k6/scenarios/gateway-routing.js

# In cloud (requires k6 cloud account)
k6 run --cloud k6/scenarios/gateway-routing.js
```

## Understanding Results

### Key Metrics

All tests track these metrics:

**Response Time Metrics** (milliseconds)
- `http_req_duration`: HTTP request/response time
- `p(50)`: 50th percentile (median)
- `p(95)`: 95th percentile (most users)
- `p(99)`: 99th percentile (tail latency)

**Success Metrics**
- `http_req_failed`: Failed request rate (0-1)
- `success_rate`: Successful responses
- `error_count`: Total errors

**Custom Metrics** (test-specific)
- Tenant isolation metrics
- Regional latency comparisons
- WebSocket connection health
- Memory leak indicators

### Interpreting Thresholds

Tests include SLA thresholds validated at test completion:

```javascript
thresholds: {
  'http_req_duration': [
    'p(95)<500',      // 95% of requests < 500ms ✓
    'p(99)<2000',     // 99% of requests < 2s ✓
  ],
  'http_req_failed': [
    'rate<0.01',      // Less than 1% error rate ✓
  ],
}
```

**Example output:**
```
✓ http_req_duration..................: avg=245.23ms, p(95)=487.3ms, p(99)=1823.5ms
✓ http_req_failed.....................: 0.45%
✓ http_req_status: 200................: 9542
✗ http_req_status: 404................: 23
```

### Analyzing JSON Results

Results are saved as JSON for deeper analysis:

```bash
# Install jq
sudo apt-get install jq  # or: brew install jq

# Extract summary statistics
jq '.metrics' results/gateway-routing-results.json | head -50

# Find slow requests (p95+)
jq '.metrics | .[] | select(.type=="Trend")' results/*.json

# Count errors by status code
jq '.metrics | .[] | select(.type=="Counter")' results/*.json
```

### HTML Report

Generate an HTML summary report:

```bash
make report
# Opens: results/report.html
```

## Test Scenarios

### 1. Gateway Routing (`gateway-routing.js`)

Tests the API gateway's proxy performance and request routing.

**What It Tests:**
- Routing latency for all service endpoints
- Request header propagation (X-Tenant-ID, X-Request-ID)
- Service discovery and circuit breaker

**Load Profile:**
```
0→50 VUs (2min) → 50 VUs (5min) → 50→200 VUs (3min) → 200 VUs (5min) → 0 (2min)
```

**Pass Criteria:**
- `routing_latency`: p(95) < 200ms, p(99) < 500ms
- `http_req_failed`: rate < 1%

**Run:**
```bash
make test-gateway
# Results: results/gateway-routing-results.json
```

### 2. Authentication Flow (`auth-flow.js`)

Tests authentication under load including login, token refresh, and brute force protection.

**What It Tests:**
- JWT token generation and validation
- Token refresh flow
- API key authentication
- Rate limiting enforcement
- Brute force attack protection
- Concurrent login handling

**Load Profile:**
```
0→100 VUs (2min) → 100 VUs (5min) → 100→300 VUs (3min) → 300 VUs (5min) → 0 (2min)
```

**Pass Criteria:**
- `auth_login_latency`: p(95) < 1s
- `auth_refresh_latency`: p(95) < 300ms
- `auth_login_success_rate`: rate > 95%

**Run:**
```bash
make test-auth
```

### 3. Conversation Lifecycle (`conversation-lifecycle.js`)

Tests the full conversation workflow across multiple channels (WhatsApp, Email, SMS, WebChat).

**What It Tests:**
- Create conversation
- Send/receive messages
- AI response generation
- Close conversation
- Multi-channel support
- Concurrent conversation handling

**Load Profile:**
```
0→10 VUs (2min) → 10→100 VUs (3min) → 100→500 VUs (3min) → 500 VUs (5min) → scale down (3min)
```

**Pass Criteria:**
- `conversation_create_latency`: p(95) < 1.5s
- `message_send_latency`: p(95) < 1s
- `ai_response_latency`: p(95) < 3s
- `conversation_success_rate`: rate > 95%

**Run:**
```bash
make test-conversations
```

### 4. Multi-Tenant Isolation (`multi-tenant-isolation.js`)

Verifies tenant data isolation and plan-based rate limiting under concurrent load.

**What It Tests:**
- Data isolation (prevent cross-tenant access)
- Rate limiting by plan tier (Starter/Growth/Professional/Enterprise)
- Per-tenant performance independence
- Tenant context propagation in headers

**Load Profile:**
```
0→50 VUs (2min) → 50 VUs (10min) → 0 (2min)
```

**Critical Thresholds:**
- `data_leakage_attempts`: count == 0 ✓ **MUST PASS**
- `ratelimit_enforced`: Starter plan limited, Enterprise not limited
- Per-tenant response times independent

**Run:**
```bash
make test-tenant
# Manually verify: grep "data_leakage" results/multi-tenant-isolation-results.json
```

### 5. WebSocket Load (`websocket-load.js`)

Stresses real-time WebSocket connections and messaging.

**What It Tests:**
- WebSocket connection establishment
- High-frequency message exchanges
- Connection drop and reconnection
- Message latency under load
- Concurrent connection limits

**Load Profile:**
```
0→100 (2min) → 100→500 (3min) → 500→1000 (2min) → 1000 (5min) → scale down (3min)
```

**Pass Criteria:**
- `ws_connect_latency`: p(95) < 1s
- `ws_message_latency`: p(95) < 200ms
- `ws_connect_success_rate`: rate > 98%

**Run:**
```bash
make test-websocket
```

### 6. Spike Test (`spike-test.js`)

Tests system behavior during sudden traffic spikes and recovery.

**What It Tests:**
- Instant load increase (50→1000 VUs)
- Circuit breaker activation
- Graceful degradation
- Recovery time
- Rate limiting under spike

**Load Profile:**
```
50 VUs (2min) → SPIKE to 1000 VUs (instant) → 1000 VUs (3min) → recover to 50 (2min)
```

**Pass Criteria:**
- `spike_success_rate`: rate > 90% (allows 10% during spike)
- `circuit_breaker_trips`: count < 10
- Recovery to normal latency within 30 seconds

**Run:**
```bash
make test-spike
```

### 7. Soak Test (`soak-test.js`)

Long-duration test for stability and resource leak detection.

**What It Tests:**
- Memory leak detection (latency degradation over time)
- Connection pool stability
- Long-term error accumulation
- Resource usage consistency

**Load Profile:**
```
0→50 VUs (2min) → 50→100 VUs (30min) → 0 (2min)
```

**Warning:** This test runs for 34 minutes total.

**Pass Criteria:**
- `latency_degradation`: < 20% between first and last 5 minutes
- `memory_leak_detection`: value < 15%
- Consistent error rate throughout

**Run:**
```bash
# Note: This takes 34 minutes
make test-soak

# Or run in background
make test-soak &
```

### 8. International Load (`international-load.js`)

Tests performance across global regions with localized content and multi-currency operations.

**What It Tests:**
- Regional traffic distribution (India 40%, US 20%, EU 15%, ME 10%, AP 15%)
- Multilingual message support (English, Hindi, Arabic, German, Chinese)
- Multi-currency billing operations
- Regional payload size variations
- Same SLA regardless of origin

**Load Profile:**
```
0→50 VUs (2min) → 50→200 VUs (3min) → 200 VUs (5min) → 0 (2min)
```

**Pass Criteria:**
- `latency_by_region`: p(95) < 1s for all regions
- `success_rate_by_region`: rate > 98% across all regions
- No region-specific degradation

**Run:**
```bash
make test-international
```

## Troubleshooting

### Test Won't Connect

```bash
# Verify gateway is running
curl http://localhost:9001/health

# Check DNS resolution
nslookup localhost

# Test with verbose output
BASE_URL=http://localhost:9001 k6 run -v k6/scenarios/gateway-routing.js
```

### Authentication Failures

```bash
# Verify token is valid and not expired
echo $TENANT_1_TOKEN | cut -d. -f2 | base64 -d | jq '.exp'

# Check current timestamp
date +%s

# If token expired, generate new one:
curl -X POST http://localhost:9001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant-load-001" \
  -d '{"email": "test@priya.local", "password": "TestPassword123!"}' \
  | jq '.access_token'

# Export new token
export TENANT_1_TOKEN="..."
```

### High Error Rates

```bash
# Check test service logs
docker logs priya-gateway
docker logs priya-auth-service
docker logs priya-conversation-service

# Run single test with verbose output
k6 run -v k6/scenarios/auth-flow.js

# Check response status codes
jq '.data[] | select(.type=="Point") | {time: .time, status: .data.resp_code}' \
  results/gateway-routing-results.json | head -20
```

### Out of Memory

```bash
# Reduce maximum VUs
k6 run --vus-max 500 k6/scenarios/websocket-load.js

# Or split across multiple machines (requires k6 cloud)
k6 run --cloud k6/scenarios/websocket-load.js
```

### Slow Performance

1. Check database queries:
   ```bash
   # Typical query latency should be <50ms
   docker exec priya-db psql -c "SELECT query, calls, mean_time FROM pg_stat_statements LIMIT 10;"
   ```

2. Check Redis latency:
   ```bash
   docker exec priya-redis redis-cli --latency-history
   ```

3. Check network latency to gateway:
   ```bash
   ping localhost
   # Should be < 1ms
   ```

## Performance Tuning

### Improving Results

1. **Close unnecessary services:**
   ```bash
   docker stop priya-analytics priya-reporting  # Less critical services
   ```

2. **Increase connection pool size:**
   - Edit `shared.core.config` or environment: `DB_POOL_SIZE=50`

3. **Enable query caching:**
   - Set `REDIS_ENABLED=true`

4. **Reduce logging verbosity:**
   - Set log level to `WARN` instead of `DEBUG`

### System Requirements for Full Suite

For running all tests with peak loads:

```
CPU:     8+ cores
Memory:  16+ GB RAM
Disk:    10+ GB free
Network: 100 Mbps+ (for CI/CD)
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Load Tests
on: [push, pull_request]

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: grafana/setup-k6-action@v1
      - name: Run load tests
        env:
          BASE_URL: ${{ secrets.API_BASE_URL }}
          TENANT_1_TOKEN: ${{ secrets.TENANT_1_TOKEN }}
        run: make ci
```

### GitLab CI Example

```yaml
load-test:
  image: grafana/k6:latest
  script:
    - make test-gateway
    - make test-auth
  artifacts:
    paths:
      - results/
```

## Advanced Usage

### Cloud Execution (K6 Cloud)

```bash
# Create account at https://app.k6.io/
k6 login cloud

# Run on K6 cloud infrastructure
k6 run --cloud k6/scenarios/gateway-routing.js

# View results at: https://app.k6.io/projects/
```

### Custom Metrics

Define custom metrics in your test:

```javascript
import { Trend, Rate, Counter } from 'k6/metrics';

const customLatency = new Trend('custom_latency');
customLatency.add(response.timings.duration);
```

### Parameterized Tests

Override test parameters:

```bash
k6 run \
  --env BASE_URL=https://staging.priyaai.com \
  --env SPIKE_DURATION=5m \
  k6/scenarios/spike-test.js
```

## Support and Debugging

### Enable Debug Logging

```bash
# Verbose output
k6 run -v k6/scenarios/gateway-routing.js

# Full HTTP logs
k6 run --http-debug=full k6/scenarios/gateway-routing.js

# Save HAR file
k6 run --include-system-env-vars k6/scenarios/gateway-routing.js > har.log
```

### Generate Reports

```bash
# HTML dashboard (requires k6 cloud)
k6 run --out html=report.html k6/scenarios/gateway-routing.js

# JSON for analysis
k6 run --out json=results.json k6/scenarios/gateway-routing.js

# Prometheus metrics
k6 run --out prometheus=localhost:9090 k6/scenarios/gateway-routing.js
```

## References

- **K6 Documentation:** https://k6.io/docs/
- **Priya API Docs:** /docs/api/openapi.yaml
- **Performance Best Practices:** https://k6.io/docs/testing-guides/load-testing/
- **Script Examples:** https://github.com/grafana/k6/tree/master/samples

## License

This load testing suite is part of the Priya Global Platform and is licensed under the same commercial license.

## Support

For issues, questions, or contributions:
- **Email:** support@priyaai.com
- **Docs:** https://docs.priyaai.com/load-testing/
- **GitHub Issues:** (link to repo)
