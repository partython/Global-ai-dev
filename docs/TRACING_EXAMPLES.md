# OpenTelemetry Tracing Examples

Complete examples showing how to use the tracing system in the Priya Global Platform.

## Example 1: Tracing a Service Handler

```python
# services/auth/handlers.py

from shared.observability.tracing import TenantTracer, get_tracer
from shared.observability.trace_decorators import trace_function, trace_db_operation
from shared.observability.trace_context import set_tenant_context

@trace_function
async def login(request: Request) -> dict:
    """Login handler with automatic tracing."""
    # Extract tenant context from request
    tenant_id = request.headers.get("x-tenant-id")
    user_id = request.headers.get("x-user-id")

    # Set context for this request
    ctx = set_tenant_context(tenant_id=tenant_id, user_id=user_id)

    # Create tenant-aware tracer
    tenant_tracer = TenantTracer(tenant_id=tenant_id, user_id=user_id)

    # Get credentials
    body = await request.json()
    email = body["email"]
    password = body["password"]

    # Trace credential validation
    with tenant_tracer.trace_span("validate_credentials"):
        if not email or not password:
            raise ValueError("Email and password required")

    # Trace database lookup
    user = await get_user_by_email(email)

    # Trace password verification
    with tenant_tracer.trace_span("verify_password"):
        if not verify_password(password, user.password_hash):
            raise ValueError("Invalid credentials")

    # Trace JWT generation
    with tenant_tracer.trace_span("generate_jwt"):
        token = generate_jwt(user.id)

    return {
        "token": token,
        "user_id": user.id,
        "expires_in": 3600,
    }


@trace_db_operation
async def get_user_by_email(email: str) -> User:
    """Fetch user by email with automatic database tracing."""
    # This span is automatically created with:
    # - Span name: "get_user_by_email.db"
    # - db.system: "postgres"
    # - db.operation: "SELECT"
    return await db.query("SELECT * FROM users WHERE email = ?", email)
```

## Example 2: Inter-Service Communication

```python
# services/billing/handlers.py

from shared.observability.trace_decorators import trace_external_call
from shared.core.http_client import get_service_client
from shared.observability.trace_context import inject_context_headers

@trace_external_call("stripe", "create_charge")
async def charge_customer(customer_id: str, amount: float) -> dict:
    """Charge a customer with Stripe, automatically traced."""
    # This creates a span: external.stripe.create_charge
    # With attributes:
    # - external.service: "stripe"
    # - external.operation: "create_charge"
    # - tenant_id: from context

    # Trace context is automatically propagated to Stripe API

    return stripe.Charge.create(
        customer=customer_id,
        amount=int(amount * 100),
        currency="usd",
    )


async def process_payment(tenant_id: str, payment_id: str) -> dict:
    """Process a payment with multiple service calls."""
    # Manual span for orchestration
    tracer = get_tracer()

    with tracer.start_as_current_span("process_payment") as span:
        span.set_attribute("tenant_id", tenant_id)
        span.set_attribute("payment_id", payment_id)

        # Call auth service to get customer info
        service_client = await get_service_client()

        headers = inject_context_headers()  # Propagate trace context!

        customer_response = await service_client.get(
            service_name="auth",
            path=f"/api/v1/customers/{customer_id}",
            headers=headers,
            tenant_id=tenant_id,
        )
        # This HTTP call is automatically traced and context-propagated

        customer = customer_response.json()

        # Charge customer with Stripe
        charge = await charge_customer(customer["stripe_id"], amount)

        # Update payment status
        await update_payment(payment_id, status="completed")

        return {
            "success": True,
            "charge_id": charge["id"],
        }
```

## Example 3: Async Task with Context Propagation

```python
# services/worker/tasks.py

import asyncio
from shared.observability.trace_context import copy_context
from shared.observability.trace_decorators import trace_background_job

@trace_background_job(queue="celery")
async def send_email(email_id: str, tenant_id: str):
    """Send email with background job tracing."""
    # This span is automatically created with:
    # - job.name: "send_email"
    # - job.queue: "celery"

    email = await get_email(email_id)
    result = await smtp_send(email)

    return result


async def spawn_background_task():
    """Spawn background task with trace context."""
    # Create a task that inherits the current trace context
    ctx = copy_context()

    # Pass context to background task
    task = asyncio.create_task(
        send_email_with_context(ctx, email_id="e_123")
    )

    return task


async def send_email_with_context(ctx, email_id: str):
    """Background task that runs in copied context."""
    from shared.observability.trace_context import _trace_context_var

    # Restore context in this task
    token = _trace_context_var.set(ctx.trace_context)

    try:
        # Now this task has the parent's trace context
        await send_email(email_id)
    finally:
        _trace_context_var.reset(token)
```

## Example 4: Kafka Event Tracing

```python
# services/auth/handlers.py

from shared.events.event_bus import EventBus, EventType
from shared.observability.trace_context import set_tenant_context

event_bus = EventBus(service_name="auth")


async def register_user(email: str, tenant_id: str) -> dict:
    """Register user and publish event with automatic tracing."""
    # Set tenant context
    set_tenant_context(tenant_id=tenant_id)

    # Create user
    user = await create_user(email=email, tenant_id=tenant_id)

    # Publish event (automatically traced!)
    # Trace context is automatically added to Kafka message headers
    event_id = await event_bus.publish(
        event_type=EventType.USER_REGISTERED,
        tenant_id=tenant_id,
        data={
            "user_id": user.id,
            "email": user.email,
            "created_at": user.created_at.isoformat(),
        },
    )
    # This publish creates a span: kafka.publish.user_registered
    # With attributes:
    # - messaging.system: "kafka"
    # - messaging.destination: "user_events"
    # - messaging.message_type: "user_registered"
    # - tenant_id: (from context)

    return {"user_id": user.id, "event_id": event_id}


# Event consumer in another service (e.g., notification service)

from shared.observability.trace_context import extract_from_kafka


async def on_user_registered(event: dict):
    """Handle user registered event with trace continuation."""
    # Extract trace context from Kafka message
    ctx = extract_from_kafka(event)

    if ctx:
        # Trace context from publisher is restored!
        # All spans in this handler are part of the original trace
        set_trace_context(ctx)

    user_id = event["user_id"]
    email = event["email"]

    # Send welcome email (traced as continuation of original trace)
    await send_welcome_email(user_id, email)
    # This span appears in the same trace tree as the original USER_REGISTERED publish!


event_bus.subscribe(EventType.USER_REGISTERED, on_user_registered)
```

## Example 5: Caching with Tracing

```python
# services/knowledge/cache.py

from shared.observability.trace_decorators import trace_cache_operation
from shared.observability.tracing import TenantTracer
import redis.asyncio as redis

redis_client = redis.from_url("redis://localhost:6379")


@trace_cache_operation(cache_system="redis")
async def get_knowledge_base(kb_id: str) -> dict:
    """Get knowledge base from cache with automatic tracing."""
    # This creates a span:
    # - span_name: "get_knowledge_base.cache"
    # - cache.operation: "GET" (inferred from function name)
    # - cache.key: "kb_id"
    # - cache.system: "redis"

    key = f"kb:{kb_id}"
    data = await redis_client.get(key)

    if data:
        return json.loads(data)

    # Cache miss, fetch from database
    return await fetch_from_database(kb_id)


@trace_cache_operation(cache_system="redis")
async def cache_knowledge_base(kb_id: str, data: dict) -> None:
    """Cache knowledge base with automatic tracing."""
    # This creates a span:
    # - cache.operation: "SET" (inferred from function name)
    # - cache.value_size: (calculated from data)

    key = f"kb:{kb_id}"
    value = json.dumps(data)

    await redis_client.setex(
        key,
        3600,  # 1 hour TTL
        value,
    )


async def update_knowledge_base(kb_id: str, tenant_id: str, new_data: dict):
    """Update knowledge base with cache invalidation tracing."""
    tenant_tracer = TenantTracer(tenant_id=tenant_id)

    with tenant_tracer.trace_cache_operation("delete", f"kb:{kb_id}"):
        # Invalidate cache
        await redis_client.delete(f"kb:{kb_id}")

    # Update database
    await db.update_knowledge_base(kb_id, new_data)

    # Re-cache
    await cache_knowledge_base(kb_id, new_data)
```

## Example 6: AI Model Inference Tracing

```python
# services/ai_engine/inference.py

from shared.observability.trace_decorators import trace_ai_inference
from shared.observability.tracing import set_span_attribute


@trace_ai_inference("gpt-4", "completion")
async def generate_ai_response(
    prompt: str,
    max_tokens: int = 500,
    tenant_id: str = None,
) -> str:
    """Generate response from GPT-4 with automatic tracing."""
    # This creates a span:
    # - span_name: "ai.gpt-4.completion"
    # - ai.model: "gpt-4"
    # - ai.operation: "completion"
    # - ai.tokens: 500 (from max_tokens parameter)
    # - tenant_id: (from context)

    response = await openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.7,
    )

    # Add completion tokens to span
    tokens_used = response["usage"]["completion_tokens"]
    set_span_attribute("ai.completion_tokens", tokens_used)

    return response["choices"][0]["message"]["content"]


@trace_ai_inference("embedding-ada-002", "embedding")
async def generate_embedding(text: str) -> list[float]:
    """Generate text embedding with automatic tracing."""
    # This creates a span:
    # - span_name: "ai.embedding-ada-002.embedding"
    # - ai.model: "embedding-ada-002"
    # - ai.operation: "embedding"

    response = await openai.Embedding.create(
        model="text-embedding-ada-002",
        input=text,
    )

    embedding = response["data"][0]["embedding"]

    set_span_attribute("embedding_dimension", len(embedding))

    return embedding
```

## Example 7: Complex Multi-Service Flow

```python
# services/conversation/conversation_handler.py

from shared.observability.tracing import TenantTracer
from shared.observability.trace_context import set_tenant_context, inject_context_headers
from shared.observability.trace_decorators import trace_function


@trace_function
async def handle_incoming_message(
    request: Request,
) -> dict:
    """
    Handle incoming message with full tracing.

    Flow:
    1. Extract tenant/user context
    2. Create conversation if needed
    3. Get AI response
    4. Update conversation
    5. Send to channel
    6. Publish event

    All with automatic tracing and context propagation.
    """
    # Set tenant context
    tenant_id = request.headers.get("x-tenant-id")
    user_id = request.headers.get("x-user-id")
    ctx = set_tenant_context(tenant_id=tenant_id, user_id=user_id)

    # Create tenant tracer
    tracer = TenantTracer(tenant_id=tenant_id, user_id=user_id)

    body = await request.json()
    conversation_id = body["conversation_id"]
    message_text = body["message"]

    # Step 1: Get conversation
    with tracer.trace_span("load_conversation"):
        conversation = await db.get_conversation(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
        )

    # Step 2: Generate AI response
    with tracer.trace_ai_inference("gpt-4"):
        ai_response = await ai_engine.generate_response(
            prompt=message_text,
            context=conversation.context,
        )
        # Trace context automatically propagated to ai_engine service!

    # Step 3: Update conversation
    with tracer.trace_db_operation():
        await db.add_message(
            conversation_id=conversation_id,
            role="user",
            text=message_text,
        )

        await db.add_message(
            conversation_id=conversation_id,
            role="assistant",
            text=ai_response,
        )

    # Step 4: Send to channel (inter-service call)
    service_client = await get_service_client()
    headers = inject_context_headers()  # Propagate trace context!

    with tracer.trace_external_call("channel_router", "send_message"):
        await service_client.post(
            service_name="channel_router",
            path="/api/v1/messages",
            headers=headers,
            json={
                "conversation_id": conversation_id,
                "message": ai_response,
            },
        )
        # This HTTP call is traced and context-propagated!

    # Step 5: Publish event
    with tracer.trace_kafka_event("conversations", "message_sent"):
        await event_bus.publish(
            event_type=EventType.MESSAGE_SENT,
            tenant_id=tenant_id,
            data={
                "conversation_id": conversation_id,
                "message_id": str(uuid.uuid4()),
                "user_id": user_id,
            },
        )
        # Kafka message includes trace context headers!

    return {
        "success": True,
        "ai_response": ai_response,
        "trace_id": ctx.trace_id,  # Return trace ID for client logging
    }
```

## Example 8: Error Handling and Exception Recording

```python
# services/billing/payment_handler.py

from shared.observability.tracing import (
    TenantTracer,
    record_span_exception,
    set_span_attribute,
)
from shared.observability.trace_context import set_tenant_context


async def process_payment(payment_request: dict, tenant_id: str) -> dict:
    """Process payment with comprehensive error tracking."""
    set_tenant_context(tenant_id=tenant_id)
    tracer = TenantTracer(tenant_id=tenant_id)

    with tracer.trace_span("process_payment") as span:
        try:
            # Validate payment
            with tracer.trace_span("validate_payment"):
                if not validate_payment(payment_request):
                    raise ValueError("Invalid payment data")

            set_span_attribute("amount", payment_request["amount"])
            set_span_attribute("currency", payment_request["currency"])

            # Charge customer
            with tracer.trace_external_call("stripe", "create_charge"):
                charge = await stripe.Charge.create(
                    amount=payment_request["amount"],
                    currency=payment_request["currency"],
                )

            set_span_attribute("charge_id", charge["id"])
            set_span_attribute("charge_status", charge["status"])

            # Update payment status
            with tracer.trace_db_operation():
                await db.update_payment(
                    payment_request["id"],
                    status="completed",
                    charge_id=charge["id"],
                )

            return {
                "success": True,
                "charge_id": charge["id"],
            }

        except ValueError as e:
            # Record validation error
            record_span_exception(e, "Payment validation failed")
            raise

        except StripeError as e:
            # Record Stripe error with more context
            set_span_attribute("error.stripe_code", e.code)
            record_span_exception(e, f"Stripe error: {e.message}")

            # Update payment status to failed
            try:
                await db.update_payment(
                    payment_request["id"],
                    status="failed",
                    error_message=str(e),
                )
            except Exception:
                pass  # Log error but don't fail

            raise

        except Exception as e:
            # Catch-all for unexpected errors
            set_span_attribute("error.type", type(e).__name__)
            record_span_exception(e, "Unexpected error during payment processing")
            raise
```

## Example 9: Custom Metrics in Spans

```python
# services/conversation/search.py

from shared.observability.tracing import TenantTracer, add_span_event


async def search_conversations(
    tenant_id: str,
    query: str,
    limit: int = 10,
) -> list[dict]:
    """Search conversations with performance tracking."""
    tracer = TenantTracer(tenant_id=tenant_id)

    with tracer.trace_span("search_conversations") as span:
        import time

        start = time.time()

        # Execute search
        results = await db.search_conversations(
            tenant_id=tenant_id,
            query=query,
            limit=limit,
        )

        elapsed_ms = (time.time() - start) * 1000

        # Add span events for business metrics
        add_span_event(
            "search_completed",
            {
                "query": query,
                "result_count": len(results),
                "elapsed_ms": elapsed_ms,
            },
        )

        # Set attributes for aggregation
        span.set_attribute("search.query_length", len(query))
        span.set_attribute("search.result_count", len(results))
        span.set_attribute("search.elapsed_ms", elapsed_ms)

        # Add business events
        if len(results) == 0:
            add_span_event("no_results", {"query": query})
        elif elapsed_ms > 1000:
            add_span_event("slow_search", {"elapsed_ms": elapsed_ms})

        return results
```

These examples demonstrate the key patterns for using OpenTelemetry in the Priya Global Platform:

1. **Tenant-aware tracing** with `TenantTracer`
2. **Automatic instrumentation** with decorators
3. **Manual span creation** for complex flows
4. **Context propagation** across services and Kafka
5. **Exception recording** for error visibility
6. **Custom attributes** for business context
7. **Events** for important state changes
