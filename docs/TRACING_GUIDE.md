# OpenTelemetry Distributed Tracing Guide

Priya Global Platform includes production-grade distributed tracing built on OpenTelemetry, enabling complete visibility into request flows across all 37 microservices.

## Architecture Overview

The tracing system consists of:

1. **Agents (in each service)**
   - OpenTelemetry SDK auto-instrumentation
   - Custom tenant-aware context propagation
   - Exception and error recording

2. **Collector (central hub)**
   - OpenTelemetry Collector with gRPC receiver
   - Tail-based sampling (100% for errors, configurable for success)
   - Batch processing and enrichment

3. **Storage & Visualization**
   - **Jaeger**: Long-term trace storage and UI (default)
   - **Grafana**: Dashboards and metrics correlation
   - **Prometheus**: Metrics for the Collector itself

## Quick Start

### 1. Start Tracing Infrastructure

```bash
cd monitoring
docker-compose -f docker-compose.tracing.yml up -d
```

This starts:
- OpenTelemetry Collector (ports 4317 gRPC, 4318 HTTP)
- Jaeger (UI at http://localhost:16686)
- Prometheus (UI at http://localhost:9090)
- Grafana (UI at http://localhost:3000, admin/admin)

### 2. Environment Variables

Configure services with these environment variables:

```bash
# OTLP Collector endpoint (required)
OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317

# Service metadata
OTEL_SERVICE_NAME=auth-service
OTEL_SERVICE_VERSION=1.0.0
ENVIRONMENT=production

# Sampling rate (0.0-1.0, default 0.01)
OTEL_SAMPLE_RATE=0.1
```

**Recommended sampling rates:**
- Development: 1.0 (trace everything)
- Staging: 0.1 (10% sampling)
- Production: 0.01 (1% sampling)

### 3. Verify Tracing is Working

1. Make a request to any service:
```bash
curl -H "x-tenant-id: tenant-123" http://localhost:9001/api/v1/auth/login
```

2. View trace in Jaeger:
   - Open http://localhost:16686
   - Select service "gateway" from dropdown
   - Click "Find Traces"
   - View full request flow across services

## Using Tracing in Your Code

### Automatic Tracing (No Code Changes)

All HTTP requests, database queries, Redis operations, and Kafka messages are **automatically traced**:

```python
# This is automatically traced:
response = await service_client.get("auth", "/api/v1/users")

# Trace context is automatically propagated to other services
```

### Manual Span Creation

#### Basic Span

```python
from shared.observability.tracing import get_tracer

tracer = get_tracer()

with tracer.start_as_current_span("process_payment") as span:
    span.set_attribute("amount", 100.50)
    span.set_attribute("currency", "USD")

    # Do work
    result = process_payment(amount=100.50)

    span.set_status(Status(StatusCode.OK))
```

#### Tenant-Aware Tracing

```python
from shared.observability.tracing import TenantTracer

tenant_tracer = TenantTracer(
    tenant_id="t_123",
    user_id="u_456"
)

# Automatically adds tenant_id and user_id to all spans
with tenant_tracer.trace_span("create_conversation"):
    conversation = create_conversation()
```

### Decorators for Common Operations

#### @trace_function

Trace any async function:

```python
from shared.observability.trace_decorators import trace_function

@trace_function
async def process_order(order_id: str):
    # Automatically traced, exceptions recorded
    return await db.fetch_order(order_id)

@trace_function(span_name="custom_name", attributes={"version": "2.0"})
async def complex_operation():
    pass
```

#### @trace_db_operation

Trace database operations:

```python
from shared.observability.trace_decorators import trace_db_operation

@trace_db_operation(db_system="postgres")
async def get_user_by_id(tenant_id: str, user_id: str):
    # Creates db.query span with operation type inferred from function name
    return await db.query("SELECT * FROM users WHERE id = ?", user_id)
```

#### @trace_cache_operation

Trace Redis/cache operations:

```python
from shared.observability.trace_decorators import trace_cache_operation

@trace_cache_operation(cache_system="redis")
async def get_user_session(session_id: str):
    # Creates cache.operation span
    return await redis.get(f"session:{session_id}")
```

#### @trace_external_call

Trace calls to external APIs:

```python
from shared.observability.trace_decorators import trace_external_call

@trace_external_call("stripe", "create_charge")
async def charge_customer(amount: float):
    # Creates external.stripe.create_charge span
    return stripe.Charge.create(amount=amount)

@trace_external_call("twilio", "send_sms")
async def send_sms(phone: str, message: str):
    pass
```

#### @trace_ai_inference

Trace AI model calls:

```python
from shared.observability.trace_decorators import trace_ai_inference

@trace_ai_inference("gpt-4", "completion")
async def generate_response(prompt: str, tokens: int = 150):
    # Creates ai.gpt-4.completion span with token count
    return await openai.ChatCompletion.create(
        model="gpt-4",
        prompt=prompt,
        max_tokens=tokens
    )
```

#### @trace_background_job

Trace background worker jobs:

```python
from shared.observability.trace_decorators import trace_background_job

@trace_background_job(queue="celery")
async def send_email(email_id: str):
    # Creates job.send_email span with queue context
    await send_email_impl(email_id)
```

### Context Management

#### Get Current Context

```python
from shared.observability.trace_context import get_current_context

ctx = get_current_context()
print(f"Trace ID: {ctx.trace_id}")
print(f"Tenant ID: {ctx.tenant_id}")
print(f"User ID: {ctx.user_id}")
```

#### Set Tenant Context

```python
from shared.observability.trace_context import set_tenant_context

# Called in middleware for each request
ctx = set_tenant_context(
    tenant_id=request.headers.get("x-tenant-id"),
    user_id=request.headers.get("x-user-id"),
    request_id=request.headers.get("x-request-id"),
)
```

#### Propagate Context Between Services

```python
from shared.observability.trace_context import inject_context_headers

# When calling another service:
headers = inject_context_headers()
response = await service_client.get("auth", "/api/users", headers=headers)

# The trace context is automatically propagated!
```

### Kafka Event Tracing

Events are automatically traced:

```python
from shared.events.event_bus import EventBus

event_bus = EventBus(service_name="auth")

# Publishing (automatically traced)
await event_bus.publish(
    event_type=EventType.USER_REGISTERED,
    tenant_id="t_123",
    data={"user_id": "u_456"}
)

# Consuming (automatically traced with continued trace)
async def handle_user_created(event):
    # This span is part of the original trace from the publisher
    await send_welcome_email(event["user_id"])

event_bus.subscribe(EventType.USER_REGISTERED, handle_user_created)
```

## Viewing Traces

### Jaeger UI

Open http://localhost:16686

#### Search for traces:

1. **By Service**: Select service from dropdown (e.g., "gateway")
2. **By Operation**: Select operation (e.g., "gateway.GET")
3. **By Tags**: Filter by tag
   - `tenant_id`: Traces for specific tenant
   - `user_id`: Traces for specific user
   - `error`: Traces with errors

#### Trace Details:

Click on a trace to see:
- **Span timeline**: Each service's contribution to latency
- **Span attributes**: Custom tags and context
- **Exceptions**: Full error details
- **Service dependencies**: How services called each other

### Grafana Dashboards

Grafana dashboards (if configured) show:
- Traces by service
- Error rates and latency percentiles
- Service dependency graph
- Correlation with metrics (CPU, memory, etc.)

## Sampling Strategies

### Error-Based Sampling

The system automatically samples 100% of traces with errors:

```yaml
# In otel-collector-config.yaml
policies:
  - name: error_spans
    type: status_code
    status_code:
      status_codes: [ERROR]
```

### Latency-Based Sampling

Sample slow requests (>1 second) at 100% to catch performance issues:

```yaml
policies:
  - name: slow_traces
    type: latency
    latency:
      threshold_ms: 1000
```

### Probabilistic Sampling

Sample normal traces at a fixed rate:

```yaml
policies:
  - name: probabilistic
    type: probabilistic
    probabilistic:
      sampling_percentage: 1  # 1% for production
```

### Adjust Sampling via Environment

```bash
# Development (trace everything)
OTEL_SAMPLE_RATE=1.0

# Staging (10% sampling)
OTEL_SAMPLE_RATE=0.1

# Production (1% sampling)
OTEL_SAMPLE_RATE=0.01
```

## Advanced Features

### Custom Span Attributes

```python
from shared.observability.tracing import set_span_attribute, record_span_exception

# Set attribute on current span
set_span_attribute("customer_type", "enterprise")
set_span_attribute("feature_flag", "new_checkout")

# Record exception
try:
    risky_operation()
except Exception as e:
    record_span_exception(e, "Failed during payment processing")
```

### Span Events

```python
from shared.observability.tracing import add_span_event

# Add event to current span
add_span_event("cache_miss", {"key": "user:123"})
```

### Baggage (Cross-Span Data)

Use baggage for data that should be visible across all spans in a trace:

```python
from opentelemetry.baggage import set_baggage, get_baggage

# Set baggage (visible to all downstream spans)
set_baggage("request_source", "mobile_app")

# Read baggage in downstream service
source = get_baggage("request_source")
```

## Production Deployment

### Memory and Performance

```yaml
# In otel-collector-config.yaml
processors:
  memory_limiter:
    limit_mib: 1024  # Memory limit
    spike_limit_mib: 256  # Spike buffer
    check_interval: 1s

  batch:
    max_queue_size: 2048  # Max spans queued
    max_export_batch_size: 512  # Batch size
    timeout: 5s  # Export timeout
```

### Tail Sampling for Cost Control

```yaml
# Sample 100% of errors (important!), 1% of success (cost control)
tail_sampling:
  policies:
    # Always sample errors (1-10% of traces usually)
    - name: error_spans
      type: status_code
      status_code:
        status_codes: [ERROR]

    # Sample 1% of successful traces
    - name: probabilistic_remainder
      type: probabilistic
      probabilistic:
        sampling_percentage: 1
```

### Alternative Backends

#### Replace Jaeger with Grafana Tempo

```yaml
exporters:
  otlp:
    endpoint: tempo:4317
    tls:
      insecure: true
```

#### Add Datadog Export

```yaml
exporters:
  datadog:
    api:
      endpoint: https://api.datadoghq.com/api/v2/spans
      key: ${DATADOG_API_KEY}
    host_metadata: true
```

## Troubleshooting

### No traces appearing in Jaeger

1. Check collector is running: `docker ps | grep otel-collector`
2. Check logs: `docker logs priya-otel-collector`
3. Verify endpoint: `OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317`
4. Test connectivity: `curl localhost:4317` (should fail but should connect)

### High memory usage in collector

- Reduce `limit_mib` in memory_limiter processor
- Reduce `sampling_percentage` for probabilistic sampling
- Check for infinite loops in span creation

### Traces not appearing in logs

- Verify `OTEL_EXPORTER_OTLP_ENDPOINT` is accessible
- Check trace sample rate isn't too low
- Verify service is importing `TracingMiddleware`

### Missing tenant context

- Ensure `TracingMiddleware` is added to FastAPI app
- Check `x-tenant-id` header is being sent in requests
- Verify `set_tenant_context()` is called in your middleware

## Best Practices

### 1. Always Use Tenant Context

```python
# Good: Tenant context for all operations
set_tenant_context(tenant_id="t_123")

# Bad: No tenant context, hard to debug tenant-specific issues
operation()
```

### 2. Use Meaningful Span Names

```python
# Good: Action-based names
"process_payment", "fetch_user", "send_email"

# Bad: Generic names
"operation", "do_work", "execute"
```

### 3. Add Custom Attributes for Business Context

```python
# Good: Business context
set_span_attribute("payment_method", "credit_card")
set_span_attribute("amount", 99.99)
set_span_attribute("feature_flag", "beta_checkout")

# Bad: Only technical details
set_span_attribute("duration_ms", 123)
```

### 4. Use Decorators for Consistency

```python
# Good: Decorators ensure consistent tracing
@trace_function
async def process_order(order_id: str):
    pass

# Bad: Manual span management is error-prone
with tracer.start_as_current_span("process_order"):
    # Many things can go wrong here
```

### 5. Log Important Events

```python
# Good: Add event for important state changes
add_span_event("payment_approved", {"transaction_id": "txn_123"})
add_span_event("order_shipped", {"tracking_id": "track_456"})

# Bad: Only relying on logs
logger.info("Payment approved")
```

## File Structure

```
shared/observability/
├── tracing.py                 # Core OpenTelemetry setup (500 lines)
├── trace_decorators.py        # Convenient decorators (200 lines)
├── trace_context.py           # Tenant-aware context (150 lines)
└── __init__.py

monitoring/
├── otel-collector/
│   └── otel-collector-config.yaml  # Collector configuration
├── docker-compose.tracing.yml      # Infrastructure stack
├── prometheus/
├── grafana/
└── loki/ (optional)
```

## Integration with Existing Monitoring

### With Prometheus Metrics

Tracing is complementary to metrics:
- **Metrics**: Aggregate trends (error rate, latency p99)
- **Tracing**: Individual request flows (why was this slow?)

### With Sentry Error Tracking

Both are included:
- **Sentry**: Error alerting and reproduction
- **Tracing**: Complete request context for errors

### With Application Logs

Use trace IDs in logs for correlation:

```python
# Log includes trace ID for correlation
logger.info(
    "Processing order",
    extra={
        "trace_id": get_current_context().trace_id,
        "order_id": order_id,
    }
)

# Find logs for a trace: search logs with trace ID from Jaeger
```

## Further Reading

- [OpenTelemetry Documentation](https://opentelemetry.io/)
- [Jaeger Getting Started](https://www.jaegertracing.io/docs/getting-started/)
- [W3C Trace Context](https://w3c.github.io/trace-context/)
