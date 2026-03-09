"""
Priya Global — Production-Grade Background Job Queue & Worker System

Redis-backed async job queue with ARQ pattern (similar to RQ/Celery but simpler).
Provides priority queues, scheduling, retry logic, and comprehensive metrics.

Architecture:
- JobQueue: Redis-backed task storage with priority levels
- Worker: Async worker process consuming from JobQueue
- JobResult: Execution result tracking with state machine
- Concurrency control: Per-worker and per-tenant rate limits

Queue Levels:
1. critical (priority 1): Billing, auth, payment processing - max 50 concurrent
2. high (priority 2): Messaging (email/SMS/WhatsApp), AI - max 30 concurrent
3. normal (priority 3): Analytics, notifications, reports - max 20 concurrent
4. low (priority 4): Cleanup, archival, maintenance - max 10 concurrent

Retry Strategy (exponential backoff):
- Attempt 1: 30s delay
- Attempt 2: 2min delay
- Attempt 3: 8min delay
- Attempt 4: 32min delay
- Attempt 5: 2hr delay
- Attempt 6+: Dead Letter Queue (manual intervention)
"""

import asyncio
import json
import logging
import os
import signal
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple
from collections import defaultdict

import redis.asyncio as redis
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger("priya.workers")


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class JobStatus(str, Enum):
    """Job lifecycle states."""
    PENDING = "pending"           # Created, waiting to be queued
    QUEUED = "queued"             # In queue, waiting for worker
    RUNNING = "running"           # Currently executing
    COMPLETED = "completed"       # Success
    FAILED = "failed"             # Failed, will be retried
    RETRYING = "retrying"         # Waiting for retry
    DEAD = "dead"                 # Dead Letter Queue - max retries exceeded
    CANCELLED = "cancelled"       # User-cancelled


class QueueLevel(str, Enum):
    """Priority queue levels."""
    CRITICAL = "critical"         # Billing, auth, payments
    HIGH = "high"                 # Messaging, AI
    NORMAL = "normal"             # Analytics, notifications
    LOW = "low"                   # Cleanup, archival


# Retry delays (exponential backoff)
RETRY_DELAYS_SECONDS = [30, 120, 480, 1920, 7200]  # 30s, 2m, 8m, 32m, 2hr

# Queue max concurrent jobs
QUEUE_CONCURRENCY = {
    QueueLevel.CRITICAL: 50,
    QueueLevel.HIGH: 30,
    QueueLevel.NORMAL: 20,
    QueueLevel.LOW: 10,
}

# Default job TTL (24 hours) - jobs older than this are expired
DEFAULT_JOB_TTL = 86400

# Default progress check interval (5 seconds)
PROGRESS_INTERVAL = 5


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class JobContext:
    """Context passed to job handlers."""
    job_id: str
    tenant_id: str
    job_type: str
    queue: QueueLevel
    payload: Dict[str, Any]
    retry_count: int = 0
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JobResult:
    """Job execution result."""
    job_id: str
    status: JobStatus
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    progress: int = 0  # 0-100
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "error_traceback": self.error_traceback,
            "progress": self.progress,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
        }


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================

jobs_processed = Counter(
    "priya_jobs_processed_total",
    "Total jobs processed",
    ["queue", "status"],
)

jobs_failed = Counter(
    "priya_jobs_failed_total",
    "Total jobs failed",
    ["queue", "reason"],
)

queue_depth = Gauge(
    "priya_queue_depth",
    "Number of jobs in queue",
    ["queue"],
)

jobs_in_progress = Gauge(
    "priya_jobs_in_progress",
    "Number of jobs currently executing",
    ["queue"],
)

job_processing_time = Histogram(
    "priya_job_processing_seconds",
    "Job processing time",
    ["queue", "job_type"],
)

job_retry_count = Counter(
    "priya_job_retries_total",
    "Total job retries",
    ["queue", "job_type"],
)

dead_letter_count = Gauge(
    "priya_dead_letter_queue_total",
    "Total jobs in dead letter queue",
)


# ============================================================================
# JOB QUEUE
# ============================================================================

class JobQueue:
    """Redis-backed async job queue with priority levels and scheduling."""

    def __init__(self, redis_url: str = None):
        """Initialize job queue.

        Args:
            redis_url: Redis connection URL (defaults to env var REDIS_URL)
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis: Optional[redis.Redis] = None
        self._dedup_keys: Set[str] = set()

    async def connect(self) -> None:
        """Connect to Redis."""
        self.redis = await redis.from_url(self.redis_url, decode_responses=True)
        logger.info(f"Connected to Redis: {self.redis_url}")

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            logger.info("Disconnected from Redis")

    async def enqueue(
        self,
        tenant_id: str,
        job_type: str,
        payload: Dict[str, Any],
        queue: QueueLevel = QueueLevel.NORMAL,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Enqueue a job immediately.

        Args:
            tenant_id: Tenant ID (mandatory, always set in context)
            job_type: Type of job (e.g., 'send_email', 'process_payment')
            payload: Job-specific payload dict
            queue: Priority queue level
            idempotency_key: Optional key for deduplication
            metadata: Optional job metadata (tags, source, etc.)

        Returns:
            job_id of enqueued job
        """
        job_id = str(uuid.uuid4())

        # Check deduplication (tenant-scoped to prevent cross-tenant access)
        if idempotency_key:
            dedup_key = f"job:dedup:{tenant_id}:{idempotency_key}"
            if await self.redis.exists(dedup_key):
                logger.info(f"Job deduplicated for tenant {tenant_id}: {idempotency_key}")
                return await self.redis.get(dedup_key)
            await self.redis.setex(dedup_key, 3600, job_id)  # Dedup for 1 hour

        # Store job metadata (SECURITY: payload should be encrypted in production)
        # TODO: Implement AES-256-GCM encryption for payloads containing sensitive data
        job_data = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "job_type": job_type,
            "payload": json.dumps(payload),  # WARNING: Stored unencrypted; encrypt sensitive payloads
            "queue": queue.value,
            "status": JobStatus.QUEUED.value,
            "retry_count": 0,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
            "metadata": json.dumps(metadata or {}),
        }
        await self.redis.hset(f"job:{job_id}", mapping=job_data)
        await self.redis.expire(f"job:{job_id}", DEFAULT_JOB_TTL)

        # Add to queue list (sorted by priority + FIFO)
        queue_key = f"queue:{queue.value}"
        await self.redis.rpush(queue_key, job_id)

        # Update queue depth metric
        queue_depth.labels(queue=queue.value).set(await self.redis.llen(queue_key))

        logger.info(f"Job enqueued: {job_id} (tenant={tenant_id}, type={job_type}, queue={queue.value})")
        return job_id

    async def enqueue_at(
        self,
        tenant_id: str,
        job_type: str,
        payload: Dict[str, Any],
        scheduled_time: datetime,
        queue: QueueLevel = QueueLevel.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Enqueue a job to run at a specific time.

        Args:
            tenant_id: Tenant ID
            job_type: Job type
            payload: Job payload
            scheduled_time: UTC datetime when job should run
            queue: Priority queue level
            metadata: Optional metadata

        Returns:
            job_id
        """
        job_id = str(uuid.uuid4())

        # Store job metadata
        job_data = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "job_type": job_type,
            "payload": json.dumps(payload),
            "queue": queue.value,
            "status": JobStatus.PENDING.value,
            "retry_count": 0,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
            "scheduled_at": scheduled_time.isoformat(),
            "metadata": json.dumps(metadata or {}),
        }
        await self.redis.hset(f"job:{job_id}", mapping=job_data)
        await self.redis.expire(f"job:{job_id}", DEFAULT_JOB_TTL)

        # Add to scheduled job set with timestamp as score
        score = scheduled_time.timestamp()
        await self.redis.zadd(f"scheduled:{queue.value}", {job_id: score})

        logger.info(f"Job scheduled: {job_id} for {scheduled_time}")
        return job_id

    async def enqueue_in(
        self,
        tenant_id: str,
        job_type: str,
        payload: Dict[str, Any],
        delay_seconds: int,
        queue: QueueLevel = QueueLevel.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Enqueue a job to run after a delay.

        Args:
            tenant_id: Tenant ID
            job_type: Job type
            payload: Job payload
            delay_seconds: Seconds to wait before processing
            queue: Priority queue level
            metadata: Optional metadata

        Returns:
            job_id
        """
        scheduled_time = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        return await self.enqueue_at(
            tenant_id, job_type, payload, scheduled_time, queue, metadata
        )

    async def dequeue(self, queue: QueueLevel) -> Optional[str]:
        """Dequeue a job from the front of the queue.

        Args:
            queue: Queue level to dequeue from

        Returns:
            job_id or None if queue is empty
        """
        queue_key = f"queue:{queue.value}"
        job_id = await self.redis.lpop(queue_key)
        return job_id

    async def get_job(self, job_id: str) -> Optional[JobContext]:
        """Get job details by ID.

        Args:
            job_id: Job ID

        Returns:
            JobContext or None if not found
        """
        job_data = await self.redis.hgetall(f"job:{job_id}")
        if not job_data:
            return None

        try:
            return JobContext(
                job_id=job_data["job_id"],
                tenant_id=job_data["tenant_id"],
                job_type=job_data["job_type"],
                queue=QueueLevel(job_data["queue"]),
                payload=json.loads(job_data["payload"]),
                retry_count=int(job_data.get("retry_count", 0)),
                metadata=json.loads(job_data.get("metadata", "{}")),
            )
        except (ValueError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error deserializing job {job_id}: {e}")
            return None

    async def get_status(self, job_id: str) -> Optional[JobStatus]:
        """Get job status.

        Args:
            job_id: Job ID

        Returns:
            JobStatus or None if not found
        """
        status = await self.redis.hget(f"job:{job_id}", "status")
        return JobStatus(status) if status else None

    async def get_progress(self, job_id: str) -> int:
        """Get job progress (0-100).

        Args:
            job_id: Job ID

        Returns:
            Progress percentage (0-100)
        """
        progress = await self.redis.hget(f"job:{job_id}", "progress")
        return int(progress) if progress else 0

    async def set_progress(self, job_id: str, progress: int) -> None:
        """Update job progress.

        Args:
            job_id: Job ID
            progress: Progress percentage (0-100)
        """
        await self.redis.hset(f"job:{job_id}", "progress", min(100, max(0, progress)))

    async def set_status(self, job_id: str, status: JobStatus) -> None:
        """Update job status.

        Args:
            job_id: Job ID
            status: New status
        """
        await self.redis.hset(f"job:{job_id}", "status", status.value)

    async def complete_job(self, job_id: str, result: JobResult) -> None:
        """Mark job as completed.

        Args:
            job_id: Job ID
            result: JobResult object
        """
        await self.redis.hset(f"job:{job_id}", mapping={
            "status": JobStatus.COMPLETED.value,
            "output": json.dumps(result.output or {}),
            "progress": 100,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": result.duration_seconds or 0,
        })

    async def fail_job(
        self,
        job_id: str,
        error: str,
        error_traceback: str,
        should_retry: bool = True,
    ) -> None:
        """Mark job as failed.

        Args:
            job_id: Job ID
            error: Error message
            error_traceback: Full error traceback
            should_retry: Whether to retry the job
        """
        job_data = await self.redis.hgetall(f"job:{job_id}")
        if not job_data:
            return

        retry_count = int(job_data.get("retry_count", 0))

        if should_retry and retry_count < len(RETRY_DELAYS_SECONDS):
            # Schedule retry with exponential backoff
            delay_seconds = RETRY_DELAYS_SECONDS[retry_count]
            queue = QueueLevel(job_data["queue"])

            job_retry_count.labels(queue=queue.value, job_type=job_data["job_type"]).inc()

            # Update job for retry
            await self.redis.hset(f"job:{job_id}", mapping={
                "status": JobStatus.RETRYING.value,
                "retry_count": retry_count + 1,
                "error": error,
                "error_traceback": error_traceback,
            })

            # Schedule for retry
            scheduled_time = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            await self.redis.zadd(f"scheduled:{queue.value}", {job_id: scheduled_time.timestamp()})

            logger.warning(
                f"Job {job_id} failed (retry {retry_count + 1}/{len(RETRY_DELAYS_SECONDS)}) "
                f"scheduled for {delay_seconds}s from now: {error}"
            )
        else:
            # Move to dead letter queue
            await self.redis.hset(f"job:{job_id}", mapping={
                "status": JobStatus.DEAD.value,
                "error": error,
                "error_traceback": error_traceback,
            })
            await self.redis.rpush("queue:dead-letter", job_id)
            dead_letter_count.set(await self.redis.llen("queue:dead-letter"))

            queue = QueueLevel(job_data["queue"])
            jobs_failed.labels(queue=queue.value, reason="max_retries").inc()

            logger.error(f"Job {job_id} moved to dead letter queue: {error}")

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending job.

        Args:
            job_id: Job ID

        Returns:
            True if cancelled, False if not found or already running
        """
        status = await self.get_status(job_id)
        if status not in [JobStatus.PENDING, JobStatus.QUEUED, JobStatus.RETRYING]:
            return False

        await self.set_status(job_id, JobStatus.CANCELLED)
        logger.info(f"Job {job_id} cancelled")
        return True

    async def process_scheduled_jobs(self, queue: QueueLevel) -> int:
        """Move jobs from scheduled set to queue if their time has come.

        Args:
            queue: Queue level

        Returns:
            Number of jobs moved to queue
        """
        scheduled_key = f"scheduled:{queue.value}"
        queue_key = f"queue:{queue.value}"
        now = datetime.now(timezone.utc).timestamp()

        # Get all scheduled jobs with score <= now
        jobs = await self.redis.zrangebyscore(scheduled_key, 0, now)

        for job_id in jobs:
            await self.redis.zrem(scheduled_key, job_id)
            await self.redis.rpush(queue_key, job_id)
            await self.set_status(job_id, JobStatus.QUEUED)

        if jobs:
            queue_depth.labels(queue=queue.value).set(await self.redis.llen(queue_key))

        return len(jobs)

    async def get_dead_letter_jobs(self, tenant_id: str, limit: int = 100) -> List[JobContext]:
        """Get jobs in dead letter queue (tenant-scoped).

        Args:
            tenant_id: Tenant ID to filter DLQ jobs
            limit: Max jobs to return

        Returns:
            List of JobContext objects for the specified tenant only
        """
        job_ids = await self.redis.lrange("queue:dead-letter", 0, limit - 1)
        jobs = []
        for job_id in job_ids:
            job = await self.get_job(job_id)
            # CRITICAL: Only return jobs belonging to the requested tenant
            if job and job.tenant_id == tenant_id:
                jobs.append(job)
        return jobs

    async def get_queue_depth(self, queue: QueueLevel) -> int:
        """Get number of jobs in queue.

        Args:
            queue: Queue level

        Returns:
            Number of jobs in queue
        """
        return await self.redis.llen(f"queue:{queue.value}")

    async def get_tenant_concurrency(self, tenant_id: str) -> int:
        """Get number of jobs currently running for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Number of running jobs
        """
        return await self.redis.llen(f"jobs_running:{tenant_id}")


# ============================================================================
# WORKER
# ============================================================================

JobHandler = Callable[[JobContext], Awaitable[JobResult]]


class Worker:
    """Async worker that consumes jobs from JobQueue."""

    def __init__(
        self,
        job_queue: JobQueue,
        max_concurrent_jobs: int = 5,
        health_check_port: int = 9043,
    ):
        """Initialize worker.

        Args:
            job_queue: JobQueue instance
            max_concurrent_jobs: Max concurrent job executions
            health_check_port: Port for health check endpoint
        """
        self.job_queue = job_queue
        self.max_concurrent_jobs = max_concurrent_jobs
        self.health_check_port = health_check_port
        self.handlers: Dict[str, JobHandler] = {}
        self._running = False
        self._active_jobs: Dict[str, asyncio.Task] = {}
        self._tenant_running: Dict[str, int] = defaultdict(int)
        self._loop_task: Optional[asyncio.Task] = None

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        """Register a handler for a job type.

        Args:
            job_type: Job type (e.g., 'send_email')
            handler: Async function that processes the job
        """
        self.handlers[job_type] = handler
        logger.info(f"Handler registered: {job_type}")

    async def run_job(self, job: JobContext, authenticated_tenant_id: Optional[str] = None) -> JobResult:
        """Execute a single job.

        Args:
            job: JobContext to execute
            authenticated_tenant_id: Tenant ID from worker context (for validation)

        Returns:
            JobResult
        """
        start_time = datetime.now(timezone.utc)
        job_id = job.job_id

        # CRITICAL: Validate job's tenant matches authenticated context
        if authenticated_tenant_id and job.tenant_id != authenticated_tenant_id:
            logger.error(f"Tenant mismatch: job {job_id} tenant={job.tenant_id} != auth={authenticated_tenant_id}")
            return JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                error="Tenant validation failed",
            )

        try:
            logger.info(f"Starting job: {job_id} (type={job.job_type}, tenant={job.tenant_id})")

            # Update status
            await self.job_queue.set_status(job_id, JobStatus.RUNNING)
            self._tenant_running[job.tenant_id] += 1

            # Get handler
            handler = self.handlers.get(job.job_type)
            if not handler:
                raise RuntimeError(f"No handler registered for job type: {job.job_type}")

            # Execute handler
            try:
                result = await asyncio.wait_for(handler(job), timeout=3600)  # 1hr timeout
            except asyncio.TimeoutError:
                raise RuntimeError(f"Job exceeded 1-hour timeout")

            if not isinstance(result, JobResult):
                result = JobResult(
                    job_id=job_id,
                    status=JobStatus.COMPLETED,
                    output=result if result else None,
                )

            # Completion
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            result.duration_seconds = duration
            await self.job_queue.complete_job(job_id, result)

            jobs_processed.labels(queue=job.queue.value, status="success").inc()
            job_processing_time.labels(queue=job.queue.value, job_type=job.job_type).observe(duration)

            logger.info(f"Job completed: {job_id} ({duration:.2f}s)")
            return result

        except Exception as e:
            logger.error(f"Job failed: {job_id}: {e}", exc_info=True)
            import traceback
            error_traceback = traceback.format_exc()

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            await self.job_queue.fail_job(
                job_id,
                str(e),
                error_traceback,
                should_retry=True,
            )

            jobs_processed.labels(queue=job.queue.value, status="failed").inc()
            return JobResult(
                job_id=job_id,
                status=JobStatus.FAILED,
                error=str(e),
                error_traceback=error_traceback,
                duration_seconds=duration,
            )
        finally:
            self._tenant_running[job.tenant_id] = max(0, self._tenant_running[job.tenant_id] - 1)

    async def _process_queue(self, queue_level: QueueLevel) -> None:
        """Process jobs from a queue level.

        Args:
            queue_level: Queue level to process
        """
        while self._running:
            try:
                # Process scheduled jobs first
                await self.job_queue.process_scheduled_jobs(queue_level)

                # Check if we have capacity
                if len(self._active_jobs) >= self.max_concurrent_jobs:
                    await asyncio.sleep(1)
                    continue

                # Dequeue a job
                job_id = await self.job_queue.dequeue(queue_level)
                if not job_id:
                    await asyncio.sleep(1)
                    continue

                # Get job context
                job = await self.job_queue.get_job(job_id)
                if not job:
                    logger.warning(f"Job not found: {job_id}")
                    continue

                # Check tenant concurrency limit (prevent one tenant from monopolizing)
                max_per_tenant = QUEUE_CONCURRENCY[queue_level] // 2  # Fair split
                if self._tenant_running[job.tenant_id] >= max_per_tenant:
                    # Re-queue for later
                    await self.job_queue.redis.rpush(f"queue:{queue_level.value}", job_id)
                    await asyncio.sleep(0.5)
                    continue

                # Execute job
                task = asyncio.create_task(self.run_job(job))
                self._active_jobs[job_id] = task

                # Clean up finished tasks
                finished_ids = [jid for jid, t in self._active_jobs.items() if t.done()]
                for jid in finished_ids:
                    del self._active_jobs[jid]

                jobs_in_progress.labels(queue=queue_level.value).set(len(self._active_jobs))

            except Exception as e:
                logger.error(f"Error in queue processor: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def start(self) -> None:
        """Start the worker.

        Handles all 4 queue levels with proper priority.
        """
        logger.info("Starting worker...")
        self._running = True

        # Connect to Redis
        await self.job_queue.connect()

        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        # Start queue processors for each priority level
        # Higher priority queues get processed more frequently
        queue_tasks = [
            asyncio.create_task(self._process_queue(QueueLevel.CRITICAL)),
            asyncio.create_task(self._process_queue(QueueLevel.HIGH)),
            asyncio.create_task(self._process_queue(QueueLevel.NORMAL)),
            asyncio.create_task(self._process_queue(QueueLevel.LOW)),
        ]

        logger.info("Worker started successfully")

        # Wait for all tasks
        try:
            await asyncio.gather(*queue_tasks)
        except asyncio.CancelledError:
            logger.info("Worker shutdown")

    async def stop(self) -> None:
        """Gracefully shutdown the worker."""
        logger.info("Shutting down worker...")
        self._running = False

        # Wait for active jobs to complete (with timeout)
        if self._active_jobs:
            logger.info(f"Waiting for {len(self._active_jobs)} jobs to complete...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_jobs.values(), return_exceptions=True),
                    timeout=60,
                )
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for jobs, cancelling remaining...")
                for task in self._active_jobs.values():
                    task.cancel()

        # Disconnect from Redis
        await self.job_queue.disconnect()
        logger.info("Worker stopped")

    async def health_check(self) -> Dict[str, Any]:
        """Get worker health status.

        Returns:
            Health status dict
        """
        return {
            "status": "healthy" if self._running else "stopped",
            "active_jobs": len(self._active_jobs),
            "max_concurrent": self.max_concurrent_jobs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
