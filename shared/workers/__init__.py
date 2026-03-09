"""
Priya Global — Background Workers & Job Queue

Production-grade async job queue with Redis, priority levels, scheduling, and retries.

Usage in any service:
    from shared.workers.base import JobQueue, Worker, JobContext, JobStatus, QueueLevel
    from shared.workers.handlers import send_email, process_subscription_renewal
    from shared.workers.scheduler import JobScheduler

    # Enqueue jobs
    job_queue = JobQueue()
    await job_queue.connect()

    job_id = await job_queue.enqueue(
        tenant_id="tenant-123",
        job_type="send_email",
        payload={"to": "user@example.com", "template": "welcome"},
        queue=QueueLevel.HIGH,
    )

    # Start worker (typically in separate process)
    worker = Worker(job_queue)
    worker.register_handler("send_email", send_email)
    worker.register_handler("process_subscription_renewal", process_subscription_renewal)
    await worker.start()

    # Start scheduler (typically in separate process)
    scheduler = JobScheduler()
    await scheduler.start()
"""

from shared.workers.base import (
    JobContext,
    JobQueue,
    JobResult,
    JobStatus,
    QueueLevel,
    Worker,
)
from shared.workers.handlers import (
    analyze_sentiment,
    archive_old_conversations,
    cleanup_expired_sessions,
    generate_ai_response,
    generate_analytics_report,
    generate_compliance_report,
    generate_invoice,
    gdpr_data_deletion,
    process_inbound_message,
    process_payment_webhook,
    process_subscription_renewal,
    process_usage_billing,
    rotate_api_keys,
    send_bulk_notification,
    send_email,
    send_push_notification,
    send_sms,
    send_whatsapp_template,
    train_knowledge_base,
    calculate_conversion_rates,
)
from shared.workers.scheduler import JobScheduler, ScheduledJob

__all__ = [
    "JobContext",
    "JobQueue",
    "JobResult",
    "JobStatus",
    "QueueLevel",
    "Worker",
    "JobScheduler",
    "ScheduledJob",
    # Handlers
    "send_email",
    "send_sms",
    "send_whatsapp_template",
    "process_inbound_message",
    "generate_ai_response",
    "train_knowledge_base",
    "analyze_sentiment",
    "aggregate_daily_metrics",
    "generate_analytics_report",
    "calculate_conversion_rates",
    "send_push_notification",
    "send_bulk_notification",
    "cleanup_expired_sessions",
    "archive_old_conversations",
    "rotate_api_keys",
    "gdpr_data_deletion",
    "generate_compliance_report",
    "process_subscription_renewal",
    "process_usage_billing",
    "process_payment_webhook",
    "generate_invoice",
]
