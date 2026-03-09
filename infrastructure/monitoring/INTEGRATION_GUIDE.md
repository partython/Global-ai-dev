# Metrics Integration Guide

Step-by-step guide to integrate Prometheus metrics into your FastAPI services.

## Overview

Each service in Priya Global should expose metrics on the `/metrics` endpoint for Prometheus to scrape every 15 seconds.

## Installation

1. **Install prometheus-client** (already in requirements.txt):
   ```bash
   pip install prometheus-client
   ```

2. **Import metrics middleware**:
   ```python
   from shared.middleware.metrics import PrometheusMiddleware, setup_metrics_routes
   ```

## Basic Integration

### Step 1: Add Middleware

```python
from fastapi import FastAPI
from shared.middleware.metrics import PrometheusMiddleware, setup_metrics_routes

app = FastAPI(
    title="My Service",
    description="Service description",
    version="1.0.0"
)

# Add metrics middleware (BEFORE other middleware)
app.add_middleware(
    PrometheusMiddleware,
    app_name="my-service"  # Service identifier for metrics
)

# Setup /metrics endpoint
setup_metrics_routes(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
```

### Step 2: Verify Metrics Endpoint

```bash
# After starting service, check metrics:
curl http://localhost:9000/metrics

# Should see:
# # HELP http_requests_total Total HTTP requests
# # TYPE http_requests_total counter
# http_requests_total{endpoint="/hello",method="GET",service_name="my-service",status_code="200"} 5.0
```

### Step 3: Test Integration

```bash
# Make some requests
curl http://localhost:9000/hello
curl http://localhost:9000/api/users
curl http://localhost:9000/api/users -X POST

# Check metrics updated
curl http://localhost:9000/metrics | grep http_requests_total
```

## Recording Custom Metrics

### Track Processed Messages

```python
from fastapi import FastAPI
from shared.middleware.metrics import record_message_processed, set_active_conversations

app = FastAPI()

@app.post("/messages/process")
async def process_message(msg: dict):
    try:
        # Process message...
        result = await handle_message(msg)

        # Record successful processing
        record_message_processed(
            service_name="my-service",
            channel="whatsapp",
            status="success"
        )
        return result
    except Exception as e:
        record_message_processed(
            service_name="my-service",
            channel="whatsapp",
            status="error"
        )
        raise

@app.get("/conversations/active")
async def get_active_conversations():
    count = await db.count_active()

    # Update active conversation gauge
    set_active_conversations(
        service_name="my-service",
        channel="whatsapp",
        count=count
    )

    return {"active": count}
```

### Track Database Operations

```python
from shared.middleware.metrics import record_db_query, time_db_operation, record_db_connection_count
from sqlalchemy.orm import Session

@app.get("/users/{user_id}")
async def get_user(user_id: int, db: Session):
    async with time_db_operation("my-service", "SELECT", "users"):
        user = db.query(User).filter(User.id == user_id).first()

    # Or record manually
    import time
    start = time.time()
    user = db.query(User).filter(User.id == user_id).first()
    duration = time.time() - start

    record_db_query("my-service", "SELECT", "users", duration)
    return user

# Update connection count periodically
@app.on_event("startup")
async def startup():
    async def update_db_connections():
        while True:
            import asyncio
            await asyncio.sleep(30)

            conn_count = get_active_connections()
            record_db_connection_count(
                "my-service",
                "postgres",
                conn_count
            )

    asyncio.create_task(update_db_connections())
```

### Track Cache Usage

```python
from shared.middleware.metrics import record_cache_hit, record_cache_miss
import redis

redis_client = redis.Redis(host='localhost', port=6379)

@app.get("/cache/{key}")
async def get_cached(key: str):
    cached = redis_client.get(key)

    if cached:
        record_cache_hit("my-service", "redis")
        return {"value": cached}
    else:
        record_cache_miss("my-service", "redis")

        # Compute and cache
        value = await compute_value(key)
        redis_client.setex(key, 3600, value)
        return {"value": value}
```

### Track AI Inferences

```python
from shared.middleware.metrics import record_ai_inference, time_ai_inference
import openai

@app.post("/ai/infer")
async def run_inference(prompt: str):
    try:
        async with time_ai_inference("ai-engine", "gpt-3.5-turbo"):
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}]
            )

        record_ai_inference(
            "ai-engine",
            "gpt-3.5-turbo",
            "success"
        )

        return response
    except Exception as e:
        record_ai_inference(
            "ai-engine",
            "gpt-3.5-turbo",
            "error"
        )
        raise
```

### Track Rate Limiting

```python
from shared.middleware.metrics import set_rate_limit_remaining
from fastapi import Header, HTTPException

@app.get("/api/endpoint")
async def protected_endpoint(x_api_key: str = Header(...)):
    # Get client info
    client_info = await get_client_info(x_api_key)

    # Check rate limit
    remaining = client_info.rate_limit_remaining
    limit = client_info.rate_limit_limit

    if remaining <= 0:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Record rate limit state
    set_rate_limit_remaining(
        "my-service",
        client_info.client_id,
        remaining - 1,
        limit
    )

    # Process request...
    return {"success": True}
```

### Track Conversations

```python
from shared.middleware.metrics import (
    set_active_conversations,
    record_conversation_completed
)

@app.post("/conversations/create")
async def create_conversation(channel: str):
    conv = await db.create_conversation(channel)

    # Update active count
    active_count = await db.count_active_by_channel(channel)
    set_active_conversations("my-service", channel, active_count)

    return conv

@app.post("/conversations/{conv_id}/close")
async def close_conversation(conv_id: str, channel: str):
    await db.close_conversation(conv_id)

    # Record completion
    record_conversation_completed("my-service", channel)

    # Update active count
    active_count = await db.count_active_by_channel(channel)
    set_active_conversations("my-service", channel, active_count)

    return {"closed": conv_id}
```

## Query Metrics in Prometheus

### Service Health

```promql
# All services status
up{job!="prometheus"}

# Specific service
up{job="my-service"}

# Services down
up == 0

# Multiple services down in last minute
count(up == 0) > 5
```

### Request Metrics

```promql
# Requests per second
rate(http_requests_total[5m])

# By service
sum by (job) (rate(http_requests_total[5m]))

# By endpoint
sum by (endpoint) (rate(http_requests_total[5m]))

# Error rate (5xx)
sum by (job) (rate(http_requests_total{status_code=~"5.."}[5m]))
/
sum by (job) (rate(http_requests_total[5m]))
```

### Latency Metrics

```promql
# P99 latency
histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))

# P95 latency
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))

# By service
histogram_quantile(0.99, sum by (job, le) (rate(http_request_duration_seconds_bucket[5m])))

# Slow requests (>1s)
sum by (job) (rate(http_request_duration_seconds_bucket{le="+Inf"}[5m]))
-
sum by (job) (rate(http_request_duration_seconds_bucket{le="1.0"}[5m]))
```

### Database Metrics

```promql
# Database connections
pg_stat_activity_count

# Connection pool usage (%)
(pg_stat_activity_count / pg_settings_max_connections) * 100

# Query latency P99
histogram_quantile(0.99, sum by (le) (rate(db_query_duration_seconds_bucket[5m])))
```

### Cache Metrics

```promql
# Redis hit rate (%)
(redis_keyspace_hits_total / (redis_keyspace_hits_total + redis_keyspace_misses_total)) * 100

# Memory usage (%)
(redis_memory_used_bytes / redis_memory_max_bytes) * 100

# Evictions
increase(redis_evicted_keys_total[5m])
```

### AI Metrics

```promql
# Inference success rate
sum by (model) (rate(ai_inference_total{status="success"}[5m]))
/
sum by (model) (rate(ai_inference_total[5m]))

# Inference latency P99
histogram_quantile(0.99, sum by (model, le) (rate(ai_inference_duration_seconds_bucket[5m])))
```

## Grafana Dashboard Queries

### Create New Dashboard

1. Go to http://localhost:3001
2. Click "Create" → "Dashboard"
3. Click "Add new panel"
4. Select Prometheus datasource
5. Enter PromQL query:

```promql
# Example: Service request rate
sum by (job) (rate(http_requests_total[5m]))
```

### Save and Share

1. Click "Save dashboard"
2. Give dashboard a name
3. Export JSON to share
4. Import in other Grafana instances

## Alert Rules with Metrics

### Create Alerts

Add to `prometheus/alert_rules.yml`:

```yaml
groups:
  - name: my_service
    interval: 30s
    rules:
      # Service down
      - alert: MyServiceDown
        expr: up{job="my-service"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "My Service is down"

      # High error rate
      - alert: MyServiceHighErrors
        expr: |
          (sum(rate(http_requests_total{job="my-service",status_code=~"5.."}[5m])) /
           sum(rate(http_requests_total{job="my-service"}[5m]))) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "My Service error rate > 5%"

      # High latency
      - alert: MyServiceHighLatency
        expr: |
          histogram_quantile(0.99, sum by (le)
          (rate(http_request_duration_seconds_bucket{job="my-service"}[5m]))) > 1.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "My Service P99 latency > 1s"
```

## Best Practices

### 1. Use Consistent Service Names

- Match service name in middleware to Docker container name
- Use lowercase, hyphen-separated names
- Document service name mapping

### 2. Avoid High Cardinality

Don't use these as metric labels:
- User IDs
- Request IDs
- Timestamps
- Customer IDs

These can explode cardinality and degrade performance.

### 3. Group Related Metrics

```python
# Good - grouped by concern
record_message_processed(service, channel, status)
set_active_conversations(service, channel, count)

# Bad - too many labels
record_event(
    service, channel, user_id, message_id,
    conversation_id, timestamp, ...
)
```

### 4. Record Meaningful Status

```python
# Good - meaningful status values
record_ai_inference(service, model, "success")
record_ai_inference(service, model, "error")
record_ai_inference(service, model, "timeout")

# Bad - generic status codes
record_ai_inference(service, model, "200")
record_ai_inference(service, model, "500")
```

### 5. Update Gauges Periodically

```python
# Good - update every few seconds/minutes
async def update_metrics():
    while True:
        count = await get_active_conversations()
        set_active_conversations(service, channel, count)
        await asyncio.sleep(10)

# Bad - only on events
# Gauges need periodic updates to be useful for alerting
```

## Troubleshooting

### Metrics not appearing

1. Check service is running
2. Verify `/metrics` endpoint works: `curl localhost:9000/metrics`
3. Check service name matches `prometheus.yml`
4. Review Prometheus logs: `docker logs priya-prometheus`

### High cardinality alerts

1. Check what labels you're recording
2. Remove dynamic labels (IDs, timestamps)
3. Use recording rules to aggregate
4. Monitor Prometheus cardinality: http://localhost:9090/tsdb-status

### Dashboard queries slow

1. Use recording rules instead of raw metrics
2. Increase time range aggregation
3. Add metric_relabel_configs to drop unnecessary metrics
4. Check Prometheus memory usage

## Examples

See `/services/*/main.py` for complete service integration examples.

Key files:
- Gateway: `/services/gateway/main.py`
- Auth: `/services/auth/main.py`
- AI Engine: `/services/ai_engine/main.py`

All services use the same metrics middleware pattern.

## References

- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [prometheus-client Python Docs](https://github.com/prometheus/client_python)
- [Grafana PromQL Guide](https://grafana.com/docs/grafana/latest/panels/visualizations/stat-panel/)
