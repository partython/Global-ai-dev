"""
Priya Global — Tenant-Partitioned Kafka Event Streaming

All messages are partitioned by tenant_id ensuring:
  1. Messages from the same tenant are always processed in order
  2. No cross-tenant message interleaving in consumer processing
  3. AI Engine gets clean context boundaries between tenants
  4. Horizontal scaling — add partitions to scale specific tenants

Topic Architecture:
  priya.inbound.messages     — Customer messages from all channels → AI Engine
  priya.outbound.messages    — AI responses → Channel services for delivery
  priya.events.conversation  — Conversation lifecycle events (created, closed, escalated)
  priya.events.analytics     — Analytics events (message_sent, message_received, etc.)
  priya.events.billing       — Usage metering events for Stripe
  priya.events.ai_training   — AI training data events (approved conversations for learning)
  priya.events.audit         — Compliance audit trail events
  priya.events.notification  — Internal notification events (alerts, reminders)

KRaft mode (no Zookeeper) — production standard since Kafka 3.3+

Usage in any service:
    from shared.events.kafka_client import TenantProducer, TenantConsumer

    # Producer
    producer = TenantProducer()
    await producer.connect()
    await producer.send_message(
        tenant_id="abc123",
        topic="inbound.messages",
        event_type="whatsapp_message",
        payload={"from": "+91...", "text": "Hi"},
    )

    # Consumer
    consumer = TenantConsumer(topic="inbound.messages", group_id="ai-engine")
    await consumer.connect()
    async for event in consumer.consume():
        await process_event(event)
"""

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Set

logger = logging.getLogger("priya.events")

# ============================================================================
# CONFIGURATION
# ============================================================================

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
# Default to SASL_SSL for production security. Only use PLAINTEXT for local development.
KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")  # PLAINTEXT | SASL_SSL
KAFKA_SASL_MECHANISM = os.getenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512")  # PLAIN | SCRAM-SHA-256 | SCRAM-SHA-512
KAFKA_SASL_USERNAME = os.getenv("KAFKA_SASL_USERNAME", "")
KAFKA_SASL_PASSWORD = os.getenv("KAFKA_SASL_PASSWORD", "")
KAFKA_SSL_CAFILE = os.getenv("KAFKA_SSL_CAFILE", "")

# Validate security configuration
if KAFKA_SECURITY_PROTOCOL == "SASL_SSL":
    if not KAFKA_SASL_USERNAME or not KAFKA_SASL_PASSWORD:
        raise ValueError(
            "KAFKA_SECURITY_PROTOCOL=SASL_SSL requires KAFKA_SASL_USERNAME and KAFKA_SASL_PASSWORD to be set"
        )
    if not KAFKA_SASL_MECHANISM:
        raise ValueError(
            "KAFKA_SECURITY_PROTOCOL=SASL_SSL requires KAFKA_SASL_MECHANISM to be set"
        )

# Topic prefix
TOPIC_PREFIX = "priya"

# Consumer configuration
CONSUMER_MAX_POLL_RECORDS = int(os.getenv("KAFKA_MAX_POLL_RECORDS", "100"))
CONSUMER_SESSION_TIMEOUT_MS = int(os.getenv("KAFKA_SESSION_TIMEOUT_MS", "30000"))
CONSUMER_HEARTBEAT_INTERVAL_MS = int(os.getenv("KAFKA_HEARTBEAT_INTERVAL_MS", "10000"))
CONSUMER_AUTO_OFFSET_RESET = os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest")

# Producer configuration
PRODUCER_ACKS = os.getenv("KAFKA_PRODUCER_ACKS", "all")  # all = strongest durability
PRODUCER_RETRIES = int(os.getenv("KAFKA_PRODUCER_RETRIES", "3"))
PRODUCER_LINGER_MS = int(os.getenv("KAFKA_PRODUCER_LINGER_MS", "10"))
PRODUCER_BATCH_SIZE = int(os.getenv("KAFKA_PRODUCER_BATCH_SIZE", "16384"))
PRODUCER_COMPRESSION = os.getenv("KAFKA_PRODUCER_COMPRESSION", "lz4")


# ============================================================================
# TOPIC REGISTRY
# ============================================================================

TOPICS = {
    # Core message flow
    "inbound.messages": {
        "full_name": f"{TOPIC_PREFIX}.inbound.messages",
        "partitions": 12,
        "replication": 3,
        "retention_ms": 7 * 24 * 60 * 60 * 1000,   # 7 days
        "description": "Customer messages from all channels → AI Engine",
    },
    "outbound.messages": {
        "full_name": f"{TOPIC_PREFIX}.outbound.messages",
        "partitions": 12,
        "replication": 3,
        "retention_ms": 7 * 24 * 60 * 60 * 1000,
        "description": "AI responses → Channel services for delivery",
    },

    # Event streams
    "events.conversation": {
        "full_name": f"{TOPIC_PREFIX}.events.conversation",
        "partitions": 6,
        "replication": 3,
        "retention_ms": 30 * 24 * 60 * 60 * 1000,  # 30 days
        "description": "Conversation lifecycle (created, escalated, closed, rated)",
    },
    "events.analytics": {
        "full_name": f"{TOPIC_PREFIX}.events.analytics",
        "partitions": 6,
        "replication": 3,
        "retention_ms": 90 * 24 * 60 * 60 * 1000,  # 90 days
        "description": "Analytics events for dashboards and reporting",
    },
    "events.billing": {
        "full_name": f"{TOPIC_PREFIX}.events.billing",
        "partitions": 3,
        "replication": 3,
        "retention_ms": 365 * 24 * 60 * 60 * 1000, # 1 year
        "description": "Usage metering events for Stripe billing",
    },
    "events.ai_training": {
        "full_name": f"{TOPIC_PREFIX}.events.ai_training",
        "partitions": 3,
        "replication": 3,
        "retention_ms": 90 * 24 * 60 * 60 * 1000,
        "description": "Approved conversation data for AI fine-tuning",
    },
    "events.audit": {
        "full_name": f"{TOPIC_PREFIX}.events.audit",
        "partitions": 3,
        "replication": 3,
        "retention_ms": 365 * 24 * 60 * 60 * 1000, # 1 year (compliance)
        "description": "Immutable audit trail for compliance (GDPR, CCPA, etc.)",
    },
    "events.notification": {
        "full_name": f"{TOPIC_PREFIX}.events.notification",
        "partitions": 6,
        "replication": 3,
        "retention_ms": 7 * 24 * 60 * 60 * 1000,
        "description": "Internal notifications (alerts, reminders, webhooks)",
    },
}


# ============================================================================
# EVENT ENVELOPE
# ============================================================================

@dataclass
class PriyaEvent:
    """
    Standard event envelope for all Kafka messages.
    Every event carries tenant_id for partitioning and tracing.
    """
    event_id: str = ""
    tenant_id: str = ""
    event_type: str = ""
    source_service: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    correlation_id: str = ""

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type,
            "source_service": self.source_service,
            "payload": self.payload,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
        }

    def to_json(self) -> bytes:
        return json.dumps(self.to_dict(), default=str).encode("utf-8")

    @classmethod
    def from_json(cls, data: bytes) -> "PriyaEvent":
        parsed = json.loads(data.decode("utf-8"))
        return cls(**parsed)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PriyaEvent":
        return cls(**data)


# ============================================================================
# SHARED KAFKA CONFIG BUILDER
# ============================================================================

def _build_kafka_config() -> Dict[str, Any]:
    """Build common Kafka configuration"""
    config = {
        "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS.split(","),
    }

    if KAFKA_SECURITY_PROTOCOL == "SASL_SSL":
        config["security_protocol"] = "SASL_SSL"
        config["sasl_mechanism"] = KAFKA_SASL_MECHANISM
        config["sasl_plain_username"] = KAFKA_SASL_USERNAME
        config["sasl_plain_password"] = KAFKA_SASL_PASSWORD
        if KAFKA_SSL_CAFILE:
            config["ssl_cafile"] = KAFKA_SSL_CAFILE

    return config


# ============================================================================
# TENANT PRODUCER
# ============================================================================

class TenantProducer:
    """
    Kafka producer with mandatory tenant-based partitioning.
    Messages from the same tenant always go to the same partition,
    guaranteeing ordered processing per tenant.
    """

    def __init__(self, service_name: str = "unknown"):
        self._producer = None
        self._connected = False
        self._service_name = service_name
        self._message_count = 0

    async def connect(self) -> bool:
        """Initialize Kafka producer"""
        try:
            from aiokafka import AIOKafkaProducer

            config = _build_kafka_config()
            self._producer = AIOKafkaProducer(
                **config,
                acks=PRODUCER_ACKS,
                retries=PRODUCER_RETRIES,
                linger_ms=PRODUCER_LINGER_MS,
                max_batch_size=PRODUCER_BATCH_SIZE,
                compression_type=PRODUCER_COMPRESSION,
                value_serializer=lambda v: v,  # We handle serialization
                key_serializer=lambda k: k.encode("utf-8") if isinstance(k, str) else k,
            )
            await self._producer.start()
            self._connected = True
            logger.info(f"Kafka producer connected ({self._service_name}): {KAFKA_BOOTSTRAP_SERVERS}")
            return True

        except ImportError:
            logger.error("aiokafka required: pip install aiokafka")
            return False
        except Exception as e:
            logger.error(f"Kafka producer connection failed: {e}")
            return False

    async def disconnect(self):
        """Flush pending messages and close producer"""
        if self._producer:
            await self._producer.stop()
            self._connected = False
            logger.info(f"Kafka producer disconnected ({self._service_name}). Messages sent: {self._message_count}")

    async def send_message(
        self,
        tenant_id: str,
        topic: str,
        event_type: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send a tenant-scoped event to Kafka.

        The tenant_id is used as the partition key, so all messages
        from the same tenant go to the same partition = guaranteed ordering.
        """
        if not self._connected:
            logger.warning("Kafka producer not connected — message dropped")
            return None

        # Validate tenant_id format — only alphanumeric, hyphen, underscore (no special chars)
        import re
        if not tenant_id:
            raise ValueError("tenant_id is required for all Kafka events")
        if not re.match(r"^[a-zA-Z0-9_-]+$", tenant_id):
            raise ValueError(
                f"Invalid tenant_id format. Only alphanumeric, hyphen, and underscore allowed. Got: {tenant_id}"
            )

        # Resolve full topic name
        topic_config = TOPICS.get(topic)
        if not topic_config:
            raise ValueError(f"Unknown topic: {topic}. Valid: {', '.join(TOPICS.keys())}")
        full_topic = topic_config["full_name"]

        # Build event envelope
        event = PriyaEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            source_service=self._service_name,
            payload=payload,
            metadata=metadata or {},
            correlation_id=correlation_id or str(uuid.uuid4()),
        )

        try:
            # Key = tenant_id → consistent partition assignment
            result = await self._producer.send_and_wait(
                topic=full_topic,
                key=tenant_id,
                value=event.to_json(),
            )
            self._message_count += 1

            logger.debug(
                f"Event sent: topic={topic} tenant={tenant_id} type={event_type} "
                f"partition={result.partition} offset={result.offset}"
            )
            return event.event_id

        except Exception as e:
            logger.error(f"Failed to send event: {e}")
            return None

    async def send_batch(
        self,
        events: List[Dict[str, Any]],
    ) -> int:
        """
        Send multiple events in a batch.
        Each dict must have: tenant_id, topic, event_type, payload

        Returns count of successfully sent events.
        """
        sent = 0
        for evt in events:
            result = await self.send_message(
                tenant_id=evt["tenant_id"],
                topic=evt["topic"],
                event_type=evt["event_type"],
                payload=evt.get("payload", {}),
                metadata=evt.get("metadata"),
                correlation_id=evt.get("correlation_id"),
            )
            if result:
                sent += 1
        return sent

    @property
    def is_connected(self) -> bool:
        return self._connected


# ============================================================================
# TENANT CONSUMER
# ============================================================================

class TenantConsumer:
    """
    Kafka consumer with tenant-aware message processing.
    Messages are automatically deserialized into PriyaEvent objects.
    """

    def __init__(
        self,
        topic: str,
        group_id: str,
        service_name: str = "unknown",
    ):
        self._consumer = None
        self._connected = False
        self._service_name = service_name
        self._topic = topic
        self._group_id = group_id
        self._message_count = 0
        self._running = False

    async def connect(self) -> bool:
        """Initialize Kafka consumer"""
        try:
            from aiokafka import AIOKafkaConsumer

            topic_config = TOPICS.get(self._topic)
            if not topic_config:
                raise ValueError(f"Unknown topic: {self._topic}")

            config = _build_kafka_config()
            self._consumer = AIOKafkaConsumer(
                topic_config["full_name"],
                **config,
                group_id=f"{TOPIC_PREFIX}.{self._group_id}",
                auto_offset_reset=CONSUMER_AUTO_OFFSET_RESET,
                max_poll_records=CONSUMER_MAX_POLL_RECORDS,
                session_timeout_ms=CONSUMER_SESSION_TIMEOUT_MS,
                heartbeat_interval_ms=CONSUMER_HEARTBEAT_INTERVAL_MS,
                enable_auto_commit=True,
                auto_commit_interval_ms=5000,
                value_deserializer=lambda v: v,  # We handle deserialization
            )
            await self._consumer.start()
            self._connected = True
            self._running = True
            logger.info(
                f"Kafka consumer connected ({self._service_name}): "
                f"topic={self._topic} group={self._group_id}"
            )
            return True

        except ImportError:
            logger.error("aiokafka required: pip install aiokafka")
            return False
        except Exception as e:
            logger.error(f"Kafka consumer connection failed: {e}")
            return False

    async def disconnect(self):
        """Stop consumer"""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            self._connected = False
            logger.info(
                f"Kafka consumer disconnected ({self._service_name}). "
                f"Messages consumed: {self._message_count}"
            )

    async def consume(self) -> AsyncIterator[PriyaEvent]:
        """
        Async generator that yields PriyaEvent objects.

        Usage:
            async for event in consumer.consume():
                tenant_id = event.tenant_id
                if event.event_type == "whatsapp_message":
                    await handle_whatsapp(event)
        """
        if not self._connected:
            logger.error("Consumer not connected")
            return

        while self._running:
            try:
                async for msg in self._consumer:
                    try:
                        event = PriyaEvent.from_json(msg.value)
                        self._message_count += 1

                        logger.debug(
                            f"Event received: topic={self._topic} tenant={event.tenant_id} "
                            f"type={event.event_type} partition={msg.partition}"
                        )
                        yield event

                    except json.JSONDecodeError as e:
                        logger.error(
                            f"Failed to deserialize message on topic={self._topic}: {e}. "
                            f"Skipping message (offset={msg.offset}, partition={msg.partition})"
                        )
                        # TODO: Send malformed message to DLQ for investigation
                        continue
                    except Exception as e:
                        logger.error(
                            f"Error processing message on topic={self._topic}: {e}. "
                            f"Offset={msg.offset}, partition={msg.partition}"
                        )
                        continue

            except Exception as e:
                if self._running:
                    logger.error(f"Consumer loop error: {e}. Reconnecting in 5s...")
                    await asyncio.sleep(5)

    async def consume_with_handler(
        self,
        handler: Callable[[PriyaEvent], Any],
        error_handler: Optional[Callable[[PriyaEvent, Exception], Any]] = None,
        max_concurrent: int = 10,
    ):
        """
        Consume messages with a handler function and concurrency control.

        Usage:
            async def handle_message(event: PriyaEvent):
                await process(event)

            await consumer.consume_with_handler(handle_message, max_concurrent=5)
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _process(event: PriyaEvent):
            async with semaphore:
                try:
                    await handler(event)
                except Exception as e:
                    logger.error(
                        f"Handler error: tenant={event.tenant_id} "
                        f"type={event.event_type}: {e}"
                    )
                    if error_handler:
                        try:
                            await error_handler(event, e)
                        except Exception:
                            pass

        tasks: Set[asyncio.Task] = set()
        async for event in self.consume():
            task = asyncio.create_task(_process(event))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

            # Prevent unbounded task accumulation
            if len(tasks) >= max_concurrent * 2:
                done, tasks_set = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                tasks = tasks_set

    @property
    def is_connected(self) -> bool:
        return self._connected


# ============================================================================
# DEAD LETTER QUEUE
# ============================================================================

class DeadLetterProducer:
    """
    Dead Letter Queue — events that fail processing after all retries
    go here for manual investigation.
    """

    DLQ_TOPIC = f"{TOPIC_PREFIX}.dlq"

    def __init__(self, producer: TenantProducer):
        self._producer = producer

    async def send_to_dlq(
        self,
        original_event: PriyaEvent,
        error_message: str,
        source_topic: str,
        retry_count: int = 0,
    ):
        """Send a failed event to the DLQ"""
        if not self._producer.is_connected:
            logger.error("Cannot send to DLQ — producer not connected")
            return

        dlq_event = PriyaEvent(
            tenant_id=original_event.tenant_id,
            event_type="dlq_entry",
            source_service="dlq",
            payload={
                "original_event": original_event.to_dict(),
                "error_message": error_message,
                "source_topic": source_topic,
                "retry_count": retry_count,
                "failed_at": datetime.now(timezone.utc).isoformat(),
            },
            correlation_id=original_event.correlation_id,
        )

        try:
            await self._producer._producer.send_and_wait(
                topic=self.DLQ_TOPIC,
                key=original_event.tenant_id,
                value=dlq_event.to_json(),
            )
            logger.warning(
                f"Event sent to DLQ: tenant={original_event.tenant_id} "
                f"type={original_event.event_type} error={error_message}"
            )
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")


# ============================================================================
# TOPIC ADMINISTRATION
# ============================================================================

class TopicAdmin:
    """Create and manage Kafka topics"""

    @staticmethod
    async def create_all_topics():
        """Create all registered topics with configured partitions and replication"""
        try:
            from aiokafka.admin import AIOKafkaAdminClient, NewTopic

            config = _build_kafka_config()
            admin = AIOKafkaAdminClient(**config)
            await admin.start()

            # Get min replication factor from environment (default 3 for production, allow override for dev)
            min_replication = int(os.getenv("KAFKA_MIN_REPLICATION", "3"))

            new_topics = []
            for name, topic_config in TOPICS.items():
                replication_factor = max(1, min(topic_config["replication"], min_replication))
                new_topics.append(NewTopic(
                    name=topic_config["full_name"],
                    num_partitions=topic_config["partitions"],
                    replication_factor=replication_factor,
                    topic_configs={
                        "retention.ms": str(topic_config["retention_ms"]),
                        "cleanup.policy": "delete",
                    },
                ))

            # Also create DLQ topic
            new_topics.append(NewTopic(
                name=f"{TOPIC_PREFIX}.dlq",
                num_partitions=3,
                replication_factor=1,
                topic_configs={
                    "retention.ms": str(365 * 24 * 60 * 60 * 1000),
                    "cleanup.policy": "compact,delete",
                },
            ))

            try:
                await admin.create_topics(new_topics)
                logger.info(f"Created {len(new_topics)} Kafka topics")
            except Exception as e:
                # Topics may already exist
                logger.info(f"Topic creation note: {e}")

            await admin.close()
            return True

        except ImportError:
            logger.error("aiokafka required for topic administration")
            return False
        except Exception as e:
            logger.error(f"Topic creation failed: {e}")
            return False

    @staticmethod
    async def list_topics() -> List[str]:
        """List all existing topics"""
        try:
            from aiokafka.admin import AIOKafkaAdminClient

            config = _build_kafka_config()
            admin = AIOKafkaAdminClient(**config)
            await admin.start()

            metadata = await admin.list_topics()
            await admin.close()
            return [t for t in metadata if t.startswith(TOPIC_PREFIX)]

        except Exception as e:
            logger.error(f"Failed to list topics: {e}")
            return []


# ============================================================================
# CONVENIENCE: Pre-built event factories
# ============================================================================

def inbound_message_event(
    tenant_id: str,
    channel: str,
    from_id: str,
    message_text: str,
    conversation_id: str,
    source_service: str,
    message_metadata: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Build an inbound message event ready for producer.send_message()"""
    return {
        "tenant_id": tenant_id,
        "topic": "inbound.messages",
        "event_type": f"{channel}_message_received",
        "payload": {
            "channel": channel,
            "from_id": from_id,
            "message_text": message_text,
            "conversation_id": conversation_id,
            "received_at": datetime.now(timezone.utc).isoformat(),
            **(message_metadata or {}),
        },
        "metadata": {"source_service": source_service},
    }


def outbound_message_event(
    tenant_id: str,
    channel: str,
    to_id: str,
    message_text: str,
    conversation_id: str,
    source_service: str = "ai-engine",
) -> Dict[str, Any]:
    """Build an outbound message event ready for producer.send_message()"""
    return {
        "tenant_id": tenant_id,
        "topic": "outbound.messages",
        "event_type": f"{channel}_message_send",
        "payload": {
            "channel": channel,
            "to_id": to_id,
            "message_text": message_text,
            "conversation_id": conversation_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "metadata": {"source_service": source_service},
    }


def billing_usage_event(
    tenant_id: str,
    usage_type: str,
    quantity: int = 1,
    metadata: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Build a billing usage metering event"""
    return {
        "tenant_id": tenant_id,
        "topic": "events.billing",
        "event_type": "usage_metered",
        "payload": {
            "usage_type": usage_type,  # "message_sent", "ai_inference", "voice_minute", etc.
            "quantity": quantity,
            "metered_at": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        },
    }


def conversation_event(
    tenant_id: str,
    conversation_id: str,
    action: str,
    data: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Build a conversation lifecycle event"""
    return {
        "tenant_id": tenant_id,
        "topic": "events.conversation",
        "event_type": f"conversation_{action}",  # created, escalated, closed, rated
        "payload": {
            "conversation_id": conversation_id,
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(data or {}),
        },
    }


def audit_event(
    tenant_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    performed_by: str,
    details: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Build a compliance audit trail event"""
    return {
        "tenant_id": tenant_id,
        "topic": "events.audit",
        "event_type": "audit_log",
        "payload": {
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "performed_by": performed_by,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(details or {}),
        },
    }
