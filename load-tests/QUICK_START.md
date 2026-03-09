# K6 Load Testing Suite - Quick Start Guide

## Installation (2 minutes)

```bash
# Install K6
brew install k6  # macOS
# OR apt-get install k6  # Linux
# OR download from https://k6.io/

# Set up environment variables
export BASE_URL="http://localhost:9001"
export WS_URL="ws://localhost:9001"
export TENANT_1_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."  # Your JWT token
export TENANT_2_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
export TENANT_3_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
export TENANT_4_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Verify installation
k6 version
```

## Running Tests

### Option 1: Using Makefile (Recommended)

```bash
# Single test (5-20 minutes)
make test-gateway         # Gateway routing (17 min, 200 VUs)
make test-auth            # Authentication (17 min, 300 VUs)
make test-conversations   # Conversations (18 min, 500 VUs)
make test-tenant          # Multi-tenant (14 min, 50 VUs)
make test-websocket       # WebSocket (17 min, 1000 VUs)
make test-spike           # Spike test (10 min, 1000 VUs)
make test-international   # Global regions (12 min, 200 VUs)

# Long-duration test (34 minutes - run separately)
make test-soak            # Stability (30 min load, 100 VUs)

# All tests sequentially (60 minutes)
make test-all
```

### Option 2: Direct K6 Commands

```bash
# Basic run
k6 run k6/scenarios/gateway-routing.js

# With custom parameters
k6 run \
  --vus 100 \
  --duration 5m \
  k6/scenarios/gateway-routing.js

# Save results for analysis
k6 run \
  --out json=results/test-results.json \
  k6/scenarios/gateway-routing.js

# Cloud execution (requires k6 cloud account)
k6 run --cloud k6/scenarios/gateway-routing.js
```

## Understanding Results

### Standard Output (Automatic)

```
✓ http_req_duration..................: avg=245.23ms, p(95)=487.3ms, p(99)=1823.5ms
✓ http_req_failed.....................: 0.45%
✓ http_req_status: 200................: 9542
✗ http_req_status: 500................: 23

THRESHOLDS:
✓ http_req_duration: p(95)<500 ✓
✓ http_req_failed: rate<0.01 ✓
```

Green checkmarks = **PASS**
Red X's = **FAIL**

### Key Metrics to Check

| Metric | Good | Warning | Bad |
|--------|------|---------|-----|
| p(95) latency | <500ms | 500-1000ms | >1000ms |
| p(99) latency | <2000ms | 2-3000ms | >3000ms |
| Success rate | >99% | 95-99% | <95% |
| Error rate | <0.5% | 0.5-1% | >1% |

## Test Coverage

### 1. Gateway Routing
- **Purpose:** Validate proxy performance
- **Duration:** 17 minutes
- **Peak Load:** 200 concurrent users
- **Key Metric:** p95 routing latency < 200ms

### 2. Authentication
- **Purpose:** Login, token refresh, brute force protection
- **Duration:** 17 minutes
- **Peak Load:** 300 concurrent users
- **Key Metric:** p95 login < 1s, rate limit kicks in

### 3. Conversations
- **Purpose:** Create, message, close conversations (core business)
- **Duration:** 18 minutes
- **Peak Load:** 500 concurrent conversations
- **Key Metric:** p95 message send < 1s, AI response < 3s

### 4. Multi-Tenant Isolation ⭐ Critical
- **Purpose:** Verify data isolation & rate limits per plan
- **Duration:** 14 minutes
- **Peak Load:** 50 concurrent users (10 tenants)
- **Critical Check:** **ZERO data leakage allowed**

### 5. WebSocket Real-Time
- **Purpose:** Connection stability, message latency
- **Duration:** 17 minutes
- **Peak Load:** 1000 concurrent connections
- **Key Metric:** Connect time p95 < 1s, message latency < 200ms

### 6. Spike/Stress Test
- **Purpose:** Handle sudden traffic surge (50→1000 users instant)
- **Duration:** 10 minutes
- **Peak Load:** 1000 concurrent users
- **Key Metric:** Recovery within 30s, circuit breaker works

### 7. Soak Test (Long Duration)
- **Purpose:** Detect memory leaks over 30 minutes
- **Duration:** 34 minutes (LONG TEST)
- **Load:** 100 concurrent users sustained
- **Key Metric:** Latency degradation <20% over time

### 8. International Load
- **Purpose:** Global regions, multilingual, multi-currency
- **Duration:** 12 minutes
- **Regional Distribution:** India (40%), US (20%), EU (15%), ME (10%), AP (15%)
- **Key Metric:** Same SLA across all regions

## Common Commands

```bash
# View test status in real-time (another terminal)
watch -n 1 'tail results/*'

# Generate HTML report
make report

# Clean up old results
make clean

# Debug a failing test
k6 run -v k6/scenarios/gateway-routing.js

# Run with verbose HTTP logging
k6 run --http-debug=full k6/scenarios/auth-flow.js

# Stop test early (Ctrl+C)
# Results for completed stage will be saved
```

## Troubleshooting Quick Fixes

### "Connection refused" error
```bash
# Check if gateway is running
curl http://localhost:9001/health

# If not, start the platform
docker-compose up -d
```

### "Authentication failed" error
```bash
# Generate new tokens
curl -X POST http://localhost:9001/api/v1/auth/login \
  -H "X-Tenant-ID: tenant-load-001" \
  -d '{"email":"test@priya.local","password":"TestPassword123!"}' | jq '.access_token'

# Export new token
export TENANT_1_TOKEN="<new-token>"
```

### High error rate (>5%)
```bash
# Check service logs
docker logs priya-gateway | tail -50
docker logs priya-auth-service | tail -50

# Run with verbose output
k6 run -v k6/scenarios/gateway-routing.js

# Check if services are healthy
curl http://localhost:9001/health
```

### Test hangs/slow progress
```bash
# Reduce load
k6 run --vus-max 100 k6/scenarios/websocket-load.js

# Increase timeout
k6 run --timeout 30s k6/scenarios/gateway-routing.js

# Check system resources
top
free -h
```

## Expected Pass Rate for Healthy System

| Test | Pass Rate | Notes |
|------|-----------|-------|
| Gateway | 99%+ | Routing should be fast & stable |
| Auth | 95%+ | Some rate limits expected |
| Conversations | 95%+ | Core feature, should be robust |
| Multi-Tenant | 100% | **Zero data leakage tolerance** |
| WebSocket | 98%+ | Real-time is harder than HTTP |
| Spike | 90%+ | Degradation acceptable during spike |
| Soak | 99%+ | Long duration should be stable |
| International | 98%+ | Global should work same everywhere |

## File Structure

```
load-tests/
├── k6/
│   ├── config.js                    # Shared configuration
│   ├── helpers.js                   # Reusable functions
│   └── scenarios/
│       ├── gateway-routing.js       # Gateway proxy tests
│       ├── auth-flow.js             # Authentication tests
│       ├── conversation-lifecycle.js # Core business logic
│       ├── multi-tenant-isolation.js # Data isolation (CRITICAL)
│       ├── websocket-load.js        # Real-time connections
│       ├── spike-test.js            # Sudden load increase
│       ├── soak-test.js             # Long-duration stability
│       └── international-load.js    # Global traffic patterns
├── Makefile                         # Test commands
├── README.md                        # Full documentation
└── QUICK_START.md                   # This file

Total: 4,368 lines of production-ready code
```

## Next Steps

1. **Install K6** (if not already done)
2. **Set environment variables** (BASE_URL, tokens)
3. **Run a quick test:** `make test-gateway`
4. **Review results:** Check p95/p99 latencies
5. **Run full suite:** `make test-all` (60 minutes)
6. **Generate report:** `make report`

## Performance Benchmarks (Example - Healthy System)

```
Gateway Routing:
  p(50): 150ms
  p(95): 380ms
  p(99): 1200ms
  Success: 99.8%

Authentication:
  Login p(95): 650ms
  Refresh p(95): 250ms
  Success: 98.5%

Conversations:
  Create p(95): 1200ms
  Message p(95): 850ms
  AI Response p(95): 2400ms
  Success: 97.2%

WebSocket:
  Connect p(95): 800ms
  Message latency p(95): 150ms
  Success: 98.9%
```

## Support

- **Documentation:** See README.md for detailed information
- **Issues:** Check troubleshooting section in README.md
- **K6 Docs:** https://k6.io/docs/
- **Priya Docs:** https://docs.priyaai.com/
