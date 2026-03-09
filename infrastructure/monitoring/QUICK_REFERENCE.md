# Monitoring Stack - Quick Reference

## Start/Stop Commands

```bash
# Start monitoring stack
docker-compose -f docker-compose.yml \
  -f infrastructure/monitoring/docker-compose.monitoring.yml \
  up -d

# Stop monitoring stack
docker-compose -f docker-compose.yml \
  -f infrastructure/monitoring/docker-compose.monitoring.yml \
  down

# Restart specific service
docker-compose -f docker-compose.yml \
  -f infrastructure/monitoring/docker-compose.monitoring.yml \
  restart prometheus

# View logs
docker logs priya-prometheus
docker logs priya-grafana
docker logs priya-alertmanager
```

## Access Points

| Service | URL | Default Credentials |
|---------|-----|-------------------|
| Prometheus | http://localhost:9090 | None (no auth) |
| Grafana | http://localhost:3001 | admin / priya_grafana_2024 |
| AlertManager | http://localhost:9093 | None (no auth) |
| Node Exporter | http://localhost:9100/metrics | Metrics only |
| PostgreSQL Exporter | http://localhost:9187/metrics | Metrics only |
| Redis Exporter | http://localhost:9121/metrics | Metrics only |

## Key Prometheus Queries

### Service Health
```promql
# All services status
up{job!="prometheus"}

# Specific service
up{job="gateway"}

# Services down
up == 0
```

### Request Metrics
```promql
# Total RPS
sum(rate(http_requests_total[5m]))

# By service
sum by (job) (rate(http_requests_total[5m]))

# Error rate
sum by (job) (rate(http_requests_total{status_code=~"5.."}[5m])) / sum by (job) (rate(http_requests_total[5m]))
```

### Latency
```promql
# P99 latency (all services)
histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))

# P99 by service
histogram_quantile(0.99, sum by (job, le) (rate(http_request_duration_seconds_bucket[5m])))
```

### Database
```promql
# Active connections
pg_stat_activity_count

# Connection pool usage
(pg_stat_activity_count / pg_settings_max_connections) * 100

# Query latency
histogram_quantile(0.99, sum by (le) (rate(db_query_duration_seconds_bucket[5m])))
```

### Cache
```promql
# Hit rate
(redis_keyspace_hits_total / (redis_keyspace_hits_total + redis_keyspace_misses_total)) * 100

# Memory usage
(redis_memory_used_bytes / redis_memory_max_bytes) * 100
```

## Common Issues

### Metrics Not Appearing
1. Service running? `docker ps | grep service-name`
2. Metrics endpoint? `curl localhost:9000/metrics`
3. Check Prometheus: http://localhost:9090/targets
4. Check logs: `docker logs priya-prometheus`

### High Memory Usage
1. Check retention: `docker exec priya-prometheus du -sh /prometheus`
2. Reduce retention time in docker-compose.monitoring.yml
3. Restart Prometheus: `docker restart priya-prometheus`

### No Alerts Firing
1. Check alert rules: http://localhost:9090/alerts
2. Check AlertManager status: http://localhost:9093
3. Verify webhook URL in .env
4. Test Slack webhook: `curl -X POST <WEBHOOK_URL>`

### Grafana Dashboard Blank
1. Verify datasource: Configuration > Data Sources > Prometheus
2. Check metrics exist: http://localhost:9090/graph
3. Review dashboard query: Edit panel > Query
4. Check time range selector (top right)

## Docker Commands

```bash
# View containers status
docker-compose -f docker-compose.yml \
  -f infrastructure/monitoring/docker-compose.monitoring.yml \
  ps

# View service logs
docker logs priya-prometheus
docker logs priya-grafana
docker logs priya-alertmanager

# Restart service
docker-compose -f docker-compose.yml \
  -f infrastructure/monitoring/docker-compose.monitoring.yml \
  restart prometheus

# Remove volumes and restart fresh
docker volume rm priya_prometheus_data
docker-compose -f docker-compose.yml \
  -f infrastructure/monitoring/docker-compose.monitoring.yml \
  up -d prometheus

# Check container health
docker ps --format "table {{.Names}}\t{{.Status}}"
```

## Useful Links

| Resource | URL |
|----------|-----|
| Prometheus Targets | http://localhost:9090/targets |
| Prometheus Graph | http://localhost:9090/graph |
| Prometheus Alerts | http://localhost:9090/alerts |
| Prometheus Rules | http://localhost:9090/rules |
| Prometheus Status | http://localhost:9090/status |
| AlertManager UI | http://localhost:9093 |
| Grafana Dashboards | http://localhost:3001/d |
| Grafana Data Sources | http://localhost:3001/datasources |

## Monitoring Checklist

- [ ] All containers healthy: `docker ps`
- [ ] Prometheus scraping targets: http://localhost:9090/targets
- [ ] Services exporting metrics: `curl localhost:9000/metrics`
- [ ] Grafana dashboard loads: http://localhost:3001/d/priya-overview
- [ ] Alert rules loaded: http://localhost:9090/alerts
- [ ] AlertManager configured: http://localhost:9093
- [ ] Notification channel tested: Check #alerts Slack channel
- [ ] Disk space available: `df -h`

## Integration Checklist (per service)

For each microservice (gateway, auth, tenant, etc.):

- [ ] Import metrics middleware: `from shared.middleware.metrics import PrometheusMiddleware, setup_metrics_routes`
- [ ] Add middleware to app: `app.add_middleware(PrometheusMiddleware, app_name="service-name")`
- [ ] Setup routes: `setup_metrics_routes(app)`
- [ ] Verify metrics: `curl localhost:9000/metrics | grep http_requests_total`
- [ ] Check Prometheus targets: http://localhost:9090/targets

## Key Metrics to Monitor

| Metric | Threshold | Action |
|--------|-----------|--------|
| up (service down) | 0 | Page on-call |
| Error rate (5xx) | >5% | Check logs, rollback if needed |
| P99 latency | >2s | Investigate slow endpoints |
| Memory usage | >80% | Increase capacity or optimize |
| CPU usage | >80% | Investigate hot spots |
| DB connections | >80% of max | Increase pool or add connections |
| Redis hit rate | <70% | Optimize cache strategy |
| Kafka lag | >10k messages | Scale consumers |

## Alert Severity Levels

- **Critical** (🔴): Page on-call immediately, P1 incident
- **Warning** (🟡): Monitor closely, may need action within hours
- **Info** (🔵): Tracking info, no immediate action needed

## Performance Baseline

Target metrics for healthy system:

```
Request Rate:        100-1000 req/sec
Error Rate:          <0.5%
P99 Latency:         <500ms
Active Connections:  10-50
Memory Usage:        30-50%
CPU Usage:           20-40%
Cache Hit Rate:      >90%
Database Query Time: <100ms (p99)
```

## Troubleshooting Flowchart

```
Issue: No metrics appearing
├─ Is service running?
│  ├─ Yes → Check /metrics endpoint
│  │        ├─ Returns data → Check Prometheus targets
│  │        └─ 404 → Add PrometheusMiddleware to service
│  └─ No → Start service in docker-compose
└─ Still not working → Check prometheus logs

Issue: Alerts not firing
├─ Is AlertManager healthy?
│  ├─ No → Restart AlertManager
│  └─ Yes → Check alert rules at /alerts
│           ├─ Rules exist → Check alert conditions
│           └─ Rules missing → Restart Prometheus
└─ Check notification channel configured

Issue: Dashboard slow
├─ Check query complexity
├─ Use recording rules instead
├─ Reduce time range
└─ Increase Prometheus memory

Issue: High disk usage
├─ Check retention time (should be 30d)
├─ Reduce metrics cardinality
├─ Delete old data: docker volume rm prometheus_data
└─ Restart Prometheus
```

## Useful Prometheus Functions

```promql
# Rate of increase
rate(metric[5m])

# Total increase
increase(metric[5m])

# Percentile
histogram_quantile(0.99, metric_bucket)

# Sum
sum(metric)

# Sum by label
sum by (job) (metric)

# Count
count(metric)

# Count by label
count by (job) (metric)

# Top K
topk(10, metric)

# Filter by label
metric{job="service"}

# Combine conditions
metric{job="service", status_code=~"5.."}
```

## Recording Rules Available

```promql
instance:http_requests_rate:per_service
instance:http_error_rate:5xx_per_service
instance:http_request_duration:p99_per_service
instance:http_request_duration:p95_per_service
instance:postgres_connection_pool_usage:percent
instance:redis_hit_rate:percent
instance:memory_usage_ratio:percent
instance:cpu_usage_ratio:percent
instance:disk_usage_ratio:percent
```

These are pre-computed and fast for dashboard queries.

## Environment Variables

```bash
# Set in infrastructure/monitoring/.env

GRAFANA_PASSWORD=priya_grafana_2024
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
PAGERDUTY_SERVICE_KEY=...
PROMETHEUS_RETENTION_TIME=30d
```

## Documentation Links

- **README.md**: Comprehensive guide (600+ lines)
- **INTEGRATION_GUIDE.md**: Step-by-step integration (500+ lines)
- **MONITORING_STACK_COMPLETE.md**: Full implementation details
- **prometheus/alert_rules.yml**: All alert definitions with descriptions
- **prometheus/recording_rules.yml**: All pre-computed metrics

## Support

For detailed help:
1. Check README.md troubleshooting section
2. Review INTEGRATION_GUIDE.md for setup issues
3. Inspect logs: `docker logs priya-prometheus`
4. Query Prometheus UI: http://localhost:9090
5. Check AlertManager status: http://localhost:9093

---

**Last Updated**: 2026-03-07
**Stack Version**: 1.0
**Status**: Production Ready
