"""
Priya Global — Background Worker Service (Port 9043)

Standalone service that:
1. Consumes jobs from Redis queue
2. Routes to appropriate handlers
3. Tracks job progress and completion
4. Exposes metrics and health endpoints

Environment variables:
- WORKER_PORT: Health check port (default 9043)
- WORKER_CONCURRENCY: Max concurrent jobs (default 5)
- WORKER_QUEUES: Comma-separated queues to process (default all)
- REDIS_URL: Redis connection URL
- LOG_LEVEL: Logging level
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Dict

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Gauge, generate_latest
import uvicorn

from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.workers.base import (
    JobQueue,
    Worker,
    JobStatus,
    QueueLevel,
)
from shared.workers.handlers import (
    send_email,
    send_sms,
    send_whatsapp_template,
    process_inbound_message,
    generate_ai_response,
    train_knowledge_base,
    analyze_sentiment,
    aggregate_daily_metrics,
    generate_analytics_report,
    calculate_conversion_rates,
    send_push_notification,
    send_bulk_notification,
    cleanup_expired_sessions,
    archive_old_conversations,
    rotate_api_keys,
    gdpr_data_deletion,
    generate_compliance_report,
    process_subscription_renewal,
    process_usage_billing,
    process_payment_webhook,
    generate_invoice,
)
from shared.workers.scheduler import JobScheduler

# ============================================================================
# LOGGING & CONFIGURATION
# ============================================================================

log_level = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("priya.worker.service")

WORKER_PORT = int(os.getenv("WORKER_PORT", "9043"))
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "5"))
WORKER_QUEUES = os.getenv("WORKER_QUEUES", "critical,high,normal,low").split(",")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Priya Global Worker Service",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="worker")
app.add_middleware(TracingMiddleware)

# Global references
worker: Worker = None
scheduler: JobScheduler = None
job_queue: JobQueue = None

# Service metrics
service_started = Counter(
    "priya_worker_service_starts_total",
    "Total service starts",
)

service_errors = Counter(
    "priya_worker_service_errors_total",
    "Total service errors",
)


# ============================================================================
# STARTUP & SHUTDOWN
# ============================================================================

async def initialize_worker() -> None:
    """Initialize worker with all handlers."""
    global worker, job_queue

    logger.info("Initializing worker...")

    # Create job queue
    job_queue = JobQueue(REDIS_URL)
    await job_queue.connect()

    # Create worker
    worker = Worker(
        job_queue=job_queue,
        max_concurrent_jobs=WORKER_CONCURRENCY,
        health_check_port=WORKER_PORT,
    )

    # Register all handlers
    handler_map = {
        # Billing
        "process_subscription_renewal": process_subscription_renewal,
        "process_usage_billing": process_usage_billing,
        "process_payment_webhook": process_payment_webhook,
        "generate_invoice": generate_invoice,
        # Messaging
        "send_email": send_email,
        "send_sms": send_sms,
        "send_whatsapp_template": send_whatsapp_template,
        "process_inbound_message": process_inbound_message,
        # AI
        "generate_ai_response": generate_ai_response,
        "train_knowledge_base": train_knowledge_base,
        "analyze_sentiment": analyze_sentiment,
        # Analytics
        "aggregate_daily_metrics": aggregate_daily_metrics,
        "generate_analytics_report": generate_analytics_report,
        "calculate_conversion_rates": calculate_conversion_rates,
        # Notifications
        "send_push_notification": send_push_notification,
        "send_bulk_notification": send_bulk_notification,
        # Maintenance
        "cleanup_expired_sessions": cleanup_expired_sessions,
        "archive_old_conversations": archive_old_conversations,
        "rotate_api_keys": rotate_api_keys,
        "gdpr_data_deletion": gdpr_data_deletion,
        "generate_compliance_report": generate_compliance_report,
    }

    for job_type, handler in handler_map.items():
        worker.register_handler(job_type, handler)
        logger.info("Registered handler: %s", job_type)

    logger.info("Worker initialized with %s handlers", len(handler_map))

    service_started.inc()


async def initialize_scheduler() -> None:
    """Initialize scheduler."""
    global scheduler

    logger.info("Initializing scheduler...")

    scheduler = JobScheduler(REDIS_URL)
    await scheduler.connect()

    logger.info("Scheduler initialized")


@app.on_event("startup")
async def startup_event() -> None:
    """FastAPI startup event."""
    try:
        await initialize_worker()
        await initialize_scheduler()

        # Start worker in background
        asyncio.create_task(worker.start())
        logger.info("Worker started")

        # Start scheduler in background
        asyncio.create_task(scheduler.start())
        logger.info("Scheduler started")

    except Exception as e:
        logger.error("Startup failed: %s", e, exc_info=True)
        service_errors.inc()
        raise


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """FastAPI shutdown event."""
    try:
        # Gracefully shutdown distributed tracing
        shutdown_tracing()

        logger.info("Shutting down worker service...")

        if scheduler:
            await scheduler.stop()
            logger.info("Scheduler stopped")

        if worker:
            await worker.stop()
            logger.info("Worker stopped")

        if job_queue:
            await job_queue.disconnect()
            logger.info("Redis disconnected")

    except Exception as e:
        logger.error("Shutdown error: %s", e, exc_info=True)
        service_errors.inc()


# ============================================================================
# HEALTH & METRICS ENDPOINTS
# ============================================================================

@app.get("/health")
async def health() -> Dict:
    """Health check endpoint."""
    if not worker:
        raise HTTPException(status_code=503, detail="Worker not ready")

    health_status = await worker.health_check()
    return {
        "status": "healthy",
        "service": "worker",
        "worker": health_status,
        "timestamp": health_status["timestamp"],
    }


@app.get("/metrics")
async def metrics() -> str:
    """Prometheus metrics endpoint."""
    return generate_latest().decode("utf-8")


@app.get("/status")
async def status() -> Dict:
    """Get worker status."""
    if not worker or not job_queue:
        raise HTTPException(status_code=503, detail="Worker not ready")

    # Queue depths
    queue_depths = {}
    for queue_level in QueueLevel:
        queue_depths[queue_level.value] = await job_queue.get_queue_depth(queue_level)

    return {
        "service": "worker",
        "running": worker._running,
        "concurrency": {
            "max": worker.max_concurrent_jobs,
            "current": len(worker._active_jobs),
        },
        "handlers": len(worker.handlers),
        "queues": queue_depths,
        "dead_letter": await job_queue.redis.llen("queue:dead-letter"),
    }


# ============================================================================
# JOB MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> Dict:
    """Get job status and details.

    Args:
        job_id: Job ID to look up

    Returns:
        Job details
    """
    if not job_queue:
        raise HTTPException(status_code=503, detail="Worker not ready")

    job_status = await job_queue.get_status(job_id)
    if not job_status:
        raise HTTPException(status_code=404, detail="Job not found")

    job = await job_queue.get_job(job_id)
    progress = await job_queue.get_progress(job_id)

    return {
        "job_id": job_id,
        "status": job_status.value,
        "progress": progress,
        "job_type": job.job_type if job else None,
        "tenant_id": job.tenant_id if job else None,
    }


@app.get("/jobs/{job_id}/progress")
async def get_job_progress(job_id: str) -> Dict:
    """Get job progress (0-100).

    Args:
        job_id: Job ID

    Returns:
        Progress details
    """
    if not job_queue:
        raise HTTPException(status_code=503, detail="Worker not ready")

    progress = await job_queue.get_progress(job_id)
    status = await job_queue.get_status(job_id)

    if not status:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "progress": progress,
        "status": status.value,
    }


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> Dict:
    """Cancel a pending job.

    Args:
        job_id: Job ID to cancel

    Returns:
        Cancellation result
    """
    if not job_queue:
        raise HTTPException(status_code=503, detail="Worker not ready")

    success = await job_queue.cancel_job(job_id)

    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel job (running or completed)")

    return {"job_id": job_id, "cancelled": True}


@app.get("/jobs/dead-letter/list")
async def list_dead_letter_jobs() -> Dict:
    """List jobs in dead letter queue.

    Returns:
        List of dead letter jobs
    """
    if not job_queue:
        raise HTTPException(status_code=503, detail="Worker not ready")

    jobs = await job_queue.get_dead_letter_jobs(limit=100)

    return {
        "count": len(jobs),
        "jobs": [
            {
                "job_id": job.job_id,
                "job_type": job.job_type,
                "tenant_id": job.tenant_id,
                "retry_count": job.retry_count,
            }
            for job in jobs
        ],
    }


# ============================================================================
# SCHEDULER ENDPOINTS
# ============================================================================

@app.get("/schedules")
async def list_schedules() -> Dict:
    """List all scheduled jobs."""
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not ready")

    schedules = await scheduler.get_schedules()

    return {
        "count": len(schedules),
        "schedules": [
            {
                "job_id": s.job_id,
                "name": s.name,
                "job_type": s.job_type,
                "cron_expression": s.cron_expression,
                "tenant_id": s.tenant_id,
                "queue": s.queue,
                "enabled": s.enabled,
            }
            for s in schedules
        ],
    }


@app.post("/schedules")
async def add_schedule(
    name: str,
    job_type: str,
    cron_expression: str,
    tenant_id: str = "*",
    queue: str = "normal",
) -> Dict:
    """Add a custom scheduled job.

    Args:
        name: Schedule name
        job_type: Job type handler
        cron_expression: 5-field cron expression
        tenant_id: Tenant ID or "*" for all
        queue: Queue level

    Returns:
        Schedule details
    """
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not ready")

    schedule_id = await scheduler.add_schedule(
        name=name,
        job_type=job_type,
        cron_expression=cron_expression,
        tenant_id=tenant_id,
        queue=queue,
    )

    return {
        "schedule_id": schedule_id,
        "name": name,
        "job_type": job_type,
        "cron_expression": cron_expression,
    }


# ============================================================================
# STARTUP
# ============================================================================

if __name__ == "__main__":
    logger.info("Starting Priya Global Worker Service on port %s", WORKER_PORT)
    logger.info("Configuration:")
    logger.info("  - Concurrency: %s", WORKER_CONCURRENCY)
    logger.info("  - Queues: %s", WORKER_QUEUES)
    logger.info("  - Redis: %s", REDIS_URL)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=WORKER_PORT,
        workers=1,  # Worker processes jobs in event loop
        log_level=log_level.lower(),
    )
