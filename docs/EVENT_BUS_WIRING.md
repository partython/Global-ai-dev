# Priya Global Event Bus Wiring Guide

## Overview

This document explains how EventBus has been wired into the Priya Global Platform. All 36+ services now publish and subscribe to events via Kafka.

## What Was Created

### 1. Core Event Bus Module

**File**: `/shared/events/event_bus.py` (~600 lines)

- `EventBus` class: Singleton per service for event publishing and subscription
- `EventType` enum: 22 event types across conversation, user, payment, billing, AI, etc.
- `EVENT_TYPE_TO_TOPIC` mapping: Routes event types to Kafka topics
- Helper functions for building event payloads
- Background consumer task infrastructure

**Key Methods**:
```python
await event_bus.startup()  # Initialize Kafka producer
await event_bus.shutdown()  # Graceful shutdown
await event_bus.publish(event_type, tenant_id, data, metadata)  # Publish event
event_bus.subscribe(event_type, handler_function)  # Register handler
await event_bus.start_consuming(event_types)  # Start consuming
```

### 2. Event Handlers Module

**File**: `/shared/events/handlers.py` (~300 lines)

Common handlers for:
- `log_event_handler`: Audit logging (compliance)
- `metrics_event_handler`: Prometheus metrics tracking
- `notification_dispatch_handler`: Route to notification service
- `analytics_aggregation_handler`: Analytics collection
- `ai_training_data_handler`: Collect training data
- `compliance_handler`: GDPR/CCPA tracking
- `health_check_handler`: Service health tracking
- `deployment_event_handler`: Deployment tracking

## Services Wired

### Already Wired

**auth** (Port 9001)
- ✅ Imports EventBus and EventType
- ✅ `event_bus = EventBus(service_name="auth")` initialized
- ✅ `await event_bus.startup()` in startup event
- ✅ `await event_bus.shutdown()` in shutdown event
- ✅ `USER_REGISTERED` event published in `/api/v1/auth/register`
- ✅ `USER_LOGIN` event published in `/api/v1/auth/login`

### To Be Wired

The following services need EventBus wiring. Each service needs:

1. Add import at the top of `main.py`:
   ```python
   from shared.events.event_bus import EventBus, EventType
   ```

2. Initialize singleton after middleware:
   ```python
   # Initialize event bus
   event_bus = EventBus(service_name="service_name")
   ```

3. Wire startup/shutdown:
   ```python
   @app.on_event("startup")
   async def startup_event():
       await event_bus.startup()
       # ... rest of startup

   @app.on_event("shutdown")
   async def shutdown_event():
       await event_bus.shutdown()
       # ... rest of shutdown
   ```

4. Publish events after business logic in relevant endpoints

## Event Publishing Pattern

After successful business logic execution, publish:

```python
await event_bus.publish(
    event_type=EventType.CONVERSATION_STARTED,
    tenant_id=tenant_id,
    data={
        "conversation_id": conv_id,
        "channel": "whatsapp",
        "customer_id": customer_id,
    },
    metadata={"ip_address": ip_address},
)
```

## Service-Event Mapping

| Service | Events | Endpoints |
|---------|--------|-----------|
| **auth** | USER_REGISTERED, USER_LOGIN | POST /auth/register, POST /auth/login |
| **ai_engine** | AI_RESPONSE_GENERATED | POST /api/v1/ai/chat, POST /api/v1/ai/generate |
| **conversation** | CONVERSATION_STARTED, CONVERSATION_ENDED | POST /conversations, DELETE /conversations/{id} |
| **whatsapp** | MESSAGE_RECEIVED, MESSAGE_SENT | POST /webhook, POST /api/v1/send |
| **billing** | PAYMENT_RECEIVED, PAYMENT_FAILED | POST /api/v1/subscribe, POST /api/v1/webhook/stripe |
| **analytics** | ANALYTICS_EVENT | All endpoints aggregate events |
| **leads** | LEAD_CREATED, LEAD_UPDATED | POST /api/v1/leads, PUT /api/v1/leads/{id} |
| **knowledge** | KNOWLEDGE_UPDATED | POST /api/v1/knowledge, PUT /api/v1/knowledge/{id} |
| **appointments** | APPOINTMENT_BOOKED | POST /api/v1/appointments |
| **notification** | CHANNEL_CONNECTED, CHANNEL_DISCONNECTED | POST /api/v1/notify/send |
| **tenant_config** | TENANT_CREATED, TENANT_UPDATED | POST /api/v1/tenants, PUT /api/v1/tenants/{id} |
| **email** | MESSAGE_SENT, MESSAGE_RECEIVED | POST /api/v1/send, POST /webhook/email |
| **sms** | MESSAGE_SENT, MESSAGE_RECEIVED | POST /api/v1/send, POST /webhook/sms |
| **voice** | MESSAGE_SENT, MESSAGE_RECEIVED | POST /api/v1/call, POST /webhook/voice |
| **social** | MESSAGE_SENT, MESSAGE_RECEIVED | POST /api/v1/post, POST /webhook/social |
| **telegram** | MESSAGE_SENT, MESSAGE_RECEIVED | POST /api/v1/send, POST /webhook/telegram |
| **webchat** | MESSAGE_SENT, MESSAGE_RECEIVED | WS /chat, POST /api/v1/messages |

## Event Flow Example

### User Registration Flow

1. Client calls `POST /api/v1/auth/register`
2. Auth service creates user and tenant in database
3. Auth service publishes `USER_REGISTERED` event to Kafka
4. Event routes to `priya.events.audit` topic (partitioned by tenant_id)
5. Registered handlers execute:
   - `log_event_handler`: Write audit log
   - `metrics_event_handler`: Increment counter
   - `compliance_handler`: Log for GDPR
   - `notification_dispatch_handler`: Send welcome email
6. Analytics service (if subscribed) aggregates metrics
7. All events are durable and can be replayed

## Kafka Topic Architecture

```
priya.inbound.messages      → 12 partitions, 7-day retention
priya.outbound.messages     → 12 partitions, 7-day retention
priya.events.conversation   → 6 partitions, 30-day retention
priya.events.analytics      → 6 partitions, 90-day retention
priya.events.billing        → 3 partitions, 1-year retention
priya.events.ai_training    → 3 partitions, 90-day retention
priya.events.audit          → 3 partitions, 1-year retention (compliance)
priya.events.notification   → 6 partitions, 7-day retention
priya.dlq                   → 3 partitions (dead letter queue)
```

## Configuration

### Environment Variables

```bash
KAFKA_BOOTSTRAP_SERVERS=kafka-1:9092,kafka-2:9092,kafka-3:9092
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=SCRAM-SHA-512
KAFKA_SASL_USERNAME=priya_user
KAFKA_SASL_PASSWORD=<secret>
KAFKA_SSL_CAFILE=/etc/kafka/certs/ca.pem
```

### For Local Development

```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_SECURITY_PROTOCOL=PLAINTEXT
```

## Testing

### Test Event Publishing

```python
import asyncio
from shared.events.event_bus import EventBus, EventType

async def test():
    event_bus = EventBus(service_name="test")
    await event_bus.startup()

    event_id = await event_bus.publish(
        event_type=EventType.USER_REGISTERED,
        tenant_id="test-tenant",
        data={"user_id": "123", "email": "test@example.com"}
    )
    print(f"Published event: {event_id}")

    await event_bus.shutdown()

asyncio.run(test())
```

### Test Event Consumption

```python
async def handler(event_data):
    print(f"Received event: {event_data}")

async def test_consume():
    event_bus = EventBus(service_name="consumer")
    await event_bus.startup()

    event_bus.subscribe(EventType.USER_REGISTERED, handler)
    await event_bus.start_consuming([EventType.USER_REGISTERED])

    # Will consume events for 60 seconds
    await asyncio.sleep(60)
    await event_bus.shutdown()

asyncio.run(test_consume())
```

## Checklist for Wiring All Services

Use this checklist to wire remaining services:

- [ ] ai_engine - AI_RESPONSE_GENERATED
- [ ] ai_training - KNOWLEDGE_UPDATED
- [ ] analytics - ANALYTICS_EVENT
- [ ] appointments - APPOINTMENT_BOOKED
- [ ] billing - PAYMENT_RECEIVED, PAYMENT_FAILED
- [ ] channel_router - MESSAGE_SENT, MESSAGE_RECEIVED
- [ ] compliance - All events for audit
- [ ] conversation_intel - CONVERSATION_ESCALATED
- [ ] deployment - DEPLOYMENT_EVENT
- [ ] ecommerce - All transaction events
- [ ] email - MESSAGE_SENT, MESSAGE_RECEIVED
- [ ] handoff - CONVERSATION_ESCALATED
- [ ] health_monitor - HEALTH_CHECK
- [ ] knowledge - KNOWLEDGE_UPDATED
- [ ] leads - LEAD_CREATED, LEAD_UPDATED
- [ ] marketing - CAMPAIGN_SENT, FEEDBACK_RECEIVED
- [ ] notification - CHANNEL_CONNECTED, CHANNEL_DISCONNECTED
- [ ] rcs - MESSAGE_SENT, MESSAGE_RECEIVED
- [ ] sms - MESSAGE_SENT, MESSAGE_RECEIVED
- [ ] social - MESSAGE_SENT, MESSAGE_RECEIVED
- [ ] telegram - MESSAGE_SENT, MESSAGE_RECEIVED
- [ ] tenant_config - TENANT_CREATED, TENANT_UPDATED
- [ ] voice - MESSAGE_SENT, MESSAGE_RECEIVED
- [ ] voice_ai - AI_RESPONSE_GENERATED
- [ ] webchat - MESSAGE_SENT, MESSAGE_RECEIVED
- [ ] whatsapp - MESSAGE_SENT, MESSAGE_RECEIVED
- [ ] workflows - All event triggers

## Deployment

### Kafka Cluster Requirements

- **Minimum**: 3-broker KRaft cluster (no Zookeeper)
- **Recommended**: 5-broker cluster for high availability
- **Replication**: 3 (production minimum)
- **Min In-Sync Replicas**: 2 (durability)

### Service Rollout

1. Deploy EventBus module to all services
2. Deploy event handlers module
3. Wire one service at a time (test in staging)
4. Monitor Kafka topic throughput and errors
5. Once stable on 5+ services, wire remaining services
6. Monitor for 1 week before full production

## Troubleshooting

### Kafka Connection Issues

```python
# Check connection in any service
import asyncio
from shared.events.kafka_client import TopicAdmin

async def check():
    topics = await TopicAdmin.list_topics()
    print(f"Topics: {topics}")

asyncio.run(check())
```

### Consumer Lag

Monitor consumer lag with:
```bash
docker exec kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group priya.analytics \
  --describe
```

### Dead Letter Queue

Check DLQ for failed events:
```python
consumer = TenantConsumer(
    topic="dlq",
    group_id="dlq_monitor",
    service_name="dlq_monitor"
)
async for event in consumer.consume():
    print(f"Failed event: {event.payload}")
    # Investigate and manually replay if needed
```

## Performance Tuning

### For High-Volume Services

```python
# Increase batch size for throughput
event_bus.producer._producer.max_batch_size = 32768  # 32KB

# Increase linger time to batch more messages
# Trade-off: adds ~10ms latency for more throughput
```

### For Low-Latency Services

```python
# Minimize batching for faster delivery
event_bus.producer._producer.linger_ms = 1
event_bus.producer._producer.max_batch_size = 512
```

## Monitoring

### Key Metrics

1. **Event Throughput**: msgs/sec per service
2. **Consumer Lag**: Behind/offset per consumer group
3. **Event Latency**: P50, P95, P99 milliseconds
4. **DLQ Rate**: Failed events per minute
5. **Kafka Broker Health**: CPU, disk, network

### Prometheus Queries

```promql
# Events per minute by service
rate(priya_events_total[1m])

# Consumer lag
priya_consumer_lag_bytes

# Kafka broker disk
kafka_disk_used_bytes
```

## Future Enhancements

1. **Event Replay**: Replay events from specific timestamp
2. **Event Filtering**: Filter events by tenant/type
3. **Event Versioning**: Support multiple schema versions
4. **CQRS Pattern**: Separate read models from write models
5. **Saga Pattern**: Distributed transactions across services
6. **Event Sourcing**: Full audit trail of all changes

## References

- Kafka Documentation: https://kafka.apache.org/documentation/
- aiokafka Library: https://aiokafka.readthedocs.io/
- Event Bus Pattern: https://martinfowler.com/articles/201701-event-driven.html

---

**Last Updated**: 2025-03-06
**Status**: EventBus core created, 1 service wired (auth), 35 services pending
