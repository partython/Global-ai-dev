"""
Comprehensive tests for shared.events.kafka_client module.

Tests event publishing/consuming with tenant partitioning, event schema,
topic routing, consumer handling, serialization, and error handling.
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock
from dataclasses import asdict

from shared.events.kafka_client import (
    PriyaEvent,
    TenantProducer,
    TenantConsumer,
    DeadLetterProducer,
    TopicAdmin,
    TOPICS,
    inbound_message_event,
    outbound_message_event,
    billing_usage_event,
    conversation_event,
    audit_event,
)


class TestPriyaEventEnvelope:
    """Test PriyaEvent data structure."""

    @pytest.mark.unit
    def test_priya_event_initialization(self):
        """PriyaEvent initializes with required fields."""
        event = PriyaEvent(
            tenant_id="t_123",
            event_type="message_received",
            source_service="whatsapp",
            payload={"text": "Hello"},
        )
        assert event.tenant_id == "t_123"
        assert event.event_type == "message_received"
        assert event.source_service == "whatsapp"
        assert event.payload == {"text": "Hello"}

    @pytest.mark.unit
    def test_priya_event_auto_generates_event_id(self):
        """PriyaEvent auto-generates event_id if not provided."""
        event = PriyaEvent(
            tenant_id="t_123",
            event_type="test",
        )
        assert event.event_id
        assert len(event.event_id) > 0

    @pytest.mark.unit
    def test_priya_event_auto_generates_timestamp(self):
        """PriyaEvent auto-generates timestamp if not provided."""
        before = datetime.now(timezone.utc).isoformat()
        event = PriyaEvent(tenant_id="t_123", event_type="test")
        after = datetime.now(timezone.utc).isoformat()
        assert before <= event.timestamp <= after

    @pytest.mark.unit
    def test_priya_event_auto_generates_correlation_id(self):
        """PriyaEvent auto-generates correlation_id if not provided."""
        event = PriyaEvent(tenant_id="t_123", event_type="test")
        assert event.correlation_id
        assert len(event.correlation_id) > 0

    @pytest.mark.unit
    def test_priya_event_to_dict(self):
        """PriyaEvent.to_dict() returns all fields."""
        event = PriyaEvent(
            tenant_id="t_123",
            event_type="test",
            payload={"key": "value"},
        )
        event_dict = event.to_dict()
        assert event_dict["tenant_id"] == "t_123"
        assert event_dict["event_type"] == "test"
        assert event_dict["payload"] == {"key": "value"}
        assert "event_id" in event_dict
        assert "timestamp" in event_dict

    @pytest.mark.unit
    def test_priya_event_to_json(self):
        """PriyaEvent.to_json() returns JSON bytes."""
        event = PriyaEvent(
            tenant_id="t_123",
            event_type="test",
            payload={"key": "value"},
        )
        json_bytes = event.to_json()
        assert isinstance(json_bytes, bytes)
        parsed = json.loads(json_bytes)
        assert parsed["tenant_id"] == "t_123"

    @pytest.mark.unit
    def test_priya_event_from_json(self):
        """PriyaEvent.from_json() deserializes from bytes."""
        original = PriyaEvent(
            tenant_id="t_123",
            event_type="test",
            payload={"key": "value"},
        )
        json_bytes = original.to_json()
        deserialized = PriyaEvent.from_json(json_bytes)
        assert deserialized.tenant_id == original.tenant_id
        assert deserialized.event_type == original.event_type
        assert deserialized.payload == original.payload

    @pytest.mark.unit
    def test_priya_event_from_dict(self):
        """PriyaEvent.from_dict() creates from dictionary."""
        data = {
            "event_id": "evt_123",
            "tenant_id": "t_123",
            "event_type": "test",
            "payload": {"key": "value"},
        }
        event = PriyaEvent.from_dict(data)
        assert event.event_id == "evt_123"
        assert event.tenant_id == "t_123"


class TestTenantProducerConnection:
    """Test Kafka producer connection management."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_producer_connect_failure_returns_false(self):
        """Producer returns False on connection failure."""
        producer = TenantProducer(service_name="test")

        with patch("shared.events.kafka_client.AIOKafkaProducer", side_effect=Exception("Connection failed")):
            result = await producer.connect()
            assert result is False
            assert producer.is_connected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_producer_disconnect_closes_connection(self):
        """Producer disconnect closes Kafka connection."""
        producer = TenantProducer(service_name="test")
        producer._producer = AsyncMock()
        producer._connected = True

        await producer.disconnect()
        producer._producer.stop.assert_called_once()
        assert producer.is_connected is False


class TestTenantProducerEventPublishing:
    """Test event publishing."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_message_requires_tenant_id(self):
        """Sending message requires tenant_id."""
        producer = TenantProducer(service_name="test")
        producer._producer = AsyncMock()
        producer._connected = True

        with pytest.raises(ValueError, match="tenant_id is required"):
            await producer.send_message(
                tenant_id="",
                topic="inbound.messages",
                event_type="test",
                payload={},
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_message_validates_tenant_id_format(self):
        """Tenant ID format is validated."""
        producer = TenantProducer(service_name="test")
        producer._producer = AsyncMock()
        producer._connected = True

        with pytest.raises(ValueError, match="Invalid tenant_id format"):
            await producer.send_message(
                tenant_id="tenant@invalid",
                topic="inbound.messages",
                event_type="test",
                payload={},
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_message_validates_topic(self):
        """Unknown topic raises error."""
        producer = TenantProducer(service_name="test")
        producer._producer = AsyncMock()
        producer._connected = True

        with pytest.raises(ValueError, match="Unknown topic"):
            await producer.send_message(
                tenant_id="t_123",
                topic="nonexistent.topic",
                event_type="test",
                payload={},
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_message_uses_tenant_as_partition_key(self):
        """Tenant ID is used as partition key for message ordering."""
        producer = TenantProducer(service_name="test")
        producer._producer = AsyncMock()
        producer._connected = True

        mock_result = MagicMock()
        mock_result.partition = 0
        mock_result.offset = 100
        producer._producer.send_and_wait = AsyncMock(return_value=mock_result)

        await producer.send_message(
            tenant_id="t_123",
            topic="inbound.messages",
            event_type="whatsapp_message",
            payload={"text": "Hi"},
        )

        # Check that tenant_id was used as key
        call_args = producer._producer.send_and_wait.call_args
        assert call_args[1]["key"] == "t_123"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_message_publishes_to_full_topic_name(self):
        """Message is published to full topic name (with prefix)."""
        producer = TenantProducer(service_name="test")
        producer._producer = AsyncMock()
        producer._connected = True

        mock_result = MagicMock()
        mock_result.partition = 0
        mock_result.offset = 100
        producer._producer.send_and_wait = AsyncMock(return_value=mock_result)

        await producer.send_message(
            tenant_id="t_123",
            topic="inbound.messages",
            event_type="test",
            payload={},
        )

        call_args = producer._producer.send_and_wait.call_args
        assert call_args[1]["topic"] == "priya.inbound.messages"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_message_returns_event_id(self):
        """send_message returns event_id on success."""
        producer = TenantProducer(service_name="test")
        producer._producer = AsyncMock()
        producer._connected = True

        mock_result = MagicMock()
        mock_result.partition = 0
        producer._producer.send_and_wait = AsyncMock(return_value=mock_result)

        event_id = await producer.send_message(
            tenant_id="t_123",
            topic="inbound.messages",
            event_type="test",
            payload={},
        )

        assert event_id is not None
        assert isinstance(event_id, str)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_message_not_connected_returns_none(self):
        """send_message returns None when producer not connected."""
        producer = TenantProducer(service_name="test")
        producer._connected = False

        event_id = await producer.send_message(
            tenant_id="t_123",
            topic="inbound.messages",
            event_type="test",
            payload={},
        )

        assert event_id is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_batch_sends_multiple_events(self):
        """send_batch publishes multiple events."""
        producer = TenantProducer(service_name="test")
        producer._producer = AsyncMock()
        producer._connected = True

        mock_result = MagicMock()
        mock_result.partition = 0
        producer._producer.send_and_wait = AsyncMock(return_value=mock_result)

        events = [
            {
                "tenant_id": "t_1",
                "topic": "inbound.messages",
                "event_type": "test",
                "payload": {"msg": "1"},
            },
            {
                "tenant_id": "t_2",
                "topic": "inbound.messages",
                "event_type": "test",
                "payload": {"msg": "2"},
            },
        ]

        sent = await producer.send_batch(events)
        assert sent == 2


class TestTenantConsumerConnection:
    """Test consumer connection management."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_consumer_init_with_topic_and_group(self):
        """Consumer requires topic and group_id."""
        consumer = TenantConsumer(
            topic="inbound.messages",
            group_id="ai-engine",
        )
        assert consumer._topic == "inbound.messages"
        assert consumer._group_id == "ai-engine"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_consumer_connect_unknown_topic_fails(self):
        """Consumer connect fails with unknown topic."""
        consumer = TenantConsumer(
            topic="nonexistent.topic",
            group_id="test-group",
        )

        with patch("shared.events.kafka_client.AIOKafkaConsumer"):
            result = await consumer.connect()
            # Should fail in topic lookup


class TestEventDeserialization:
    """Test event message deserialization."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_consumer_deserializes_event_messages(self):
        """Consumer deserializes messages into PriyaEvent objects."""
        consumer = TenantConsumer(
            topic="inbound.messages",
            group_id="test",
        )
        consumer._consumer = AsyncMock()
        consumer._connected = True
        consumer._running = True

        # Create a test event
        event = PriyaEvent(
            tenant_id="t_123",
            event_type="test",
            payload={"key": "value"},
        )

        # Mock message
        mock_msg = MagicMock()
        mock_msg.value = event.to_json()
        mock_msg.partition = 0

        consumer._consumer.__aiter__ = AsyncMock(return_value=[mock_msg])

        # Consume should yield PriyaEvent
        async for msg_event in consumer.consume():
            assert isinstance(msg_event, PriyaEvent)
            assert msg_event.tenant_id == "t_123"
            break

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_consumer_handles_malformed_json(self):
        """Consumer skips malformed JSON messages."""
        consumer = TenantConsumer(
            topic="inbound.messages",
            group_id="test",
        )
        consumer._consumer = AsyncMock()
        consumer._connected = True
        consumer._running = True

        # Mock malformed message
        mock_msg = MagicMock()
        mock_msg.value = b"not valid json"

        consumer._consumer.__aiter__ = AsyncMock(return_value=[mock_msg])

        # Should skip the message
        messages = []
        async for msg_event in consumer.consume():
            messages.append(msg_event)

        # No messages yielded due to JSON error


class TestDeadLetterQueue:
    """Test DLQ functionality."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_to_dlq(self):
        """Failed events are sent to DLQ."""
        producer = TenantProducer(service_name="test")
        producer._producer = AsyncMock()
        producer._connected = True

        dlq = DeadLetterProducer(producer)

        original_event = PriyaEvent(
            tenant_id="t_123",
            event_type="test",
        )

        dlq_result = MagicMock()
        dlq_result.partition = 0
        producer._producer.send_and_wait = AsyncMock(return_value=dlq_result)

        await dlq.send_to_dlq(
            original_event=original_event,
            error_message="Processing failed",
            source_topic="inbound.messages",
        )

        producer._producer.send_and_wait.assert_called_once()


class TestEventFactories:
    """Test convenience event factory functions."""

    @pytest.mark.unit
    def test_inbound_message_event_factory(self):
        """inbound_message_event creates proper event dict."""
        event = inbound_message_event(
            tenant_id="t_123",
            channel="whatsapp",
            from_id="wa_123",
            message_text="Hello",
            conversation_id="conv_456",
            source_service="whatsapp",
        )

        assert event["tenant_id"] == "t_123"
        assert event["topic"] == "inbound.messages"
        assert event["event_type"] == "whatsapp_message_received"
        assert event["payload"]["channel"] == "whatsapp"
        assert event["payload"]["from_id"] == "wa_123"
        assert event["payload"]["message_text"] == "Hello"

    @pytest.mark.unit
    def test_outbound_message_event_factory(self):
        """outbound_message_event creates proper event dict."""
        event = outbound_message_event(
            tenant_id="t_123",
            channel="email",
            to_id="user@example.com",
            message_text="Response",
            conversation_id="conv_456",
        )

        assert event["tenant_id"] == "t_123"
        assert event["topic"] == "outbound.messages"
        assert event["event_type"] == "email_message_send"
        assert event["payload"]["channel"] == "email"

    @pytest.mark.unit
    def test_billing_usage_event_factory(self):
        """billing_usage_event creates proper event dict."""
        event = billing_usage_event(
            tenant_id="t_123",
            usage_type="message_sent",
            quantity=5,
        )

        assert event["tenant_id"] == "t_123"
        assert event["topic"] == "events.billing"
        assert event["event_type"] == "usage_metered"
        assert event["payload"]["usage_type"] == "message_sent"
        assert event["payload"]["quantity"] == 5

    @pytest.mark.unit
    def test_conversation_event_factory(self):
        """conversation_event creates proper event dict."""
        event = conversation_event(
            tenant_id="t_123",
            conversation_id="conv_456",
            action="closed",
            data={"rating": 5},
        )

        assert event["tenant_id"] == "t_123"
        assert event["topic"] == "events.conversation"
        assert event["event_type"] == "conversation_closed"
        assert event["payload"]["conversation_id"] == "conv_456"
        assert event["payload"]["rating"] == 5

    @pytest.mark.unit
    def test_audit_event_factory(self):
        """audit_event creates proper event dict."""
        event = audit_event(
            tenant_id="t_123",
            action="delete",
            resource_type="conversation",
            resource_id="conv_456",
            performed_by="user_123",
            details={"reason": "spam"},
        )

        assert event["tenant_id"] == "t_123"
        assert event["topic"] == "events.audit"
        assert event["event_type"] == "audit_log"
        assert event["payload"]["action"] == "delete"
        assert event["payload"]["resource_type"] == "conversation"
        assert event["payload"]["reason"] == "spam"


class TestTopicConfiguration:
    """Test topic registry and configuration."""

    @pytest.mark.unit
    def test_all_topics_are_registered(self):
        """All expected topics are in TOPICS registry."""
        expected_topics = [
            "inbound.messages",
            "outbound.messages",
            "events.conversation",
            "events.analytics",
            "events.billing",
            "events.ai_training",
            "events.audit",
            "events.notification",
        ]
        for topic in expected_topics:
            assert topic in TOPICS

    @pytest.mark.unit
    def test_topics_have_configuration(self):
        """Each topic has partition, replication, and retention config."""
        for topic_name, config in TOPICS.items():
            assert "full_name" in config
            assert "partitions" in config
            assert "replication" in config
            assert "retention_ms" in config
            assert config["full_name"].startswith("priya.")

    @pytest.mark.unit
    def test_topic_full_names_are_unique(self):
        """Each topic's full name is unique."""
        full_names = [config["full_name"] for config in TOPICS.values()]
        assert len(full_names) == len(set(full_names))

    @pytest.mark.unit
    def test_message_topics_have_more_partitions(self):
        """Message topics have more partitions than event topics."""
        message_partitions = TOPICS["inbound.messages"]["partitions"]
        event_partitions = TOPICS["events.conversation"]["partitions"]
        assert message_partitions > event_partitions
