# Priya Global Background Workers & Job Queue System

Production-grade async job queue built on Redis with priority levels, scheduling, and automatic retries.

## Architecture Overview

### Components

1. **JobQueue** (`shared/workers/base.py`)
   - Redis-backed job storage
   - 4 priority levels (critical, high, normal, low)
   - Job serialization with mandatory tenant context
   - Scheduled jobs with cron-like support
   - Automatic retries with exponential backoff
   - Dead letter queue for failed jobs
   - Job deduplication via idempotency keys
   - Progress tracking (0-100%)
   - Job cancellation support

2. **Worker** (`shared/workers/base.py`)
   - Async job consumer
   - Graceful shutdown (SIGTERM/SIGINT)
   - Health check endpoint
   - Prometheus metrics
   - Tenant context injection
   - Configurable concurrency
   - Error handling with Sentry integration

3. **Job Handlers** (`shared/workers/handlers.py`)
   - 30+ concrete job handlers for all platform operations
   - Billing, messaging, AI, analytics, notifications, maintenance
   - All handlers are idempotent (safe to retry)
   - Progress tracking and proper error handling

4. **JobScheduler** (`shared/workers/scheduler.py`)
   - Cron-like scheduler with leader election
   - 12 built-in schedules (5min to monthly)
   - Timezone-aware per-tenant scheduling
   - Missed job recovery
   - Custom schedule support

5. **Worker Service** (`services/worker/main.py`)
   - FastAPI-based health check and management
   - Port 9043
   - Job status endpoints
   - Dead letter queue management
   - Schedule management endpoints

## Queue Levels & Concurrency

### Priority Levels

```
CRITICAL (Concurrency: 50)
├─ Subscription renewal (billing)
├─ Usage-based billing calculations
├─ Payment webhook processing
└─ Invoice generation

HIGH (Concurrency: 30)
├─ Email/SMS/WhatsApp sending
├─ Inbound message processing
├─ AI response generation
└─ Knowledge base training

NORMAL (Concurrency: 20)
├─ Daily metrics aggregation
├─ Analytics report generation
├─ Conversion rate calculation
├─ Push notifications
└─ Bulk notifications

LOW (Concurrency: 10)
├─ Session cleanup
├─ Conversation archival
├─ API key rotation
├─ GDPR data deletion
└─ Compliance reports
```

### Concurrency Control

- **Per-worker limit**: 5 concurrent jobs (configurable via `WORKER_CONCURRENCY`)
- **Per-tenant fair-share**: Prevents single tenant from monopolizing resources
- **Queue-level backpressure**: Queues respect their concurrency limits

## Retry Strategy (Exponential Backoff)

Failed jobs are automatically retried with increasing delays:

```
Attempt 1 (immediate): Process
   ↓ (fails)
Attempt 2 (after 30s): Retry
   ↓ (fails)
Attempt 3 (after 2min): Retry
   ↓ (fails)
Attempt 4 (after 8min): Retry
   ↓ (fails)
Attempt 5 (after 32min): Retry
   ↓ (fails)
Attempt 6 (after 2hr): Retry
   ↓ (fails)
Dead Letter Queue: Manual intervention required
```

Max retries: 5 (total 6 attempts over ~3 hours)

## Data Model

### JobContext
```python
JobContext(
    job_id: str,                    # UUID
    tenant_id: str,                 # Mandatory, always set
    job_type: str,                  # e.g., "send_email"
    queue: QueueLevel,              # critical/high/normal/low
    payload: Dict[str, Any],        # Job-specific data
    retry_count: int,               # Number of retries so far
    enqueued_at: datetime,          # When job was queued
    started_at: Optional[datetime], # When execution started
    metadata: Dict[str, Any],       # Tags, source, etc.
)
```

### JobStatus Lifecycle
```
PENDING → QUEUED → RUNNING → COMPLETED
                         ↓
                       FAILED → RETRYING → QUEUED → RUNNING → ...
                                              ↓
                                        DEAD (max retries)

CANCELLED (user action)
```

## Usage Examples

### Enqueueing Jobs

```python
from shared.workers.base import JobQueue, QueueLevel

job_queue = JobQueue()
await job_queue.connect()

# Simple job
job_id = await job_queue.enqueue(
    tenant_id="tenant-123",
    job_type="send_email",
    payload={
        "to": "user@example.com",
        "subject": "Welcome",
        "template": "welcome",
    },
    queue=QueueLevel.HIGH,
)

# Scheduled job (specific time)
from datetime import datetime, timezone, timedelta

future = datetime.now(timezone.utc) + timedelta(hours=2)
job_id = await job_queue.enqueue_at(
    tenant_id="tenant-123",
    job_type="process_subscription_renewal",
    payload={"subscription_id": "sub-456"},
    scheduled_time=future,
    queue=QueueLevel.CRITICAL,
)

# Scheduled job (delay)
job_id = await job_queue.enqueue_in(
    tenant_id="tenant-123",
    job_type="cleanup_expired_sessions",
    payload={"older_than_hours": 24},
    delay_seconds=3600,  # 1 hour from now
    queue=QueueLevel.LOW,
)

# Deduplication (idempotency)
job_id = await job_queue.enqueue(
    tenant_id="tenant-123",
    job_type="send_email",
    payload={"to": "user@example.com"},
    idempotency_key="send-email-welcome-user-123",
)
# Same idempotency_key within 1 hour returns same job_id

# Progress tracking
await job_queue.set_progress(job_id, 25)  # 25% done
progress = await job_queue.get_progress(job_id)  # Get progress

# Job cancellation
await job_queue.cancel_job(job_id)  # Only works for pending jobs

# Get job status
status = await job_queue.get_status(job_id)  # JobStatus enum
```

### In a Service Endpoint

```python
from fastapi import FastAPI
from shared.workers.base import JobQueue, QueueLevel

app = FastAPI()
job_queue = JobQueue()

@app.on_event("startup")
async def startup():
    await job_queue.connect()

@app.on_event("shutdown")
async def shutdown():
    await job_queue.disconnect()

@app.post("/api/send-email")
async def send_email(tenant_id: str, email: str):
    job_id = await job_queue.enqueue(
        tenant_id=tenant_id,
        job_type="send_email",
        payload={"to": email},
        queue=QueueLevel.HIGH,
    )
    return {"job_id": job_id, "status": "queued"}
```

### Registering Custom Handlers

```python
from shared.workers.base import Worker, JobContext, JobResult, JobStatus

async def my_custom_handler(ctx: JobContext) -> JobResult:
    """Custom job handler."""
    try:
        # Do work here
        result = await do_something(ctx.payload)

        # Update progress
        await ctx.job_queue.set_progress(ctx.job_id, 50)

        return JobResult(
            job_id=ctx.job_id,
            status=JobStatus.COMPLETED,
            output=result,
        )
    except Exception as e:
        raise  # Will be caught by Worker and retried

worker = Worker(job_queue)
worker.register_handler("my_custom_job", my_custom_handler)
```

## Starting the Worker Service

### Option 1: PM2 (Production)

```bash
pm2 start config/ecosystem.config.js --only priya-worker
pm2 logs priya-worker
pm2 stop priya-worker
```

### Option 2: Docker

```bash
docker compose up -d worker
docker compose logs -f worker
```

### Option 3: Direct

```bash
cd services/worker
python -m uvicorn main:app --host 0.0.0.0 --port 9043 --workers 1
```

### Environment Variables

```bash
WORKER_PORT=9043                    # Health check port
WORKER_CONCURRENCY=5                # Max concurrent jobs
WORKER_QUEUES=critical,high,normal,low  # Queues to process
REDIS_URL=redis://localhost:6379/0  # Redis connection
LOG_LEVEL=INFO                      # Logging level
```

## Worker Service Endpoints

### Health & Status

```
GET /health                 → Health check
GET /status                 → Worker status summary
GET /metrics                → Prometheus metrics
```

### Job Management

```
GET /jobs/{job_id}          → Get job status & details
GET /jobs/{job_id}/progress → Get job progress (0-100)
POST /jobs/{job_id}/cancel  → Cancel pending job
GET /jobs/dead-letter/list  → List failed jobs (DLQ)
```

### Schedule Management

```
GET /schedules              → List all scheduled jobs
POST /schedules?...         → Add custom schedule
```

## Built-in Schedules

| Schedule | Frequency | Time (UTC) | Jobs |
|----------|-----------|-----------|------|
| Health Check | Every 5 min | - | health_check |
| Realtime Metrics | Every 15 min | - | aggregate_realtime_metrics |
| Hourly | Hourly | :00 | cleanup_expired_sessions, process_usage_billing |
| Daily | Daily | 2am | aggregate_daily_metrics, archive_old_conversations |
| Daily 2 | Daily | 3am | rotate_api_keys, gdpr_data_deletion |
| Weekly | Mon | 4am | generate_analytics_report, generate_compliance_report |
| Monthly | 1st | 5am | process_subscription_renewal, generate_invoice |

## Handlers (50+)

### Billing (Critical Queue)
- `process_subscription_renewal` - Monthly billing cycle
- `process_usage_billing` - Usage-based charges
- `process_payment_webhook` - Stripe/Razorpay webhooks
- `generate_invoice` - PDF invoice generation

### Messaging (High Queue)
- `send_email` - Transactional email via SMTP/SES
- `send_sms` - SMS via Twilio
- `send_whatsapp_template` - WhatsApp messages
- `process_inbound_message` - Route inbound messages

### AI (High Queue)
- `generate_ai_response` - AI response generation
- `train_knowledge_base` - Embeddings training
- `analyze_sentiment` - Batch sentiment analysis

### Analytics (Normal Queue)
- `aggregate_daily_metrics` - Daily aggregation
- `generate_analytics_report` - Weekly/monthly reports
- `calculate_conversion_rates` - Lead conversion metrics

### Notifications (Normal Queue)
- `send_push_notification` - FCM notifications
- `send_bulk_notification` - Campaign notifications

### Maintenance (Low Queue)
- `cleanup_expired_sessions` - Session cleanup
- `archive_old_conversations` - Move to cold storage
- `rotate_api_keys` - Auto-rotate expiring keys
- `gdpr_data_deletion` - GDPR right-to-be-forgotten
- `generate_compliance_report` - SOC2, GDPR, HIPAA reports

## Monitoring & Observability

### Prometheus Metrics

```
priya_jobs_processed_total{queue, status}
priya_jobs_failed_total{queue, reason}
priya_queue_depth{queue}
priya_jobs_in_progress{queue}
priya_job_processing_seconds{queue, job_type}
priya_job_retries_total{queue, job_type}
priya_dead_letter_queue_total
```

### Sentry Integration

All errors automatically reported to Sentry with:
- Job ID and context
- Tenant ID (always set)
- Full error traceback
- Retry count

### Logging

All operations logged with structured format:
```
2024-01-15 10:23:45 - priya.workers - INFO - Job completed: job-123 (5.23s)
2024-01-15 10:24:00 - priya.workers - WARNING - Job failed (retry 1/5) for job-456: Network timeout
2024-01-15 10:25:30 - priya.workers - ERROR - Job moved to dead letter queue: job-789: Max retries exceeded
```

## Best Practices

1. **Always set tenant_id**: Mandatory, enables multi-tenancy isolation
2. **Make handlers idempotent**: Can be safely retried
3. **Use appropriate queue levels**: Avoid queueing low-priority jobs at critical level
4. **Track progress**: Call `set_progress()` for long-running jobs
5. **Handle timeouts**: 1-hour timeout per job (configurable)
6. **Monitor dead letter queue**: Investigate and fix failed jobs
7. **Use idempotency keys**: Prevent duplicate processing
8. **Batch processing**: Split large jobs into smaller batches
9. **Graceful degradation**: Don't fail user request if job fails
10. **Test handlers**: Ensure they're idempotent and handle errors

## Scaling Considerations

### Horizontal Scaling

Run multiple worker instances:
```bash
pm2 start config/ecosystem.config.js --only priya-worker -i max
```

All workers consume from same Redis queues. Leader election ensures scheduler runs once.

### Vertical Scaling

Increase concurrency:
```bash
WORKER_CONCURRENCY=20 python -m uvicorn main:app --port 9043
```

### Load Distribution

By design:
- Higher priority queues checked more frequently
- Per-tenant fair-share prevents monopolization
- Scheduled jobs spread over time

## Troubleshooting

### Jobs Not Processing

1. Check worker health: `curl http://localhost:9043/health`
2. Check Redis connection: `redis-cli ping`
3. Verify handlers registered: `curl http://localhost:9043/status`
4. Check logs: `pm2 logs priya-worker`

### High Dead Letter Queue

1. List jobs: `curl http://localhost:9043/jobs/dead-letter/list`
2. Investigate error messages
3. Fix root cause
4. Manually re-queue jobs (implementation TBD)

### Performance Issues

1. Check `priya_queue_depth` metric
2. Monitor `priya_job_processing_seconds` per job type
3. Increase `WORKER_CONCURRENCY` if workers have spare capacity
4. Run multiple worker instances

### Tenant Getting Stuck

Tenant concurrency limit prevents one tenant from monopolizing workers:
- Each tenant limited to ~25% of worker concurrency
- Adjust in code if needed: `max_per_tenant = QUEUE_CONCURRENCY[queue_level] // 2`

## Architecture Decisions

### Why Redis?
- Fast, simple, proven
- Multi-purpose platform (cache + queue + locks)
- No additional infrastructure
- Good enough for 99% of use cases

### Why ARQ Pattern?
- Simpler than Celery (no AMQP broker)
- More reliable than basic FIFO queue
- Better than scheduled tasks scattered across services
- Single source of truth for job state

### Why Priority Queues?
- Billing jobs never blocked by analytics jobs
- AI inference doesn't compete with cleanup tasks
- Prevents head-of-line blocking

### Why Exponential Backoff?
- Gives transient failures time to recover
- Prevents thundering herd (all jobs retrying simultaneously)
- Reduces load on service during outages

### Why Dead Letter Queue?
- Prevents infinite retries
- Enables manual investigation
- Provides audit trail of failures

## Future Enhancements

1. **Job Chaining**: Sequential dependent jobs
2. **Batch Processing**: Group similar jobs
3. **Priority Boosts**: Elevate job priority after timeouts
4. **Job Templates**: Predefined job patterns
5. **Webhook Callbacks**: Notify external systems on completion
6. **Job Metrics Dashboards**: Real-time job analytics
7. **Per-tenant Job Limits**: Rate limiting per customer
8. **Job Cost Tracking**: Measure resource consumption
