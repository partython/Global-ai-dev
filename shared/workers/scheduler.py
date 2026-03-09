"""
Priya Global — Cron-Like Job Scheduler

Schedules recurring jobs at fixed intervals:
- Leader election (only one scheduler runs per platform)
- Timezone-aware per-tenant scheduling (future extension)
- Missed job recovery (jobs not run due to downtime)
- Simple but robust, uses Redis for state

Built-in Schedule:
- Every 5 min: health_check_all_services
- Every 15 min: aggregate_realtime_metrics
- Hourly: cleanup_expired_sessions, process_usage_billing
- Daily 2am UTC: aggregate_daily_metrics, archive_old_conversations
- Daily 3am UTC: rotate_api_keys, gdpr_data_deletion
- Weekly Mon 4am UTC: generate_analytics_report, generate_compliance_report
- Monthly 1st 5am UTC: process_subscription_renewal, generate_invoice
"""

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Callable, List, Optional, Dict, Any

import redis.asyncio as redis
from croniter import croniter

logger = logging.getLogger("priya.scheduler")


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ScheduledJob:
    """Definition of a scheduled job."""
    job_id: str
    name: str
    job_type: str
    cron_expression: str  # 5-field cron: minute hour day month day-of-week
    tenant_id: str = "*"  # "*" means all tenants, or specific tenant_id
    payload: Dict[str, Any] = field(default_factory=dict)
    queue: str = "normal"
    enabled: bool = True
    timezone: str = "UTC"
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None


# ============================================================================
# JOB SCHEDULER
# ============================================================================

class JobScheduler:
    """Cron-like scheduler for recurring jobs with leader election."""

    # Built-in schedules
    BUILTIN_SCHEDULES = [
        # Every 5 minutes
        ScheduledJob(
            job_id="health-check",
            name="Health Check All Services",
            job_type="health_check",
            cron_expression="*/5 * * * *",
            tenant_id="*",
            queue="low",
        ),
        # Every 15 minutes
        ScheduledJob(
            job_id="realtime-metrics",
            name="Aggregate Real-time Metrics",
            job_type="aggregate_realtime_metrics",
            cron_expression="*/15 * * * *",
            tenant_id="*",
            queue="normal",
        ),
        # Hourly
        ScheduledJob(
            job_id="hourly-sessions",
            name="Cleanup Expired Sessions",
            job_type="cleanup_expired_sessions",
            cron_expression="0 * * * *",
            tenant_id="*",
            queue="low",
        ),
        ScheduledJob(
            job_id="hourly-billing",
            name="Process Hourly Usage Billing",
            job_type="process_usage_billing",
            cron_expression="0 * * * *",
            tenant_id="*",
            queue="critical",
        ),
        # Daily 2am UTC
        ScheduledJob(
            job_id="daily-metrics",
            name="Aggregate Daily Metrics",
            job_type="aggregate_daily_metrics",
            cron_expression="0 2 * * *",
            tenant_id="*",
            queue="normal",
            payload={"date": "TODAY"},  # Templated at runtime
        ),
        ScheduledJob(
            job_id="daily-archive",
            name="Archive Old Conversations",
            job_type="archive_old_conversations",
            cron_expression="0 2 * * *",
            tenant_id="*",
            queue="low",
        ),
        # Daily 3am UTC
        ScheduledJob(
            job_id="daily-keys",
            name="Rotate Expiring API Keys",
            job_type="rotate_api_keys",
            cron_expression="0 3 * * *",
            tenant_id="*",
            queue="low",
        ),
        ScheduledJob(
            job_id="daily-gdpr",
            name="Process GDPR Deletions",
            job_type="gdpr_data_deletion",
            cron_expression="0 3 * * *",
            tenant_id="*",
            queue="low",
        ),
        # Weekly Monday 4am UTC
        ScheduledJob(
            job_id="weekly-report",
            name="Generate Weekly Analytics Report",
            job_type="generate_analytics_report",
            cron_expression="0 4 * * 1",
            tenant_id="*",
            queue="normal",
            payload={"report_type": "weekly"},
        ),
        ScheduledJob(
            job_id="weekly-compliance",
            name="Generate Weekly Compliance Report",
            job_type="generate_compliance_report",
            cron_expression="0 4 * * 1",
            tenant_id="*",
            queue="low",
            payload={"report_type": "compliance", "period_type": "weekly"},
        ),
        # Monthly 1st day 5am UTC
        ScheduledJob(
            job_id="monthly-billing",
            name="Process Monthly Subscription Renewal",
            job_type="process_subscription_renewal",
            cron_expression="0 5 1 * *",
            tenant_id="*",
            queue="critical",
        ),
        ScheduledJob(
            job_id="monthly-invoices",
            name="Generate Monthly Invoices",
            job_type="generate_invoice",
            cron_expression="0 5 1 * *",
            tenant_id="*",
            queue="normal",
        ),
    ]

    def __init__(self, redis_url: str = None):
        """Initialize scheduler.

        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis: Optional[redis.Redis] = None
        self.is_leader = False
        self._scheduler_id = str(uuid.uuid4())
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Connect to Redis."""
        self.redis = await redis.from_url(self.redis_url, decode_responses=True)
        logger.info(f"Connected to Redis: {self.redis_url}")

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()

    async def start(self) -> None:
        """Start the scheduler (attempts leader election)."""
        logger.info("Starting scheduler...")
        await self.connect()

        self._running = True
        self._loop_task = asyncio.create_task(self._run_scheduler_loop())

        try:
            await self._loop_task
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")

    async def stop(self) -> None:
        """Stop the scheduler."""
        logger.info("Stopping scheduler...")
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        await self.disconnect()

    async def _run_scheduler_loop(self) -> None:
        """Main scheduler loop: leader election + job scheduling."""
        while self._running:
            try:
                # 1. Attempt leader election (10 second TTL)
                self.is_leader = await self._try_become_leader()

                if self.is_leader:
                    logger.info("Scheduler became leader")
                    # Process scheduled jobs
                    await self._process_scheduled_jobs()
                else:
                    logger.debug("Not scheduler leader, waiting...")

                # Sleep before next attempt
                await asyncio.sleep(60)  # Check every minute

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _try_become_leader(self) -> bool:
        """Attempt to acquire leadership lock.

        Only one scheduler runs at a time using Redis SET NX.

        Returns:
            True if acquired leadership, False otherwise
        """
        # SET NX with expiry - simple distributed lock
        acquired = await self.redis.set(
            "scheduler:leader",
            self._scheduler_id,
            nx=True,
            ex=30,  # 30 second TTL
        )
        return acquired is not None

    async def _process_scheduled_jobs(self) -> None:
        """Check all scheduled jobs and queue if due."""
        now = datetime.now(timezone.utc)

        for job_def in self.BUILTIN_SCHEDULES:
            if not job_def.enabled:
                continue

            # Get last run time from Redis
            last_run_key = f"scheduler:last_run:{job_def.job_id}"
            last_run_str = await self.redis.get(last_run_key)
            last_run = datetime.fromisoformat(last_run_str) if last_run_str else None

            # Check if job is due
            is_due = self._is_job_due(job_def.cron_expression, last_run)

            if is_due:
                logger.info(f"Scheduling job: {job_def.name}")
                await self._queue_scheduled_job(job_def, now)
                # Record that we ran it
                await self.redis.set(last_run_key, now.isoformat(), ex=86400)

    def _is_job_due(self, cron_expr: str, last_run: Optional[datetime]) -> bool:
        """Check if a cron job is due to run.

        Args:
            cron_expr: 5-field cron expression
            last_run: Last execution time, or None if never run

        Returns:
            True if job should run now
        """
        try:
            now = datetime.now(timezone.utc)

            # Create croniter from cron expression
            # It uses now as reference point to determine next run
            cron = croniter(cron_expr, now)
            last_execution = cron.get_prev(datetime)

            # Job is due if:
            # 1. Never run before, OR
            # 2. Last execution time is after our last_run time
            if last_run is None:
                return True

            return last_execution > last_run

        except Exception as e:
            logger.error(f"Error checking cron {cron_expr}: {e}")
            return False

    async def _queue_scheduled_job(
        self,
        job_def: ScheduledJob,
        now: datetime,
    ) -> None:
        """Queue a scheduled job for all tenants.

        Args:
            job_def: ScheduledJob definition
            now: Current time
        """
        # Import here to avoid circular imports
        from shared.workers.base import JobQueue, QueueLevel

        job_queue = JobQueue(self.redis_url)
        await job_queue.connect()

        try:
            if job_def.tenant_id == "*":
                # Queue for all tenants
                # For this, we need to get all tenant IDs from database
                # In production, fetch from tenant service
                tenant_ids = await self._get_all_tenant_ids()
                logger.info(f"Queueing {job_def.name} for {len(tenant_ids)} tenants")

                for tenant_id in tenant_ids:
                    payload = self._prepare_payload(job_def.payload, now)
                    await job_queue.enqueue(
                        tenant_id=tenant_id,
                        job_type=job_def.job_type,
                        payload=payload,
                        queue=QueueLevel(job_def.queue),
                        metadata={"scheduled": True, "scheduler_run": now.isoformat()},
                    )
            else:
                # Queue for specific tenant
                payload = self._prepare_payload(job_def.payload, now)
                await job_queue.enqueue(
                    tenant_id=job_def.tenant_id,
                    job_type=job_def.job_type,
                    payload=payload,
                    queue=QueueLevel(job_def.queue),
                    metadata={"scheduled": True, "scheduler_run": now.isoformat()},
                )

        finally:
            await job_queue.disconnect()

    def _prepare_payload(
        self,
        payload: Dict[str, Any],
        now: datetime,
    ) -> Dict[str, Any]:
        """Prepare job payload by replacing template variables.

        Args:
            payload: Base payload with possible template variables
            now: Current datetime for replacements

        Returns:
            Prepared payload
        """
        prepared = {}

        for key, value in payload.items():
            if value == "TODAY":
                prepared[key] = now.date().isoformat()
            elif value == "NOW":
                prepared[key] = now.isoformat()
            elif isinstance(value, str) and value.startswith("DATETIME_"):
                # e.g., DATETIME_-7DAYS
                prepared[key] = value  # Keep for handler to process
            else:
                prepared[key] = value

        return prepared

    async def _get_all_tenant_ids(self) -> List[str]:
        """Get all active tenant IDs.

        In production, this must call the tenant service API to get authoritative
        list of active tenants. Wildcard (*) jobs should only run once per tenant,
        not be silently dropped.

        Returns:
            List of tenant IDs (or raises exception if tenant service unavailable)

        Raises:
            RuntimeError: If tenant service is unavailable
        """
        # CRITICAL: Must call tenant service in production
        # TODO: Implement actual tenant service call
        # For development, raise error to prevent silent failures
        logger.error("Tenant service call not implemented; wildcard (*) jobs will be skipped")

        # In development, return a hardcoded list for testing
        import os
        if os.getenv("ENVIRONMENT", "development") == "development":
            return ["dev-tenant-1", "dev-tenant-2"]

        # In production, this must be implemented
        raise RuntimeError("Tenant service not configured; cannot queue jobs for all tenants")

    # ========================================================================
    # Public API for custom schedules
    # ========================================================================

    async def add_schedule(
        self,
        name: str,
        job_type: str,
        cron_expression: str,
        tenant_id: str = "*",
        payload: Optional[Dict[str, Any]] = None,
        queue: str = "normal",
    ) -> str:
        """Add a custom scheduled job.

        Args:
            name: Human-readable name
            job_type: Job type (must have handler)
            cron_expression: 5-field cron expression
            tenant_id: "*" for all tenants or specific ID
            payload: Job payload
            queue: Queue level (critical, high, normal, low)

        Returns:
            Schedule ID
        """
        schedule_id = str(uuid.uuid4())

        schedule_data = {
            "id": schedule_id,
            "name": name,
            "job_type": job_type,
            "cron_expression": cron_expression,
            "tenant_id": tenant_id,
            "payload": json.dumps(payload or {}),
            "queue": queue,
            "enabled": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        await self.redis.hset(f"schedule:{schedule_id}", mapping=schedule_data)
        logger.info(f"Added custom schedule: {name} ({schedule_id})")

        return schedule_id

    async def disable_schedule(self, schedule_id: str) -> bool:
        """Disable a schedule.

        Args:
            schedule_id: Schedule ID

        Returns:
            True if disabled, False if not found
        """
        if await self.redis.hexists(f"schedule:{schedule_id}", "id"):
            await self.redis.hset(f"schedule:{schedule_id}", "enabled", False)
            logger.info(f"Disabled schedule: {schedule_id}")
            return True
        return False

    async def get_schedules(self) -> List[ScheduledJob]:
        """Get all active schedules (builtin + custom).

        Returns:
            List of ScheduledJob objects
        """
        schedules = list(self.BUILTIN_SCHEDULES)

        # Also get custom schedules from Redis
        # Pattern: schedule:*
        keys = await self.redis.keys("schedule:*")
        for key in keys:
            data = await self.redis.hgetall(key)
            if data:
                try:
                    schedule = ScheduledJob(
                        job_id=data["id"],
                        name=data["name"],
                        job_type=data["job_type"],
                        cron_expression=data["cron_expression"],
                        tenant_id=data.get("tenant_id", "*"),
                        payload=json.loads(data.get("payload", "{}")),
                        queue=data.get("queue", "normal"),
                        enabled=data.get("enabled") != "False",
                    )
                    schedules.append(schedule)
                except Exception as e:
                    logger.error(f"Error deserializing schedule {key}: {e}")

        return schedules
