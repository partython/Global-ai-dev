# Priya Global Platform — Monitoring Stack Setup

Complete Prometheus + Grafana observability stack for all 36 microservices and the Next.js dashboard.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Grafana (port 3001)                          │
│                    • Platform Overview Dashboard                │
│                    • Tenant Analytics Dashboard                 │
│                    • Alert Management                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                  Prometheus (port 9090)                         │
│                  • Metric Scraping (15s interval)               │
│                  • 30-day Retention                             │
│                  • Alert Evaluation                             │
│                  • Time Series Database                         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
   ┌─────────────┐   ┌──────────────┐   ┌──────────────┐
   │  API Layer  │   │ Business     │   │  Advanced    │
   │             │   │ Services     │   │  Features    │
   │ gateway     │   │              │   │              │
   │ auth        │   │ billing      │   │ conversation │
   │ tenant      │   │ analytics    │   │ knowledge    │
   │ ...         │   │ marketing    │   │ ai-training  │
   └─────────────┘   └──────────────┘   └──────────────┘

   ┌─────────────────────────────────────┐
   │    Infrastructure Services          │
   │                                     │
   │ • PostgreSQL (port 5432)            │
   │ • Redis (port 6379)                 │
   │ • Kafka (port 9092)                 │
   └─────────────────────────────────────┘
```

## Quick Start

### 1. Start Monitoring Stack

```bash
# Start Prometheus + Grafana
docker compose --profile monitoring up -d

# Verify services are running
docker compose ps | grep -E "prometheus|grafana"
```

### 2. Access Dashboards

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3001
  - Username: `admin`
  - Password: `priya_grafana_2024` (override with `GRAFANA_PASSWORD` env var)

### 3. Check Metrics Collection

```bash
# Verify Prometheus is scraping targets
curl http://localhost:9090/api/v1/targets

# Check metrics endpoint of any service
curl http://localhost:9001/metrics  # auth service
curl http://localhost:9000/metrics  # gateway
```

## Integration Guide

### For FastAPI Services

Every FastAPI service must:

1. **Install prometheus_client**:
   ```bash
   pip install prometheus-client
   ```

2. **Initialize metrics in main.py**:
   ```python
   from fastapi import FastAPI
   from shared.monitoring.metrics import (
       PrometheusMiddleware,
       init_service_info,
       metrics_handler,
   )

   app = FastAPI()

   # Initialize metrics
   init_service_info(
       service_name="auth",
       version=os.getenv("SERVICE_VERSION", "1.0.0"),
       environment=os.getenv("ENVIRONMENT", "development")
   )

   # Add Prometheus middleware for automatic HTTP instrumentation
   app.add_middleware(PrometheusMiddleware, service_name="auth")

   # Expose /metrics endpoint
   app.add_api_route("/metrics", metrics_handler, methods=["GET"])
   ```

3. **Use decorators for custom metrics**:
   ```python
   from shared.monitoring.metrics import (
       track_metric,
       db_query_duration_seconds,
       redis_operations_total,
   )

   @app.get("/users/{user_id}")
   @track_metric(
       histogram=db_query_duration_seconds,
       metric_labels={"query_type": "select_by_id", "service": "auth"}
   )
   async def get_user(user_id: int):
       # Query logic here
       pass

   @app.post("/cache/set")
   @track_metric(
       counter=redis_operations_total,
       metric_labels={"operation": "set", "service": "auth"}
   )
   async def set_cache(key: str, value: str):
       # Cache logic here
       pass
   ```

4. **Report metrics manually**:
   ```python
   from shared.monitoring.metrics import (
       active_conversations,
       ai_tokens_used_total,
       kafka_messages_produced_total,
   )

   # In your conversation handler
   active_conversations.labels(
       tenant_id="tenant-123",
       channel="whatsapp"
   ).set(42)

   # In your AI service
   ai_tokens_used_total.labels(
       tenant_id="tenant-123",
       model="gpt-4",
       service="ai-engine"
   ).inc(250)

   # When publishing to Kafka
   kafka_messages_produced_total.labels(
       topic="conversations",
       service="channel-router"
   ).inc()
   ```

## Available Metrics

### HTTP Request Metrics

```
http_requests_total
  Labels: method, endpoint, status, tenant_id, service
  Type: Counter
  Example: requests per endpoint per tenant

http_request_duration_seconds
  Labels: method, endpoint, service
  Type: Histogram (buckets: 5ms to 10s)
  Example: latency percentiles (p50, p95, p99)

http_requests_in_progress
  Labels: service
  Type: Gauge
  Example: concurrent request count
```

### Database Metrics

```
db_query_duration_seconds
  Labels: query_type, service
  Type: Histogram
  Example: SELECT/INSERT/UPDATE query latency

db_connections_active
  Labels: service, pool
  Type: Gauge
  Example: active connection count

db_connections_available
  Labels: service, pool
  Type: Gauge
  Example: free connections in pool
```

### Cache/Redis Metrics

```
redis_operations_total
  Labels: operation, service
  Type: Counter
  Example: GET, SET, INCR operations

redis_operation_duration_seconds
  Labels: operation, service
  Type: Histogram
  Example: cache hit/miss latency

redis_memory_usage_bytes
  Type: Gauge
  Example: total memory consumption

redis_connected_clients
  Type: Gauge
  Example: active client connections
```

### Message Queue Metrics

```
kafka_messages_produced_total
  Labels: topic, service
  Type: Counter
  Example: published message count

kafka_messages_consumed_total
  Labels: topic, service
  Type: Counter
  Example: consumed message count

kafka_consumer_lag
  Labels: topic, consumer_group, service
  Type: Gauge
  Example: messages behind in queue

kafka_produce_duration_seconds
  Labels: topic, service
  Type: Histogram
  Example: publish latency
```

### Feature-Specific Metrics

#### Conversations
```
active_conversations
  Labels: tenant_id, channel
  Type: Gauge
  Example: WhatsApp (10), Email (5), Webchat (3)

conversations_created_total
  Labels: tenant_id, channel, service
  Type: Counter

conversation_duration_seconds
  Labels: tenant_id, channel, service
  Type: Histogram
```

#### AI/LLM
```
ai_tokens_used_total
  Labels: tenant_id, model, service
  Type: Counter
  Example: GPT-4 tokens, Claude tokens per tenant

ai_api_calls_total
  Labels: model, service, status
  Type: Counter

ai_api_duration_seconds
  Labels: model, service
  Type: Histogram

ai_token_budget_used_percent
  Labels: tenant_id, model
  Type: Gauge
  Example: Alert when > 95%
```

#### Multi-Tenancy
```
tenant_api_calls_total
  Labels: tenant_id, plan, service
  Type: Counter

tenant_rate_limit_exceeded_total
  Labels: tenant_id, service
  Type: Counter
  Example: Alerts on > 100/min

active_tenants
  Type: Gauge

tenant_token_usage_percent
  Labels: tenant_id, quota_type
  Type: Gauge
```

## Dashboards

### Platform Overview (`platform-overview.json`)

Main dashboard for operations team with panels:

1. **Service Health Matrix** — Table showing all 36+ services (up/down)
2. **Request Rate** — Time series graph of requests/sec per service
3. **Error Rate** — 5xx error percentage with thresholds
4. **Response Time Percentiles** — p50, p95, p99 latency
5. **Active Conversations** — Real-time conversation count
6. **Top Tenants by API Calls** — Bar chart of heaviest users
7. **Database Connection Pool** — Gauge for connection utilization
8. **Redis Memory Usage** — Gauge with threshold alerts
9. **Kafka Consumer Lag** — Time series for queue backlog
10. **AI Token Usage** — Stacked bar by model and tenant
11. **Conversations by Channel** — Pie chart breakdown

**Access**: http://localhost:3001/d/priya-platform-overview

### Tenant Analytics (`tenant-analytics.json`)

Per-tenant detailed analytics:

1. **API Calls by Endpoint** — Service-level breakdown
2. **Response Times (p95)** — Latency trends
3. **Error Rate (%)** — Service quality metrics
4. **Channel Usage Breakdown** — Pie chart
5. **AI Token Budget Used** — Gauge (alerts at 80%, 95%)
6. **Conversations (24h)** — Total daily count
7. **AI Tokens by Model** — Stacked bar chart
8. **Conversation Volume by Channel** — Time series
9. **Customer Satisfaction Score** — Rating widget

**Access**: http://localhost:3001/d/priya-tenant-analytics

**Variables**:
- `$tenant`: Select tenant ID to filter all panels
- `$interval`: Aggregation interval (auto, 1m, 5m, 1h)

## Alerting

Alert rules are defined in `/monitoring/prometheus/alerts.yml`.

### Alert Categories

#### Service Health (Critical)
- **ServiceDown**: Service unreachable for 1 minute
- **HighErrorRate**: >5% 5xx errors for 5 minutes
- **VeryHighErrorRate**: >20% 5xx errors for 2 minutes

#### Performance (Warning)
- **HighLatencyP50**: Median latency >500ms
- **HighLatencyP95**: p95 latency >2s
- **HighLatencyP99**: p99 latency >5s

#### Resources (Warning/Critical)
- **HighMemoryUsage**: >85% of limit for 10 minutes
- **HighCPUUsage**: >80% for 10 minutes
- **DiskSpaceLow**: <10% free space remaining

#### Database (Critical)
- **DatabaseConnectionPoolExhausted**: <2 connections available
- **HighDatabaseQueryLatency**: p95 query time >1s

#### Cache (Warning/Critical)
- **RedisHighMemory**: >80% of 512MB
- **RedisDown**: Unreachable for 1 minute

#### Message Queue (Warning/Critical)
- **KafkaConsumerLagHigh**: >10k messages behind
- **KafkaConsumerLagCritical**: >100k messages behind

#### Multi-Tenancy (Info/Warning)
- **TenantRateLimitExceeded**: >100 limit hits/min
- **AITokenBudgetExceeded**: Quota usage >100%
- **AITokenBudgetCritical**: Quota usage >95%

#### Security
- **SSLCertExpiringSoon**: <14 days to expiry
- **SSLCertExpired**: Certificate already expired

#### Errors
- **HighExceptionRate**: >0.1 exceptions/sec
- **ValidationErrorSpike**: >1 validation error/sec

### Enabling Alertmanager

To route alerts to Slack, PagerDuty, or email:

```yaml
# In prometheus.yml, uncomment and configure:
alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

# Create /monitoring/prometheus/alertmanager.yml
global:
  resolve_timeout: 5m

route:
  receiver: 'default'
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h

receivers:
  - name: 'default'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#alerts'
        title: 'Priya Alert: {{ .GroupLabels.alertname }}'
```

## PromQL Query Examples

### Request Rate by Service
```promql
sum(rate(http_requests_total[5m])) by (service)
```

### Error Percentage
```promql
(sum(rate(http_requests_total{status=~"5.."}[5m])) /
 sum(rate(http_requests_total[5m]))) * 100
```

### Latency Percentiles
```promql
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (service, le))
```

### Top 10 Slowest Endpoints (p99)
```promql
topk(10, histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (endpoint, le)))
```

### Tenants Near Token Budget Limit
```promql
ai_token_budget_used_percent > 80
```

### Database Connection Pool Health
```promql
db_connections_available / (db_connections_available + db_connections_active)
```

### Kafka Lag per Consumer Group
```promql
kafka_consumer_lag{consumer_group="conversation-processor"}
```

### Active Conversations by Tenant
```promql
sum(active_conversations) by (tenant_id)
```

## Maintenance

### Backup Prometheus Data

```bash
# Prometheus stores data in prometheus_data volume
docker run --rm -v prometheus_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/prometheus-backup-$(date +%Y%m%d).tar.gz -C /data .
```

### Clean Old Metrics

Prometheus automatically removes data older than 30 days based on:
```yaml
command:
  - '--storage.tsdb.retention.time=30d'
```

To modify, update `docker-compose.yml` and restart:
```bash
docker compose up -d --force-recreate prometheus
```

### Reset Grafana

```bash
# Clear all dashboards and datasources
docker compose exec grafana grafana-cli admin reset-admin-password newpassword
docker volume rm grafana_data
docker compose up -d grafana
```

### Performance Tuning

For high-volume environments:

```yaml
# In prometheus.yml
global:
  scrape_interval: 30s        # Increase if needed
  evaluation_interval: 30s

# Reduce cardinality (unique label combinations)
# Example: Drop high-cardinality labels
metric_relabel_configs:
  - source_labels: [__name__]
    regex: http_requests_total
    target_label: endpoint
    replacement: "aggregated"
```

## Troubleshooting

### Prometheus not scraping targets

```bash
# Check targets in Prometheus UI
curl http://localhost:9090/api/v1/targets

# Check service metrics endpoint
curl http://localhost:9001/metrics

# View Prometheus logs
docker logs priya-prometheus
```

### High cardinality warnings

If you see "metric has high cardinality" warnings:

1. Identify the problematic metric:
   ```promql
   topk(10, count by (__name__) (count by (__name__, job, le, quantile) (rate(metric[5m]))))
   ```

2. Add metric relabel rules to drop unwanted labels
3. Consider using label limits:
   ```yaml
   # In prometheus.yml
   metric_relabel_configs:
     - source_labels: [__name__]
       regex: http_requests_total
       action: keep
   ```

### Grafana datasource connectivity

```bash
# Ensure Prometheus is healthy
docker compose exec prometheus wget -q -O- http://localhost:9090/-/healthy

# Verify Grafana can reach Prometheus
docker compose exec grafana curl http://prometheus:9090/api/v1/query
```

### Out of memory issues

If Prometheus uses too much memory:

1. Reduce retention time:
   ```bash
   docker compose down prometheus
   docker volume prune -f
   ```

2. Reduce scrape frequency or metric cardinality

3. Enable compression in remote write config

## Next Steps

1. **Add custom metrics** to each service (see Integration Guide)
2. **Configure Alertmanager** for notification routing
3. **Set up remote storage** (Thanos, Cortex) for long-term retention
4. **Create service-specific dashboards** for ops teams
5. **Implement SLO tracking** with custom metrics
6. **Add distributed tracing** integration (Jaeger, Zipkin)

## Files Created

```
monitoring/
├── prometheus/
│   ├── prometheus.yml          # Prometheus configuration (36+ services)
│   └── alerts.yml              # Alert rules (12 categories)
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── prometheus.yml  # Auto-provision Prometheus datasource
│   │   └── dashboards/
│   │       └── dashboard.yml   # Dashboard provisioning config
│   └── dashboards/
│       ├── platform-overview.json   # Main ops dashboard
│       └── tenant-analytics.json    # Per-tenant analytics
shared/monitoring/
└── metrics.py                  # Prometheus metrics module (shared)
```

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/grafana/)
- [prometheus_client Python Library](https://github.com/prometheus/client_python)
- [PromQL Query Language](https://prometheus.io/docs/prometheus/latest/querying/basics/)
