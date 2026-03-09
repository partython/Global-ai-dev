# Priya Global Monitoring Stack

Complete Prometheus + Grafana monitoring solution for the Priya Global platform with 41+ microservices.

## Overview

This monitoring stack provides:

- **Prometheus**: Time-series metrics collection and alerting (port 9090)
- **Grafana**: Visualization and dashboards (port 3001)
- **AlertManager**: Alert routing and notifications (port 9093)
- **Node Exporter**: Host system metrics (port 9100)
- **PostgreSQL Exporter**: Database metrics (port 9187)
- **Redis Exporter**: Cache metrics (port 9121)
- **Grafana Renderer**: Dashboard image rendering

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│         Priya Global Microservices (41 services)       │
│         Each service: /metrics endpoint @ 9000-9043    │
└────────────┬────────────────────────────────────────────┘
             │
             ├─────────────────────┬──────────────────────┐
             ▼                     ▼                      ▼
        ┌─────────┐          ┌──────────┐        ┌───────────┐
        │Prometheus│          │AlertManager│      │ Exporters │
        │ (9090)  │          │ (9093)    │      │(9100,9121,│
        │         │          │           │      │ 9187)     │
        └────┬────┘          └─────┬─────┘      └─────┬─────┘
             │                     │                   │
             └─────────────────────┼───────────────────┘
                                   ▼
                            ┌──────────────┐
                            │   Grafana    │
                            │  (3001)      │
                            │              │
                            │ - Dashboards │
                            │ - Alerts     │
                            │ - Datasources│
                            └──────────────┘
```

## Quick Start

### 1. Start the Monitoring Stack

```bash
# From project root
docker-compose -f docker-compose.yml -f infrastructure/monitoring/docker-compose.monitoring.yml up -d prometheus grafana alertmanager node-exporter redis-exporter postgres-exporter grafana-renderer
```

### 2. Verify Services

```bash
# Check all monitoring containers are running
docker-compose -f docker-compose.yml -f infrastructure/monitoring/docker-compose.monitoring.yml ps

# Expected output:
# priya-prometheus    Up (healthy)
# priya-grafana       Up (healthy)
# priya-alertmanager  Up (healthy)
# priya-node-exporter Up (healthy)
# priya-redis-exporter Up (healthy)
# priya-postgres-exporter Up (healthy)
# priya-grafana-renderer Up (healthy)
```

### 3. Access Dashboards

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3001
  - Default credentials: admin / priya_grafana_2024
- **AlertManager**: http://localhost:9093

## Integration with Services

### Adding Metrics to a Service

Each microservice needs to:

1. **Install prometheus-client**:
   ```bash
   pip install prometheus-client
   ```

2. **Add middleware to FastAPI app**:
   ```python
   from fastapi import FastAPI
   from shared.middleware.metrics import PrometheusMiddleware, setup_metrics_routes

   app = FastAPI(title="My Service")

   # Add metrics middleware (order matters - before other middleware)
   app.add_middleware(
       PrometheusMiddleware,
       app_name="my-service"  # Service name for labels
   )

   # Setup /metrics endpoint
   setup_metrics_routes(app)
   ```

3. **Record custom metrics**:
   ```python
   from shared.middleware.metrics import record_message_processed, record_ai_inference

   # Record a processed message
   record_message_processed("my-service", "whatsapp", "success")

   # Record AI inference with timing
   from shared.middleware.metrics import time_ai_inference
   async with time_ai_inference("ai-engine", "gpt-3.5-turbo"):
       # perform inference
       result = await model.infer(prompt)
   ```

4. **Update prometheus.yml**:
   - The configuration already includes all 41 services (ports 9000-9043)
   - Services are auto-discovered when they start

### Available Custom Metrics

```python
from shared.middleware.metrics import (
    # Conversation metrics
    set_active_conversations,
    record_message_processed,
    record_conversation_completed,

    # Database metrics
    record_db_query,
    record_db_connection_count,

    # Cache metrics
    record_cache_hit,
    record_cache_miss,

    # AI metrics
    record_ai_inference,

    # Rate limiting
    set_rate_limit_remaining,

    # Kafka/messaging
    record_kafka_consumer_lag,

    # SSL certificates
    record_ssl_cert_expiry,

    # Context managers for timing
    time_db_operation,
    time_ai_inference,
)
```

## Metrics Collected

### Automatic HTTP Metrics (all services)

- `http_requests_total`: Total requests by method, endpoint, status
- `http_request_duration_seconds`: Request latency histogram
- `http_requests_in_progress`: Currently processing requests
- `http_request_size_bytes`: Request body size
- `http_response_size_bytes`: Response body size

### Infrastructure Metrics

- **Node Exporter** (host system):
  - CPU usage, memory, disk, network I/O
  - System load, filesystem usage
  - Process metrics

- **PostgreSQL Exporter** (database):
  - Connection count and status
  - Query performance
  - Index usage, table sizes
  - WAL metrics

- **Redis Exporter** (cache):
  - Memory usage and hit rate
  - Key evictions
  - Command latency
  - Persistence metrics

### Recording Rules

Pre-computed metrics for better dashboard performance:

- Per-service request rates
- Per-service error rates
- Latency percentiles (P50, P95, P99)
- Resource utilization (CPU, memory, disk)
- Database and cache efficiency metrics
- AI inference metrics

See `prometheus/recording_rules.yml` for complete list.

## Alert Rules

Configured alerts with auto-remediation suggestions:

### Service Health
- Service down (> 1 minute)
- Multiple services down
- High error rate (> 5% 5xx)
- Critical error rate (> 10% 5xx)

### Performance
- High P99 latency (> 2s)
- Critical P99 latency (> 5s)
- Slow queries detected

### Infrastructure
- High memory usage (> 80%, critical > 90%)
- High CPU usage (> 80%, critical > 90%)
- High disk usage (> 85%, critical > 95%)

### Database
- PostgreSQL down
- Connection pool exhaustion
- Slow queries

### Cache
- Redis down
- High memory usage
- Evictions occurring
- Low hit rate

### Messaging
- High Kafka consumer lag
- Consumer lag critical

### Security
- SSL certificate expiring soon (< 14 days)
- SSL certificate critical (< 7 days)

### Rate Limiting
- Rate limit exhaustion
- Request queue building up

See `prometheus/alert_rules.yml` for complete definitions.

## Dashboard Panels

The included Grafana dashboard provides:

1. **Service Health Matrix**: Grid showing status of all 41 services
2. **Request Rate**: Requests per second across all services
3. **Error Rate**: 5xx error percentage by service
4. **Latency**: P99 and P95 latency trends
5. **Active Conversations**: Real-time active conversation gauge
6. **Message Throughput**: Messages processed per second
7. **AI Engine Latency**: P99 inference latency
8. **Database Connections**: Active and max connections
9. **Redis Hit Rate**: Cache efficiency trend
10. **Top 10 Slowest Endpoints**: Table of slowest API routes

## Configuration Files

```
infrastructure/monitoring/
├── docker-compose.monitoring.yml     # Container definitions
├── prometheus/
│   ├── prometheus.yml               # Scrape configs for all services
│   ├── alert_rules.yml              # Alert definitions
│   └── recording_rules.yml          # Pre-computed metric rules
├── alertmanager/
│   └── alertmanager.yml             # Alert routing and notifications
└── grafana/
    ├── provisioning/
    │   ├── datasources/
    │   │   └── datasource.yml       # Prometheus datasource config
    │   └── dashboards/
    │       └── dashboard.yml        # Dashboard provisioning
    └── dashboards/
        └── priya-global-overview.json # Main dashboard
```

## Troubleshooting

### Prometheus not scraping services

1. Check service is running: `curl localhost:9000/metrics`
2. Check prometheus logs: `docker logs priya-prometheus`
3. Verify service name matches `prometheus.yml`
4. Check firewall/networking between containers

### Grafana dashboard shows no data

1. Check Prometheus datasource: Home > Configuration > Data Sources
2. Verify metrics exist: Visit http://localhost:9090/graph
3. Check dashboard queries: Edit panel > Inspect > Queries
4. Verify service metrics endpoint: `curl localhost:9000/metrics`

### Alerts not firing

1. Check AlertManager logs: `docker logs priya-alertmanager`
2. Verify alert rules loaded: http://localhost:9090/alerts
3. Check alert conditions in expressions
4. Verify notification channel configured in alertmanager.yml

### High Prometheus disk usage

1. Reduce retention: Edit `docker-compose.monitoring.yml`
   ```yaml
   - "--storage.tsdb.retention.time=7d"  # Reduce from 30d
   ```
2. Downsample old data
3. Rebuild storage: Stop Prometheus, delete `prometheus_data` volume, restart

## Performance Tuning

### Reducing metrics cardinality

High cardinality (many unique label combinations) can slow Prometheus.

1. Review endpoint labels in middleware
2. Use metric relabeling to drop unnecessary metrics
3. Limit dynamic labels (e.g., customer_id, request_id)

### Improving query performance

1. Use recording rules for complex queries
2. Increase Prometheus memory: `docker-compose.monitoring.yml`
   ```yaml
   environment:
     GOGC: 75  # Garbage collection target
   ```
3. Optimize scrape intervals: balance freshness vs overhead

### Grafana optimization

1. Increase query timeout in datasource config
2. Reduce dashboard refresh rate
3. Use recording rules instead of raw metrics
4. Limit table query results

## Alerting Channels

To receive alerts, configure notification channels in `alertmanager.yml`:

### Slack

```yaml
global:
  slack_api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'

receivers:
  - name: 'default'
    slack_configs:
      - channel: '#alerts'
```

### PagerDuty

```yaml
global:
  pagerduty_url: 'https://events.pagerduty.com/v2/enqueue'

receivers:
  - name: 'critical'
    pagerduty_configs:
      - service_key: 'YOUR_SERVICE_KEY'
```

### Email

```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_auth_username: 'your-email@gmail.com'
  smtp_auth_password: 'app-password'
  smtp_from: 'alerts@priya-global.com'

receivers:
  - name: 'default'
    email_configs:
      - to: 'ops@priya-global.com'
```

## API Reference

### Query Prometheus

```bash
# Get all metrics
curl "http://localhost:9090/api/v1/query?query=up"

# Query time range
curl "http://localhost:9090/api/v1/query_range?query=http_requests_total&start=1609459200&end=1609545600&step=300"
```

### Manage Alerts

```bash
# Get active alerts
curl "http://localhost:9090/api/v1/alerts"

# Get recording rules
curl "http://localhost:9090/api/v1/rules"
```

## Maintenance

### Backup Metrics Data

```bash
# Backup Prometheus data
docker cp priya-prometheus:/prometheus ./prometheus_backup_$(date +%Y%m%d)
```

### Update Grafana Dashboards

1. Make changes in Grafana UI
2. Export dashboard JSON
3. Update `priya-global-overview.json`
4. Restart: `docker-compose restart grafana`

### Monitor Storage

```bash
# Check Prometheus storage usage
docker exec priya-prometheus du -sh /prometheus

# Check Grafana storage
docker exec priya-grafana du -sh /var/lib/grafana
```

## Security

### Enable Authentication

```yaml
# grafana/provisioning/datasources/datasource.yml
- name: Prometheus
  basicAuth: true
  basicAuthUser: prometheus
  basicAuthPassword: ${PROMETHEUS_PASSWORD}
```

### Use TLS

```yaml
# docker-compose.monitoring.yml
prometheus:
  volumes:
    - ./certs/prometheus.crt:/etc/prometheus/prometheus.crt
    - ./certs/prometheus.key:/etc/prometheus/prometheus.key
```

### Restrict Access

```bash
# Only allow from monitoring network
docker network create monitoring --internal
```

## Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [prometheus-client Python](https://github.com/prometheus/client_python)
- [Monitoring Best Practices](https://prometheus.io/docs/practices/naming/)

## Support

For issues or questions about the monitoring stack:

1. Check logs: `docker logs priya-prometheus`
2. Review metrics: http://localhost:9090
3. Check dashboards: http://localhost:3001
4. Test alerts: http://localhost:9090/alerts

## License

Part of Priya Global Platform - See main repository LICENSE
