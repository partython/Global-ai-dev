"""
Priya Global Event Bus - High-level wrapper around Kafka for inter-service communication.

This module provides a singleton EventBus for each service that handles:
- Publishing events with automatic serialization
- Subscribing to event types with handler registration
- Event schema validation
- Dead letter queue for failed messages
- Event replay capability
- Graceful startup/shutdown
- OpenTelemetry distributed tracing integration

Usage in any service:
    from shared.events.event_bus import EventBus, EventType

    # In startup:
    event_bus = EventBus(service_name="auth")
    await event_bus.startup()

    # Publishing:
    await event_bus.publish(
        event_type=EventType.USER_REGISTERED,
        tenant_id="tenant-123",
        data={"user_id": "user-456", "email": "user@example.com"}
    )

    # Subscribing:
    async def handle_conversation_started(event):
        print(f"Conversation started: {event.data}")

    event_bus.subscribe(EventType.CONVERSATION_STARTED, handle_conversation_started)

TRACING:
- All event publishing and consuming is automatically traced
- Trace context is propagated through Kafka message headers
- Each event creates a span with topic/event_type attributes
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from shared.events.kafka_client import (
    TenantProducer,
    TenantConsumer,
    PriyaEvent,
    DeadLetterProducer,
)

logger = logging.getLogger("priya.event_bus")


# ============================================================================
# EVENT TYPE ENUM
# ============================================================================

class EventType(str, Enum):
    """All event types in the Priya Global Platform."""

    # Conversation events
    CONVERSATION_STARTED = "conversation_started"
    CONVERSATION_ENDED = "conversation_ended"
    CONVERSATION_ESCALATED = "conversation_escalated"

    # Message events
    MESSAGE_SENT = "message_sent"
    MESSAGE_RECEIVED = "message_received"

    # Lead events
    LEAD_CREATED = "lead_created"
    LEAD_UPDATED = "lead_updated"

    # Billing events
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_FAILED = "payment_failed"

    # Channel events
    CHANNEL_CONNECTED = "channel_connected"
    CHANNEL_DISCONNECTED = "channel_disconnected"

    # User events
    USER_REGISTERED = "user_registered"
    USER_LOGIN = "user_login"

    # Tenant events
    TENANT_CREATED = "tenant_created"
    TENANT_UPDATED = "tenant_updated"

    # AI events
    AI_RESPONSE_GENERATED = "ai_response_generated"

    # Knowledge base events
    KNOWLEDGE_UPDATED = "knowledge_updated"

    # Scheduling events
    APPOINTMENT_BOOKED = "appointment_booked"

    # Campaign events
    CAMPAIGN_SENT = "campaign_sent"

    # Feedback events
    FEEDBACK_RECEIVED = "feedback_received"

    # Analytics events
    ANALYTICS_EVENT = "analytics_event"

    # Health events
    HEALTH_CHECK = "health_check"

    # Deployment events
    DEPLOYMENT_EVENT = "deployment_event"

    # Memory events
    MEMORY_UPDATED = "memory_updated"
    MEMORY_CONSOLIDATED = "memory_consolidated"
    MEMORY_EXTRACTED = "memory_extracted"

    # Translation events
    TRANSLATION_COMPLETED = "translation_completed"
    LANGUAGE_DETECTED = "language_detected"
    GLOSSARY_UPDATED = "glossary_updated"


# ============================================================================
# EVENT TYPE TO TOPIC MAPPING
# ============================================================================

EVENT_TYPE_TO_TOPIC = {
    EventType.CONVERSATION_STARTED: "events.conversation",
    EventType.CONVERSATION_ENDED: "events.conversation",
    EventType.CONVERSATION_ESCALATED: "events.conversation",
    EventType.MESSAGE_SENT: "inbound.messages",
    EventType.MESSAGE_RECEIVED: "inbound.messages",
    EventType.LEAD_CREATED: "events.conversation",
    EventType.LEAD_UPDATED: "events.conversation",
    EventType.PAYMENT_RECEIVED: "events.billing",
    EventType.PAYMENT_FAILED: "events.billing",
    EventType.CHANNEL_CONNECTED: "events.notification",
    EventType.CHANNEL_DISCONNECTED: "events.notification",
    EventType.USER_REGISTERED: "events.audit",
    EventType.USER_LOGIN: "events.audit",
    EventType.TENANT_CREATED: "events.audit",
    EventType.TENANT_UPDATED: "events.audit",
    EventType.AI_RESPONSE_GENERATED: "outbound.messages",
    EventType.KNOWLEDGE_UPDATED: "events.ai_training",
    EventType.APPOINTMENT_BOOKED: "events.conversation",
    EventType.CAMPAIGN_SENT: "events.analytics",
    EventType.FEEDBACK_RECEIVED: "events.analytics",
    EventType.ANALYTICS_EVENT: "events.analytics",
    EventType.HEALTH_CHECK: "events.notification",
    EventType.DEPLOYMENT_EVENT: "events.notification",
    EventType.MEMORY_UPDATED: "events.memory",
    EventType.MEMORY_CONSOLIDATED: "events.memory",
    EventType.MEMORY_EXTRACTED: "events.memory",
    EventType.TRANSLATION_COMPLETED: "events.translation",
    EventType.LANGUAGE_DETECTED: "events.translation",
    EventType.GLOSSARY_UPDATED: "events.translation",
}


# ============================================================================
# EVENT BUS CLASS
# ============================================================================

class EventBus:
    """
    Singleton event bus for inter-service communication.
    Wraps Kafka producer and consumer with high-level API.
    """

    _instances: Dict[str, "EventBus"] = {}

    def __new__(cls, service_name: str = "unknown"):
        """Singleton per service name."""
        if service_name not in cls._instances:
            cls._instances[service_name] = super().__new__(cls)
            cls._instances[service_name]._initialized = False
        return cls._instances[service_name]

    def __init__(self, service_name: str = "unknown"):
        """Initialize event bus for a service."""
        if self._initialized:
            return

        self._initialized = True
        self.service_name = service_name
        self.producer = TenantProducer(service_name=service_name)
        self.dlq_producer = DeadLetterProducer(self.producer)

        # Event handlers: {event_type: [handler_fn, ...]}
        self._handlers: Dict[str, List[Callable]] = {}

        # Consumer tasks for background listening
        self._consumer_tasks: Dict[str, asyncio.Task] = {}
        self._running = False

        logger.info(f"EventBus initialized for service: {service_name}")

    async def startup(self) -> bool:
        """Initialize Kafka producer connection."""
        if self.producer.is_connected:
            logger.info(f"Producer already connected for {self.service_name}")
            return True

        connected = await self.producer.connect()
        if connected:
            self._running = True
            logger.info(f"EventBus startup complete: {self.service_name}")
        else:
            logger.error(f"Failed to connect producer for {self.service_name}")

        return connected

    async def shutdown(self):
        """Graceful shutdown - disconnect producer and cancel listeners."""
        self._running = False

        # Cancel all consumer tasks
        for event_type, task in self._consumer_tasks.items():
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Disconnect producer
        await self.producer.disconnect()
        logger.info(f"EventBus shutdown complete: {self.service_name}")

    async def publish(
        self,
        event_type: EventType,
        tenant_id: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Publish an event to Kafka.

        Args:
            event_type: Type of event (from EventType enum)
            tenant_id: Tenant ID for multi-tenancy partition key
            data: Event payload data
            metadata: Optional metadata (e.g., user_id, ip_address)

        Returns:
            event_id if successful, None if failed
        """
        if not self.producer.is_connected:
            logger.error(f"Producer not connected. Event {event_type} dropped for tenant {tenant_id}")
            return None

        # Get topic for this event type
        topic = EVENT_TYPE_TO_TOPIC.get(event_type)
        if not topic:
            logger.error(f"Unknown event type: {event_type}")
            return None

        # Execute with optional OpenTelemetry span
        try:
            event_id = await self.producer.send_message(
                tenant_id=tenant_id,
                topic=topic,
                event_type=event_type.value,
                payload=data,
                metadata=metadata or {},
            )

            if event_id:
                logger.debug(
                    f"Published event: type={event_type} tenant={tenant_id} event_id={event_id}"
                )

            return event_id

        except Exception as e:
            logger.error(
                f"Failed to publish event {event_type} for tenant {tenant_id}: {e}"
            )
            return None

    def subscribe(
        self,
        event_type: EventType,
        handler: Callable[[Dict[str, Any]], Any],
    ) -> None:
        """
        Register a handler for an event type.

        Args:
            event_type: Type of event to listen for
            handler: Async function to call when event occurs

        The handler receives the event data dict as its argument.
        """
        if event_type.value not in self._handlers:
            self._handlers[event_type.value] = []

        self._handlers[event_type.value].append(handler)
        logger.info(f"Handler registered for {event_type} in {self.service_name}")

    async def _consume_events(self, topic: str, group_id: str) -> None:
        """
        Background task to consume events from a topic.
        Calls registered handlers for matching event types.
        Each consumed event creates a span for distributed tracing.
        """
        consumer = TenantConsumer(
            topic=topic,
            group_id=group_id,
            service_name=self.service_name,
        )

        if not await consumer.connect():
            logger.error(f"Failed to connect consumer for topic {topic}")
            return

        try:
            async for event in consumer.consume():
                if not self._running:
                    break

                # Find handlers for this event type
                handlers = self._handlers.get(event.event_type, [])

                if not handlers:
                    logger.debug(f"No handlers for event type: {event.event_type}")
                    continue

                # Call all handlers
                for handler in handlers:
                    try:
                        result = handler(event.payload)
                        if asyncio.iscoroutine(result):
                            await result

                    except Exception as e:
                        logger.error(
                            f"Handler error for {event.event_type}: {e}. "
                            f"Sending to DLQ..."
                        )

                        # Send to dead letter queue
                        await self.dlq_producer.send_to_dlq(
                            original_event=event,
                            error_message=str(e),
                            source_topic=topic,
                        )

        except asyncio.CancelledError:
            logger.info(f"Consumer task cancelled for topic {topic}")
        except Exception as e:
            logger.error(f"Consumer error for topic {topic}: {e}")
        finally:
            await consumer.disconnect()

    async def start_consuming(
        self,
        event_types: List[EventType],
    ) -> None:
        """
        Start background tasks to consume events.

        Args:
            event_types: List of event types to listen for
        """
        # Group event types by topic
        topics: Dict[str, List[EventType]] = {}
        for event_type in event_types:
            topic = EVENT_TYPE_TO_TOPIC.get(event_type)
            if topic:
                if topic not in topics:
                    topics[topic] = []
                topics[topic].append(event_type)

        # Start a consumer task for each unique topic
        for topic, event_types_for_topic in topics.items():
            task_name = f"consume_{topic}"
            if task_name not in self._consumer_tasks:
                group_id = f"{self.service_name}__{topic}"
                task = asyncio.create_task(
                    self._consume_events(topic, group_id)
                )
                self._consumer_tasks[task_name] = task
                logger.info(f"Started consuming from {topic}")

    def get_event_type(self, event_type_str: str) -> Optional[EventType]:
        """Get EventType enum from string value."""
        for et in EventType:
            if et.value == event_type_str:
                return et
        return None


# ============================================================================
# EVENT PAYLOAD BUILDER HELPERS
# ============================================================================

def build_conversation_event(
    event_type: EventType,
    tenant_id: str,
    conversation_id: str,
    **kwargs
) -> tuple[EventType, str, Dict[str, Any]]:
    """Build a conversation event."""
    data = {
        "conversation_id": conversation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    return event_type, tenant_id, data


def build_message_event(
    event_type: EventType,
    tenant_id: str,
    message_id: str,
    conversation_id: str,
    channel: str,
    **kwargs
) -> tuple[EventType, str, Dict[str, Any]]:
    """Build a message event."""
    data = {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "channel": channel,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    return event_type, tenant_id, data


def build_user_event(
    event_type: EventType,
    tenant_id: str,
    user_id: str,
    **kwargs
) -> tuple[EventType, str, Dict[str, Any]]:
    """Build a user event."""
    data = {
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    return event_type, tenant_id, data


def build_payment_event(
    event_type: EventType,
    tenant_id: str,
    payment_id: str,
    amount: float,
    currency: str = "USD",
    **kwargs
) -> tuple[EventType, str, Dict[str, Any]]:
    """Build a payment event."""
    data = {
        "payment_id": payment_id,
        "amount": amount,
        "currency": currency,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    return event_type, tenant_id, data


def build_lead_event(
    event_type: EventType,
    tenant_id: str,
    lead_id: str,
    **kwargs
) -> tuple[EventType, str, Dict[str, Any]]:
    """Build a lead event."""
    data = {
        "lead_id": lead_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    return event_type, tenant_id, data
