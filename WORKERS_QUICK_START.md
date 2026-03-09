# Background Workers — Quick Start Guide

## Installation

The worker system is already integrated into the platform. No additional installation needed.

## Starting the Worker

### Development (Local)

```bash
cd services/worker
python -m uvicorn main:app --host 0.0.0.0 --port 9043
```

### Production (PM2)

```bash
pm2 start config/ecosystem.config.js --only priya-worker
pm2 logs priya-worker -f
```

### Docker

```bash
docker compose up -d worker
docker compose logs -f worker
```

## Quick Examples

### 1. Send Email (From Any Service)

```python
from shared.workers.base import JobQueue, QueueLevel

job_queue = JobQueue()
await job_queue.connect()

job_id = await job_queue.enqueue(
    tenant_id="tenant-123",
    job_type="send_email",
    payload={
        "to": "user@example.com",
        "subject": "Welcome!",
        "template": "welcome",
        "data": {"name": "John"},
    },
    queue=QueueLevel.HIGH,
)

print(f"Email queued: {job_id}")
```

### 2. Process Subscription Renewal (Scheduled)

```python
from datetime import datetime, timezone, timedelta
from shared.workers.base import JobQueue, QueueLevel

job_queue = JobQueue()
await job_queue.connect()

# Queue for next month
next_month = datetime.now(timezone.utc) + timedelta(days=30)

job_id = await job_queue.enqueue_at(
    tenant_id="tenant-123",
    job_type="process_subscription_renewal",
    payload={"subscription_id": "sub-456"},
    scheduled_time=next_month,
    queue=QueueLevel.CRITICAL,
)

print(f"Subscription renewal scheduled: {job_id}")
```

### 3. Check Job Status

```bash
curl http://localhost:9043/jobs/job-id-here
```

Response:
```json
{
  "job_id": "job-id-here",
  "status": "running",
  "progress": 45,
  "job_type": "send_email",
  "tenant_id": "tenant-123"
}
```

### 4. Monitor Queue Depth

```bash
curl http://localhost:9043/status
```

Response:
```json
{
  "service": "worker",
  "running": true,
  "concurrency": {
    "max": 5,
    "current": 3
  },
  "handlers": 30,
  "queues": {
    "critical": 2,
    "high": 15,
    "normal": 42,
    "low": 5
  },
  "dead_letter": 0
}
```

### 5. View Failed Jobs

```bash
curl http://localhost:9043/jobs/dead-letter/list
```

### 6. Add Custom Schedule

```bash
curl -X POST http://localhost:9043/schedules \
  -d "name=Daily Cleanup" \
  -d "job_type=cleanup_old_files" \
  -d "cron_expression=0 2 * * *" \
  -d "queue=low"
```

## Enqueuing Pattern

Every service that needs to queue jobs should follow this pattern:

```python
from fastapi import FastAPI
from shared.workers.base import JobQueue, QueueLevel

app = FastAPI()
job_queue: JobQueue = None

@app.on_event("startup")
async def startup():
    global job_queue
    job_queue = JobQueue()
    await job_queue.connect()

@app.on_event("shutdown")
async def shutdown():
    if job_queue:
        await job_queue.disconnect()

@app.post("/api/notify-user")
async def notify_user(tenant_id: str, user_id: str, message: str):
    job_id = await job_queue.enqueue(
        tenant_id=tenant_id,
        job_type="send_push_notification",
        payload={
            "user_id": user_id,
            "title": "Notification",
            "message": message,
        },
        queue=QueueLevel.NORMAL,
    )
    return {"job_id": job_id, "status": "queued"}
```

## Available Handlers

### Billing
- `process_subscription_renewal` - Monthly billing
- `process_usage_billing` - Usage charges
- `process_payment_webhook` - Stripe/Razorpay
- `generate_invoice` - PDF invoices

### Messaging
- `send_email` - Email
- `send_sms` - SMS
- `send_whatsapp_template` - WhatsApp
- `process_inbound_message` - Route messages

### AI
- `generate_ai_response` - AI response
- `train_knowledge_base` - Embeddings
- `analyze_sentiment` - Sentiment analysis

### Analytics
- `aggregate_daily_metrics` - Daily stats
- `generate_analytics_report` - Reports
- `calculate_conversion_rates` - Conversions

### Notifications
- `send_push_notification` - Push
- `send_bulk_notification` - Bulk

### Maintenance
- `cleanup_expired_sessions` - Sessions
- `archive_old_conversations` - Archive
- `rotate_api_keys` - Keys
- `gdpr_data_deletion` - GDPR deletion
- `generate_compliance_report` - Compliance

## Queue Priority Guide

```
CRITICAL  - Use for: Billing, payments, auth
HIGH      - Use for: Email, SMS, AI
NORMAL    - Use for: Analytics, notifications
LOW       - Use for: Cleanup, archival, reports
```

## Testing Jobs Locally

```python
# Test job enqueueing
import asyncio
from shared.workers.base import JobQueue, QueueLevel

async def test():
    queue = JobQueue()
    await queue.connect()

    job_id = await queue.enqueue(
        tenant_id="test-tenant",
        job_type="send_email",
        payload={"to": "test@example.com"},
        queue=QueueLevel.HIGH,
    )

    print(f"Queued: {job_id}")
    status = await queue.get_status(job_id)
    print(f"Status: {status}")

    await queue.disconnect()

asyncio.run(test())
```

## Common Patterns

### Idempotent Job Enqueueing

```python
# Same idempotency_key within 1 hour = same job_id
job_id = await job_queue.enqueue(
    tenant_id=tenant_id,
    job_type="send_email",
    payload={"to": email},
    idempotency_key=f"send-welcome-{user_id}",  # Prevents duplicates
)
```

### Deferred Execution

```python
# Queue for execution after delay
job_id = await job_queue.enqueue_in(
    tenant_id=tenant_id,
    job_type="process_subscription_renewal",
    payload={"subscription_id": sub_id},
    delay_seconds=3600,  # 1 hour delay
    queue=QueueLevel.CRITICAL,
)
```

### Progress Tracking

```python
# In a long-running handler
async def my_handler(ctx):
    total_items = 1000
    for i, item in enumerate(items):
        process(item)
        progress = int((i / total_items) * 100)
        await ctx.job_queue.set_progress(ctx.job_id, progress)

    return JobResult(...)
```

### Batch Processing

```python
# Split large jobs into smaller batches
items = list_all_items()  # 10,000 items
batch_size = 100

for i in range(0, len(items), batch_size):
    batch = items[i:i+batch_size]
    await job_queue.enqueue(
        tenant_id=tenant_id,
        job_type="process_batch",
        payload={"items": batch},
        queue=QueueLevel.NORMAL,
    )
```

## Monitoring Commands

```bash
# Health check
curl http://localhost:9043/health

# Worker status
curl http://localhost:9043/status

# Queue metrics (Prometheus)
curl http://localhost:9043/metrics

# Job status
curl http://localhost:9043/jobs/{job_id}

# Job progress
curl http://localhost:9043/jobs/{job_id}/progress

# Dead letter jobs
curl http://localhost:9043/jobs/dead-letter/list

# Scheduled jobs
curl http://localhost:9043/schedules
```

## Troubleshooting

### Jobs not processing?
1. Check worker is running: `curl http://localhost:9043/health`
2. Check Redis: `redis-cli ping`
3. Check logs: `pm2 logs priya-worker`

### Job stuck in QUEUED?
1. Check worker concurrency: `curl http://localhost:9043/status`
2. Check queue depth is reasonable
3. Check handler is registered

### Job in Dead Letter Queue?
1. Get job details: `curl http://localhost:9043/jobs/dead-letter/list`
2. Check error message
3. Fix root cause
4. Manually re-queue if needed

### High latency?
1. Check queue depth: `curl http://localhost:9043/status`
2. Check worker concurrency
3. Scale up workers: `WORKER_CONCURRENCY=20`

## Configuration

```bash
# Environment variables
WORKER_PORT=9043                           # Health check port
WORKER_CONCURRENCY=5                       # Max jobs executing
WORKER_QUEUES=critical,high,normal,low    # Queues to process
REDIS_URL=redis://localhost:6379/0        # Redis URL
LOG_LEVEL=INFO                             # Logging
```

## Next Steps

1. Read `/WORKERS_ARCHITECTURE.md` for detailed documentation
2. Check `shared/workers/handlers.py` for all available handlers
3. Add your own custom handlers following the pattern
4. Monitor with `/metrics` endpoint (Prometheus compatible)
5. Set up alerts for dead letter queue growth
