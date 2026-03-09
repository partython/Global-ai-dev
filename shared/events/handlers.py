"""
Common event handlers used across multiple services.

These handlers provide:
- Audit logging for compliance
- Metrics collection for Prometheus
- Notification dispatch to notification service
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("priya.event_handlers")


# ============================================================================
# AUDIT LOGGING HANDLER
# ============================================================================

async def log_event_handler(event_data: Dict[str, Any]) -> None:
    """
    Log all events for audit trail.
    Used for compliance (GDPR, CCPA, etc.)

    Args:
        event_data: Event payload from EventBus
    """
    try:
        # In production, this would write to a compliance database
        logger.info(
            f"Audit: {event_data.get('event_type')} "
            f"tenant={event_data.get('tenant_id')} "
            f"timestamp={datetime.now(timezone.utc).isoformat()}"
        )

        # TODO: Write to audit_log table
        # async with db.tenant_connection(tenant_id) as conn:
        #     await conn.execute(
        #         """
        #         INSERT INTO audit_log (event_type, event_data, tenant_id, created_at)
        #         VALUES ($1, $2, $3, NOW())
        #         """,
        #         event_data.get("event_type"),
        #         json.dumps(event_data),
        #         tenant_id,
        #     )

    except Exception as e:
        logger.error(f"Failed to log event: {e}")


# ============================================================================
# METRICS HANDLER (PROMETHEUS)
# ============================================================================

# In-memory metrics counters (would be replaced by proper Prometheus in production)
_event_counters: Dict[str, int] = {}
_event_timers: Dict[str, float] = {}


async def metrics_event_handler(event_data: Dict[str, Any]) -> None:
    """
    Update Prometheus metrics based on events.
    Tracks:
    - Event counts by type
    - Performance metrics

    Args:
        event_data: Event payload from EventBus
    """
    try:
        event_type = event_data.get("event_type", "unknown")

        # Increment counter for this event type
        key = f"event_{event_type}_total"
        _event_counters[key] = _event_counters.get(key, 0) + 1

        # TODO: In production, use prometheus_client library
        # from prometheus_client import Counter
        # event_counter = Counter(
        #     "priya_events_total",
        #     "Total events by type",
        #     ["event_type"],
        # )
        # event_counter.labels(event_type=event_type).inc()

        # Log metrics every 100 events
        total = sum(_event_counters.values())
        if total % 100 == 0:
            logger.info(f"Total events published: {total}")

    except Exception as e:
        logger.error(f"Failed to update metrics: {e}")


# ============================================================================
# NOTIFICATION DISPATCH HANDLER
# ============================================================================

async def notification_dispatch_handler(event_data: Dict[str, Any]) -> None:
    """
    Route events that require notifications to the notification service.
    Handles:
    - User registration confirmations
    - Payment confirmations
    - Channel alerts
    - Escalation notifications

    Args:
        event_data: Event payload from EventBus
    """
    try:
        event_type = event_data.get("event_type")
        tenant_id = event_data.get("tenant_id")

        # Determine if this event requires a notification
        notification_config = {
            "user_registered": {
                "template": "welcome_email",
                "channel": "email",
            },
            "user_login": {
                "template": "login_alert",
                "channel": "email",
                "condition": "suspicious_location",  # Only if needed
            },
            "payment_received": {
                "template": "payment_confirmation",
                "channel": "email",
            },
            "payment_failed": {
                "template": "payment_failed",
                "channel": "email",
            },
            "conversation_escalated": {
                "template": "escalation_alert",
                "channel": "internal",
            },
            "channel_disconnected": {
                "template": "channel_alert",
                "channel": "internal",
            },
        }

        config = notification_config.get(event_type)
        if not config:
            logger.debug(f"No notification needed for {event_type}")
            return

        # Build notification payload
        notification_payload = {
            "tenant_id": tenant_id,
            "template": config.get("template"),
            "channel": config.get("channel"),
            "data": event_data,
            "priority": "high" if "failed" in event_type else "normal",
        }

        # Route to notification service
        await _dispatch_notification(notification_payload)

    except Exception as e:
        logger.error(f"Failed to dispatch notification: {e}")


async def _dispatch_notification(payload: Dict[str, Any]) -> None:
    """
    Send notification to the notification service via HTTP.

    Args:
        payload: Notification payload
    """
    try:
        import httpx
        from ..core.service_registry import get_registry

        # Resolve notification service URL from registry (supports local, docker, kubernetes)
        registry = get_registry()
        notification_url = registry.get_service_url("notification")
        notification_endpoint = f"{notification_url}/api/v1/notifications/send"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                notification_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                logger.debug(f"Notification dispatched: {payload.get('template')}")
            else:
                logger.warning(
                    f"Notification dispatch failed: {response.status_code} {response.text}"
                )

    except Exception as e:
        logger.error(f"Error dispatching notification: {e}")


# ============================================================================
# ANALYTICS AGGREGATION HANDLER
# ============================================================================

async def analytics_aggregation_handler(event_data: Dict[str, Any]) -> None:
    """
    Aggregate events for analytics service.
    Collects metrics for dashboards and reports.

    Args:
        event_data: Event payload from EventBus
    """
    try:
        event_type = event_data.get("event_type")
        tenant_id = event_data.get("tenant_id")

        # Events to aggregate
        aggregatable_events = [
            "message_sent",
            "message_received",
            "conversation_started",
            "conversation_ended",
            "payment_received",
            "lead_created",
        ]

        if event_type not in aggregatable_events:
            return

        # TODO: Write to analytics table for aggregation
        # async with db.tenant_connection(tenant_id) as conn:
        #     await conn.execute(
        #         """
        #         INSERT INTO event_analytics (event_type, event_data, tenant_id, created_at)
        #         VALUES ($1, $2, $3, NOW())
        #         """,
        #         event_type,
        #         json.dumps(event_data),
        #         tenant_id,
        #     )

        logger.debug(f"Analytics event aggregated: {event_type}")

    except Exception as e:
        logger.error(f"Failed to aggregate analytics: {e}")


# ============================================================================
# AI TRAINING DATA HANDLER
# ============================================================================

async def ai_training_data_handler(event_data: Dict[str, Any]) -> None:
    """
    Collect approved conversation data for AI fine-tuning.

    Args:
        event_data: Event payload from EventBus
    """
    try:
        event_type = event_data.get("event_type")

        # Only process conversation and feedback events
        if event_type not in ["conversation_ended", "feedback_received"]:
            return

        # TODO: Store in training data queue
        # async with db.tenant_connection(tenant_id) as conn:
        #     await conn.execute(
        #         """
        #         INSERT INTO ai_training_queue (event_type, event_data, status, created_at)
        #         VALUES ($1, $2, 'pending_approval', NOW())
        #         """,
        #         event_type,
        #         json.dumps(event_data),
        #     )

        logger.debug(f"AI training data queued: {event_type}")

    except Exception as e:
        logger.error(f"Failed to queue AI training data: {e}")


# ============================================================================
# COMPLIANCE/GDPR HANDLER
# ============================================================================

async def compliance_handler(event_data: Dict[str, Any]) -> None:
    """
    Ensure GDPR and CCPA compliance.
    - PII masking in logs
    - Data retention policies
    - Right to be forgotten tracking

    Args:
        event_data: Event payload from EventBus
    """
    try:
        event_type = event_data.get("event_type")

        # Events to monitor for compliance
        compliance_events = [
            "user_registered",
            "user_login",
            "payment_received",
        ]

        if event_type not in compliance_events:
            return

        # Log for compliance audit
        logger.info(
            f"Compliance event: {event_type} "
            f"tenant={event_data.get('tenant_id')} "
            f"timestamp={datetime.now(timezone.utc).isoformat()}"
        )

        # TODO: Write to compliance_audit table
        # async with db.admin_connection() as conn:
        #     await conn.execute(
        #         """
        #         INSERT INTO compliance_audit
        #         (event_type, tenant_id, user_id, action, details, created_at)
        #         VALUES ($1, $2, $3, $4, $5, NOW())
        #         """,
        #         event_type,
        #         event_data.get("tenant_id"),
        #         event_data.get("user_id"),
        #         "event_received",
        #         json.dumps(event_data),
        #     )

    except Exception as e:
        logger.error(f"Failed compliance check: {e}")


# ============================================================================
# HEALTH CHECK HANDLER
# ============================================================================

async def health_check_handler(event_data: Dict[str, Any]) -> None:
    """
    Handle health check events from services.
    Updates service status and availability metrics.

    Args:
        event_data: Event payload from EventBus
    """
    try:
        service_name = event_data.get("service_name")
        status = event_data.get("status", "unknown")

        logger.debug(f"Health check from {service_name}: {status}")

        # TODO: Update service_health table
        # async with db.admin_connection() as conn:
        #     await conn.execute(
        #         """
        #         INSERT INTO service_health
        #         (service_name, status, metrics, checked_at)
        #         VALUES ($1, $2, $3, NOW())
        #         ON CONFLICT (service_name) DO UPDATE SET
        #             status = $2, metrics = $3, checked_at = NOW()
        #         """,
        #         service_name,
        #         status,
        #         json.dumps(event_data.get("metrics", {})),
        #     )

    except Exception as e:
        logger.error(f"Failed to handle health check: {e}")


# ============================================================================
# DEPLOYMENT EVENT HANDLER
# ============================================================================

async def deployment_event_handler(event_data: Dict[str, Any]) -> None:
    """
    Handle deployment events (new version, rollout, rollback).
    Tracks version changes and deployment status.

    Args:
        event_data: Event payload from EventBus
    """
    try:
        service_name = event_data.get("service_name")
        version = event_data.get("version")
        action = event_data.get("action")  # deploy, rollback, etc.

        logger.info(
            f"Deployment event: {service_name} {action} version {version}"
        )

        # TODO: Update deployment tracking
        # async with db.admin_connection() as conn:
        #     await conn.execute(
        #         """
        #         INSERT INTO deployment_log
        #         (service_name, version, action, details, deployed_at)
        #         VALUES ($1, $2, $3, $4, NOW())
        #         """,
        #         service_name,
        #         version,
        #         action,
        #         json.dumps(event_data),
        #     )

    except Exception as e:
        logger.error(f"Failed to handle deployment event: {e}")


# ============================================================================
# HANDLER REGISTRY
# ============================================================================

# Map event types to default handlers that should always be attached
DEFAULT_HANDLERS = {
    # Audit logging
    "user_registered": [log_event_handler, metrics_event_handler, compliance_handler, notification_dispatch_handler],
    "user_login": [log_event_handler, compliance_handler],
    "payment_received": [log_event_handler, metrics_event_handler, notification_dispatch_handler],
    "payment_failed": [log_event_handler, notification_dispatch_handler],

    # Conversation events
    "conversation_started": [log_event_handler, metrics_event_handler, analytics_aggregation_handler],
    "conversation_ended": [log_event_handler, metrics_event_handler, analytics_aggregation_handler, ai_training_data_handler],
    "conversation_escalated": [log_event_handler, notification_dispatch_handler],

    # Message events
    "message_sent": [metrics_event_handler, analytics_aggregation_handler],
    "message_received": [metrics_event_handler, analytics_aggregation_handler],

    # Lead events
    "lead_created": [log_event_handler, metrics_event_handler, analytics_aggregation_handler],

    # Channel events
    "channel_disconnected": [log_event_handler, notification_dispatch_handler],

    # AI events
    "ai_response_generated": [metrics_event_handler],

    # Health/Deployment
    "health_check": [health_check_handler],
    "deployment_event": [deployment_event_handler],
}


def get_default_handlers(event_type: str):
    """Get default handlers for an event type."""
    return DEFAULT_HANDLERS.get(event_type, [log_event_handler, metrics_event_handler])
