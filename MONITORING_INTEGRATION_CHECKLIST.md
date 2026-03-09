# Monitoring Stack Integration Checklist

Complete this checklist to integrate metrics monitoring into each of the 36 microservices.

## Pre-Integration

- [ ] Read `MONITORING_SETUP.md` for architecture overview
- [ ] Review `shared/monitoring/metrics.py` module
- [ ] Understand Prometheus histogram buckets and label cardinality

## Per-Service Integration

### Step 1: Dependencies
- [ ] Add `prometheus-client` to `requirements.txt`
  ```
  prometheus-client>=0.20.0
  ```

### Step 2: Import Metrics in `main.py`
```python
from shared.monitoring.metrics import (
    PrometheusMiddleware,
    init_service_info,
    metrics_handler,
)
import os
```

### Step 3: Initialize Service Info
Add after creating FastAPI app:
```python
# Initialize metrics
init_service_info(
    service_name="YOUR_SERVICE_NAME",
    version=os.getenv("SERVICE_VERSION", "1.0.0"),
    environment=os.getenv("ENVIRONMENT", "development")
)
```

### Step 4: Add Prometheus Middleware
Add before defining routes:
```python
# Add Prometheus middleware for automatic HTTP instrumentation
app.add_middleware(PrometheusMiddleware, service_name="YOUR_SERVICE_NAME")
```

### Step 5: Expose Metrics Endpoint
Add to route definitions:
```python
# Expose Prometheus metrics endpoint
app.add_api_route("/metrics", metrics_handler, methods=["GET"])
```

### Step 6: (Optional) Custom Metrics
Add custom metric tracking for business logic:

#### For Database Queries
```python
from shared.monitoring.metrics import track_metric, db_query_duration_seconds

@app.get("/users/{user_id}")
@track_metric(
    histogram=db_query_duration_seconds,
    metric_labels={"query_type": "select_by_id", "service": "YOUR_SERVICE_NAME"}
)
async def get_user(user_id: int):
    # Query logic
    pass
```

#### For Cache Operations
```python
from shared.monitoring.metrics import redis_operations_total

async def cache_operation(key: str, value: str):
    redis_operations_total.labels(
        operation="set",
        service="YOUR_SERVICE_NAME"
    ).inc()
    # Cache logic
```

#### For Feature Events
```python
from shared.monitoring.metrics import active_conversations

# Update conversation gauge
active_conversations.labels(
    tenant_id="tenant-123",
    channel="whatsapp"
).set(current_count)
```

#### For AI Token Usage
```python
from shared.monitoring.metrics import ai_tokens_used_total

# Record token consumption
ai_tokens_used_total.labels(
    tenant_id="tenant-123",
    model="gpt-4",
    service="YOUR_SERVICE_NAME"
).inc(tokens_consumed)
```

## Service-Specific Checklist

### Gateway Service (9000)
- [ ] Step 1-5 complete
- [ ] Custom: Track incoming tenant_id from headers
- [ ] Custom: Track rate limiting violations

### Auth Service (9001)
- [ ] Step 1-5 complete
- [ ] Custom: Track auth success/failure rates
- [ ] Custom: Track token generation time

### Tenant Service (9002)
- [ ] Step 1-5 complete
- [ ] Custom: Track tenant_api_calls_total
- [ ] Custom: Track tenant_rate_limit_exceeded_total

### Channel Services (WhatsApp, Email, Voice, Social, Webchat, SMS, Telegram)
- [ ] Step 1-5 complete
- [ ] Custom: Track active_conversations by channel
- [ ] Custom: Track conversations_created_total
- [ ] Custom: Track conversation_duration_seconds

### AI Engine Service (9004)
- [ ] Step 1-5 complete
- [ ] Custom: Track ai_api_calls_total
- [ ] Custom: Track ai_api_duration_seconds
- [ ] Custom: Track ai_tokens_used_total
- [ ] Custom: Track ai_token_budget_used_percent (check quota)

### Billing Service (9020)
- [ ] Step 1-5 complete
- [ ] Custom: Track tenant_token_usage_percent
- [ ] Custom: Track ai_token_budget_exceeded alerts

### Analytics Service (9021)
- [ ] Step 1-5 complete
- [ ] Custom: Expose aggregated metrics

### All Database-Heavy Services
- [ ] Step 1-5 complete
- [ ] Custom: Track db_query_duration_seconds
- [ ] Custom: Track db_connections_active/available

### All Kafka-Using Services
- [ ] Step 1-5 complete
- [ ] Custom: Track kafka_messages_produced_total
- [ ] Custom: Track kafka_messages_consumed_total
- [ ] Custom: Track kafka_consumer_lag (consumers only)

### All Redis-Using Services
- [ ] Step 1-5 complete
- [ ] Custom: Track redis_operations_total
- [ ] Custom: Track redis_operation_duration_seconds

## Testing Integration

### Per Service

1. **Verify metrics endpoint accessible**:
   ```bash
   curl http://localhost:9001/metrics  # auth service example
   ```

2. **Generate test traffic**:
   ```bash
   # Make requests to service
   curl http://localhost:9001/health
   curl http://localhost:9001/health
   ```

3. **Check metrics reflected**:
   ```bash
   curl http://localhost:9001/metrics | grep http_requests_total
   ```

   Should show:
   ```
   # HELP http_requests_total Total HTTP requests received
   # TYPE http_requests_total counter
   http_requests_total{method="GET",endpoint="/health",status="200",tenant_id="unknown",service="auth"} 2.0
   ```

### Prometheus Level

1. **Verify target discovery**:
   ```bash
   curl http://localhost:9090/api/v1/targets | jq .
   ```

2. **Query metrics**:
   ```bash
   # Request rate per service
   curl 'http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total%5B5m%5D))%20by%20(service)'

   # Active conversations
   curl 'http://localhost:9090/api/v1/query?query=sum(active_conversations)%20by%20(tenant_id)'
   ```

### Grafana Level

1. **Verify datasource**:
   - Dashboard Settings > Datasources > Prometheus
   - Click "Test Connection"

2. **View dashboards**:
   - Platform Overview: http://localhost:3001/d/priya-platform-overview
   - Tenant Analytics: http://localhost:3001/d/priya-tenant-analytics

## Common Issues & Solutions

### Metrics Endpoint 404
**Issue**: `curl http://localhost:9001/metrics` returns 404
**Solution**: Verify route added: `app.add_api_route("/metrics", metrics_handler, methods=["GET"])`

### Prometheus Target Down
**Issue**: Target marked as `DOWN` in Prometheus UI
**Solution**:
1. Check service is running: `docker ps | grep service-name`
2. Check service has metrics endpoint: `curl http://localhost:PORT/metrics`
3. Check docker-compose port mapping matches prometheus.yml scrape_configs
4. Check service logs: `docker logs priya-service-name`

### No Data in Grafana
**Issue**: Dashboards show "no data"
**Solution**:
1. Wait 1-2 minutes for metrics to be scraped (scrape interval is 15s)
2. Verify Prometheus has data: Query in Prometheus UI
3. Verify Grafana datasource: Settings > Datasources > Test Connection
4. Check dashboard variables match available labels

### High Memory Usage
**Issue**: Prometheus or Grafana memory usage increasing
**Solution**:
1. **Reduce cardinality**: Avoid unbounded labels (e.g., request IDs)
2. **Reduce retention**: Edit docker-compose `--storage.tsdb.retention.time=14d`
3. **Drop metrics**: Add `metric_relabel_configs` to prometheus.yml to drop unneeded metrics

### Service Not Appearing in Prometheus
**Issue**: Service not in targets list
**Solution**:
1. Verify service name in docker-compose matches prometheus.yml
2. Verify port in prometheus.yml matches service expose port
3. Check DNS resolution: `docker compose exec prometheus nslookup service-name`
4. Reload config: `curl -X POST http://localhost:9090/-/reload` (requires `--web.enable-lifecycle`)

## Validation Checklist

Before declaring monitoring complete:

- [ ] All 36 services have metrics endpoint responding
- [ ] Prometheus targets page shows all services as UP
- [ ] Platform Overview dashboard has data in all panels
- [ ] Tenant Analytics dashboard filters by tenant correctly
- [ ] Sample alert conditions fire in test scenario
- [ ] Grafana alerts webhook configured (if using)
- [ ] Historical data retention meets requirements (30 days)
- [ ] No "high cardinality" warnings in Prometheus logs
- [ ] Dashboards accessible and readable
- [ ] Custom metrics appear in metric dropdowns

## Rollout Order (Recommended)

1. **Core Layer** (Layer 0-1):
   - gateway, auth, tenant, tenant-config

2. **Routing & AI** (Layer 2):
   - channel-router, ai-engine

3. **Channels** (Layer 3):
   - whatsapp, email, voice, social, webchat, sms, telegram

4. **Business** (Layer 4):
   - billing, analytics, marketing, ecommerce, notification, plugins, handoff, leads

5. **Advanced** (Layer 5):
   - conversation-intel, appointments, knowledge, voice-ai, video, rcs, workflows, advanced-analytics, ai-training, marketplace

6. **Operations** (Layer 6):
   - compliance, health-monitor, cdn-manager, deployment

## Service Template

Use this template for each new service:

```python
# main.py
import os
from fastapi import FastAPI
from shared.monitoring.metrics import (
    PrometheusMiddleware,
    init_service_info,
    metrics_handler,
    # Additional imports for custom metrics
)

SERVICE_NAME = "your-service-name"
SERVICE_PORT = 9XYZ
app = FastAPI()

# Initialize metrics at startup
init_service_info(
    service_name=SERVICE_NAME,
    version=os.getenv("SERVICE_VERSION", "1.0.0"),
    environment=os.getenv("ENVIRONMENT", "development")
)

# Add Prometheus middleware before defining routes
app.add_middleware(PrometheusMiddleware, service_name=SERVICE_NAME)

# Routes
@app.get("/health")
async def health():
    return {"status": "ok"}

# Metrics endpoint
app.add_api_route("/metrics", metrics_handler, methods=["GET"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)
```

## Support & Questions

- Review `MONITORING_SETUP.md` for comprehensive documentation
- Check `shared/monitoring/metrics.py` source for available metrics
- Query examples in `MONITORING_SETUP.md` PromQL section
