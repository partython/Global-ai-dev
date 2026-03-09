# Monitoring Stack — Quick Start Guide

Fast reference for getting metrics and dashboards running.

## 1. Start Monitoring (One Command)

```bash
# Launch Prometheus + Grafana
docker compose --profile monitoring up -d

# Wait for services to be healthy
sleep 10
docker compose ps
```

## 2. Verify It Works

```bash
# Check Prometheus is scraping
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[0]'

# Check Grafana is running
curl http://localhost:3001/api/health
```

## 3. Access Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| **Prometheus** | http://localhost:9090 | (none) |
| **Grafana** | http://localhost:3001 | admin / priya_grafana_2024 |
| **Platform Overview** | http://localhost:3001/d/priya-platform-overview | (auto-load) |
| **Tenant Analytics** | http://localhost:3001/d/priya-tenant-analytics | (auto-load) |

## 4. Add Metrics to a Service (5 minutes)

### 4a. Example: Auth Service

**Edit `services/auth/main.py`**:

```python
from fastapi import FastAPI
from shared.monitoring.metrics import (
    PrometheusMiddleware,
    init_service_info,
    metrics_handler,
)
import os

app = FastAPI()

# Add these 3 blocks:

# 1. Initialize service info
init_service_info(
    service_name="auth",
    version=os.getenv("SERVICE_VERSION", "1.0.0"),
    environment=os.getenv("ENVIRONMENT", "development")
)

# 2. Add Prometheus middleware (goes BEFORE your routes)
app.add_middleware(PrometheusMiddleware, service_name="auth")

# 3. Add metrics endpoint
app.add_api_route("/metrics", metrics_handler, methods=["GET"])

# ... rest of your routes
```

### 4b. Optional: Custom Metrics

```python
from shared.monitoring.metrics import (
    ai_tokens_used_total,
    active_conversations,
)

# Track AI token usage
ai_tokens_used_total.labels(
    tenant_id="tenant-123",
    model="gpt-4",
    service="auth"
).inc(250)

# Track active conversations
active_conversations.labels(
    tenant_id="tenant-123",
    channel="whatsapp"
).set(42)
```

### 4c. Verify Metrics Appear

```bash
# Restart service
docker compose up -d auth

# Check metrics endpoint (after ~30s)
curl http://localhost:9001/metrics | head -20
```

## 5. Query Examples

### Prometheus UI (http://localhost:9090/graph)

```promql
# Request rate per service (req/sec)
sum(rate(http_requests_total[5m])) by (service)

# Error rate percentage
(sum(rate(http_requests_total{status=~"5.."}[5m])) /
 sum(rate(http_requests_total[5m]))) * 100

# p95 latency per service
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m]))
  by (service, le))

# Top 5 busiest services
topk(5, sum(rate(http_requests_total[5m])) by (service))

# Active conversations
sum(active_conversations) by (channel)

# Tenants near token budget
ai_token_budget_used_percent > 80
```

## 6. Common Commands

```bash
# View Prometheus targets
curl http://localhost:9090/api/v1/targets

# Query a metric
curl 'http://localhost:9090/api/v1/query?query=up'

# View alerts
curl http://localhost:9090/api/v1/alerts

# Check service metrics
curl http://localhost:9001/metrics     # auth
curl http://localhost:9000/metrics     # gateway
curl http://localhost:9020/metrics     # billing

# Reload Prometheus config
curl -X POST http://localhost:9090/-/reload

# View Grafana API
curl http://localhost:3001/api/search

# Restart monitoring stack
docker compose --profile monitoring restart

# Stop monitoring (keep data)
docker compose --profile monitoring stop

# Stop monitoring (remove data)
docker compose --profile monitoring down -v
```

## 7. Troubleshooting

### Service metrics not appearing

```bash
# 1. Check service is running
docker ps | grep your-service

# 2. Verify metrics endpoint exists
curl http://localhost:PORT/metrics

# 3. Check Prometheus logs
docker logs priya-prometheus | tail -20

# 4. Manually trigger Prometheus reload
curl -X POST http://localhost:9090/-/reload
```

### Dashboard shows "no data"

```bash
# 1. Wait 1-2 minutes for metrics to be scraped
sleep 60

# 2. Check Prometheus has the metric
curl 'http://localhost:9090/api/v1/query?query=up'

# 3. Check Grafana datasource connection
# In Grafana: Settings > Data Sources > Prometheus > Test Connection

# 4. Check dashboard variable matches
# In Grafana: Dashboard > Settings > Variables
```

### High Prometheus memory usage

```bash
# Check metric cardinality
curl 'http://localhost:9090/api/v1/query?query=count(count%20by%20(__name__)(%7B__name__%7D))'

# Reduce retention time
docker compose stop prometheus
docker volume rm prometheus_data
docker compose up -d prometheus

# Then edit docker-compose.yml:
# --storage.tsdb.retention.time=14d  # reduce from 30d
```

## 8. Useful Metrics Reference

```
HTTP Requests:
  http_requests_total              # total requests (counter)
  http_request_duration_seconds    # request latency (histogram)
  http_requests_in_progress        # concurrent requests (gauge)

Database:
  db_query_duration_seconds        # query latency (histogram)
  db_connections_active            # active connections (gauge)
  db_connections_available         # free connections (gauge)

Cache (Redis):
  redis_operations_total           # operations count (counter)
  redis_memory_usage_bytes         # memory usage (gauge)
  redis_connected_clients          # client count (gauge)

Message Queue (Kafka):
  kafka_messages_produced_total    # published messages (counter)
  kafka_messages_consumed_total    # consumed messages (counter)
  kafka_consumer_lag               # queue lag (gauge)

Features:
  active_conversations             # active chats (gauge)
  conversations_created_total      # new chats (counter)
  ai_tokens_used_total             # LLM tokens (counter)
  ai_token_budget_used_percent     # quota % (gauge)
  tenant_api_calls_total           # per-tenant calls (counter)
  tenant_rate_limit_exceeded_total # rate limits (counter)
```

## 9. Integration Checklist (Per Service)

Repeat for each of your 36 services:

- [ ] Add imports to main.py
- [ ] Call `init_service_info()`
- [ ] Add `PrometheusMiddleware`
- [ ] Add `/metrics` route
- [ ] Add custom metrics (if needed)
- [ ] Test: `curl http://localhost:PORT/metrics`
- [ ] Check: Service appears in Prometheus targets
- [ ] Verify: Data appears in Grafana dashboards

## 10. Full Integration Timeline

```
Time    | Task
--------|----------------------------------
0 min   | Start monitoring: docker compose --profile monitoring up -d
5 min   | Add metrics to gateway + auth
10 min  | Add metrics to tenant + ai-engine
15 min  | Add metrics to channel services (7 services)
20 min  | Add metrics to business services (8 services)
25 min  | Add metrics to advanced services (9 services)
30 min  | Add metrics to ops services (4 services)
35 min  | Verify all services in Prometheus targets
40 min  | View Platform Overview dashboard
45 min  | View Tenant Analytics dashboard
50 min  | Test custom metrics
60 min  | COMPLETE! Full observability enabled
```

## 11. Next: Make It Production-Ready

After completing quick start:

1. **Enable Alertmanager** → Route alerts to Slack/PagerDuty
2. **Configure remote storage** → Thanos/Cortex for long-term retention
3. **Add SLO dashboards** → Track error budgets
4. **Integrate with tracing** → Jaeger/Zipkin for request flows
5. **Set recording rules** → Pre-aggregate common queries
6. **Configure backups** → Regular Prometheus data backups

## 12. File Locations

```
priya-global/
├── shared/monitoring/
│   └── metrics.py                    # ← Import this!
├── monitoring/
│   ├── prometheus/
│   │   ├── prometheus.yml            # 36+ service configs
│   │   └── alerts.yml                # 12 alert categories
│   └── grafana/
│       ├── provisioning/
│       │   ├── datasources/prometheus.yml
│       │   └── dashboards/dashboard.yml
│       └── dashboards/
│           ├── platform-overview.json
│           └── tenant-analytics.json
├── MONITORING_SETUP.md               # Full documentation
├── MONITORING_INTEGRATION_CHECKLIST.md
└── docker-compose.yml                # Updated with monitoring services
```

## 13. Key Contacts

Documentation:
- **Main Guide**: `MONITORING_SETUP.md` (architecture, configuration, queries)
- **Integration**: `MONITORING_INTEGRATION_CHECKLIST.md` (step-by-step per service)
- **Source Code**: `shared/monitoring/metrics.py` (all available metrics)

## Quick Reference Links

- Prometheus Web UI: http://localhost:9090
- Grafana Web UI: http://localhost:3001
- Prometheus API: http://localhost:9090/api/v1/
- Grafana API: http://localhost:3001/api/
- Platform Overview: http://localhost:3001/d/priya-platform-overview
- Tenant Analytics: http://localhost:3001/d/priya-tenant-analytics

---

**💡 Pro Tips:**

1. **Most important metric**: `http_requests_total` — automatically tracked by middleware
2. **Best dashboard**: Platform Overview — shows health of all 36+ services at a glance
3. **Most useful query**: `rate(http_requests_total[5m])` — requests per second
4. **Fastest integration**: Just add middleware, get HTTP metrics automatically
5. **Custom metrics**: Use decorators for database/cache operations

Start with just HTTP metrics, add custom metrics later!
